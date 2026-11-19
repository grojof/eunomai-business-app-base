"""Writes the application as files, for a server that only serves files: no process, no database. A reverse proxy in
front signs people in and sends the headers. See docs/base/a-static-application.md#a-static-application

uv run --frozen python tools/export_static.py <output>

It writes `<output>/site/`, the folder to serve at the root of its host (`index.html`, `404.html`, a folder for each
language with its pages, its `search.html` and its `404.html`, and `static/` with the application's own files), and
`<output>/headers.json`, the HTTP headers the proxy must send with every file: those the application itself sends.

Settings come from the environment, as the application's do (`APP_NAME`, `APP_TIME_ZONE`, `APP_LANGUAGES`...), and
no `.env` is read. It ends with 0 only if every page was exported. Otherwise it says why, a reason a line, writes
nothing to `<output>`, and ends with 1: an application that needs a server is not exported by halves.
"""

import argparse
import html
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterable
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.dependencies.models import Dependant  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.routing import BaseRoute, Mount  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

from app.core import application as core  # noqa: E402
from app.core import templating  # noqa: E402
from app.core.database import get_session  # noqa: E402
from app.core.settings import SIGNED_IN, Settings  # noqa: E402

FORCED: dict[str, Any] = {
    "environment": "production",
    "database_url": "postgresql+psycopg://application@localhost/application",  # nothing connects to it
    "fake_identity": False,
    "fake_groups": [],
    "trusted_proxies": ["testclient"],
    "header_username": "X-Remote-User",
    "header_name": "X-Remote-Name",
    "header_email": "X-Remote-Email",
    "header_groups": "X-Remote-Groups",
    "role_groups": {},
    "layout_choices": [],
}
"""The settings an export never takes from the environment: it runs as production does, its database is an address
nothing connects to, the one who asks for each page is a made-up person with no group, so with `signed_in` alone, and
nobody may change the arrangement, since no server would remember it."""
PERSON = {"X-Remote-User": "export"}
BRAND_FILES = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".ico", ".woff2", ".woff", ".ttf", ".otf"}
"""What a page shows of app/brand: its images and its fonts. Its theme is already in the stylesheet, and its
arrangement in the pages."""
CORE_ROUTES = (core._health, core._search, core._save_preferences, core._settings_page)
"""The core's own routes, which are not pages to export: an export has no health to ask after, its search is a file,
and its preferences stay in the browser."""
SEARCH = "/search"
NOT_FOUND = "/404.html"
HTMX = re.compile(r"(?:data-)?(?:hx-(?:get|post|put|patch|delete|sse|ws)|sse-connect|ws-connect)")
"""htmx's attributes that reach the server: a request, or a connection kept open by one of its extensions."""
LOADED = {"src", "href", "xlink:href", "poster", "data", "background", "manifest", "ping"}
"""Attributes that hold one address a browser fetches; `srcset` and `imagesrcset` hold several."""
REFRESH = re.compile(r"^\s*[\d.]+\s*[;,]?\s*(?:url\s*=\s*)?[\"']?([^\"']+)", re.I)
STYLE_ADDRESS = re.compile(r"""url\(\s*["']?(/static/[^"')\s]+)""")
HREF = re.compile(r"""(\shref\s*=\s*)(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.I)


def folder_of(language: str) -> str:
    """A language's folder in the site: its tag, as `lang` and `hreflang` write it."""
    return language.replace("_", "-")


def address_of(path: str, folder: str) -> str:
    """Where a page of the application is in the site: `/` is `/en/`, `/guide` is `/en/guide/`, and a path that names
    a file, such as the page for what is not found, keeps its name."""
    if path == "/":
        return f"/{folder}/"
    return f"/{folder}{path}" if path.endswith(".html") else f"/{folder}{path}/"


def page_of(path: str) -> str:
    """A page's name whichever way its address is written: `/guide/` and `/guide` are one page."""
    return path.rstrip("/") or "/"


def _calls(dependant: Dependant) -> Iterable[Dependant]:
    yield dependant
    for inner in dependant.dependencies:
        yield from _calls(inner)


def _why_not(route: APIRoute) -> list[str]:
    """Why a route cannot be a file: what it does needs a server at the moment a person asks."""
    methods = sorted((route.methods or set()) - {"HEAD", "OPTIONS"})
    if methods != ["GET"]:
        return [f"it answers {', '.join(methods)}: a change needs a server"]
    reasons = []
    if route.param_convertors:
        reasons.append("its address has a parameter: its pages are made when asked for")
    parts = list(_calls(route.dependant))
    if any(part.call is get_session for part in parts):
        reasons.append("it reads the database")
    if any(part.body_params for part in parts):
        reasons.append("it reads a form or a file a person sends")
    if any(part.query_params or part.header_params or part.cookie_params for part in parts):
        reasons.append("it reads the request's query, headers or cookies")
    roles = sorted({str(role) for part in parts if (role := getattr(part.call, "role", None)) not in (None, SIGNED_IN)})
    if roles:
        reasons.append(f"it asks for the role {', '.join(roles)}: an export is the same for everyone who is signed in")
    return reasons


def pages_of(application: FastAPI) -> tuple[list[str], list[str]]:
    """The addresses to export, and why any route cannot be: every route is a page of the export or a reason."""
    pages: list[str] = []
    reasons: list[str] = []
    route: BaseRoute
    for route in application.routes:
        path = str(getattr(route, "path", route))
        if isinstance(route, Mount):
            if not (isinstance(route.app, StaticFiles) and route.app.directory):
                reasons.append(f"{path}: what is mounted there is not a folder of files")
        elif not isinstance(route, APIRoute):
            reasons.append(f"{path}: not a page the export knows how to write")
        elif route.endpoint not in CORE_ROUTES:
            found = _why_not(route)
            reasons += [f"{path}: {reason}" for reason in found]
            if not found:
                pages.append(path)
    once: dict[str, str] = {}
    for path in pages:
        once.setdefault(page_of(path), path)
    return list(once.values()), reasons


class _Files:
    """The folders of files the application serves as they are, by where it mounts them: its own under /static/ui
    and /static/brand, and any other a module mounts. The export copies them to the same addresses."""

    def __init__(self, application: FastAPI) -> None:
        self.mounted = {
            route.path: Path(route.app.directory).resolve()
            for route in application.routes
            if isinstance(route, Mount) and isinstance(route.app, StaticFiles) and route.app.directory
        }
        self._brand = templating.BRAND.resolve()

    def _copied(self, folder: Path, file: Path) -> bool:
        return file.is_file() and (folder != self._brand or file.suffix.lower() in BRAND_FILES)

    def link_problems(self) -> list[str]:
        """A link among the files to copy would be copied as what it points at, which may be anything on the computer
        that makes the export: no link is followed, and one stops the export."""
        problems = []
        for prefix, folder in self.mounted.items():
            for path in sorted(folder.rglob("*")):
                if path.is_symlink() or path.is_junction():
                    name = f"{prefix}/{path.relative_to(folder).as_posix()}"
                    problems.append(f"{name}: it is a link to somewhere else, which is not copied: put the file there")
        return problems

    def is_theirs(self, address: str) -> bool:
        return address.startswith("/static/") or any(address.startswith(prefix + "/") for prefix in self.mounted)

    def has(self, address: str) -> bool:
        """Whether the export has a file at this address."""
        path = urlsplit(address).path
        for prefix, folder in self.mounted.items():
            if path.startswith(prefix + "/"):
                file = (folder / path.removeprefix(prefix + "/")).resolve()
                return file.is_relative_to(folder) and self._copied(folder, file)
        return False

    def style_problems(self) -> list[str]:
        """A stylesheet of the application's own that names a file of its own which is not there."""
        problems = []
        for prefix, folder in self.mounted.items():
            for sheet in sorted(file for file in folder.rglob("*.css") if self._copied(folder, file)):
                for address in STYLE_ADDRESS.findall(sheet.read_text(encoding="utf-8", errors="replace")):
                    if not self.has(address):
                        name = f"{prefix}/{sheet.relative_to(folder).as_posix()}"
                        problems.append(f"{name}: {address} is not a file the export has")
        return problems

    def copy(self, site: Path) -> None:
        for prefix, folder in self.mounted.items():
            for file in sorted(folder.rglob("*")):
                if self._copied(folder, file) and "__pycache__" not in file.parts:
                    target = site / prefix.lstrip("/") / file.relative_to(folder)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(file, target)


class _Page(HTMLParser):
    """Reads a page as the application wrote it: finds what would need a server, and where each link must change to
    stay inside the language's folder. `pages` is None for a page whose links are already the site's."""

    def __init__(
        self, text: str, path: str, folder: str, folders: set[str], pages: set[str] | None, files: _Files
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.files = files
        self.text = text
        self.path = path
        self.folder = folder
        self.folders = folders
        self.pages = pages
        self.problems: list[str] = []
        self._edits: list[tuple[int, int, str]] = []
        self._lines = [0, *(found.end() for found in re.finditer("\n", text))]
        self._calendar = False
        self._json: list[str] | None = None
        self.feed(text)
        self.close()

    def rewritten(self) -> str:
        text = self.text
        for start, end, new in sorted(self._edits, reverse=True):
            text = text[:start] + new + text[end:]
        return text

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        for name, value in values.items():
            if HTMX.fullmatch(name):
                self.problems.append(f'{name}="{value}" asks the server for a piece of the page')
            elif name in ("srcset", "imagesrcset"):
                for part in value.split(","):
                    self._loads(part.split()[0] if part.split() else "", needed=True)
            elif name == "href" and tag in ("a", "area"):
                self._link(value, values.get("hreflang", ""))
            elif name in LOADED:
                self._loads(value, needed=True)
            else:
                self._loads(value)
        if tag == "meta" and values.get("http-equiv", "").lower() == "refresh":
            target = REFRESH.match(values.get("content", ""))
            if target and not urlsplit(target[1].strip()).scheme:
                self.problems.append(f'the page sends itself on to "{target[1].strip()}": use a link instead')
        method = values.get("method", "get").lower()
        if tag == "form" and method == "post":
            self.problems.append(f'a form sends a change to "{values.get("action", self.path)}"')
        elif tag == "form" and method != "dialog" and values.get("action"):
            self.problems.append(f'a form sends its fields to "{values["action"]}", where nothing would read them')
        if values.get("formmethod", "").lower() == "post" or "formaction" in values:
            self.problems.append(f"a button of a form sends it to the server ({self.get_starttag_text()})")
        if "data-url" in values and values["data-url"] != f"/{self.folder}/search.html":
            self.problems.append(f'data-url="{values["data-url"]}" is fetched from the server')
        if "data-calendar" in values:
            self._calendar = True
        if tag == "script" and values.get("type") == "application/json" and self._calendar:
            self._json = []

    def handle_data(self, data: str) -> None:
        if self._json is not None:
            self._json.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._json is not None:
            try:
                settings = json.loads("".join(self._json))
            except ValueError:
                settings = {}
            if isinstance(settings, dict) and isinstance(settings.get("events"), str):
                self.problems.append(f'a calendar asks the server for its events at "{settings["events"]}"')
            if isinstance(settings, dict) and settings.get("canMove"):
                self.problems.append(f'a calendar sends each move to the server at "{settings.get("move")}"')
            self._json, self._calendar = None, False

    def _loads(self, address: str, needed: bool = False) -> None:
        """An address a page loads from. `needed`: the attribute holds nothing but an address."""
        if self.files.is_theirs(address):
            if not self.files.has(address):
                self.problems.append(f"{address} is not a file the export has")
        elif not needed or not address or address.startswith(("#", "//")) or urlsplit(address).scheme:
            return  # not an address, a part of this page, or another site, which the policy decides
        elif address.startswith("/"):
            self.problems.append(f"{address} is loaded from the server")
        else:
            self.problems.append(f"{address} is a relative address: write it from the root, as /static/...")

    def _link(self, href: str, hreflang: str) -> None:
        if self.pages is None or href.startswith("#"):
            return self._loads(href)
        if urlsplit(href).scheme or href.startswith("//"):
            return None  # another site, or a mail address
        target = urlsplit(urljoin(self.path, href))
        if self.files.is_theirs(target.path):
            return self._loads(href)
        page = page_of(target.path)
        if target.query:
            self.problems.append(f'a link to "{href}" has a query, which only a server reads')
        elif page not in self.pages:
            self.problems.append(f'a link to "{href}" leads to a page that is not exported')
        else:
            folder = hreflang if hreflang in self.folders else self.folder
            new = address_of(page, folder) + (f"#{target.fragment}" if target.fragment else "")
            line, column = self.getpos()
            start = self._lines[line - 1] + column
            tag = self.get_starttag_text() or ""
            changed = HREF.sub(lambda found: f'{found[1]}"{html.escape(new)}"', tag, count=1)
            if self.text.startswith(tag, start) and changed != tag:
                self._edits.append((start, start + len(tag), changed))
            else:
                self.problems.append(f'a link to "{href}" could not be rewritten for the language\'s folder')
        return None


class _Errors(logging.Handler):
    """What the application logged while a page was made: the reason behind its error page."""

    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.last = ""

    def emit(self, record: logging.LogRecord) -> None:
        error = record.exc_info[1] if record.exc_info else None
        self.last = f"{type(error).__name__}: {error}" if error else record.getMessage()


def _no_database() -> Any:
    raise RuntimeError("an exported application has no database")


def _write(site: Path, address: str, text: str) -> None:
    file = site / address.lstrip("/")
    if address.endswith("/"):
        file = file / "index.html"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(text.encode("utf-8"))


def build(application: FastAPI, site: Path) -> list[str]:
    """Writes the site into an empty folder and returns why it could not, if it could not: then the folder is not to
    be used."""
    application.state.static = True
    application.state.sessions = _no_database
    languages = application.state.languages
    settings = application.state.settings
    pages, reasons = pages_of(application)
    if reasons:
        return reasons
    files = _Files(application)
    reasons += files.link_problems() + files.style_problems()
    errors = _Errors()
    logging.getLogger(core.__name__).addHandler(errors)
    known = {page_of(path) for path in pages} | {NOT_FOUND}
    folders = {folder_of(code) for code in languages.offered}
    written: dict[str, str] = {}
    try:
        for code in languages.offered:
            folder = folder_of(code)
            client = TestClient(application, raise_server_exceptions=False, follow_redirects=False)
            client.cookies.set("language", code)
            for declared in (*pages, NOT_FOUND, SEARCH):
                errors.last = ""
                response = client.get(
                    declared, headers=PERSON
                )  # as declared: `/guide/` asked without its bar redirects
                path = page_of(declared)
                expected = 404 if path == NOT_FOUND else 200
                kind = response.headers.get("content-type", "")
                if response.status_code in (301, 302, 303, 307, 308):
                    reasons.append(f"{path}: it sends the person on to {response.headers.get('location')}")
                elif response.status_code != expected:
                    why = f" ({errors.last})" if errors.last else ""
                    reasons.append(f"{path}: it answers {response.status_code}{why}")
                elif not kind.startswith("text/html"):
                    reasons.append(f"{path}: it answers {kind or 'nothing'}, which is not a page")
                else:
                    page = _Page(response.text, "/" if path == SEARCH else path, folder, folders, known, files)
                    reasons += [f"{path}: {problem}" for problem in page.problems]
                    address = f"/{folder}/search.html" if path == SEARCH else address_of(path, folder)
                    written[address] = page.rewritten()
    finally:
        logging.getLogger(core.__name__).removeHandler(errors)
    first = templating.environment.get_template("static_index.html").render(
        app_name=settings.name,
        default_language=folder_of(languages.default),
        languages=[(folder_of(code), name) for code, name in languages.options()],
    )
    reasons += [f"/: {problem}" for problem in _Page(first, "/", "", folders, None, files).problems]
    written["/index.html"] = first
    # One page for what is not found, at the root, for a proxy that takes a single address: the default language's.
    written[NOT_FOUND] = written.get(f"/{folder_of(languages.default)}{NOT_FOUND}", "")
    if reasons:
        return list(dict.fromkeys(reasons))
    for address, text in written.items():
        _write(site, address, text)
    files.copy(site)
    return []


def export(output: Path, create: Callable[[Settings], FastAPI]) -> list[str]:
    """Exports the application `create` makes into `output`, whole or not at all: an empty list means it is there, and
    anything else is why nothing was written."""
    try:
        settings = Settings(**FORCED, _env_file=None)  # type: ignore[call-arg]
    except ValueError as error:
        return [f"settings: {line}" for line in str(error).splitlines()]
    with tempfile.TemporaryDirectory(prefix="export-static-") as temporary:
        made = Path(temporary)
        reasons = build(create(settings), made / "site")
        if reasons:
            return reasons
        headers = json.dumps(core.SECURITY_HEADERS, indent=2) + "\n"
        (made / "headers.json").write_bytes(headers.encode("utf-8"))
        output.mkdir(parents=True, exist_ok=True)
        if (output / "site").exists():
            shutil.rmtree(output / "site")
        (output / "headers.json").unlink(missing_ok=True)
        shutil.move(made / "site", output / "site")
        shutil.move(made / "headers.json", output / "headers.json")
    return []


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Writes the application as files, for a server of files.")
    parser.add_argument("output", type=Path, help="the folder that gets site/ and headers.json")
    options = parser.parse_args(arguments)
    # app.main builds the application as it is imported, from the environment: it must find what an export runs with.
    for name, value in FORCED.items():
        os.environ[f"APP_{name.upper()}"] = value if isinstance(value, str) else json.dumps(value)
    from app.main import create_app

    reasons = export(options.output, create_app)
    if reasons:
        print("\n".join(reasons), file=sys.stderr)
        return 1
    site = options.output / "site"
    count = sum(1 for _ in site.rglob("*.html"))
    print(f"{site.as_posix()}: {count} pages, and the headers to send with them in headers.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
