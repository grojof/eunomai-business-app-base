import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.core.identity import require_role
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
