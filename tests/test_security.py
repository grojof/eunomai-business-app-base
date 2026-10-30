import http.client
import json
import logging
import re
import tomllib

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import PERSON, build_settings, running_server
from tests.helpers import ROOT, repository_text_files
from tools import css


@pytest.mark.rule("SEC-06")
def test_every_response_carries_the_security_headers(client, person):
    for path, headers in (("/", person), ("/", {}), ("/missing", person), ("/health", {})):
        response = client.get(path, headers=headers)
        policy = response.headers["content-security-policy"]
        assert "default-src 'none'" in policy
        assert "script-src 'self'" in policy
        assert "unsafe" not in policy
        assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.rule("SEC-06")
def test_pages_have_no_inline_script_or_style(client, person):
    html = client.get("/", headers=person).text
    assert not re.search(r"<script(?![^>]*\ssrc=)", html)
    assert "<style" not in html
    assert " style=" not in html
    assert not re.search(r"\son\w+=", html)


@pytest.mark.rule("SEC-07")
def test_a_change_from_another_site_is_refused(client, person):
    response = client.post(
        "/preferences",
        data={"theme": "dark"},
        headers=person | {"Sec-Fetch-Site": "cross-site"},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert "theme" not in response.cookies


@pytest.mark.rule("SEC-07")
def test_a_change_with_a_foreign_origin_is_refused(client, person):
    response = client.post(
        "/preferences", data={"theme": "dark"}, headers=person | {"Origin": "https://attacker.example"}
    )
    assert response.status_code == 403


@pytest.mark.rule("SEC-07")
def test_a_change_from_the_application_works(client, person):
    response = client.post(
        "/preferences",
        data={"theme": "dark", "next": "/"},
        headers=person | {"Sec-Fetch-Site": "same-origin"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.cookies["theme"] == "dark"


@pytest.mark.rule("SEC-13")
@pytest.mark.parametrize("target", ["https://attacker.example/", "//attacker.example/", "/\\attacker.example", ""])
def test_going_back_never_leaves_the_application(client, person, target):
    response = client.post(
        "/preferences", data={"theme": "dark", "next": target}, headers=person, follow_redirects=False
    )
    assert response.headers["location"] == "/"


@pytest.mark.rule("SEC-13")
def test_every_cookie_is_secure_in_production(person):
    application = create_app(build_settings(environment="production"))
    application.state.layout_preview = True
    chosen = {"theme": "dark", "language": "es", "layout_navigation": "top", "layout_density": "compact"}
    response = TestClient(application).post("/preferences", data=chosen, headers=person, follow_redirects=False)
    cookies = [cookie.lower() for cookie in response.headers.get_list("set-cookie")]
    assert {cookie.split("=")[0] for cookie in cookies} == set(chosen)
    for cookie in cookies:
        assert "; secure" in cookie
        assert "; httponly" in cookie
        assert "samesite=lax" in cookie


@pytest.mark.rule("SEC-04")
def test_escaping_is_on(client, person):
    person["X-Remote-Name"] = "<script>alert(1)</script>"
    html = client.get("/", headers=person).text
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.rule("SEC-04")
def test_no_template_turns_escaping_off():
    for template in (ROOT / "app").rglob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert "|safe" not in text.replace(" ", ""), template
        assert "autoescape false" not in text, template


@pytest.mark.rule("SEC-14")
def test_no_code_of_ours_runs_text_as_code():
    sources = [
        *(ROOT / "app").rglob("*.py"),
        *(ROOT / "tools").rglob("*.py"),
        ROOT / "app" / "ui" / "static" / "app.js",
    ]
    for source in sources:
        assert not re.search(r"\b(eval|exec)\(|new Function", source.read_text(encoding="utf-8")), source


@pytest.mark.rule("SEC-14")
def test_no_template_uses_the_features_that_need_eval():
    for template in (ROOT / "app").rglob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert not re.search(r"hx-on|hx-vars|hx-vals=[\"']js:|hx-headers=[\"']js:|x-html", text), template


@pytest.mark.rule("SEC-11")
def test_an_error_reveals_nothing_and_is_logged_for_it(person, caplog):
    application = create_app(build_settings())

    async def broken() -> None:
        raise RuntimeError("password=hunter2 in /srv/app/secret.py")

    application.add_api_route("/broken", broken)
    with caplog.at_level(logging.ERROR, logger="app.core.application"):
        response = TestClient(application, raise_server_exceptions=False).get("/broken", headers=person)
    assert response.status_code == 500
    assert "Unhandled error on /broken" in caplog.text
    assert "hunter2" in caplog.text  # the detail goes to IT, in the log
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text
    assert "content-security-policy" in response.headers


SECRETS = {
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "cloud access key": r"\bAKIA[0-9A-Z]{16}\b",
    "repository token": r"\bgh[pousr]_[A-Za-z0-9]{36}\b",
    "chat token": r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    "password in an address": r"[a-z][a-z0-9+.-]*://[^/\s:@\"']+:[^/\s:@\"']{3,}@",
    "assigned secret": r"(?i)\b(?:password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']",
}


def secrets_in(text: str) -> list[str]:
    return [name for name, pattern in SECRETS.items() if re.search(pattern, text)]


@pytest.mark.rule("SEC-09")
def test_no_file_in_the_repository_holds_an_obvious_secret():
    files = repository_text_files()
    assert len(files) > 50
    found = {path: secrets_in(path.read_text(encoding="utf-8", errors="replace")) for path in files}
    assert {path: secrets for path, secrets in found.items() if secrets} == {}


@pytest.mark.rule("SEC-09")
@pytest.mark.parametrize(
    "text",
    [
        "AKIA" + "ABCDEFGHIJKLMNOP",
        "gho_" + "a" * 36,
        "-----BEGIN RSA " + "PRIVATE KEY-----",
        "postgresql://user:long" + "pass@host/base",
        'password = "' + 'correct-horse"',
    ],
)
def test_the_secret_scan_finds_a_planted_secret(text):
    assert secrets_in(text) != []


@pytest.mark.rule("SEC-09")
def test_no_secret_file_is_tracked_by_default():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env\n" in ignored
    assert "!.env.example" in ignored


@pytest.mark.rule("SEC-10")
def test_every_package_in_the_lock_carries_hashes():
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = [package for package in lock["package"] if package["name"] != "business-app-base"]
    assert packages
    for package in packages:
        files = [*package.get("wheels", []), *([package["sdist"]] if "sdist" in package else [])]
        assert files, package["name"]
        assert all(re.fullmatch(r"sha256:[0-9a-f]{64}", file.get("hash", "")) for file in files), package["name"]


@pytest.mark.rule("SEC-10")
def test_the_stylesheets_executable_has_a_hash_for_each_supported_platform():
    entry = json.loads((ROOT / "vendor.json").read_text(encoding="utf-8"))["tailwindcss"]
    assert set(entry["executables"]) == set(css.SUPPORTED)
    assert all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in entry["executables"].values())


def status_through_a_local_proxy(port: int) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", "/", headers=PERSON | {"X-Forwarded-For": "203.0.113.9"})
    status = connection.getresponse().status
    connection.close()
    return status


@pytest.mark.rule("SEC-01")
def test_a_proxy_on_the_same_host_is_believed_when_uvicorn_ignores_its_forwarding_headers():
    application = create_app(build_settings(trusted_proxies=["127.0.0.1"]))
    with running_server(application, proxy_headers=False) as port:
        assert status_through_a_local_proxy(port) == 200


@pytest.mark.rule("SEC-01")
def test_with_uvicorns_default_everyone_behind_that_proxy_is_refused():
    """Why the flag is needed: this rewrites the address the application trusts."""
    application = create_app(build_settings(trusted_proxies=["127.0.0.1"]))
    with running_server(application, proxy_headers=True) as port:
        assert status_through_a_local_proxy(port) == 401


def test_the_example_settings_show_the_start_command():
    assert "--no-proxy-headers" in (ROOT / ".env.example").read_text(encoding="utf-8")


def test_every_documented_start_command_turns_proxy_headers_off():
    commands = re.findall(r"^.*uvicorn app\.main:app.*$", (ROOT / "README.md").read_text(encoding="utf-8"), re.M)
    assert commands
    assert all("--no-proxy-headers" in command for command in commands)


def test_a_refused_method_says_what_is_allowed(client, person):
    response = client.post("/", headers=person)
    assert response.status_code == 405
    assert "GET" in response.headers["allow"]
    assert "content-security-policy" in response.headers


def test_the_repository_names_no_product_it_does_not_depend_on():
    word = "co" + "work"
    assert [p.name for p in repository_text_files() if word in p.read_text("utf-8", "replace").lower()] == []


def test_interactive_documentation_is_off(client, person):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path, headers=person).status_code == 404
