"""Translation catalogues: the texts in the code, compared with what each language has.

uv run python tools/translations.py update   add new texts to every catalogue, and mark the removed ones
uv run python tools/translations.py check    report anything missing, unfinished or inconsistent
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from babel.messages.catalog import Catalog, Message
from babel.messages.extract import DEFAULT_KEYWORDS, extract_from_dir
from babel.messages.pofile import read_po, write_po

ROOT = Path(__file__).resolve().parent.parent
KEYWORDS = {**DEFAULT_KEYWORDS, "N_": None}
PYTHON = "python"
TEMPLATES = "jinja2.ext:babel_extract"
PLACEHOLDER = re.compile(r"%\((\w+)\)[sd]")


@dataclass(frozen=True)
class Domain:
    """Texts found in `sources`, kept in `catalogues`. The demo's go with it when it is deleted."""

    catalogues: Path
    sources: tuple[tuple[Path, str, str], ...]


DOMAINS = [
    Domain(
        ROOT / "locales",
        ((ROOT / "app" / "core", "**.py", PYTHON), (ROOT / "app" / "ui" / "templates", "**.html", TEMPLATES)),
    ),
    Domain(
        ROOT / "app" / "demo" / "locales",
        ((ROOT / "app" / "demo", "**.py", PYTHON), (ROOT / "app" / "demo" / "templates", "**.html", TEMPLATES)),
    ),
]
REQUIRED = ["es", "ca"]


def extract(domain: Domain) -> Catalog:
    template = Catalog(project="business-app-base")
    for folder, pattern, method in domain.sources:
        for filename, lineno, message, comments, context in extract_from_dir(
            folder, method_map=[(pattern, method)], keywords=KEYWORDS, strip_comment_tags=True
        ):
            template.add(message, None, [(filename, lineno)], auto_comments=comments, context=context)
    return template


def path_of(domain: Domain, language: str) -> Path:
    return domain.catalogues / language / "LC_MESSAGES" / "messages.po"


def read(path: Path, language: str) -> Catalog:
    if not path.exists():
        return Catalog(locale=language, project="business-app-base")
    with path.open("rb") as file:
        return read_po(file, locale=language)


def update() -> None:
    for domain in DOMAINS:
        if not domain.catalogues.parent.exists():
            continue
        template = extract(domain)
        for language in REQUIRED:
            path = path_of(domain, language)
            catalog = read(path, language)
            catalog.update(template, no_fuzzy_matching=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as file:
                write_po(file, catalog, omit_header=False, sort_output=True, no_location=True, ignore_obsolete=True)


def _texts(message: object) -> list[str]:
    return [t for t in (message if isinstance(message, tuple | list) else (message,)) if isinstance(t, str)]


def _key(message: Message) -> tuple[str | None, str]:
    return (message.context, _texts(message.id)[0])


def check() -> list[str]:
    problems = []
    for domain in DOMAINS:
        if not domain.catalogues.parent.exists():
            continue
        expected = {_key(m) for m in extract(domain) if m.id}
        for language in REQUIRED:
            path = path_of(domain, language)
            catalog = read(path, language)
            present = {_key(m): m for m in catalog if m.id}
            where = f"{path.relative_to(ROOT).as_posix()}:"
            problems += [f"{where} not in the catalogue: {key!r}" for key in expected if key not in present]
            problems += [f"{where} no longer in the code: {key!r}" for key in present if key not in expected]
            for key, message in present.items():
                if "fuzzy" in message.flags:
                    problems.append(f"{where} not accepted by a person yet: {key!r}")
                translations = _texts(message.string)
                if not translations or not all(translations):
                    problems.append(f"{where} not translated: {key!r}")
                    continue
                source = {tuple(sorted(PLACEHOLDER.findall(text))) for text in _texts(message.id)}
                for text in translations:
                    if tuple(sorted(PLACEHOLDER.findall(text))) not in source:
                        problems.append(f"{where} placeholders differ: {key!r}")
    return problems


def main() -> int:
    if sys.argv[1:] == ["update"]:
        update()
        return 0
    if sys.argv[1:] == ["check"]:
        problems = check()
        print("\n".join(problems) or "translations complete")
        return 1 if problems else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
