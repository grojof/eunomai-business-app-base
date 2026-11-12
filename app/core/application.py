"""The application's core: request context, safety headers, preferences, errors and health."""

import logging
import mimetypes
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import StaleDataError
from starlette.convertors import IntegerConvertor, register_url_convertor
from starlette.exceptions import HTTPException

from app.core import identity
from app.core.addresses import is_local
from app.core.database import create_database_engine
from app.core.i18n import Languages, _
from app.core.settings import LAYOUTS, Settings
from app.core.templating import UI, SearchItem, register_search, render, search_items
from app.core.uploads import BODY_TOO_LARGE, RequestLimit, UploadStore

FONT_TYPES = {".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".otf": "font/otf"}
"""A font's media type by its extension (RFC 8081), for the organization's fonts in app/brand/fonts/. Python reads these
from the system, and Windows has none: without them a font goes out as application/octet-stream."""
for _extension, _kind in FONT_TYPES.items():
    mimetypes.add_type(_kind, _extension)

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent.parent
THEMES = ("system", "light", "dark")
ONE_YEAR = 60 * 60 * 24 * 365
LONGEST_LENGTH = 18
"""Digits in a Content-Length worth reading: more is past any limit, and Python refuses to read thousands of them."""


class _Identifier(IntegerConvertor):
    """A number in an address, of a length no row can have past. Longer is no such address, a 404, and not a 500: Python
    refuses to read an int of more than 4,300 digits. Registered once, so every `{id:int}` route of a clone has it."""

    regex = "[0-9]{1,19}"


register_url_convertor("int", _Identifier())

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "form-action 'self'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
    ]
)


def _cross_site(request: Request) -> bool:
    """Browsers say where a request comes from: a change from another site is refused."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return False
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        return site not in ("same-origin", "none")
    origin = request.headers.get("origin")
    if origin is None:
        return False
    try:
        return urlsplit(origin).netloc != request.headers.get("host")
    except ValueError:  # an origin no browser sends: refused, and not an error
        return True


def _declared_too_long(request: Request) -> bool:
    length = request.headers.get("content-length", "")
    if not (length.isascii() and length.isdigit()):
        return False
    return len(length) > LONGEST_LENGTH or int(length) > request.app.state.settings.request_max_bytes


def _framed_twice(request: Request) -> bool:
    """Both headers mean two lengths, and a server and a proxy may each believe a different one: RFC 9112, 6.1."""
    return "transfer-encoding" in request.headers and "content-length" in request.headers


def _is_public(path: str) -> bool:
    return path == "/health" or path.startswith("/static/")


async def _context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    state = request.app.state
    language = state.languages.choose(request.cookies.get("language"), request.headers.get("accept-language"))
    state.languages.activate(language)
    theme = request.cookies.get("theme")
    request.state.theme = theme if theme in THEMES else "system"

    if _is_public(request.url.path):
        response = await call_next(request)
    else:
        client = request.client.host if request.client else None
        person = identity.from_request(request.headers, client, state.settings)
        request.state.person = person
        if person is None:
            response = _error_page(request, 401)
        elif _cross_site(request):
            response = _error_page(request, 403)
        elif _framed_twice(request):
            response = _error_page(request, 400)
        elif _declared_too_long(request):
            response = _error_page(request, 413)
        else:
            try:
                response = await call_next(request)
            except Exception:  # here, so the error page keeps its language and the headers below
                logger.exception("Unhandled error on %s", request.url.path)
                response = _error_page(request, 500)
            if request.scope.get(BODY_TOO_LARGE):
                response = _error_page(request, 413)

    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


def _error_page(request: Request, status: int) -> Response:
    titles = {
        400: (_("That could not be read"), _("Go back and try again. If it happens again, tell whoever runs this.")),
        401: (_("Sign-in required"), _("We could not tell who you are. Open the application from your portal.")),
        403: (_("You do not have permission"), _("Ask whoever manages this application if you need access.")),
        404: (_("Page not found"), _("Check the address, or go back to the start.")),
        413: (_("That is too large to send"), _("Go back and choose a smaller file.")),
        500: (_("Something went wrong"), _("It is not your fault. Try again in a moment.")),
    }
    title, advice = titles.get(status, titles[500])
    return render(request, "error.html", status_code=status, title=title, advice=advice, status=status)


async def _on_stale_row(request: Request, _error: Exception) -> Response:
    """Someone removed the row between reading and saving it: the same answer as if it had gone a moment earlier."""
    return _error_page(request, 404)


async def _on_unreadable_form(request: Request, _error: Exception) -> Response:
    """A form that is not what a page sends, as when a file arrives for a text field. No page of ours sends that, and
    FastAPI's own answer repeats what came, so a person gets a page."""
    return _error_page(request, 400)


async def _on_http_error(request: Request, error: Exception) -> Response:
    assert isinstance(error, HTTPException)  # noqa: S101  # FastAPI only sends these here
    response = _error_page(request, error.status_code)
    response.headers.update(error.headers or {})  # a 405 must say what is allowed, for example
    return response


def _safe_path(next_path: str) -> str:
    """Goes back to where the person was, and never to another site."""
    return next_path if is_local(next_path) else "/"


async def _save_preferences(
    request: Request,
    language: Annotated[str, Form()] = "",
    theme: Annotated[str, Form()] = "",
    next_path: Annotated[str, Form(alias="next")] = "/",
    layout_navigation: Annotated[str, Form()] = "",
    layout_bar: Annotated[str, Form()] = "",
    layout_sticky_header: Annotated[str, Form()] = "",
    layout_width: Annotated[str, Form()] = "",
    layout_density: Annotated[str, Form()] = "",
    layout_theme_control: Annotated[str, Form()] = "",
    layout_language_control: Annotated[str, Form()] = "",
    layout_page_title: Annotated[str, Form()] = "",
    layout_list_width: Annotated[str, Form()] = "",
    layout_list_density: Annotated[str, Form()] = "",
) -> Response:
    response = RedirectResponse(_safe_path(next_path), status_code=303)
    secure = request.app.state.settings.environment == "production"
    options = {"max_age": ONE_YEAR, "httponly": True, "samesite": "lax", "secure": secure}
    if language in request.app.state.languages.offered:
        response.set_cookie("language", language, **options)
    if theme in THEMES:
        response.set_cookie("theme", theme, **options)
    chosen = {
        "navigation": layout_navigation,
        "bar": layout_bar,
        "sticky_header": layout_sticky_header,
        "width": layout_width,
        "density": layout_density,
        "theme_control": layout_theme_control,
        "language_control": layout_language_control,
        "page_title": layout_page_title,
        "list_width": layout_list_width,
        "list_density": layout_list_density,
    }
    for field in request.app.state.settings.layout_choices:
        if chosen[field] in LAYOUTS[field]:
            response.set_cookie(f"layout_{field}", chosen[field], **options)
    return response


def _settings_item() -> list[SearchItem]:
    return [
        SearchItem(
            _("Settings"),
            "/settings",
            _("Pages"),
            _("Layout, theme, language and how their controls look."),
            icon="sliders-horizontal",
        )
    ]


BAR_THEME = "[data-theme=bar]" in (UI / "static" / "app.css").read_text(encoding="utf-8")
"""Whether the brand has a theme called bar: without one, its colours would look like the page's, so they are not
offered as a choice."""


async def _settings_page(request: Request) -> Response:
    """Everything a person may change about how the application looks, each choice shown as it would be applied."""
    groups = {
        "navigation": (
            _("Navigation"),
            {"side": _("Side"), "compact": _("Icons only"), "top": _("Top"), "hidden": _("Hidden")},
        ),
        "bar": (_("Top bar and menu"), {"plain": _("Plain"), "brand": _("In the brand's colours")}),
        "sticky_header": (_("Fixed header"), {"on": _("Yes"), "off": _("No")}),
        "width": (_("Width"), {"full": _("Full"), "centered": _("Centred")}),
        "density": (_("Density"), {"normal": _("Normal"), "compact": _("Compact")}),
        "page_title": (_("Page title"), {"page": _("In the page"), "header": _("In the top bar")}),
        "list_width": (_("Width of lists"), {"page": _("As the page"), "wide": _("Whole width")}),
        "list_density": (_("Rows of lists"), {"normal": _("Normal"), "dense": _("Dense")}),
    }
    choices = request.app.state.settings.layout_choices
    options = [
        (field, title, [(value, labels[value]) for value in LAYOUTS[field]])
        for field, (title, labels) in groups.items()
        if field in choices and (field != "bar" or BAR_THEME)
    ]
    return render(
        request,
        "settings.html",
        options=options,
        choices=choices,
        theme_controls=[
            ("dropdown", _("Dropdown")),
            ("toggle", _("Toggle")),
            ("swap", _("Swap")),
            ("radio", _("Radio")),
        ],
        language_controls=[("dropdown", _("Dropdown")), ("select", _("Select")), ("menu", _("Menu list"))],
    )


async def _search(request: Request) -> HTMLResponse:
    """What the command palette can find, as ready-made options: the browser only filters them."""
    groups: dict[str, list[SearchItem]] = {}
    for item in search_items(request):
        groups.setdefault(item.group, []).append(item)
    return render(request, "ui/palette_results.html", groups=groups)


async def _health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_core(settings: Settings) -> FastAPI:
    application = FastAPI(title=settings.name, docs_url=None, redoc_url=None, openapi_url=None)
    application.state.settings = settings
    application.state.navigation = []
    application.state.search = []
    application.state.related = {}
    engine = create_database_engine(settings.database_url.get_secret_value())
    application.state.sessions = sessionmaker(engine, expire_on_commit=False)
    application.state.uploads = UploadStore(settings.upload_folder, settings.upload_max_bytes)
    application.state.languages = Languages(
        settings.languages, settings.default_language, allow_pseudo=settings.environment == "development"
    )
    application.state.languages.add_folder(ROOT / "locales")
    application.mount("/static/ui", StaticFiles(directory=UI / "static"), name="ui")
    application.mount("/static/brand", StaticFiles(directory=UI.parent / "brand"), name="brand")
    application.add_api_route("/preferences", _save_preferences, methods=["POST"], include_in_schema=False)
    application.add_api_route("/search", _search, include_in_schema=False)
    if settings.layout_choices:
        application.add_api_route("/settings", _settings_page, include_in_schema=False)
        register_search(application.state, _settings_item)
    application.add_api_route("/health", _health, include_in_schema=False)
    application.add_exception_handler(HTTPException, _on_http_error)
    application.add_exception_handler(RequestValidationError, _on_unreadable_form)
    application.add_exception_handler(StaleDataError, _on_stale_row)
    application.middleware("http")(_context)
    application.add_middleware(RequestLimit, limit=settings.request_max_bytes)
    return application


def install_home(application: FastAPI) -> None:
    """The start page of an application without the demo. Replace it with your own."""
    if any(getattr(route, "path", None) == "/" for route in application.routes):
        return

    async def home(request: Request) -> Response:
        return render(request, "home.html")

    application.add_api_route("/", home, include_in_schema=False)
