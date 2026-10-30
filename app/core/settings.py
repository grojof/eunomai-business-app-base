"""Settings, read from the environment (APP_*) or a local .env file. See .env.example."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    environment: Literal["development", "production"] = "production"
    name: str = "Business App"

    # Languages: the first one the person accepts wins; `default_language` is the last resort.
    default_language: str = "en"
    languages: list[str] = ["en", "es", "ca"]
    time_zone: str = "Europe/Madrid"

    # How the application is arranged. See docs/specification.md#layouts
    layout_navigation: Literal["side", "compact", "top", "hidden"] = "side"
    layout_sticky_header: bool = True
    layout_width: Literal["full", "centered"] = "full"
    layout_density: Literal["normal", "compact"] = "normal"

    # Identity: who is allowed to send these headers, and what they are called.
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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
