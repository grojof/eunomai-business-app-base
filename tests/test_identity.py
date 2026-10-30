import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app import __version__
from app.core.identity import require_role
from app.core.templating import NavigationItem
from app.main import create_app
from tests.conftest import build_settings


@pytest.mark.rule("SEC-01")
def test_without_identity_nothing_is_served(client):
    response = client.get("/")
    assert response.status_code == 401
    assert "demo.person" not in response.text


@pytest.mark.rule("SEC-01")
def test_headers_are_ignored_unless_they_come_from_the_proxy(person):
    settings = build_settings(trusted_proxies=["10.0.0.1"])
    response = TestClient(create_app(settings)).get("/", headers=person)
    assert response.status_code == 401


@pytest.mark.rule("SEC-01")
def test_a_fake_identity_refuses_to_start_outside_development():
    with pytest.raises(ValueError, match="only in development"):
        build_settings(environment="production", fake_identity=True)


@pytest.mark.rule("SEC-01")
@pytest.mark.parametrize("path", ["/healthcare/x", "/health-reports", "/healthz", "/staticfiles/x", "/static"])
def test_a_path_that_only_starts_like_a_public_one_needs_identity(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.rule("SEC-01")
@pytest.mark.parametrize("header", ["X-Remote-User", "X-Remote-Name", "X-Remote-Email", "X-Remote-Groups"])
def test_a_repeated_identity_header_means_no_identity(client, person, header):
    repeated = [*person.items(), (header, "first"), (header, "second")]
    assert client.get("/", headers=repeated).status_code == 401


def test_a_stranger_sees_no_navigation_and_no_version(client):
    client.app.state.navigation = [NavigationItem("Open to all", "/open", "menu")]
    html = client.get("/").text
    assert 'href="/open"' not in html
    assert 'id="navigation"' not in html
    assert __version__ not in html


@pytest.mark.parametrize("path", ["/", "/static/missing"])
def test_a_stranger_gets_no_user_menu(client, path):
    html = client.get(path).text
    assert "data-menu" not in html
    assert "/preferences" not in html


def test_the_user_menu_is_there_for_a_person_with_identity(client, person):
    html = client.get("/", headers=person).text
    assert "data-menu" in html
    assert 'action="/preferences"' in html


def test_the_proxy_identity_reaches_the_page(client, person):
    assert "Demo Person" in client.get("/", headers=person).text


def test_a_name_with_accents_arrives_intact(client, person):
    raw = {name: value.encode() for name, value in person.items()} | {"X-Remote-Name": "Núria Peña".encode()}
    assert "Núria Peña" in client.get("/", headers=raw).text


def test_health_needs_no_identity_and_says_nothing_else(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.rule("SEC-02")
def test_a_role_is_checked_on_the_server(person):
    application = create_app(build_settings())

    async def secret() -> dict[str, str]:
        return {"secret": "yes"}

    application.add_api_route("/secret", secret, dependencies=[Depends(require_role("auditor"))])
    client = TestClient(application)
    response = client.get("/secret", headers=person)
    assert response.status_code == 403
    assert "secret" not in response.text.split("<title>")[0]
