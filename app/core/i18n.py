"""Languages: catalogues read straight from their .po files, so there is nothing to compile."""

import gettext as stdlib_gettext
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


def _load(path: Path, language: str) -> stdlib_gettext.GNUTranslations:
    with path.open("rb") as file:
        catalog = read_po(file, locale=language)
    compiled = BytesIO()
    write_mo(compiled, catalog)
    compiled.seek(0)
    return Translations(compiled)


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
            merged = Translations()
            for folder in self._folders:
                path = folder / language / "LC_MESSAGES" / "messages.po"
                if path.exists():
                    merged.merge(_load(path, language))  # type: ignore[arg-type]
            self._catalogues[language] = merged
        return self._catalogues[language]

    def choose(self, saved: str | None, accept_language: str | None) -> str:
        """The person's choice, then what their browser accepts, then the default."""
        if saved in self.offered or (self.allow_pseudo and saved == PSEUDO):
            return str(saved)
        accepted = [part.split(";")[0].strip().replace("-", "_") for part in (accept_language or "").split(",")]
        return negotiate_locale([a for a in accepted if a and a != "*"], self.offered) or self.default

    def options(self) -> list[tuple[str, str]]:
        """Each language with its name in that language: a person looks for their own."""
        return [(code, (Locale.parse(code).get_display_name(code) or code).capitalize()) for code in self.offered]

    def activate(self, language: str) -> None:
        _language.set(self.default if language == PSEUDO else language)
        _translations.set(self.catalogue(language))
