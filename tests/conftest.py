import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI
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


@contextmanager
def running_server(application: FastAPI, proxy_headers: bool = False) -> Iterator[int]:
    """A real uvicorn on a real port, which it returns. Without proxy headers, as it runs behind a proxy."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = uvicorn.Config(application, host="127.0.0.1", port=port, log_level="warning", proxy_headers=proxy_headers)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield port
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    """The real application, for the browser checks."""
    settings = build_settings(fake_identity=True, fake_groups=["admins"], trusted_proxies=[])
    with running_server(create_app(settings)) as port:
        yield f"http://127.0.0.1:{port}"


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
        path: str,
        theme: str = "light",
        language: str = "en",
        width: int = 1280,
        bypass_csp: bool = False,
        layout: dict[str, str] | None = None,
    ) -> Any:
        context = browser.new_context(viewport={"width": width, "height": 800}, bypass_csp=bypass_csp)
        contexts.append(context)
        context.add_cookies(
            [
                {"name": "theme", "value": theme, "url": base_url},
                {"name": "language", "value": language, "url": base_url},
                *({"name": f"layout_{k}", "value": v, "url": base_url} for k, v in (layout or {}).items()),
            ]
        )
        page = context.new_page()
        page.goto(base_url + path)
        return page

    yield opener
    for context in contexts:
        context.close()
