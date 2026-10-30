"""Languages: catalogues read straight from their .po files, so there is nothing to compile."""

import re
from collections.abc import Iterable
from contextvars import ContextVar
from io import BytesIO
from pathlib import Path

from babel import Locale, negotiate_locale
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po
from babel.support import NullTranslations, Translations

PSEUDO = "qps"
"""A made-up language for the checks: it marks and lengthens every translated text."""

_translations: ContextVar[NullTranslations] = ContextVar(
    "translations",
    default=NullTranslations(),  # noqa: B039  # never changed: each request sets its own
)
_language: ContextVar[str] = ContextVar("language", default="en")


def N_(message: str) -> str:
    """Marks a text for translation where it is defined; it is translated where it is shown."""
    return message


def _(message: str) -> str:
    return _translations.get().gettext(message)


def ngettext(singular: str, plural: str, number: int) -> str:
    return _translations.get().ngettext(singular, plural, number)


def pgettext(context: str, message: str) -> str:
    return str(_translations.get().pgettext(context, message))


def npgettext(context: str, singular: str, plural: str, number: int) -> str:
    return _translations.get().npgettext(context, singular, plural, number)


def current_language() -> str:
    return _language.get()


def _pseudo(text: str) -> str:
    return f"⟦{text}{'·' * (len(text) * 2 // 5)}⟧"


class PseudoTranslations(NullTranslations):
    """Used only by the checks: any text on a page without these marks was never translated."""

    def gettext(self, message: str) -> str:
        return _pseudo(message)

    def ngettext(self, msgid1: str, msgid2: str, n: int) -> str:
        return _pseudo(msgid1 if n == 1 else msgid2)

    def pgettext(self, context: str, message: str) -> str:
        return _pseudo(message)

    def npgettext(self, context: str, singular: str, plural: str, num: int) -> str:
        return _pseudo(singular if num == 1 else plural)


def _load(path: Path, language: str) -> Translations:
    with path.open("rb") as file:
        catalog = read_po(file, locale=language)
    compiled = BytesIO()
    write_mo(compiled, catalog)
    compiled.seek(0)
    return Translations(compiled)


def _accepted(header: str | None) -> list[str]:
    """The languages of an Accept-Language header, by preference: its order is not guaranteed (RFC 9110, 12.5.4)."""
    weighted = []
    for part in (header or "").split(","):
        tag, _separator, parameters = part.partition(";")
        tag = tag.strip().replace("-", "_")
        found = re.search(r"\bq=([01](?:\.\d{1,3})?)", parameters, re.I)
        weight = float(found[1]) if found else 1.0
        if tag and tag != "*" and weight > 0:
            weighted.append((weight, tag))
    return [tag for _weight, tag in sorted(weighted, key=lambda item: -item[0])]


class Languages:
    """The catalogues of the application: one per language, merged from every folder that adds texts."""

    def __init__(self, offered: Iterable[str], default: str, allow_pseudo: bool = False) -> None:
        self.offered = list(offered)
        self.default = default
        self.allow_pseudo = allow_pseudo
        self._catalogues: dict[str, NullTranslations] = {PSEUDO: PseudoTranslations()}
        self._folders: list[Path] = []

    def add_folder(self, folder: Path) -> None:
        self._folders.append(folder)
        self._catalogues = {PSEUDO: self._catalogues[PSEUDO]}

    def catalogue(self, language: str) -> NullTranslations:
        if language not in self._catalogues:
            # The first catalogue is the base: it carries the language's plural rule, which merging does not.
            merged: Translations | None = None
            for folder in self._folders:
                path = folder / language / "LC_MESSAGES" / "messages.po"
                if path.exists():
                    loaded = _load(path, language)
                    merged = loaded if merged is None else merged.merge(loaded)
            self._catalogues[language] = merged if merged is not None else NullTranslations()
        return self._catalogues[language]

    def choose(self, saved: str | None, accept_language: str | None) -> str:
        """The person's choice, then what their browser accepts, then the default."""
        if saved in self.offered or (self.allow_pseudo and saved == PSEUDO):
            return str(saved)
        return negotiate_locale(_accepted(accept_language), self.offered) or self.default

    def options(self) -> list[tuple[str, str]]:
        """Each language with its name in that language: a person looks for their own."""
        names = ((code, Locale.parse(code).get_display_name(code) or code) for code in self.offered)
        return [(code, name[:1].upper() + name[1:]) for code, name in names]

    def activate(self, language: str) -> None:
        _language.set(self.default if language == PSEUDO else language)
        _translations.set(self.catalogue(language))
