import socket
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app

PERSON = {"X-Remote-User": "demo.person", "X-Remote-Name": "Demo Person", "X-Remote-Groups": "staff|admins"}


def build_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "development",
        "trusted_proxies": ["testclient"],
        "role_groups": {"admin": ["admins"]},
    }
    return Settings(**(values | overrides), _env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(build_settings()), raise_server_exceptions=False)


@pytest.fixture
def person() -> dict[str, str]:
    return dict(PERSON)


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    """The real application on a real port, for the browser checks."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    settings = build_settings(fake_identity=True, fake_groups=["admins"], trusted_proxies=[])
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def browser() -> Iterator[Any]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        chrome = playwright.chromium.launch(channel="chrome")
        yield chrome
        chrome.close()


@pytest.fixture
def open_page(browser: Any, base_url: str) -> Iterator[Callable[..., Any]]:
    contexts = []

    def opener(
        path: str, theme: str = "light", language: str = "en", width: int = 1280, bypass_csp: bool = False
    ) -> Any:
        context = browser.new_context(viewport={"width": width, "height": 800}, bypass_csp=bypass_csp)
        contexts.append(context)
        context.add_cookies(
            [
                {"name": "theme", "value": theme, "url": base_url},
                {"name": "language", "value": language, "url": base_url},
            ]
        )
        page = context.new_page()
        page.goto(base_url + path)
        return page

    yield opener
    for context in contexts:
        context.close()
