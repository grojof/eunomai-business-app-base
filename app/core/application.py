"""The application's core: request context, safety headers, preferences, errors and health."""

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.core import identity
from app.core.i18n import Languages, _
from app.core.settings import Settings
from app.core.templating import LAYOUTS, UI, render

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent.parent
THEMES = ("system", "light", "dark")
PUBLIC_PREFIXES = ("/static/", "/health")
ONE_YEAR = 60 * 60 * 24 * 365

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
    return origin is not None and urlsplit(origin).netloc != request.headers.get("host")


async def _context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    state = request.app.state
    language = state.languages.choose(request.cookies.get("language"), request.headers.get("accept-language"))
    state.languages.activate(language)
    theme = request.cookies.get("theme")
    request.state.theme = theme if theme in THEMES else "system"

    if request.url.path.startswith(PUBLIC_PREFIXES):
        response = await call_next(request)
    else:
        client = request.client.host if request.client else None
        person = identity.from_request(request.headers, client, state.settings)
        request.state.person = person
        if person is None:
            response = _error_page(request, 401)
        elif _cross_site(request):
            response = _error_page(request, 403)
        else:
            try:
                response = await call_next(request)
            except Exception:  # here, so the error page keeps its language and the headers below
                logger.exception("Unhandled error on %s", request.url.path)
                response = _error_page(request, 500)

    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


def _error_page(request: Request, status: int) -> Response:
    titles = {
        401: (_("Sign-in required"), _("We could not tell who you are. Open the application from your portal.")),
        403: (_("You do not have permission"), _("Ask whoever manages this application if you need access.")),
        404: (_("Page not found"), _("Check the address, or go back to the start.")),
        500: (_("Something went wrong"), _("It is not your fault. Try again in a moment.")),
    }
    title, advice = titles.get(status, titles[500])
    return render(request, "error.html", status_code=status, title=title, advice=advice, status=status)


async def _on_http_error(request: Request, error: Exception) -> Response:
    assert isinstance(error, HTTPException)  # noqa: S101  # FastAPI only sends these here
    return _error_page(request, error.status_code)


def _safe_path(next_path: str) -> str:
    """Goes back to where the person was, and never to another site."""
    return next_path if next_path.startswith("/") and not next_path.startswith(("//", "/\\")) else "/"


async def _save_preferences(
    request: Request,
    language: Annotated[str, Form()] = "",
    theme: Annotated[str, Form()] = "",
    next_path: Annotated[str, Form(alias="next")] = "/",
    layout_navigation: Annotated[str, Form()] = "",
    layout_sticky_header: Annotated[str, Form()] = "",
    layout_width: Annotated[str, Form()] = "",
    layout_density: Annotated[str, Form()] = "",
) -> Response:
    response = RedirectResponse(_safe_path(next_path), status_code=303)
    secure = request.app.state.settings.environment == "production"
    options = {"max_age": ONE_YEAR, "httponly": True, "samesite": "lax", "secure": secure}
    if language in request.app.state.languages.offered:
        response.set_cookie("language", language, **options)
    if theme in THEMES:
        response.set_cookie("theme", theme, **options)
    if request.app.state.layout_preview:
        chosen = {
            "navigation": layout_navigation,
            "sticky_header": layout_sticky_header,
            "width": layout_width,
            "density": layout_density,
        }
        for field, value in chosen.items():
            if value in LAYOUTS[field]:
                response.set_cookie(f"layout_{field}", value, **options)
    return response


async def _health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_core(settings: Settings) -> FastAPI:
    application = FastAPI(title=settings.name, docs_url=None, redoc_url=None, openapi_url=None)
    application.state.settings = settings
    application.state.navigation = []
    application.state.layout_preview = False
    application.state.languages = Languages(
        settings.languages, settings.default_language, allow_pseudo=settings.environment == "development"
    )
    application.state.languages.add_folder(ROOT / "locales")
    application.mount("/static/ui", StaticFiles(directory=UI / "static"), name="ui")
    application.mount("/static/brand", StaticFiles(directory=UI.parent / "brand"), name="brand")
    application.add_api_route("/preferences", _save_preferences, methods=["POST"], include_in_schema=False)
    application.add_api_route("/health", _health, include_in_schema=False)
    application.add_exception_handler(HTTPException, _on_http_error)
    application.middleware("http")(_context)
    return application


def install_home(application: FastAPI) -> None:
    """The start page of an application without the demo. Replace it with your own."""
    if any(getattr(route, "path", None) == "/" for route in application.routes):
        return

    async def home(request: Request) -> Response:
        return render(request, "home.html")

    application.add_api_route("/", home, include_in_schema=False)
