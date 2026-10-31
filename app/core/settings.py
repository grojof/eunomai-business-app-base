"""Settings, read from the environment (APP_*) or a local .env file. See .env.example."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import make_url
from sqlalchemy.exc import ArgumentError

LAYOUTS: dict[str, tuple[str, ...]] = {
    "navigation": ("side", "compact", "top", "hidden"),
    "sticky_header": ("on", "off"),
    "width": ("full", "centered"),
    "density": ("normal", "compact"),
    "theme_control": ("dropdown", "toggle", "swap", "radio"),
    "language_control": ("dropdown", "select", "menu"),
}
"""What the settings menu offers, and the only values the server accepts. See docs/specification.md#layouts"""


class Settings(BaseSettings):
    # Hiding the input keeps a password in database_url out of the message of any refused setting.
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore", hide_input_in_errors=True)

    environment: Literal["development", "production"] = "production"
    name: str = "Business App"

    # PostgreSQL is the real database. SQLite is for the demo and previews, and refuses to start in production.
    database_url: SecretStr = SecretStr("sqlite:///.data/app.db")

    # Languages: the first one the person accepts wins; `default_language` is the last resort.
    default_language: str = "en"
    languages: list[str] = ["en", "es", "ca"]
    time_zone: str = "UTC"

    # How the application is arranged. See docs/specification.md#layouts
    layout_navigation: Literal["side", "compact", "top", "hidden"] = "side"
    layout_sticky_header: bool = True
    layout_width: Literal["full", "centered"] = "full"
    layout_density: Literal["normal", "compact"] = "normal"
    layout_theme_control: Literal["dropdown", "toggle", "swap", "radio"] = "dropdown"
    layout_language_control: Literal["dropdown", "select", "menu"] = "dropdown"
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
