"""Who is asking: a trusted proxy says so in headers. The application has no login of its own."""

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request
from starlette.datastructures import Headers

from app.core.settings import Settings


@dataclass(frozen=True)
class Person:
    username: str
    name: str
    email: str
    groups: frozenset[str]
    roles: frozenset[str]


def _text(value: str) -> str:
    """HTTP headers are read as Latin-1, but proxies send names in UTF-8: without this, accents break."""
    try:
        return value.encode("latin-1").decode("utf-8").strip()
    except UnicodeError:
        return value.strip()


def _roles(groups: frozenset[str], settings: Settings) -> frozenset[str]:
    return frozenset(role for role, granted_by in settings.role_groups.items() if groups & set(granted_by))


def from_request(headers: Headers, client_host: str | None, settings: Settings) -> Person | None:
    if settings.fake_identity:
        groups = frozenset(settings.fake_groups)
        return Person("demo.user", "Demo User", "demo.user@example.org", groups, _roles(groups, settings))
    if client_host not in settings.trusted_proxies:
        return None
    names = (settings.header_username, settings.header_name, settings.header_email, settings.header_groups)
    if any(len(headers.getlist(name)) > 1 for name in names):
        return None  # a proxy sends each once: a repeated one may be a visitor's, passed through
    username = _text(headers.get(settings.header_username, ""))
    if not username:
        return None
    raw_groups = _text(headers.get(settings.header_groups, ""))
    groups = frozenset(g.strip() for g in raw_groups.split(settings.groups_separator) if g.strip())
    return Person(
        username=username,
        name=_text(headers.get(settings.header_name, "")) or username,
        email=_text(headers.get(settings.header_email, "")),
        groups=groups,
        roles=_roles(groups, settings),
    )


def require_role(role: str) -> Callable[[Request], Person]:
    """A route dependency: the check happens here, on the server, whatever the page shows."""

    def check(request: Request) -> Person:
        person: Person = request.state.person
        if role not in person.roles:
            raise HTTPException(status_code=403)
        return person

    return check
