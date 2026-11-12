"""The application's own files and the copied libraries are linked with a stamp of their content, so a browser never
keeps an old script or stylesheet after an update: an old library would even fail its new integrity and not run."""

import re

from fastapi.testclient import TestClient

from app.core import templating
from app.main import create_app
from tests.conftest import build_settings


def test_an_own_file_is_linked_with_a_stamp_that_follows_its_content(tmp_path, monkeypatch):
    monkeypatch.setattr(templating, "BRAND", tmp_path)
    logo = tmp_path / "logo.svg"
    logo.write_text("<svg/>")
    first = templating.asset("/static/brand/logo.svg")
    assert re.fullmatch(r"/static/brand/logo\.svg\?v=[0-9a-f]{12}", first)
    assert templating.asset("/static/brand/logo.svg") == first  # the same content, the same address
    logo.write_text("<svg viewBox='0 0 1 1'/>")
    assert templating.asset("/static/brand/logo.svg") != first


def test_every_script_and_stylesheet_of_a_page_carries_its_stamp(person):
    html = TestClient(create_app(build_settings())).get("/", headers=person).text
    linked = re.findall(r'(?:src|href)="(/static/(?:ui|brand)/[^"]+\.(?:js|css|svg)[^"]*)"', html)
    assert linked, "the page links its files"
    assert [address for address in linked if "?v=" not in address] == []
