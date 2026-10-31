"""An htmx request gets a fragment or a whole-page redirect, never a page inside a page, in any state of the rows."""

import pytest
from fastapi.testclient import TestClient

from app.demo import equipment, planning
from app.demo.data import MISSING, UNREACHABLE
from app.main import create_app
from tests.conftest import PERSON, build_settings

HTMX = {"HX-Request": "true"}
SAME_SITE = {"Sec-Fetch-Site": "same-origin"}
FORM = {"status": "planned", "planned_on": "", "hours": "1", "back": "/planning"}


@pytest.fixture(params=[MISSING, UNREACHABLE])
def not_ready(request, monkeypatch):
    for module in (equipment, planning):
        monkeypatch.setattr(module, "rows_state", lambda _session, state=request.param: state)
    client = TestClient(create_app(build_settings()), raise_server_exceptions=False, follow_redirects=False)
    client.headers.update(PERSON)
    return client


@pytest.mark.parametrize(
    ("path", "address"),
    [
        ("/equipment?status=stopped", "/equipment"),
        ("/equipment/1?tab=orders", "/equipment/1"),
        ("/planning?group=month", "/planning"),
        ("/planning/1/edit", "/planning"),
    ],
)
def test_a_fragment_request_is_sent_to_a_whole_page(not_ready, path, address):
    response = not_ready.get(path, headers=HTMX)
    assert response.status_code == 200
    assert response.headers["hx-redirect"] == address
    assert "<html" not in response.text


def test_a_save_is_sent_to_a_whole_page(not_ready):
    response = not_ready.post("/planning/1", data=FORM, headers=HTMX | SAME_SITE)
    assert response.headers["hx-redirect"] == "/planning"
    assert "<html" not in response.text


@pytest.mark.parametrize("path", ["/equipment", "/equipment/1", "/planning"])
def test_a_plain_request_still_gets_its_whole_page(not_ready, path):
    response = not_ready.get(path)
    assert response.status_code == 200
    assert "<html" in response.text


def test_going_back_gets_the_whole_page_too(not_ready):
    response = not_ready.get("/equipment", headers=HTMX | {"HX-History-Restore-Request": "true"})
    assert "<html" in response.text


def test_without_javascript_the_editor_redirects_as_a_browser_expects(not_ready):
    response = not_ready.get("/planning/1/edit")
    assert (response.status_code, response.headers["location"]) == (303, "/planning")
