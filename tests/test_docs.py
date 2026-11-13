"""The documentation: every relative link leads somewhere, and an application's own pages are a map the README reaches.

The base's documentation lives in `docs/base/`, which every application keeps as it is: how the base works, read to
build. An application's own pages are the other files under `docs/`, in folders of their own when a kind of page grows,
each with its frontmatter, each reached from the README, directly or through the index page of its folder. See
docs/base/specification.md#documentation
"""

import re
import unicodedata
from pathlib import Path

import pytest

from tests.helpers import ROOT

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^(```|~~~).*?^\1", re.M | re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.M)
NAMED = re.compile(r'<a\s+(?:id|name)="([^"]+)"\s*>\s*</a>')
"""An anchor that stays when the heading after it is translated: `<a id="run-it"></a>`."""
TYPES = {"tutorial", "how-to", "reference", "explanation", "decision"}
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
TAGS = re.compile(r"\[\s*(?:[a-z0-9]+(?:-[a-z0-9]+)*(?:\s*,\s*[a-z0-9]+(?:-[a-z0-9]+)*)*)?\s*\]")
"""A page's `tags`: a list of lowercase words joined by hyphens, such as [context, order-intake], so they can be
gathered across applications."""


def pages(root: Path) -> list[Path]:
    found = [root / "README.md", root / "AGENTS.md", *sorted((root / "docs").rglob("*.md"))]
    return [page for page in found if page.is_file()]


def prose(text: str) -> str:
    """The text a reader sees as text: code blocks and inline code hold examples, not links."""
    return INLINE_CODE.sub("", FENCE.sub("", text))


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation gone, spaces as hyphens."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)  # a link in a heading keeps its words
    text = re.sub(r"[`*_]", "", text).strip().lower()
    kept = "".join(char for char in text if char in " -" or unicodedata.category(char)[0] in "LN")
    return kept.replace(" ", "-")


def anchors(page: Path) -> set[str]:
    text = FENCE.sub("", page.read_text(encoding="utf-8"))
    found: set[str] = set(NAMED.findall(INLINE_CODE.sub("", text)))
    for heading in HEADING.findall(text):
        base, number = slug(heading), 0
        while (candidate := base if number == 0 else f"{base}-{number}") in found:
            number += 1
        found.add(candidate)
    return found


def broken_links(root: Path) -> list[str]:
    problems = []
    for page in pages(root):
        for link in LINK.findall(prose(page.read_text(encoding="utf-8"))):
            if re.match(r"^[a-z][a-z0-9+.-]*:", link) or link.startswith("/"):
                continue  # another site, or a path the application serves
            path, _, anchor = link.partition("#")
            target = (page.parent / path).resolve() if path else page
            where = f"{page.relative_to(root).as_posix()}: {link}"
            if not target.exists():
                problems.append(f"{where} (no such file)")
            elif anchor and target.suffix == ".md" and anchor not in anchors(target):
                problems.append(f"{where} (no such heading)")
    return problems


def own_pages(root: Path) -> list[Path]:
    """The application's own pages: everything under docs/ that is not the base's."""
    docs = root / "docs"
    return [page for page in sorted(docs.rglob("*.md")) if not page.is_relative_to(docs / "base")]


def reached(root: Path) -> set[Path]:
    """The application's own pages a reader gets to from the README, following links through its own pages: a folder's
    index page, linked from the README, reaches the pages of that folder."""
    own = {page.resolve() for page in own_pages(root)}
    found: set[Path] = set()
    waiting = [root / "README.md"]
    while waiting:
        page = waiting.pop()
        for link in LINK.findall(prose(page.read_text(encoding="utf-8"))):
            target = (page.parent / link.partition("#")[0]).resolve()
            if target in own and target not in found:
                found.add(target)
                waiting.append(target)
    return found


def own_page_problems(root: Path) -> list[str]:
    linked = reached(root)
    problems = []
    for page in own_pages(root):
        name = page.relative_to(root).as_posix()
        front = FRONTMATTER.match(page.read_text(encoding="utf-8").replace("\r\n", "\n"))
        fields = dict(re.findall(r"^(\w+):\s*(.+?)\s*$", front.group(1), re.M)) if front else {}
        if fields.get("type") not in TYPES:
            problems.append(f"{name}: frontmatter needs a type, one of {', '.join(sorted(TYPES))}")
        missing = [field for field in ("title", "description") if not fields.get(field)]
        problems += [f"{name}: frontmatter needs a {field}" for field in missing]
        if "tags" in fields and not TAGS.fullmatch(fields["tags"]):
            problems.append(f"{name}: tags must be a list of lowercase words joined by hyphens, such as [context]")
        if page.resolve() not in linked:
            problems.append(f"{name}: README.md does not reach it, directly or through the index of its folder")
    return problems


def test_every_relative_link_leads_to_a_file_and_a_heading():
    assert broken_links(ROOT) == []


def test_every_page_of_the_applications_own_is_in_the_readme_with_its_frontmatter():
    """In the base there are none: everything under docs/ is the base's. An application's are checked here."""
    assert own_page_problems(ROOT) == []


def test_the_bases_documentation_is_in_one_folder():
    """Beside `docs/base/`, only the application's own pages, or folders that hold them."""
    docs = ROOT / "docs"
    assert {path.name for path in docs.iterdir()} <= {"base", *(page.relative_to(docs).parts[0] for page in own_pages(ROOT))}
    assert (docs / "base" / "specification.md").is_file() and (docs / "base" / "standards.md").is_file()


@pytest.fixture
def application(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "base").mkdir(parents=True)
    (tmp_path / "docs" / "base" / "specification.md").write_text("# Specification\n\n## Data\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")
    return tmp_path


def page(title: str, kind: str = "reference") -> str:
    return f"---\ntype: {kind}\ntitle: {title}\ndescription: What {title} says.\n---\n\n# {title}\n"


def test_a_page_with_its_frontmatter_linked_from_the_readme_passes(application):
    (application / "docs" / "screens.md").write_text(page("Screens", "how-to"), encoding="utf-8")
    (application / "README.md").write_text("# App\n\n[Screens](docs/screens.md)\n", encoding="utf-8")
    assert own_page_problems(application) == [] and broken_links(application) == []


def test_a_page_the_readme_does_not_reach_or_without_frontmatter_is_named(application):
    (application / "docs" / "data.md").write_text("# Data\n", encoding="utf-8")
    (application / "docs" / "roles.md").write_text(page("Roles", "guide"), encoding="utf-8")
    (application / "README.md").write_text("# App\n\n[Roles](docs/roles.md)\n", encoding="utf-8")
    problems = own_page_problems(application)
    assert "docs/data.md: README.md does not reach it, directly or through the index of its folder" in problems
    assert any(problem.startswith("docs/data.md: frontmatter needs a type") for problem in problems)
    assert any(problem.startswith("docs/roles.md: frontmatter needs a type") for problem in problems)
    assert not any(problem.startswith("docs/roles.md: README") for problem in problems)


def test_a_link_to_a_missing_file_or_heading_is_named_and_code_is_not_a_link(application):
    (application / "README.md").write_text(
        "# App\n\n[Gone](docs/gone.md) [Data](docs/base/specification.md#data) "
        "[Nowhere](docs/base/specification.md#nowhere) `[not](a-link.md)`\n\n```\n[nor](this.md)\n```\n",
        encoding="utf-8",
    )
    assert broken_links(application) == [
        "README.md: docs/gone.md (no such file)",
        "README.md: docs/base/specification.md#nowhere (no such heading)",
    ]


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("Lists on the server", "lists-on-the-server"),
        ("An organization's template", "an-organizations-template"),
        ("`[preview]` and its data", "preview-and-its-data"),
        ("Where the two databases differ", "where-the-two-databases-differ"),
    ],
)
def test_anchors_follow_githubs_rules(heading, expected):
    assert slug(heading) == expected


def test_a_named_anchor_stays_when_its_heading_is_translated(application):
    """A link from AGENTS.md to a README section must not tie the heading to English: a team writes it in its own."""
    (application / "README.md").write_text('# App\n\n<a id="run-it"></a>\n\n## Pruébala\n', encoding="utf-8")
    (application / "AGENTS.md").write_text("[Run it](README.md#run-it) [Gone](README.md#try-it)\n", encoding="utf-8")
    assert broken_links(application) == ["AGENTS.md: README.md#try-it (no such heading)"]


def test_agents_reaches_the_readmes_run_section_by_a_named_anchor():
    assert "README.md#run-it" in (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "run-it" in anchors(ROOT / "README.md")


def test_a_kind_that_grew_is_a_folder_reached_through_its_index(application):
    """A large application splits its decisions by subject: the page becomes the index of a folder of its name, so
    nothing is deleted, and the README keeps linking it."""
    folder = application / "docs" / "decisions"
    folder.mkdir()
    (application / "docs" / "decisions.md").write_text(page("Decisions") + "\n[Closing](decisions/closing.md)\n",
                                                       encoding="utf-8")
    (folder / "closing.md").write_text(page("Closing", "decision"), encoding="utf-8")
    (folder / "orphan.md").write_text(page("Orphan", "decision"), encoding="utf-8")
    (application / "README.md").write_text("# App\n\n[Decisions](docs/decisions.md)\n", encoding="utf-8")
    assert own_page_problems(application) == [
        "docs/decisions/orphan.md: README.md does not reach it, directly or through the index of its folder"]


@pytest.mark.parametrize(("tags", "right"), [("[context]", True), ("[decision, order-intake]", True), ("[]", True),
                                             ("[Context]", False), ("context", False), ("[order intake]", False)])
def test_tags_are_lowercase_words_joined_by_hyphens(application, tags, right):
    text = page("Context", "explanation").replace("description:", f"tags: {tags}\ndescription:")
    (application / "docs" / "context.md").write_text(text, encoding="utf-8")
    (application / "README.md").write_text("# App\n\n[Context](docs/context.md)\n", encoding="utf-8")
    assert (own_page_problems(application) == []) is right

