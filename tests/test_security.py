import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import build_settings
from tests.helpers import ROOT


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
def test_cookies_are_secure_in_production(person):
    client = TestClient(create_app(build_settings(environment="production")))
    response = client.post("/preferences", data={"theme": "dark"}, headers=person, follow_redirects=False)
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie
    assert "httponly" in cookie
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
def test_an_error_reveals_nothing(person):
    application = create_app(build_settings())

    async def broken() -> None:
        raise RuntimeError("password=hunter2 in /srv/app/secret.py")

    application.add_api_route("/broken", broken)
    response = TestClient(application, raise_server_exceptions=False).get("/broken", headers=person)
    assert response.status_code == 500
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text
    assert "content-security-policy" in response.headers


@pytest.mark.rule("SEC-09")
def test_no_secret_file_is_tracked_by_default():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env\n" in ignored
    assert "!.env.example" in ignored


def test_interactive_documentation_is_off(client, person):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path, headers=person).status_code == 404
