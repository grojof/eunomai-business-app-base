import http.client
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import tomllib
import unicodedata
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from babel.dates import get_day_names, get_month_names

ROOT = Path(__file__).resolve().parent.parent
TEXT_ATTRIBUTES = ("aria-label", "title", "placeholder", "alt", "data-announce")
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
NOT_OURS = {".git", ".venv", ".cache", ".data", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
ANIMATIONS_FINISHED = """Promise.race([
    Promise.allSettled(
        document.getAnimations()
            .filter((animation) => animation.timeline === document.timeline)
            .filter((animation) => animation.effect.getComputedTiming().iterations !== Infinity)
            .filter((animation) => animation.effect.target.checkVisibility())
            .map((animation) => animation.finished)
    ),
    new Promise((resolve) => setTimeout(resolve, 3000)),
]).then(() => null)"""
"""Text still fading in fails the contrast scan: what is measured must be what stays on the page. An animation on an
element that never renders may never finish, and one driven by scrolling has no end: neither changes what is measured,
so neither is waited for. The wait keeps a limit anyway."""
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


def _date_words() -> re.Pattern[str]:
    words: set[str] = set()
    for language in ("en", "es", "ca"):
        for width in ("wide", "abbreviated"):
            for context in ("format", "stand-alone"):
                words.update(get_month_names(width, context, language).values())
                words.update(get_day_names(width, context, language).values())
    return re.compile(r"(?<!\w)(?:" + "|".join(sorted(map(re.escape, words), key=len, reverse=True)) + r")(?!\w)", re.I)


DATE_WORDS = _date_words()
"""The months and days the formatters write, in each language the base brings: a date is formatted, not translated,
so the pseudo-language does not mark it."""


def untranslated(html: str, allowed: tuple[str, ...]) -> list[str]:
    """Texts a person would see that did not go through translation: in the pseudo-language, all others are marked.
    A text made only of the names of months and days is a formatted date."""
    parser = _Texts()
    html = without_official_examples(html)
    while "⟦" in html:  # innermost first, because a translated text can hold another. Marks may hold <code>
        html, removed = re.subn(r"⟦[^⟦⟧]*⟧", "", html, flags=re.S)
        if not removed:
            break
    parser.feed(html)
    found = []
    for rest in parser.texts:
        text = rest
        for word in allowed:
            rest = rest.replace(word, "")
        rest = DATE_WORDS.sub("", rest)
        if re.search(r"[^\W\d_]", rest):
            found.append(text)
    return found


def run_axe(page: Any, exclude: tuple[str, ...] = ()) -> list[str]:
    """Runs the accessibility scan on the open page and returns each failure, with where it is."""
    page.evaluate(ANIMATIONS_FINISHED)
    if not page.evaluate("typeof axe !== 'undefined'"):
        page.add_script_tag(path=str(ROOT / "tests" / "vendor" / "axe.min.js"))
    context = {"exclude": [[selector] for selector in exclude]}
    result = page.evaluate(
        "([tags, context]) => axe.run(context, {runOnly: {type: 'tag', values: tags}})",
        [WCAG_TAGS, context],
    )
    return [f"{v['id']}: {node['target']}" for v in result["violations"] for node in v["nodes"]]


TO_DARK = """() => {
    const still = document.createElement("style");
    still.textContent = "*, *::before, *::after { transition: none !important; }";
    document.head.append(still);
    document.querySelectorAll("input.theme-controller").forEach((input) => { input.checked = input.value === "dark"; });
    document.documentElement.dataset.theme = "dark";
}"""
"""The dark theme on the open page, as the theme control puts it with no reload; charts follow it. The colours change
at once and stay still: eased in, those of content not on screen, such as a closed menu's, would start easing only when
shown, and the scan measures the page at rest. The base's own tests prove, on its richest pages, that the page then
paints wherever the scan looks as the page loaded dark."""


def run_axe_in_both_themes(page: Any, exclude: tuple[str, ...] = ()) -> list[str]:
    """The scan on a page opened in the light theme, then again in the dark one: one load instead of two."""
    assert page.evaluate("document.documentElement.dataset.theme") == "light"
    light = run_axe(page, exclude)
    page.evaluate(TO_DARK)
    return [f"light {failure}" for failure in light] + [f"dark {failure}" for failure in run_axe(page, exclude)]


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
    """Runs Python there, as a person would, with nothing set that a person would not set."""
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=folder,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",  # a child's traceback can be in the system's encoding, and it must still be read
    )


def preview_section(folder: Path) -> dict[str, Any]:
    section: dict[str, Any] = tomllib.loads((folder / ".eunomai" / "project.toml").read_text(encoding="utf-8"))[
        "preview"
    ]
    return section


@contextmanager
def preview_running(folder: Path, data: Path | None = None) -> Iterator[int]:
    """Exactly what `[preview]` says, in a folder with no `.env`, and only the system's variables besides its own.
    `data` is the folder a connector keeps between versions, outside the copy, as `{data}`."""
    section = preview_section(folder)
    kept = data or folder.parent / "kept"
    kept.mkdir(exist_ok=True)

    def filled(word: str) -> str:
        return word.replace("{data}", kept.resolve().as_posix())

    tools = str(Path(sys.executable).parent)
    system = {name: os.environ[name] for name in ("SYSTEMROOT", "TEMP", "TMP", "HOME", "PATH") if name in os.environ}
    environment = system | {name: filled(value) for name, value in section["environment"].items()}

    def command(words: list[str]) -> list[str]:
        words = [filled(word) for word in words]
        return [shutil.which(words[0], path=tools) or words[0], *words[1:]]

    for step in section["setup"]:
        done = subprocess.run(
            command(step), cwd=folder, env=environment, capture_output=True, text=True, errors="replace"
        )
        assert done.returncode == 0, f"{step}: {done.stdout[-1000:]} {done.stderr[-1000:]}"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    words = command([word.replace("{port}", str(port)) for word in section["run"]])
    server = subprocess.Popen(words, cwd=folder, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(600):
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    break
            assert server.poll() is None, "the application ended before it answered"
            time.sleep(0.05)
        yield port
    finally:
        server.terminate()
        server.wait(timeout=10)


def fetch(port: int, path: str) -> tuple[int, str]:
    """What a person's browser gets, with no headers of anyone's."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    connection.request("GET", path)
    response = connection.getresponse()
    text = response.read().decode("utf-8")
    connection.close()
    return response.status, text


def _is_ours(name: str) -> bool:
    return name not in NOT_OURS and (name == ".env.example" or not re.fullmatch(r"\.env(\..*)?", name))


def repository_text_files() -> list[Path]:
    """Every text file that is ours, from the folder itself: a copy has no git, and a sandbox's may not work there."""
    files: list[Path] = []
    for folder, folders, names in ROOT.walk():
        folders[:] = [name for name in folders if name not in NOT_OURS]
        files += [folder / name for name in names if _is_ours(name)]
    return [path for path in files if b"\0" not in path.read_bytes()[:8000]]


def overflows_sideways(page: Any) -> bool:
    return bool(page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"))


def plain(text: object) -> str:
    """Without accents or capitals: as a search compares."""
    letters = unicodedata.normalize("NFKD", str(text))
    return "".join(letter for letter in letters if not unicodedata.combining(letter)).casefold()


def shows_only(page: str, inside: Iterable[str], outside: Iterable[str]) -> None:
    """A page of results shows a row that belongs and none that does not. `inside` and `outside` are the names of the
    rows as the page writes them, whatever the rows are. A name both have, or one written inside another, proves
    nothing and is left out."""
    kept = set(inside)
    assert any(name in page for name in kept), "none of the rows that belong is shown"
    for name in set(outside) - kept:
        if not any(name in other for other in kept):
            assert name not in page, f"{name} does not belong and is shown"
