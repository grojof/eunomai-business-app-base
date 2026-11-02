"""Pages: Jinja2 with escaping always on, the translation functions and the locale's formatters."""

import json
from collections.abc import Callable, Iterable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, PrefixLoader, StrictUndefined

from app import __version__
from app.core import formatters, i18n
from app.core.i18n import N_, current_language
from app.core.settings import LAYOUTS

UI = Path(__file__).resolve().parent.parent / "ui"
ROOT = UI.parent.parent
_loaders: list[FileSystemLoader] = [FileSystemLoader(UI / "templates")]
BRAND_ICONS = FileSystemLoader(UI.parent / "brand" / "icons")
"""The organization's own icons, as `brand-icons/<name>.svg`. Only the icon macro includes them, as it does Lucide's."""
_VENDORED = json.loads((ROOT / "vendor.json").read_text(encoding="utf-8"))


def _script(entry: dict[str, Any]) -> dict[str, str]:
    return {"src": "/static/ui/vendor/" + Path(entry["target"]).name, "integrity": "sha384-" + entry["sha384"]}


_VENDOR_SCRIPTS = [_script(entry) for entry in _VENDORED.values() if entry.get("script") and not entry.get("on_demand")]

environment = Environment(
    loader=ChoiceLoader([ChoiceLoader(_loaders), PrefixLoader({"brand-icons": BRAND_ICONS})]),
    autoescape=True,
    undefined=StrictUndefined,
    extensions=["jinja2.ext.i18n"],
)
cast(Any, environment).install_gettext_callables(
    gettext=i18n._, ngettext=i18n.ngettext, newstyle=True, pgettext=i18n.pgettext, npgettext=i18n.npgettext
)
environment.globals["chart_library"] = _script(
    _VENDORED["chart.js"]
)  # charts.js loads it, only for a page with a chart
environment.globals["board_library"] = _script(_VENDORED["sortablejs"])  # board.js loads it, only for a board
environment.globals["calendar_library"] = {  # calendar.js loads the scripts, and the macro links the styles
    "library": _script(_VENDORED["fullcalendar"]),
    "theme": _script(_VENDORED["fullcalendar-classic"]),
    "styles": [
        _script(_VENDORED[name])
        for name in ("fullcalendar-css", "fullcalendar-classic-css", "fullcalendar-palette-css")
    ],
}
environment.filters["decimal"] = formatters.format_decimal
environment.filters["date"] = formatters.format_date
environment.filters["percent"] = formatters.format_percent
environment.filters["filesize"] = formatters.format_file_size


@dataclass
class PageTitle:
    """Where a page's h1 goes. The layout asks for the top bar before it draws the content, `page_heading` then leaves
    its title here instead of in the page, and the top bar writes it, still as the page's one h1."""

    in_header: bool = False
    text: str = ""

    def ask(self, in_header: bool) -> str:
        self.in_header = in_header
        return ""

    def take(self, text: str) -> bool:
        if self.in_header and not self.text:
            self.text = text
            return True
        return False


_page_title: ContextVar[PageTitle | None] = ContextVar("page_title", default=None)
environment.globals["page_title"] = lambda: _page_title.get() or PageTitle()
"""Each render has its own: a fragment never asks for the top bar, so its heading stays where it is."""


@dataclass(frozen=True)
class NavigationGroup:
    """Links shown under a navigation item while a person is inside it, already in their language."""

    title: str
    links: Sequence[tuple[str, str]]  # (label, path)


@dataclass(frozen=True)
class NavigationItem:
    label: str  # marked with N_ where it is defined, translated when shown
    path: str
    icon: str
    role: str | None = None
    children: Callable[[], Sequence[NavigationGroup]] | None = None


@dataclass(frozen=True)
class SearchItem:
    """One result of the command palette, already in the person's language."""

    label: str
    path: str
    group: str
    description: str = ""
    keywords: str = ""
    icon: str = ""


SearchProvider = Callable[[], Iterable[SearchItem]]
"""Called on each search, inside the request, so it can use the person's language."""


def register_search(state: Any, provider: SearchProvider) -> None:
    """Adds results to the command palette. Navigation items are always in it."""
    state.search.append(provider)


def visible_navigation(request: Request) -> list[NavigationItem]:
    person = getattr(request.state, "person", None)
    roles = person.roles if person else frozenset()
    return [item for item in request.app.state.navigation if person and (item.role is None or item.role in roles)]


def search_items(request: Request) -> list[SearchItem]:
    """Everything the palette can find for this person: what they may open, once each, navigation first."""
    items = [
        SearchItem(i18n._(item.label), item.path, i18n._(N_("Pages")), icon=item.icon)
        for item in visible_navigation(request)
    ]
    for provider in request.app.state.search:
        items += provider()
    seen: set[str] = set()
    return [item for item in items if not (item.path in seen or seen.add(item.path))]  # type: ignore[func-returns-value]


def layout_for(request: Request) -> dict[str, Any]:
    """The application's arrangement; where the demo lets people try others, their choice."""
    settings = request.app.state.settings
    layout: dict[str, Any] = {field: getattr(settings, f"layout_{field}") for field in LAYOUTS}
    for field in settings.layout_choices:
        value = request.cookies.get(f"layout_{field}")
        if value in LAYOUTS[field]:
            layout[field] = value == "on" if field == "sticky_header" else value
    return layout


def add_templates(folder: Path) -> None:
    if not any(str(folder) in loader.searchpath for loader in _loaders):
        _loaders.insert(0, FileSystemLoader(folder))


def _render(request: Request, name: str, status_code: int, context: dict[str, Any]) -> HTMLResponse:
    state = request.app.state
    person = getattr(request.state, "person", None)
    query = f"?{request.url.query}" if request.url.query else ""

    def local_datetime(value: datetime) -> str:
        return formatters.format_datetime(value, state.settings.time_zone)

    def local_date(value: datetime) -> str:
        return formatters.format_date(value.astimezone(ZoneInfo(state.settings.time_zone)).date())

    token = _page_title.set(PageTitle())
    try:
        html = environment.get_template(name).render(
            app_name=state.settings.name,
            version=__version__,
            language=current_language(),
            language_tag=current_language().replace("_", "-"),
            languages=state.languages.options(),
            theme=getattr(request.state, "theme", "system"),
            layout=layout_for(request),
            person=person,
            navigation=visible_navigation(request),
            settings_menu=bool(state.settings.layout_choices),
            theme_options=[
                ("system", i18n._("As the system"), "monitor"),
                ("light", i18n._("Light"), "sun"),
                ("dark", i18n._("Dark"), "moon"),
            ],
            current_path=request.url.path,
            here=request.url.path + query,
            vendor_scripts=_VENDOR_SCRIPTS,
            local_datetime=local_datetime,
            local_date=local_date,
            **context,
        )
    finally:
        _page_title.reset(token)
    return HTMLResponse(html, status_code=status_code)


def render(request: Request, name: str, status_code: int = 200, **context: Any) -> HTMLResponse:
    return _render(request, name, status_code, context)
