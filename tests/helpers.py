import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TEXT_ATTRIBUTES = ("aria-label", "title", "placeholder", "alt", "data-announce")
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]


class _Texts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.texts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style") or (tag == "option" and dict(attrs).get("lang")):
            self._skip += 1
        self.texts += [value for name, value in attrs if name in TEXT_ATTRIBUTES and value]

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") or (tag == "option" and self._skip):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.texts.append(data.strip())


def untranslated(html: str, allowed: tuple[str, ...]) -> list[str]:
    """Texts a person would see that did not go through translation: in the pseudo-language, all others are marked."""
    parser = _Texts()
    parser.feed(html)
    found = []
    for text in parser.texts:
        rest = re.sub(r"⟦.*?⟧", "", text, flags=re.S)
        for word in allowed:
            rest = rest.replace(word, "")
        if re.search(r"[^\W\d_]", rest):
            found.append(text)
    return found


def run_axe(page: Any) -> list[str]:
    """Runs the accessibility scan on the open page and returns each failure, with where it is."""
    page.add_script_tag(path=str(ROOT / "tests" / "vendor" / "axe.min.js"))
    result = page.evaluate(
        "tags => axe.run(document, {runOnly: {type: 'tag', values: tags}})",
        WCAG_TAGS,
    )
    return [f"{v['id']}: {node['target']}" for v in result["violations"] for node in v["nodes"]]


def overflows_sideways(page: Any) -> bool:
    return bool(page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"))
