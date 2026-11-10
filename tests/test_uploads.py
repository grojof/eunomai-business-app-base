"""Uploads: checked by size and real type, stored under names of our own, and sent back only as attachments."""

import io
import os
import re
import socket
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

import anyio
import pytest
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core import application as application_module
from app.core import i18n
from app.core.formatters import format_file_size
from app.core.forms import Refused
from app.core.settings import Settings
from app.core.uploads import BODY_TOO_LARGE, KINDS, RequestLimit, UploadStore, check_upload, read_upload
from app.main import create_app
from tests.conftest import PERSON, build_settings, running_server
from tests.helpers import ROOT

PDF = b"%PDF-1.7\n1 0 obj\n"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(32)
JPEG = b"\xff\xd8\xff\xe0" + bytes(32)
LARGEST = 1024


@pytest.fixture
def store(tmp_path: Path) -> UploadStore:
    return UploadStore(tmp_path / "uploads", LARGEST)


def checking(content: bytes, name: str):
    return check_upload(io.BytesIO(content), name, LARGEST)


@pytest.mark.rule("SEC-12")
@pytest.mark.parametrize(
    ("content", "name", "media_type"),
    [
        (PDF, "report.pdf", "application/pdf"),
        (PNG, "photo.png", "image/png"),
        (JPEG, "photo.jpg", "image/jpeg"),
        (JPEG, "photo.jpeg", "image/jpeg"),
        (PDF, "REPORT.PDF", "application/pdf"),
        (PNG, "foto de la avería.png", "image/png"),
    ],
)
def test_what_is_on_the_list_passes(content, name, media_type):
    assert checking(content, name).media_type == media_type


@pytest.mark.rule("SEC-12")
def test_too_big_is_refused_and_exactly_the_limit_is_not():
    assert checking(PDF + bytes(LARGEST - len(PDF)), "report.pdf")
    with pytest.raises(Refused, match="1 KB or smaller"):
        checking(PDF + bytes(LARGEST - len(PDF) + 1), "report.pdf")


@pytest.mark.rule("SEC-12")
def test_empty_is_refused():
    with pytest.raises(Refused, match="empty"):
        checking(b"", "report.pdf")


@pytest.mark.rule("SEC-12")
@pytest.mark.parametrize(
    "name", ["virus.exe", "page.html", "page.svg", "script.js", "macro.docm", "archive.zip", "noextension", ".pdf"]
)
def test_a_type_off_the_list_is_refused_whatever_it_holds(name):
    with pytest.raises(Refused, match="PDF, PNG, JPEG"):
        checking(PDF, name)


@pytest.mark.rule("SEC-12")
@pytest.mark.parametrize(
    ("content", "name"),
    [
        (b"MZ\x90\x00 an executable", "photo.png"),
        (b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>", "photo.png"),
        (b"<html><script>alert(1)</script>", "report.pdf"),
        (b"#!/bin/sh\nrm -rf /\n", "photo.jpg"),
        (b"PK\x03\x04 a zip", "report.pdf"),
    ],
)
def test_a_renamed_extension_is_refused_by_what_the_file_really_is(content, name):
    with pytest.raises(Refused, match="not really"):
        checking(content, name)


@pytest.mark.rule("SEC-12")
@pytest.mark.parametrize(("content", "name"), [(PNG, "report.pdf"), (PDF, "photo.png"), (JPEG, "photo.png")])
def test_a_real_file_with_the_name_of_another_kind_is_refused(content, name):
    with pytest.raises(Refused, match="does not match"):
        checking(content, name)


@pytest.mark.rule("SEC-12")
@pytest.mark.parametrize(
    "name",
    [
        "../../etc/passwd.png",
        "..\\..\\windows\\photo.png",
        "/etc/photo.png",
        "C:\\temp\\photo.png",
        "photo..png",
        "uploads/photo.png",
        "photo\x00.png",
        "photo\n.png",
        "photo.png:evil.exe",
        "photo\u202egnp.png",
        "photo\u2028.png",
        "photo\x85.png",
        "\u200b.png",
        " .png",
        "\u00a0.png",
        "x" * 201 + ".png",
    ],
)
def test_a_name_with_a_path_or_a_trick_is_refused(name):
    with pytest.raises(Refused, match="Rename"):
        checking(PNG, name)


@pytest.mark.rule("SEC-12")
@pytest.mark.parametrize("name", ["report.pdf.exe", "photo.php.png", "photo.png.pdf", "a.b.c.pdf", "report.pdf."])
def test_a_double_extension_is_refused(name):
    with pytest.raises(Refused, match="one extension"):
        checking(PDF, name)


def test_the_list_says_what_it_takes():
    assert {kind.label for kind in KINDS} == {"PDF", "PNG", "JPEG"}


def test_nothing_chosen_is_nothing_to_read():
    assert read_upload(None, LARGEST) is None
    assert read_upload(UploadFile(io.BytesIO(b""), filename=""), LARGEST) is None


def test_a_file_chosen_is_checked():
    assert read_upload(UploadFile(io.BytesIO(PDF), filename="report.pdf"), LARGEST).media_type == "application/pdf"
    with pytest.raises(Refused):
        read_upload(UploadFile(io.BytesIO(b""), filename="report.pdf"), LARGEST)


# Storing


@pytest.mark.rule("SEC-12")
def test_a_stored_name_is_ours_with_nothing_of_the_persons(store):
    stored = store.save(io.BytesIO(PDF))
    assert re.fullmatch(r"[0-9a-f]{32}", stored)
    assert store.path_of(stored).read_bytes() == PDF
    assert [path.name for path in store.folder.iterdir()] == [stored]


@pytest.mark.rule("SEC-12")
@pytest.mark.skipif(os.name == "nt", reason="Windows has no such modes")
def test_a_stored_file_cannot_run_and_only_the_application_reads_it(store):
    stored = store.save(io.BytesIO(PDF))
    assert store.path_of(stored).stat().st_mode & 0o777 == 0o600


@pytest.mark.rule("SEC-12")
@pytest.mark.parametrize("name", ["../secret", "..\\secret", "/etc/passwd", "a" * 31, "A" * 32, "g" * 32, ""])
def test_a_path_is_never_built_from_anything_but_a_stored_name(store, name):
    with pytest.raises(ValueError, match="stored"):
        store.path_of(name)


def test_saving_makes_the_folder_only_when_it_is_needed(tmp_path):
    folder = tmp_path / "later" / "uploads"
    store = UploadStore(folder, LARGEST)
    assert not folder.exists()
    store.save(io.BytesIO(PDF))
    assert folder.exists()


def test_removing_twice_is_no_error(store):
    stored = store.save(io.BytesIO(PDF))
    store.remove(stored)
    store.remove(stored)
    assert not store.path_of(stored).exists()


def test_clearing_takes_stored_files_and_nothing_else(store):
    store.save(io.BytesIO(PDF))
    (store.folder / "notes.txt").write_text("not ours", encoding="utf-8")
    store.clear()
    assert [path.name for path in store.folder.iterdir()] == ["notes.txt"]


def test_a_write_that_fails_leaves_nothing_behind(store):
    class Failing(io.BytesIO):
        def read(self, *_arguments):
            if self.tell():
                raise OSError("no space left")
            self.seek(4)
            return PDF

    with pytest.raises(OSError, match="no space"):
        store.save(Failing(PDF))
    assert list(store.folder.iterdir()) == []


def test_clearing_takes_what_a_crash_left_half_written(store):
    store.save(io.BytesIO(PDF))
    (store.folder / ("a" * 32 + ".part")).write_bytes(PDF)
    store.clear()
    assert list(store.folder.iterdir()) == []


def test_clearing_a_folder_that_never_was_is_no_error(store):
    store.clear()


# Sending back


@pytest.mark.rule("SEC-12")
def test_a_file_goes_back_as_an_attachment_that_nothing_sniffs(store):
    application = create_app(build_settings())
    stored = store.save(io.BytesIO(PDF))
    application.add_api_route("/file", lambda: store.response(stored, "informe de avería.pdf", "application/pdf"))
    response = TestClient(application).get("/file", headers=PERSON)
    assert response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("attachment; ")
    assert "avería" not in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"


def test_a_file_that_is_no_longer_on_disk_is_not_found(store):
    application = create_app(build_settings())
    application.add_api_route("/file", lambda: store.response("a" * 32, "report.pdf", "application/pdf"))
    assert TestClient(application, raise_server_exceptions=False).get("/file", headers=PERSON).status_code == 404


# Settings


@pytest.mark.rule("SEC-12")
def test_the_folder_is_set_and_git_ignores_where_it_is_by_default():
    assert build_settings(upload_folder="/srv/files").upload_folder == Path("/srv/files")
    assert Settings.model_fields["upload_folder"].default.parts[0] == ".data"
    assert ".data/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


@pytest.mark.rule("SEC-12")
@pytest.mark.parametrize("folder", ["app/ui/static/uploads", "app", "./app/demo/static"])
def test_a_folder_the_application_could_serve_from_is_refused(folder):
    with pytest.raises(ValidationError, match="upload_folder"):
        build_settings(upload_folder=folder)


def test_a_whole_request_must_have_room_for_a_whole_file():
    with pytest.raises(ValidationError, match="request_max_bytes"):
        build_settings(upload_max_bytes=2000, request_max_bytes=1000)


# A request too long


def limited(**settings) -> FastAPI:
    application = create_app(build_settings(request_max_bytes=2000, upload_max_bytes=1000, **settings))

    def route(title: Annotated[str, Form()] = "", attachment: Annotated[UploadFile | None, File()] = None) -> str:
        return title

    application.add_api_route("/sample", route, methods=["POST"])
    return application


@pytest.fixture
def client() -> TestClient:
    return TestClient(limited(), raise_server_exceptions=False)


@pytest.mark.rule("SEC-12")
def test_a_body_that_says_it_is_too_long_is_refused_before_it_is_read(client):
    response = client.post("/sample", files={"attachment": ("a.pdf", bytes(5000))}, headers=PERSON)
    assert response.status_code == 413
    assert response.headers["content-type"].startswith("text/html")


@pytest.mark.rule("SEC-12")
def test_a_body_that_does_not_say_is_counted_as_it_arrives(client):
    def chunks() -> Iterator[bytes]:
        yield b'--x\r\nContent-Disposition: form-data; name="title"\r\n\r\n'
        yield b"a" * 5000
        yield b"\r\n--x--\r\n"

    headers = PERSON | {"Content-Type": "multipart/form-data; boundary=x"}
    assert client.post("/sample", content=chunks(), headers=headers).status_code == 413


def test_a_body_within_the_limit_passes(client):
    assert client.post("/sample", data={"title": "short"}, headers=PERSON).json() == "short"


@pytest.mark.rule("SEC-07")
def test_the_limit_does_not_take_the_place_of_the_other_refusals(client):
    assert client.post("/sample", files={"attachment": ("a.pdf", bytes(5000))}).status_code == 401
    other_site = PERSON | {"Sec-Fetch-Site": "cross-site"}
    assert client.post("/sample", files={"attachment": ("a.pdf", bytes(5000))}, headers=other_site).status_code == 403


@pytest.mark.rule("SEC-12")
def test_a_real_server_refuses_a_request_that_would_not_fit_without_reading_it():
    application = limited(fake_identity=True, fake_groups=["admins"], trusted_proxies=[])
    with running_server(application) as port, socket.create_connection(("127.0.0.1", port)) as client:
        head = "POST /sample HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: multipart/form-data; boundary=x\r\n"
        client.sendall(f"{head}Content-Length: 500000000\r\n\r\n".encode())
        assert b" 413 " in client.recv(4096).split(b"\r\n", 1)[0]


def chunk(data: bytes) -> bytes:
    return f"{len(data):x}\r\n".encode() + data + b"\r\n"


def raw_post(port: int, headers: str, length: int) -> bytes:
    """A valid form, sent in chunks on a real socket, and the first line of the answer."""
    with socket.create_connection(("127.0.0.1", port), timeout=10) as client:
        head = "POST /sample HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: multipart/form-data; boundary=x\r\n"
        client.sendall(f"{head}{headers}\r\n".encode())
        client.sendall(chunk(b'--x\r\nContent-Disposition: form-data; name="title"\r\n\r\n'))
        client.sendall(chunk(b"a" * length) + chunk(b"\r\n--x--\r\n") + b"0\r\n\r\n")
        return client.recv(4096).split(b"\r\n", 1)[0]


@pytest.mark.rule("SEC-12")
def test_a_request_with_both_framing_headers_is_refused_unread():
    """h11 frames by Transfer-Encoding, so a small Content-Length beside it promised nothing and took any amount."""
    application = limited(fake_identity=True, fake_groups=["admins"], trusted_proxies=[])
    with running_server(application) as port:
        assert b" 200 " in raw_post(port, "Transfer-Encoding: chunked\r\n", 10)
        assert b" 400 " in raw_post(port, "Transfer-Encoding: chunked\r\nContent-Length: 5\r\n", 10)


@pytest.mark.rule("SEC-12")
def test_a_real_server_stops_a_chunked_body_at_the_limit():
    application = limited(fake_identity=True, fake_groups=["admins"], trusted_proxies=[])
    with running_server(application) as port:
        assert b" 413 " in raw_post(port, "Transfer-Encoding: chunked\r\n", 3000)


@pytest.mark.rule("SEC-12")
@pytest.mark.parametrize("declared", ["5", "999999", ""])
def test_what_is_counted_is_what_arrives_whatever_the_headers_say(declared):
    """The limit reads the bytes, not the promise."""
    seen = []

    async def application(_scope, receive, _send):
        while (message := await receive())["type"] == "http.request":
            seen.append(len(message["body"]))

    messages = iter([{"type": "http.request", "body": bytes(600), "more_body": True}] * 3)

    async def arrives():
        return next(messages, {"type": "http.disconnect"})

    headers = [(b"content-length", declared.encode())] if declared else []
    scope = {"type": "http", "headers": headers}
    limit = RequestLimit(application, 1000)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(anyio.run, limit, scope, arrives, None).result()
    assert seen == [600]
    assert scope[BODY_TOO_LARGE]


def test_a_length_of_thousands_of_digits_is_too_long_and_no_error():
    request = Request({"type": "http", "headers": [(b"content-length", b"9" * 5000)], "app": limited()})
    assert application_module._declared_too_long(request)


@pytest.mark.parametrize(
    ("size", "language", "text"),
    [
        (500, "en", "500 B"),
        (2048, "en", "2 KB"),
        (1_572_864, "en", "1.5 MB"),
        (1_572_864, "es", "1,5 MB"),
        (10_485_760, "en", "10 MB"),
    ],
)
def test_a_size_reads_as_a_person_says_it(size, language, text):
    i18n._language.set(language)
    assert format_file_size(size) == text
