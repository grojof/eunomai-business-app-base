"""Files people send, as SEC-12 asks: checked by size and by what they really are, and kept where nothing can run them.

What a file calls itself proves nothing, so its first bytes decide, against a short list. It is stored under a random
name of ours, with no extension, in a folder the application does not serve, and goes back only as an attachment, with
`nosniff`. Its own name is kept as data, for showing.

This is the floor, not the whole answer: a real PDF can carry something harmful. What a clone must add for production is
in docs/specification.md#uploads.
"""

import logging
import os
import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.formatters import format_file_size
from app.core.forms import Refused
from app.core.i18n import _

logger = logging.getLogger(__name__)
LONGEST_NAME = 200
_STORED_NAME = re.compile(r"[0-9a-f]{32}")
_NOT_IN_A_NAME = set('/\\:*?"<>|')
BODY_TOO_LARGE = "body_too_large"
"""What `RequestLimit` leaves in the request's scope when a body with no declared length goes past the limit."""


@dataclass(frozen=True)
class FileKind:
    """What a file may be: the first bytes that prove it, and the names it may go by."""

    label: str
    media_type: str
    extensions: tuple[str, ...]
    signature: bytes


KINDS = (
    FileKind("PDF", "application/pdf", ("pdf",), b"%PDF-"),
    FileKind("PNG", "image/png", ("png",), b"\x89PNG\r\n\x1a\n"),
    FileKind("JPEG", "image/jpeg", ("jpg", "jpeg"), b"\xff\xd8\xff"),
)
"""The allow-list. To add a kind, add its signature: an extension alone proves nothing. Formats with no signature of
their own, such as plain text and CSV, need a reader, not a line here."""
ACCEPTED = ",".join(f".{extension}" for kind in KINDS for extension in kind.extensions)
"""For the browser's `accept`, which helps a person choose and decides nothing."""


def _kinds_in_words() -> str:
    return _("The file must be one of these: %(kinds)s.") % {"kinds": ", ".join(kind.label for kind in KINDS)}


def _named_kind(name: str) -> FileKind:
    """What the name claims, once the name itself is safe. A browser sends a bare name, so a path is someone's doing."""
    unsafe = _NOT_IN_A_NAME & set(name) or ".." in name or len(name) > LONGEST_NAME
    # Category C holds control characters and the invisible ones that turn `gnp.exe` around on screen.
    if unsafe or any(unicodedata.category(character).startswith("C") for character in name):
        raise Refused(_("Rename the file: its name cannot have a path or special characters."))
    stem, _dot, extension = name.rpartition(".")
    if "." in stem:
        raise Refused(_("Rename the file so that it has one extension, such as report.pdf."))
    kind = next((kind for kind in KINDS if extension.lower() in kind.extensions), None)
    if kind is None or not stem:
        raise Refused(_kinds_in_words())
    return kind


def check_upload(file: IO[bytes], name: str, largest: int) -> FileKind:
    """The name, the size, then what the file really is. Raises `Refused` with what the person should do."""
    kind = _named_kind(name)
    size = file.seek(0, os.SEEK_END)
    if not size:
        raise Refused(_("The file is empty. Choose one with something in it."))
    if size > largest:
        raise Refused(_("The file must be %(most)s or smaller.") % {"most": format_file_size(largest)})
    file.seek(0)
    start = file.read(max(len(known.signature) for known in KINDS))
    file.seek(0)
    real = next((known for known in KINDS if start.startswith(known.signature)), None)
    if real is None:
        raise Refused(_("This is not really a %(kind)s file. Choose another.") % {"kind": kind.label})
    if real is not kind:
        raise Refused(_("The name of this file does not match what it holds. Rename it, or choose another."))
    return kind


def read_upload(upload: UploadFile | None, largest: int) -> FileKind | None:
    """What a file field sent, for `read_fields`. Nothing chosen arrives as a file with no name."""
    if upload is None or not upload.filename:
        return None
    return check_upload(upload.file, upload.filename, largest)


class UploadStore:
    """The folder of files. Nothing reaches a path from outside: names are made here, read back from the database, and
    checked again on the way to the disk."""

    def __init__(self, folder: Path, largest: int) -> None:
        self.folder = folder
        self.largest = largest

    def path_of(self, stored: str) -> Path:
        if not _STORED_NAME.fullmatch(stored):
            raise ValueError("not a stored name")
        return self.folder / stored

    def save(self, file: IO[bytes]) -> str:
        """Writes to a name no one can guess, in one step: a half-written file is never there under its final name."""
        self.folder.mkdir(parents=True, exist_ok=True)
        stored = uuid4().hex
        target = self.path_of(stored)
        partial = target.with_suffix(".part")
        file.seek(0)
        descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        with os.fdopen(descriptor, "wb") as written:
            while block := file.read(64 * 1024):
                written.write(block)
        partial.replace(target)
        return stored

    def remove(self, stored: str) -> None:
        """After the row has gone. A file left behind is untidy, and a row without its file an error, so it comes last,
        and a failure stays in the log."""
        try:
            self.path_of(stored).unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove stored file %s", stored)

    def clear(self) -> None:
        """Every stored file, and nothing else that may be in the folder."""
        if self.folder.exists():
            for path in self.folder.iterdir():
                if _STORED_NAME.fullmatch(path.name):
                    path.unlink()

    def response(self, stored: str, name: str, media_type: str) -> FileResponse:
        path = self.path_of(stored)
        if not path.is_file():
            raise HTTPException(status_code=404)
        headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}
        return FileResponse(path, media_type=media_type, filename=name, headers=headers)


class RequestLimit:
    """The whole request has a limit, for every route: FastAPI reads a form to disk before any route or check runs.

    A body that declares its length is judged by `_context` before a byte is read. One that does not is counted as it
    arrives, and ends as if the client had left, with a note in the scope, because an exception raised while a request
    is read does not cross `BaseHTTPMiddleware` as itself.
    """

    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or "content-length" in Headers(scope=scope):
            await self.app(scope, receive, send)
            return
        await self.app(scope, self._counted(scope, receive), send)

    def _counted(self, scope: Scope, receive: Receive) -> Callable[[], Awaitable[Message]]:
        seen = 0

        async def counted() -> Message:
            nonlocal seen
            message = await receive()
            seen += len(message.get("body", b""))
            if seen > self.limit:
                scope[BODY_TOO_LARGE] = True
                return {"type": "http.disconnect"}
            return message

        return counted
