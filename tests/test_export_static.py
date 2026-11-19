"""An application whose pages need nothing from a server is written as files by tools/export_static.py: a folder for
each language, its search as a file, the theme and the language kept by the browser, and the headers the proxy must
send. An application that needs a server is refused whole, with every reason. See docs/base/a-static-application.md

The applications here are made up for each test, on the core: the exporter takes whatever `create` builds."""

import json
import os
import re
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.testclient import TestClient

from app.core.application import SECURITY_HEADERS, create_core, install_home
from app.core.database import DatabaseSession
from app.core.identity import Person, require_role
from app.core.settings import Settings
from app.core.templating import NavigationItem, SearchItem, register_search, render
from tests.conftest import build_settings
from tests.helpers import ROOT, run_axe, run_axe_in_both_themes
from tools import export_static, remove_demo

LANGUAGES = ("en", "es", "ca")
"""The languages these exports are made in, whatever the application offers: an application that kept fewer still
gets the three folders, the ones without a catalogue in the source language."""
Install = Callable[[FastAPI], None]


def made_of(*steps: Install) -> Callable[[Settings], FastAPI]:
    """An application on the core: what each step adds, and the base's start page."""

    def create(settings: Settings) -> FastAPI:
        application = create_core(settings)
        for step in steps:
            step(application)
        install_home(application)
        return application

    return create


def a_page(path: str, body: str = "<h1>Page</h1>", **route: Any) -> Install:
    def install(application: FastAPI) -> None:
        async def show() -> HTMLResponse:
            return HTMLResponse(f"<!doctype html><html lang='en'><head><title>Page</title></head><body>{body}</body>")

        application.add_api_route(path, show, include_in_schema=False, **route)

    return install


def a_guide(application: FastAPI) -> None:
    """A second page in the shell, in the menu and in the search."""

    async def show(request: Request) -> Response:
        return render(request, "home.html")

    application.add_api_route("/guide", show, include_in_schema=False)
    application.state.navigation += [
        NavigationItem("Start", "/", "house"),
        NavigationItem("Guide", "/guide", "book-open"),
    ]
    register_search(application.state, lambda: [SearchItem("Glossary", "/guide#words", "Pages", "The words we use")])


def export(output: Path, *steps: Install) -> list[str]:
    with pytest.MonkeyPatch.context() as environment:
        if "APP_LANGUAGES" not in os.environ:  # a test that sets its own keeps them
            environment.setenv("APP_LANGUAGES", json.dumps(LANGUAGES))
            environment.setenv("APP_DEFAULT_LANGUAGE", "en")
        return export_static.export(output, made_of(*steps))


def translated(language: str) -> bool:
    """Whether the application kept this language's catalogue: an organization's template may offer fewer."""
    return (ROOT / "locales" / language).is_dir()


def exported(tmp_path: Path, *steps: Install) -> Path:
    output = tmp_path / "exported"
    assert export(output, *steps) == []
    return output / "site"


def refused(tmp_path: Path, *steps: Install) -> str:
    """Why an application is not exported, a reason a line, and nothing written."""
    output = tmp_path / "refused"
    reasons = export(output, *steps)
    assert reasons and not output.exists()
    return "\n".join(reasons)


def read(file: Path) -> str:
    return file.read_text(encoding="utf-8")


def test_an_application_is_written_once_for_each_language_with_its_files(tmp_path):
    site = exported(tmp_path, a_guide)
    assert (site / "index.html").is_file()
    for language in LANGUAGES:
        for name in ("index.html", "guide/index.html", "search.html", "404.html", "../404.html"):
            assert (site / language / name).is_file(), f"{language}/{name}"
    for name in ("ui/app.css", "ui/app.js", "ui/preferences.js", "ui/vendor/htmx.min.js", "brand/logo.svg"):
        assert (site / "static" / name).is_file(), name
    assert not (site / "static" / "brand" / "theme.css").exists()  # the stylesheet already holds it
    for language, start in (("es", "Inicio"), ("ca", "Inici")):
        page = read(site / language / "index.html")
        assert f'<html lang="{language}"' in page and (start in page or not translated(language))
    assert "Page not found" in read(site / "en" / "404.html")


@pytest.mark.rule("SEC-17")
def test_every_link_stays_inside_its_language_and_leads_to_a_file(tmp_path):
    site = exported(tmp_path, a_guide)
    for page in site.rglob("*.html"):
        language = "en" if page.parent == site else page.relative_to(site).parts[0]
        for link, address in re.findall(r'(<a\b[^>]*\shref="([^"#][^"]*)"[^>]*>)', read(page)):
            path = address.partition("#")[0]
            target = site / path.lstrip("/")
            assert (target / "index.html" if path.endswith("/") else target).is_file(), f"{page}: {address}"
            if "hreflang" not in link:
                assert path.startswith(f"/{language}/"), f"{page}: {address}"
    spanish = read(site / "es" / "index.html")
    assert 'href="/es/guide/"' in spanish and 'href="/es/"' in spanish
    assert 'href="/es/guide/#words"' in read(site / "es" / "search.html")


@pytest.mark.rule("SEC-17")
def test_every_file_a_page_loads_is_in_the_export(tmp_path):
    site = exported(tmp_path, a_guide)
    loaded = {address for page in site.rglob("*.html") for address in re.findall(r'"(/static/[^"?]+)', read(page))}
    assert len(loaded) > 8
    assert [address for address in sorted(loaded) if not (site / address.lstrip("/")).is_file()] == []


@pytest.mark.rule("LANG-12")
def test_the_language_control_is_links_to_the_same_page_in_each_folder(tmp_path):
    site = exported(tmp_path, a_guide)
    guide = read(site / "es" / "guide" / "index.html")
    links = re.findall(r"<a([^>]*hreflang[^>]*)>([^<]+)</a>", guide)
    assert {text for _attributes, text in links} == {"English", "Español", "Català"}
    for attributes, _text in links:
        tag = re.search(r'hreflang="([^"]+)"', attributes)[1]
        assert f'href="/{tag}/guide/"' in attributes and f'lang="{tag}"' in attributes
        assert ('aria-current="true"' in attributes) is (tag == "es")
    first = read(site / "index.html")
    assert 'data-languages="en es ca"' in first and 'data-default-language="en"' in first
    for tag, name in (("en", "English"), ("es", "Español"), ("ca", "Català")):
        assert f'<a class="justify-center" href="/{tag}/" hreflang="{tag}" lang="{tag}">{name}</a>' in first


@pytest.mark.rule("SEC-17")
def test_the_shell_of_an_export_asks_the_server_for_nothing(tmp_path):
    site = exported(tmp_path, a_guide)
    for page in site.rglob("*.html"):
        text = read(page)
        assert not re.search(
            r"""method=["']?post|\shx-(get|post|put|patch|delete)=|/preferences\b(?!\.js)|/settings\b""", text
        ), page
    start = read(site / "en" / "index.html")
    assert 'data-url="/en/search.html"' in start and "/static/ui/preferences.js?v=" in start
    assert "data-theme-control" in start and "data-theme=" not in start.split("<body")[0]
    assert "circle-user" not in start and "export" not in re.sub(r"<[^>]+>", "", start).lower()  # nobody is named


@pytest.mark.parametrize("variant", ["dropdown", "toggle", "swap", "radio"])
def test_every_look_of_the_theme_control_is_exported_without_a_form(tmp_path, monkeypatch, variant):
    monkeypatch.setenv("APP_LAYOUT_THEME_CONTROL", variant)
    start = read(exported(tmp_path) / "en" / "index.html")
    assert start.count("data-theme-control") == 2 and "<form method" not in start.replace('<form method="dialog"', "")
    assert 'name="header-theme"' in start and 'name="menu-theme"' in start  # two copies, never one group of radios


@pytest.mark.parametrize("variant", ["dropdown", "select", "menu"])
def test_every_look_of_the_language_control_is_exported_as_links(tmp_path, monkeypatch, variant):
    monkeypatch.setenv("APP_LAYOUT_LANGUAGE_CONTROL", variant)
    start = read(exported(tmp_path) / "en" / "index.html")
    assert start.count("data-language-control") == 2 and start.count('hreflang="ca"') == 2 and "<select" not in start


@pytest.mark.rule("SEC-06")
def test_the_headers_for_the_proxy_are_the_ones_the_application_sends(tmp_path, person):
    site = exported(tmp_path)
    headers = json.loads(read(site.parent / "headers.json"))
    assert headers == SECURITY_HEADERS and "default-src 'none'" in headers["Content-Security-Policy"]
    answer = TestClient(made_of()(build_settings())).get("/", headers=person)
    assert {name: answer.headers[name] for name in headers} == headers


def test_settings_come_from_the_environment_and_the_exports_own_cannot_be_changed(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_NAME", "Labels")
    monkeypatch.setenv("APP_LANGUAGES", '["en", "es"]')
    monkeypatch.setenv("APP_DEFAULT_LANGUAGE", "en")
    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("APP_FAKE_IDENTITY", "true")
    monkeypatch.setenv("APP_LAYOUT_CHOICES", '["navigation"]')
    site = exported(tmp_path, a_guide)
    assert sorted(path.name for path in site.iterdir()) == ["404.html", "en", "es", "index.html", "static"]
    start = read(site / "es" / "index.html")
    assert " · Labels</title>" in start and "Demo User" not in start
    assert 'data-preferences="navigation-fold"' not in start  # nobody may change what no server would remember


def test_no_setting_makes_a_running_application_static(monkeypatch, person):
    monkeypatch.setenv("APP_STATIC", "true")
    application = made_of()(build_settings())
    assert application.state.static is False
    start = TestClient(application).get("/", headers=person).text
    assert 'action="/preferences"' in start and "preferences.js" not in start and "Demo Person" in start


def a_route_for_a_role(application: FastAPI) -> None:
    async def show(person: Annotated[Person, Depends(require_role("admin"))]) -> HTMLResponse:
        return HTMLResponse("<h1>Administration</h1>")

    application.add_api_route("/administration", show, include_in_schema=False)


def a_route_on_the_database(application: FastAPI) -> None:
    def show(session: DatabaseSession) -> HTMLResponse:
        return HTMLResponse("<h1>Rows</h1>")

    application.add_api_route("/rows", show, include_in_schema=False)


def a_route_with_a_parameter(application: FastAPI) -> None:
    async def show(row: int) -> HTMLResponse:
        return HTMLResponse("<h1>Row</h1>")

    application.add_api_route("/rows/{row:int}", show, include_in_schema=False)


def a_route_that_reads_the_query(application: FastAPI) -> None:
    async def show(page: int = 1) -> HTMLResponse:
        return HTMLResponse("<h1>Rows</h1>")

    application.add_api_route("/list", show, include_in_schema=False)


def a_route_that_fails(application: FastAPI) -> None:
    async def show() -> HTMLResponse:
        raise RuntimeError("the shelf is empty")

    application.add_api_route("/broken", show, include_in_schema=False)


def a_route_that_opens_the_database_itself(application: FastAPI) -> None:
    async def show(request: Request) -> HTMLResponse:
        with request.app.state.sessions():
            return HTMLResponse("<h1>Rows</h1>")

    application.add_api_route("/rows", show, include_in_schema=False)


def a_route_that_sends_elsewhere(application: FastAPI) -> None:
    async def show() -> RedirectResponse:
        return RedirectResponse("/", status_code=303)

    application.add_api_route("/old", show, include_in_schema=False)


def a_route_of_data(application: FastAPI) -> None:
    async def show() -> JSONResponse:
        return JSONResponse({"rows": []})

    application.add_api_route("/rows.json", show, include_in_schema=False)


def a_search_item_to_nowhere(application: FastAPI) -> None:
    register_search(application.state, lambda: [SearchItem("Invoices", "/invoices", "Records")])


A_CALENDAR = (
    '<section data-calendar><script type="application/json">'
    '{"events": "/calendar/events", "move": "/calendar/move", "canMove": true}</script></section>'
)
REFUSALS = [
    (a_page("/save", methods=["POST"]), "/save: it answers POST"),
    (
        a_page("/edit", '<form method="post" action="/save"><button>Save</button></form>'),
        "/edit: a form sends a change",
    ),
    (a_page("/edit", '<form method="POST"><button>Save</button></form>'), "/edit: a form sends a change"),
    (a_page("/find", '<form action="/find"><input name="q"></form>'), "/find: a form sends its fields"),
    (a_page("/rows", '<div hx-get="/rows/more">More</div>'), '/rows: hx-get="/rows/more" asks the server'),
    (a_page("/rows", '<button hx-delete="/rows/1">Delete</button>'), '/rows: hx-delete="/rows/1" asks the server'),
    (a_page("/live", '<div hx-ext="sse" sse-connect="/events"></div>'), '/live: sse-connect="/events" asks the server'),
    (a_page("/live", '<div hx-ext="ws" ws-connect="/chat"></div>'), '/live: ws-connect="/chat" asks the server'),
    (a_page("/plan", '<object data="/plan.pdf"></object>'), "/plan: /plan.pdf is loaded from the server"),
    (
        a_page("/old", '<meta http-equiv="refresh" content="0;url=/admin?x=1">'),
        '/old: the page sends itself on to "/admin?x=1"',
    ),
    (
        a_page("/photo", '<img srcset="/static/ui/app.css 1x, /api/a.png 2x" alt="">'),
        "/photo: /api/a.png is loaded from the server",
    ),
    (a_page("/photo", '<img src="photo.png" alt="">'), "/photo: photo.png is a relative address"),
    (a_route_on_the_database, "/rows: it reads the database"),
    (a_route_that_opens_the_database_itself, "an exported application has no database"),
    (a_route_for_a_role, "/administration: it asks for the role admin"),
    (a_route_with_a_parameter, "/rows/{row:int}: its address has a parameter"),
    (a_route_that_reads_the_query, "/list: it reads the request's query"),
    (a_page("/photo", '<img src="/static/ui/missing.png" alt="">'), "/photo: /static/ui/missing.png is not a file"),
    (a_page("/photo", '<img src="/static/brand/theme.css" alt="">'), "/static/brand/theme.css is not a file"),
    (a_page("/photo", '<img src="/photo.png" alt="">'), "/photo: /photo.png is loaded from the server"),
    (
        a_page("/more", '<a href="/nowhere">More</a>'),
        '/more: a link to "/nowhere" leads to a page that is not exported',
    ),
    (a_page("/more", '<a href="/?page=2">Next</a>'), '/more: a link to "/?page=2" has a query'),
    (a_page("/more", '<div data-url="/more/rows"></div>'), '/more: data-url="/more/rows" is fetched from the server'),
    (a_page("/calendar", A_CALENDAR), '/calendar: a calendar asks the server for its events at "/calendar/events"'),
    (a_page("/calendar", A_CALENDAR), '/calendar: a calendar sends each move to the server at "/calendar/move"'),
    (a_route_that_fails, "/broken: it answers 500 (RuntimeError: the shelf is empty)"),
    (a_route_that_sends_elsewhere, "/old: it sends the person on to /"),
    (a_route_of_data, "/rows.json: it answers application/json, which is not a page"),
    (a_search_item_to_nowhere, '/search: a link to "/invoices" leads to a page that is not exported'),
]


@pytest.mark.rule("SEC-17")
@pytest.mark.parametrize(("step", "reason"), REFUSALS, ids=[reason for _step, reason in REFUSALS])
def test_what_needs_a_server_is_refused_with_its_reason_and_nothing_is_written(tmp_path, step, reason):
    assert reason in refused(tmp_path, step)


@pytest.mark.rule("SEC-17")
def test_every_reason_is_said_at_once_a_line_each(tmp_path):
    reasons = refused(tmp_path, a_route_on_the_database, a_route_for_a_role, a_page("/save", methods=["POST"]))
    assert len(reasons.splitlines()) == 3


def test_a_page_for_everyone_signed_in_is_exported(tmp_path):
    def for_everyone(application: FastAPI) -> None:
        async def show(person: Annotated[Person, Depends(require_role("signed_in"))]) -> HTMLResponse:
            return HTMLResponse("<!doctype html><html lang='en'><title>Open</title><h1>Open to all</h1>")

        application.add_api_route("/open", show, include_in_schema=False)

    assert "Open to all" in read(exported(tmp_path, for_everyone) / "en" / "open" / "index.html")


def test_a_failed_export_leaves_the_last_good_one_as_it_was(tmp_path):
    output = tmp_path / "exported"
    site = exported(tmp_path, a_guide)
    (output / "kept.txt").write_text("someone's own", encoding="utf-8")
    assert export(output, a_route_on_the_database) != []
    assert (site / "es" / "guide" / "index.html").is_file() and (output / "headers.json").is_file()
    assert export(output) == []  # and a good one replaces it whole
    assert not (site / "es" / "guide").exists() and (site / "es" / "index.html").is_file()
    assert read(output / "kept.txt") == "someone's own"


def test_a_folder_of_files_a_module_mounts_is_copied_where_it_is_served(tmp_path):
    from fastapi.staticfiles import StaticFiles

    own = tmp_path / "own"
    own.mkdir()
    (own / "label.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")

    def mounted(application: FastAPI) -> None:
        application.mount("/static/labels", StaticFiles(directory=own), name="labels")

    site = exported(tmp_path, mounted, a_page("/labels", '<img src="/static/labels/label.svg" alt="">'))
    assert (site / "static" / "labels" / "label.svg").is_file()
    assert "/static/labels/gone.svg is not a file" in refused(
        tmp_path, mounted, a_page("/labels", '<img src="/static/labels/gone.svg" alt="">')
    )


def test_a_route_declared_with_a_bar_at_its_end_is_asked_for_as_declared(tmp_path):
    site = exported(
        tmp_path, a_page("/guide/"), a_page("/more", '<a href="/guide/">Guide</a> <a href="/guide">Too</a>')
    )
    assert (site / "es" / "guide" / "index.html").is_file()
    assert read(site / "es" / "more" / "index.html").count('href="/es/guide/"') == 2


def test_the_root_has_the_default_languages_page_for_what_is_not_found(tmp_path, monkeypatch):
    """A proxy that answers every missing address with one file has it, with links that lead somewhere."""
    monkeypatch.setenv("APP_LANGUAGES", '["en", "es"]')
    monkeypatch.setenv("APP_DEFAULT_LANGUAGE", "es")
    site = exported(tmp_path)
    assert read(site / "404.html") == read(site / "es" / "404.html") != read(site / "en" / "404.html")
    assert '<html lang="es"' in read(site / "404.html") and 'href="/es/"' in read(site / "404.html")


@pytest.mark.rule("SEC-17")
def test_a_link_among_the_files_to_copy_stops_the_export(tmp_path):
    """Copied, it would publish whatever it points at on the computer that makes the export."""
    from fastapi.staticfiles import StaticFiles

    own = tmp_path / "own"
    own.mkdir()
    private = tmp_path / "private"
    private.mkdir()
    (private / "notes.txt").write_text("not for anyone", encoding="utf-8")
    try:
        (own / "notes").symlink_to(private, target_is_directory=True)
    except OSError:  # Windows keeps symbolic links for administrators, and lets anyone make a junction
        import _winapi

        _winapi.CreateJunction(str(private), str(own / "notes"))

    def mounted(application: FastAPI) -> None:
        application.mount("/static/labels", StaticFiles(directory=own), name="labels")

    assert "/static/labels/notes: it is a link to somewhere else" in refused(tmp_path, mounted)


def test_the_exporter_reaches_every_application():
    assert "tools/export_static.py" not in remove_demo.ONLY_FOR_THE_BASE


@contextmanager
def served(site: Path, headers: dict[str, str]) -> Iterator[str]:
    """The exported folder behind a server of files that sends the headers, as the proxy in front of it will."""

    class Files(SimpleHTTPRequestHandler):
        def __init__(self, *arguments: Any, **named: Any) -> None:
            super().__init__(*arguments, directory=str(site), **named)

        def end_headers(self) -> None:
            for name, value in headers.items():
                self.send_header(name, value)
            super().end_headers()

        def log_message(self, *arguments: Any) -> None:
            pass

    class Server(ThreadingHTTPServer):
        request_queue_size = 128  # a page asks for its files at once: Python's 5 refuses some on a busy computer

    server = Server(("127.0.0.1", 0), Files)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(scope="module")
def site_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    site = exported(tmp_path_factory.mktemp("static"), a_guide)
    with served(site, json.loads(read(site.parent / "headers.json"))) as url:
        yield url


@pytest.fixture
def opened(browser: Any, site_url: str) -> Iterator[Callable[..., Any]]:
    contexts = []

    def opener(path: str, width: int = 1280, locale: str = "en-GB", **options: Any) -> Any:
        context = browser.new_context(viewport={"width": width, "height": 800}, locale=locale, **options)
        contexts.append(context)
        page = context.new_page()
        page.problems = []
        page.on("console", lambda message: page.problems.append(message.text) if message.type == "error" else None)
        page.goto(site_url + path)
        return page

    yield opener
    for context in contexts:
        context.close()


def theme_of(page: Any) -> str | None:
    return page.evaluate("document.documentElement.dataset.theme ?? null")


@pytest.mark.browser
@pytest.mark.rule("SEC-06")
def test_the_served_export_runs_under_the_headers_with_no_violation(opened, site_url):
    page = opened("/es/guide/")
    page.wait_for_load_state("networkidle")
    assert page.evaluate("typeof htmx") == "object"
    answer = page.reload()
    assert "script-src 'self'" in answer.headers["content-security-policy"]
    page.keyboard.press("Control+k")
    page.locator("[data-palette-option]").first.wait_for(state="visible")
    assert page.problems == []


@pytest.mark.browser
def test_the_first_page_goes_to_the_browsers_language_then_to_the_one_chosen(opened, site_url):
    page = opened("/", locale="ca-ES")
    page.wait_for_url(site_url + "/ca/")
    assert page.locator("html").get_attribute("lang") == "ca"
    page.locator("[data-language-control] summary >> visible=true").click()
    page.locator('[data-language-control] a[hreflang="es"] >> visible=true').click()
    page.wait_for_url(site_url + "/es/")
    assert page.locator("html").get_attribute("lang") == "es"
    page.goto(site_url + "/")
    page.wait_for_url(site_url + "/es/")  # the person's choice, before the browser's own language
    assert page.problems == []


@pytest.mark.browser
def test_a_language_nobody_offers_gets_the_default_and_without_scripts_the_links(opened, site_url):
    page = opened("/", locale="fr-FR")
    page.wait_for_url(site_url + "/en/")
    plain = opened("/", locale="fr-FR", java_script_enabled=False)
    assert plain.url == site_url + "/"
    plain.get_by_role("link", name="Català").click()
    plain.wait_for_url(site_url + "/ca/")
    assert plain.locator("html").get_attribute("lang") == "ca"


@pytest.mark.browser
def test_the_theme_is_kept_by_the_browser_from_one_page_to_the_next(opened, site_url):
    page = opened("/en/")
    assert theme_of(page) is None  # as the system, until a person chooses
    page.locator("[data-theme-control] summary >> visible=true").click()
    page.locator('[data-theme-control] input[value="dark"] >> visible=true').check()
    assert theme_of(page) == "dark"
    assert page.locator('[data-theme-control] input[value="dark"]:checked').count() == 2  # every copy says the same
    dark = page.evaluate("getComputedStyle(document.body).backgroundColor")
    page.keyboard.press("Escape")
    page.get_by_role("link", name="Guide").click()
    page.wait_for_url(site_url + "/en/guide/")
    assert theme_of(page) == "dark"
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == dark
    assert page.locator('[data-theme-icon="dark"] >> visible=true').count() == 1
    page.locator("[data-theme-control] summary >> visible=true").click()
    page.locator('[data-theme-control] input[value="system"] >> visible=true').check()
    assert theme_of(page) is None
    page.reload()
    assert theme_of(page) is None and page.problems == []


@pytest.mark.browser
def test_the_search_finds_a_page_from_its_file_and_opens_it_in_the_same_language(opened, site_url):
    page = opened("/ca/")
    page.keyboard.press("Control+k")
    page.locator("[data-palette-option]").first.wait_for(state="visible")
    page.locator("#palette-input").fill("gloss")
    assert page.locator("[data-palette-option] >> visible=true").count() == 1
    page.keyboard.press("Enter")
    page.wait_for_url(site_url + "/ca/guide/#words")
    assert page.problems == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-06")
@pytest.mark.parametrize("width", [1280, 390])
def test_the_exported_shell_has_no_detectable_accessibility_failure(opened, site_url, width):
    page = opened("/es/guide/", width=width, bypass_csp=True)
    page.evaluate("localStorage.setItem('theme', 'light')")
    page.reload()
    assert theme_of(page) == "light"
    if width < 1024:  # a small screen keeps the controls in a menu of their own, with nobody's name on it
        page.locator("header details:has([data-theme-control]) > summary").click()
        assert page.locator("[data-language-control] summary >> visible=true").count() == 1
    assert run_axe_in_both_themes(page) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-06")
def test_the_first_page_has_no_detectable_accessibility_failure(opened, site_url):
    page = opened("/", java_script_enabled=False)
    assert page.locator("a[hreflang]").count() == 3
    scanned = opened("/es/404.html", bypass_csp=True)  # the scan needs scripts; the first page with them has gone
    scanned.route("**/preferences.js*", lambda route: route.abort())
    scanned.goto(site_url + "/")
    assert scanned.url == site_url + "/"
    assert run_axe(scanned) == []
