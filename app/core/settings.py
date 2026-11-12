"""Settings, read from the environment (APP_*) or a local .env file. See .env.example."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import make_url
from sqlalchemy.exc import ArgumentError

LAYOUTS: dict[str, tuple[str, ...]] = {
    "navigation": ("side", "compact", "top", "hidden"),
    "bar": ("plain", "brand"),
    "sticky_header": ("on", "off"),
    "width": ("full", "centered"),
    "density": ("normal", "compact"),
    "theme_control": ("dropdown", "toggle", "swap", "radio"),
    "language_control": ("dropdown", "select", "menu"),
    "page_title": ("page", "header"),
    "list_width": ("page", "wide"),
    "list_density": ("normal", "dense"),
}
"""What the settings menu offers, and the only values the server accepts. See docs/base/specification.md#layouts"""
SERVED = Path(__file__).resolve().parent.parent
"""The application's own folders, some of them served as they are: no upload ever goes here."""
ONE_MEGABYTE = 1024 * 1024


SIGNED_IN = "signed_in"
"""The role of everyone the proxy identified: a module open to them all asks for it."""


class Settings(BaseSettings):
    # Hiding the input keeps a password in database_url out of the message of any refused setting.
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore", hide_input_in_errors=True)

    environment: Literal["development", "production"] = "production"
    name: str = "Business App"

    # PostgreSQL is the real database. SQLite is for the demo and previews, and refuses to start in production.
    database_url: SecretStr = SecretStr("sqlite:///.data/app.db")

    # Uploads: where they are kept, the largest file, and the largest request of any kind. The folder is outside
    # anything served and, by default, under .data/, which git ignores. See docs/base/specification.md#uploads
    upload_folder: Path = Path(".data/uploads")
    upload_max_bytes: int = 10 * ONE_MEGABYTE
    request_max_bytes: int = 32 * ONE_MEGABYTE

    # Languages: the first one the person accepts wins; `default_language` is the last resort.
    default_language: str = "en"
    languages: list[str] = ["en", "es", "ca"]
    time_zone: str = "UTC"

    # How the application is arranged. See docs/base/specification.md#layouts
    layout_navigation: Literal["side", "compact", "top", "hidden"] = "side"
    # The top bar and the menu: as the page, or in the brand's colours (the theme called "bar" in app/brand/theme.css).
    layout_bar: Literal["plain", "brand"] = "plain"
    layout_sticky_header: bool = True
    layout_width: Literal["full", "centered"] = "full"
    layout_density: Literal["normal", "compact"] = "normal"
    layout_theme_control: Literal["dropdown", "toggle", "swap", "radio"] = "dropdown"
    layout_language_control: Literal["dropdown", "select", "menu"] = "dropdown"
    # Where the page's title goes: in the page, or in the top bar for more room. Top navigation keeps it in the page.
    layout_page_title: Literal["page", "header"] = "page"
    # How a list is shown: within the page's width or across all of it, and with normal or dense rows.
    layout_list_width: Literal["page", "wide"] = "page"
    layout_list_density: Literal["normal", "dense"] = "normal"
    # What each person may change in the settings menu. What is left out stays as set above; empty hides the menu.
    layout_choices: list[str] = list(LAYOUTS)

    # Identity: who is allowed to send these headers, and what they are called. Uvicorn must run with
    # --no-proxy-headers: otherwise X-Forwarded-For replaces the proxy's address, and nobody is believed.
    trusted_proxies: list[str] = ["127.0.0.1", "::1"]
    header_username: str = "X-Remote-User"
    header_name: str = "X-Remote-Name"
    header_email: str = "X-Remote-Email"
    header_groups: str = "X-Remote-Groups"
    groups_separator: str = "|"
    role_groups: dict[str, list[str]] = {}
    """Each role and the groups that give it. `*` in a group stands for any text: {"manager": ["departamento-*"]}.
    Everyone the proxy identified also has `signed_in`, which no group gives."""

    # Local work only: a person without a proxy. Refuses to start outside development.
    fake_identity: bool = False
    fake_groups: list[str] = []

    @model_validator(mode="after")
    def check(self) -> Self:
        if self.fake_identity and self.environment != "development":
            raise ValueError("fake_identity works only in development")
        if self.default_language not in self.languages:
            raise ValueError("default_language must be one of languages")
        unknown = set(self.layout_choices) - set(LAYOUTS)
        if unknown:
            raise ValueError(f"layout_choices has unknown names: {sorted(unknown)}")
        if self.upload_folder.resolve().is_relative_to(SERVED):
            raise ValueError("upload_folder must be outside app/, where nothing a person sends can be served or run")
        if SIGNED_IN in self.role_groups:
            raise ValueError(f"role_groups cannot give {SIGNED_IN}: everyone the proxy identified has it")
        if any(not name.strip("*") for granted_by in self.role_groups.values() for name in granted_by):
            raise ValueError("role_groups: a group cannot be only *, which any group matches; use signed_in")
        if self.request_max_bytes < self.upload_max_bytes:
            raise ValueError("request_max_bytes must leave room for a whole file of upload_max_bytes")
        self._check_database()
        return self

    def _check_database(self) -> None:
        try:
            backend = make_url(self.database_url.get_secret_value()).get_backend_name()
        except ArgumentError:
            raise ValueError("database_url is not a database address") from None
        if backend not in ("postgresql", "sqlite"):
            raise ValueError("database_url must be PostgreSQL or SQLite")
        if backend != "postgresql" and self.environment != "development":
            raise ValueError(
                "SQLite never runs in production: set APP_DATABASE_URL to PostgreSQL. "
                "To try the application, copy .env.example to .env, which sets APP_ENVIRONMENT=development"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
