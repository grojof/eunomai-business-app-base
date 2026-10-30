import os
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TEXT_ATTRIBUTES = ("aria-label", "title", "placeholder", "alt", "data-announce")
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
NOT_OURS = {".git", ".venv", ".cache", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
ANIMATIONS_FINISHED = """Promise.race([
    Promise.allSettled(
        document.getAnimations()
            .filter((animation) => animation.effect.getComputedTiming().iterations !== Infinity)
            .map((animation) => animation.finished)
    ),
    new Promise((resolve) => setTimeout(resolve, 3000)),
]).then(() => null)"""
"""Text still fading in fails the contrast scan: what is measured must be what stays on the page. An animation on an
element that never renders never finishes, so the wait has an end."""
FOCUSABLE = (
    "a[href], summary, select:not([disabled]), textarea:not([disabled]), button:not([disabled]), "
    'input:not([disabled]):not([type="hidden"]):not([type="radio"]:not(:checked)), [tabindex]:not([tabindex="-1"])'
)


def without_official_examples(html: str) -> str:
    """Our frame only: daisyUI's examples are reference material, left as published."""
    return re.sub(r"<!--official-->.*?<!--/official-->", "", html, flags=re.S)


class _Texts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.texts: list[str] = []
        self._skipping = ""
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skipping:
            self._depth += tag == self._skipping
            return
        if tag in ("script", "style", "code", "kbd") or (tag != "html" and dict(attrs).get("lang")):
            self._skipping, self._depth = tag, 1
        self.texts += [value for name, value in attrs if name in TEXT_ATTRIBUTES and value]

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self._skipping:
            self.texts += [value for name, value in attrs if name in TEXT_ATTRIBUTES and value]

    def handle_endtag(self, tag: str) -> None:
        if tag == self._skipping:
            self._depth -= 1
            if not self._depth:
                self._skipping = ""

    def handle_data(self, data: str) -> None:
        if not self._skipping and data.strip():
            self.texts.append(data.strip())


def untranslated(html: str, allowed: tuple[str, ...]) -> list[str]:
    """Texts a person would see that did not go through translation: in the pseudo-language, all others are marked."""
    parser = _Texts()
    parser.feed(re.sub(r"⟦.*?⟧", "", without_official_examples(html), flags=re.S))  # marks may hold <code>
    found = []
    for rest in parser.texts:
        text = rest
        for word in allowed:
            rest = rest.replace(word, "")
        if re.search(r"[^\W\d_]", rest):
            found.append(text)
    return found


def run_axe(page: Any, exclude: tuple[str, ...] = ()) -> list[str]:
    """Runs the accessibility scan on the open page and returns each failure, with where it is."""
    page.evaluate(ANIMATIONS_FINISHED)
    page.add_script_tag(path=str(ROOT / "tests" / "vendor" / "axe.min.js"))
    context = {"exclude": [[selector] for selector in exclude]}
    result = page.evaluate(
        "([tags, context]) => axe.run(context, {runOnly: {type: 'tag', values: tags}})",
        [WCAG_TAGS, context],
    )
    return [f"{v['id']}: {node['target']}" for v in result["violations"] for node in v["nodes"]]


def focus_order(page: Any) -> tuple[list[str], list[str]]:
    """The visible controls in the order of the page, and the order the Tab key really visits them."""
    expected: list[str] = page.evaluate(
        """(selector) => [...document.querySelectorAll(selector)]
            .filter((element) => element.checkVisibility({visibilityProperty: true}))
            .map((element, position) => (element.dataset.order = String(position)))""",
        FOCUSABLE,
    )
    reached = []
    for _ in expected:
        page.keyboard.press("Tab")
        reached.append(str(page.evaluate("document.activeElement.dataset.order")))
    return expected, reached


def _link_or_copy(source: str, target: str) -> None:
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def repository_copy(target: Path) -> Path:
    """A copy to change freely. The stylesheet's executable is linked: it weighs 100 megabytes and is only read."""
    shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns(*NOT_OURS, ".env"))
    if (ROOT / ".cache").exists():
        shutil.copytree(ROOT / ".cache", target / ".cache", copy_function=_link_or_copy)
    return target


def run_in(folder: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Runs Python there, as a person would, with the marker that stops the copy from copying itself."""
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=folder,
        env=os.environ | {"BASE_WITHOUT_DEMO": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def repository_text_files() -> list[Path]:
    """Every file git tracks or would track; in a copy without git, every file that is ours."""
    if (ROOT / ".git").exists():
        listing = ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
        names = subprocess.run(listing, cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8")
        files = [ROOT / name for name in names.stdout.split("\0") if name]
    else:
        files = [path for path in ROOT.rglob("*") if not NOT_OURS & set(path.relative_to(ROOT).parts)]
    return [path for path in files if path.is_file() and b"\0" not in path.read_bytes()[:8000]]


def overflows_sideways(page: Any) -> bool:
    return bool(page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"))
