"""Pages: Jinja2 with escaping always on, the translation functions and the locale's formatters."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, StrictUndefined

from app import __version__
from app.core import formatters, i18n
from app.core.i18n import current_language

LAYOUTS = {
    "navigation": ("side", "compact", "top", "hidden"),
    "sticky_header": ("on", "off"),
    "width": ("full", "centered"),
    "density": ("normal", "compact"),
}
UI = Path(__file__).resolve().parent.parent / "ui"
ROOT = UI.parent.parent
_loaders: list[FileSystemLoader] = [FileSystemLoader(UI / "templates")]
_VENDOR_SCRIPTS = [
    {"src": "/static/ui/vendor/" + Path(entry["target"]).name, "integrity": "sha384-" + entry["sha384"]}
    for entry in json.loads((ROOT / "vendor.json").read_text(encoding="utf-8")).values()
    if entry.get("script")
]

environment = Environment(
    loader=ChoiceLoader(_loaders),
    autoescape=True,
    undefined=StrictUndefined,
    extensions=["jinja2.ext.i18n"],
)
cast(Any, environment).install_gettext_callables(
    gettext=i18n._, ngettext=i18n.ngettext, newstyle=True, pgettext=i18n.pgettext, npgettext=i18n.npgettext
)
environment.filters["decimal"] = formatters.format_decimal
environment.filters["date"] = formatters.format_date


@dataclass(frozen=True)
class NavigationItem:
    label: str  # marked with N_ where it is defined, translated when shown
    path: str
    icon: str
    role: str | None = None


def layout_for(request: Request) -> dict[str, Any]:
    """The application's arrangement; where the demo lets people try others, their choice."""
    settings = request.app.state.settings
    layout: dict[str, Any] = {
        "navigation": settings.layout_navigation,
        "sticky_header": settings.layout_sticky_header,
        "width": settings.layout_width,
        "density": settings.layout_density,
    }
    if request.app.state.layout_preview:
        for field, allowed in LAYOUTS.items():
            value = request.cookies.get(f"layout_{field}")
            if value in allowed:
                layout[field] = value == "on" if field == "sticky_header" else value
    return layout


def add_templates(folder: Path) -> None:
    if not any(str(folder) in loader.searchpath for loader in _loaders):
        _loaders.insert(0, FileSystemLoader(folder))


def _render(request: Request, name: str, status_code: int, context: dict[str, Any]) -> HTMLResponse:
    state = request.app.state
    person = getattr(request.state, "person", None)
    roles = person.roles if person else frozenset()
    query = f"?{request.url.query}" if request.url.query else ""

    def local_datetime(value: datetime) -> str:
        return formatters.format_datetime(value, state.settings.time_zone)

    html = environment.get_template(name).render(
        app_name=state.settings.name,
        version=__version__,
        language=current_language(),
        language_tag=current_language().replace("_", "-"),
        languages=state.languages.options(),
        theme=getattr(request.state, "theme", "system"),
        layout=layout_for(request),
        person=person,
        navigation=[item for item in state.navigation if item.role is None or item.role in roles],
        current_path=request.url.path,
        here=request.url.path + query,
        vendor_scripts=_VENDOR_SCRIPTS,
        local_datetime=local_datetime,
        **context,
    )
    return HTMLResponse(html, status_code=status_code)


def render(request: Request, name: str, status_code: int = 200, **context: Any) -> HTMLResponse:
    return _render(request, name, status_code, context)
