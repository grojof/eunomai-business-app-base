"""The gallery's data, generated from daisyUI's own documentation so that nothing in it is written by hand.

    uv run --frozen python tools/gallery.py         write app/demo/examples/
    uv run --frozen python tools/gallery.py check   fail if it is out of date

The source is tools/tailwind/daisyui-docs.json, pinned in vendor.json to the same version as daisyUI itself. For each
component it takes the title, description, class tables and every example, with the Spanish and Catalan that daisyUI
publishes. `transform` is the only place an example changes, so that it runs under this application's Content Security
Policy. A page whose structure has changed stops the generator rather than give a gallery with holes:
tools/update_dependencies.py then holds daisyUI back, as it does for docs/base/components/.

With the demo deleted there is no gallery, and this tool has nothing to do.
"""

import json
import re
import sys
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ui.catalog import CATEGORIES  # noqa: E402

SOURCE = ROOT / "tools" / "tailwind" / "daisyui-docs.json"
TARGET = ROOT / "app" / "demo" / "examples"
PLACEHOLDERS = "/static/ui/placeholders"
PLACEHOLDER_KINDS = 4
FRAME_IDS = {"main", "navigation", "announcements", "palette", "gallery-search"}
"""Ids of the application's frame: an example must never take one."""
STAGE = {"dock", "fab", "toast", "drawer"}
"""Classes fixed to the screen: their examples get a box of their own to be fixed to."""
FLOATS = {"dropdown", "tooltip"}
"""Classes that leave their box on purpose: it must not cut them."""
THUMBNAIL_CANDIDATES = 5
THUMBNAIL_SIZE = 900
"""Characters of markup: a longer example does not read at the size of a card."""
REFERENCES = {"for", "popovertarget", "list", "aria-controls", "aria-labelledby", "aria-describedby", "aria-owns"}
DIALOG_CALLS = {"showModal": "data-dialog", "close": "data-dialog-close"}
PALETTE = re.compile(
    r"(?:^|:)(?:bg|text|border|from|to|via|ring|fill|stroke|outline)-(?:"
    r"(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet"
    r"|purple|fuchsia|pink|rose)-\d+|white|black)(?:/\d+)?$"
    r"|var\(--color-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue"
    r"|indigo|violet|purple|fuchsia|pink|rose)-\d+\)"
)
"""Tailwind's own colours, which this base removes: docs/base/decisions.md says why."""
TOKEN = re.compile(
    r"<!--.*?-->"
    r"|<(?P<tag>[a-zA-Z][\w-]*)(?P<attributes>(?:\s+[^\s=>/]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>\"']+))?)*)\s*(?P<end>/?)>",
    re.S,
)
ATTRIBUTE = re.compile(r"""([^\s=>/]+)(?:(\s*=\s*)("[^"]*"|'[^']*'|[^\s>"']+))?""")
EXTERNAL = re.compile(r"""^(?:https?:)?//""")
LOADS_FROM = re.compile(r"""\b(?:src|href|poster|srcset)\s*=\s*["']?(?:https?:)?//|url\(\s*["']?(?:https?:)?//""")
CSS_URL = re.compile(r"""url\(\s*["']?((?:https?:)?//[^"')]+)["']?\s*\)""")
SVG_STYLE = re.compile(r"(<svg\b(?:(?!</svg>).)*?)(?:<defs>\s*)?<style>(.*?)</style>(?:\s*</defs>)?(.*?</svg>)", re.S)
FENCE = re.compile(r"^```(\S*)\s*$")
HEADING = re.compile(r"^(#{2,4}) (.+?)\s*$")
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)


class StructureChanged(ValueError):
    """daisyUI's pages no longer look as this tool expects. A person must look: nothing is guessed."""


@dataclass
class Seen:
    """Every id and radio group already on a page: two examples with one name would act as one."""

    ids: set[str] = field(default_factory=lambda: set(FRAME_IDS))
    groups: set[str] = field(default_factory=set)


def _unique(name: str, taken: set[str]) -> str:
    candidate, number = name, 2
    while candidate in taken:
        candidate = f"{name}-{number}"
        number += 1
    taken.add(candidate)
    return candidate


def _placeholder(url: str) -> str:
    """A local neutral image: the same address always gives the same one, and different ones usually differ."""
    kind = "avatar" if "/profile/" in url else "photo"
    return f"{PLACEHOLDERS}/{kind}-{zlib.crc32(url.encode()) % PLACEHOLDER_KINDS + 1}.svg"


def _inline_svg_style(html: str) -> str:
    """A <style> inside an SVG, refused by the policy, becomes a style on each element it names."""

    def inline(found: re.Match[str]) -> str:
        declarations: dict[str, str] = {}
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", found[2]):
            for selector in selectors.split(","):
                if not re.fullmatch(r"\.[\w-]+", selector.strip()):
                    raise StructureChanged(f"a style inside an SVG uses {selector.strip()!r}, not a plain class")
                name = selector.strip()[1:]
                declarations[name] = declarations.get(name, "") + body.strip().rstrip(";") + ";"

        def apply(tag: re.Match[str]) -> str:
            classes = tag["attributes"] and re.search(r'class="([^"]*)"', tag["attributes"])
            names = classes[1].split() if classes else []
            wanted = "".join(declarations.get(name, "") for name in names)
            if not wanted:
                return tag[0]
            return tag[0].replace(tag["attributes"], f'{tag["attributes"]} style="{wanted}"', 1)

        return TOKEN.sub(apply, found[1] + found[3])

    return SVG_STYLE.sub(inline, html)


def _renames(html: str, seen: Seen) -> dict[str, str]:
    """What each repeated id and radio group of this example becomes. Anchor names follow too: they share the page."""
    renames: dict[str, str] = {}
    for found in TOKEN.finditer(html):
        if not found["tag"]:
            continue
        attributes = dict(_attributes(found["attributes"]))
        if "id" in attributes and attributes["id"] not in renames:
            renames[attributes["id"]] = _unique(attributes["id"], seen.ids)
        if found["tag"] == "input" and attributes.get("type") == "radio" and attributes.get("name"):
            name = attributes["name"]
            if f"name:{name}" not in renames:
                renames[f"name:{name}"] = _unique(name, seen.groups)
        for anchor in re.findall(r"anchor-name:\s*(--[\w-]+)", attributes.get("style", "")):
            renames[anchor] = _unique(anchor, seen.ids)
    return renames


def _attributes(text: str) -> Iterator[tuple[str, str]]:
    for name, _equals, value in ATTRIBUTE.findall(text):
        yield name, value[1:-1] if value[:1] in ('"', "'") else value


def _dialog_attribute(handler: str, value: str, renames: dict[str, str]) -> str:
    call = re.fullmatch(r"\s*([A-Za-z_][\w]*)\.(\w+)\(\)\s*;?\s*", value)
    if call is None or call[2] not in DIALOG_CALLS:
        raise StructureChanged(f"{handler}={value!r} is not a call this tool knows how to replace")
    return f'{DIALOG_CALLS[call[2]]}="{renames.get(call[1], call[1])}"'


def _rewrite(found: re.Match[str], renames: dict[str, str], runs: bool) -> str:
    """One start tag with its inline code, other servers and repeated names replaced."""
    tag = found["tag"]
    if not tag:
        return found[0]
    attributes = dict(_attributes(found["attributes"]))
    is_radio = tag == "input" and attributes.get("type") == "radio"

    def rewrite(attribute: re.Match[str]) -> str:
        name, equals, raw = attribute[1], attribute[2] or "", attribute[3] or ""
        value = raw[1:-1] if raw[:1] in ('"', "'") else raw
        lowered = name.lower()
        if lowered.startswith("on") and runs:
            return _dialog_attribute(name, value, renames)
        if lowered == "style":
            for old, new in renames.items():
                value = re.sub(rf"{re.escape(old)}(?![\w-])", new, value)
            value = CSS_URL.sub(lambda url: f"url({_placeholder(url[1])})", value)
            return f'data-style="{value}"'
        if lowered == "src" and tag == "img" and EXTERNAL.match(value):
            return f'src="{_placeholder(value)}"'
        if lowered == "id" or lowered in REFERENCES:
            return f'{name}{equals}"{" ".join(renames.get(part, part) for part in value.split())}"'
        if lowered == "href" and value.startswith("#") and value[1:] in renames:
            return f'href="#{renames[value[1:]]}"'
        if lowered == "name" and is_radio:
            return f'name="{renames.get(f"name:{value}", value)}"'
        return attribute[0]

    return found[0].replace(found["attributes"], ATTRIBUTE.sub(rewrite, found["attributes"]), 1)


def transform(source: str, seen: Seen) -> dict[str, Any]:
    """An official example as this application can show it. Every change made to an example is made here.

    - `$$`, daisyUI's placeholder for a class prefix, goes.
    - The year its documentation computes in place is left as `YYYY`.
    - Images on other servers become a local neutral placeholder. Their width, height and classes stay.
    - `style="..."` becomes `data-style`, applied by app.js through the CSSOM, which the policy allows. A <style>
      inside an SVG goes the same way.
    - `onclick="x.showModal()"` and `x.close()` become `data-dialog` and `data-dialog-close`, handled by app.js.
    - Ids and radio groups repeated on a page get a new name, and whatever refers to them follows.
    - An example with a <script> is not run: it is shown as code only, as `runs: false`.

    Anything else that would break the policy stops the generator.
    """
    html = source.replace("$$", "").replace("{new Date().getFullYear()}", "YYYY")
    runs = "<script" not in html.lower()
    if runs:
        html = _inline_svg_style(html)
    renames = _renames(html, seen) if runs else {}
    html = TOKEN.sub(lambda found: _rewrite(found, renames, runs), html)
    if runs and (LOADS_FROM.search(html) or "<style" in html.lower()):
        raise StructureChanged(f"an example still loads something it may not: {html[:120]!r}")
    classes = class_names(html)
    kind = ""
    if classes & STAGE or ("modal" in classes and "<dialog" not in html):
        kind = "stage"
    elif classes & FLOATS:
        kind = "floats"
    return {
        "html": html.strip("\n"),
        "runs": runs,
        "kind": kind,
        "palette": any(PALETTE.search(name) for name in classes),
    }


def class_names(html: str) -> set[str]:
    found: set[str] = set()
    for token in TOKEN.finditer(html):
        if token["tag"]:
            found |= set(dict(_attributes(token["attributes"])).get("class", "").split())
    return found


def _plain(value: str) -> str:
    value = value.strip()
    if len(value) > 1 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1].replace("''", "'") if value[0] == "'" else value[1:-1].replace('\\"', '"')
    return value


def read_frontmatter(name: str, text: str) -> tuple[dict[str, str], dict[str, list[dict[str, Any]]], str]:
    """The page's title and description, its class tables, and the rest. Only the shapes in use are accepted."""
    head = FRONTMATTER.match(text)
    if head is None:
        raise StructureChanged(f"{name}: no frontmatter")
    fields: dict[str, str] = {}
    tables: dict[str, list[dict[str, Any]]] = {}
    group = ""
    item: dict[str, Any] | None = None
    inside = False
    for line in head[1].splitlines():
        if line.startswith("#"):  # a key switched off with a comment, its nested values left in place
            inside = False
            continue
        if not line.strip():
            continue
        top = re.fullmatch(r"([A-Za-z]+):\s*(.*)", line)
        if top:
            inside = top[1] == "classnames"
            group, item = "", None
            if not inside:
                fields[top[1]] = _plain(top[2])
            continue
        if not inside:
            if line.startswith((" ", "\t")):  # another key's nested value: nothing this tool uses
                continue
            raise StructureChanged(f"{name}: frontmatter line not understood: {line!r}")
        heading = re.fullmatch(r"\s+([a-z]+):\s*", line)
        entry = re.fullmatch(r"\s+- class:\s*(.+)", line)
        detail = re.fullmatch(r"\s+(desc|default):\s*(.*)", line)
        if entry and group:
            item = {"class": _plain(entry[1]), "description": ""}
            tables[group].append(item)
        elif detail and item is not None:
            if detail[1] == "desc":
                item["description"] = _plain(detail[2])
            else:
                item["default"] = detail[2].strip() == "true"
        elif heading:
            group, item = heading[1], None
            tables[group] = []
        else:
            raise StructureChanged(f"{name}: class table line not understood: {line!r}")
    for required in ("title", "desc"):
        if not fields.get(required):
            raise StructureChanged(f"{name}: no {required} in its frontmatter")
    if not tables:
        raise StructureChanged(f"{name}: no class table in its frontmatter")
    return fields, tables, text[head.end() :]


def read_examples(name: str, body: str) -> list[dict[str, Any]]:
    """Each ```html block with the headings above it, in order: `### ~Title`, an optional `#### subtitle`."""
    examples: list[dict[str, Any]] = []
    section = title = subtitle = ""
    language: str | None = None
    lines: list[str] = []
    used = True
    for line in body.splitlines():
        fence = FENCE.match(line)
        if language is None:
            heading = HEADING.match(line)
            if fence:
                language, lines = fence[1], []
            elif heading and heading[1] == "##":
                section, title, subtitle = heading[2], "", ""
            elif heading and heading[1] == "###":
                if heading[2].startswith("~") and title.startswith("~") and not used:
                    raise StructureChanged(f"{name}: {title!r} has no html block")
                title, subtitle, used = heading[2], "", False
            elif heading and heading[1] == "####":
                subtitle = heading[2]
        elif line.startswith("```"):
            if language == "html":
                if not title:
                    raise StructureChanged(f"{name}: an html block with no heading above it")
                if used:
                    raise StructureChanged(f"{name}: a second html block under {title!r}")
                examples.append(
                    {"section": section, "title": title.removeprefix("~"), "subtitle": subtitle, "source": lines}
                )
                used = True
            language = None
        else:
            lines.append(line)
    if language is not None:
        raise StructureChanged(f"{name}: a code block is never closed")
    if title.startswith("~") and not used:
        raise StructureChanged(f"{name}: {title!r} has no html block")
    if not examples:
        raise StructureChanged(f"{name}: no examples found")
    return examples


def _inline(text: str) -> str:
    """Headings and translations in one form: `code` stays, links and other tags become their text."""
    text = re.sub(r"</?code>", "`", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    return re.sub(r"</?a\b[^>]*>", "", text).strip()


def localised(text: str, translations: dict[str, dict[str, str]]) -> dict[str, str]:
    """The English text, plus each language where daisyUI publishes a real translation of it."""
    keys = (text, re.sub(r"`([^`]+)`", r"<code>\1</code>", text))
    found = {"en": _inline(text)}
    for language, entries in translations.items():
        value = next((entries[key] for key in keys if entries.get(key)), "")
        if value and _inline(value) != found["en"]:
            found[language] = _inline(value)
    return found


def component(name: str, text: str, translations: dict[str, dict[str, str]], seen: Seen) -> dict[str, Any]:
    fields, tables, body = read_frontmatter(name, text)
    examples = read_examples(name, body)

    anchors: set[str] = set()
    for example in examples:
        slug = re.sub(r"[^a-z0-9-]", "", example["title"].lower().replace(" ", "-")) or "example"
        example["id"] = _unique(slug, anchors)
    seen.ids |= anchors
    seen.ids |= {f"{anchor}-{part}" for anchor in anchors for part in ("tab-preview", "tab-code", "preview", "code")}

    return {
        "name": name,
        "title": localised(fields["title"], translations),
        "description": localised(fields["desc"], translations),
        "classes": [
            {
                "group": group,
                "items": [
                    {**item, "description": localised(item["description"], translations)} for item in items if item
                ],
            }
            for group, items in tables.items()
            if items
        ],
        "examples": [
            {
                "id": example["id"],
                "section": localised(example["section"], translations) if example["section"] else None,
                "title": localised(example["title"], translations),
                "subtitle": localised(example["subtitle"], translations) if example["subtitle"] else None,
                **transform("\n".join(example["source"]), seen),
            }
            for example in examples
        ],
    }


def thumbnails(pages: dict[str, str]) -> dict[str, str]:
    """A small live picture of each component, for the index: the fullest of its first examples that still fits.

    All of them share one page, so they go through `transform` with one `Seen`.
    """
    seen = Seen()
    found = {}
    for name, text in pages.items():
        _fields, _tables, body = read_frontmatter(name, text)
        sources = ["\n".join(example["source"]) for example in read_examples(name, body)][:THUMBNAIL_CANDIDATES]
        running = [source for source in sources if "<script" not in source.lower()]
        if sources[0] not in running:  # a component that needs a library shows nothing without it
            continue
        fitting = [source for source in running if len(source) <= THUMBNAIL_SIZE] or running[:1]
        solid = [source for source in fitting if "-soft" not in source]  # the plain look says more than a pale one
        if fitting:
            found[name] = transform(max(solid or fitting, key=len), seen)["html"]
    return found


def _json(value: Any) -> str:
    return json.dumps(value, indent=1, ensure_ascii=False) + "\n"


def generate() -> dict[str, str]:
    """Every generated file, by name. Empty without the demo."""
    if not TARGET.parent.exists():
        return {}
    bundle = json.loads(SOURCE.read_text(encoding="utf-8"))
    pages: dict[str, str] = bundle["pages"]
    catalogue = {item.name for _title, group in CATEGORIES.values() for item in group}
    unknown = sorted(set(pages) - catalogue)
    if unknown:
        raise StructureChanged(f"in daisyUI's documentation but not in app/ui/catalog.py: {unknown}")
    files = {}
    classes: set[str] = set()
    for name, text in sorted(pages.items()):
        data = component(name, text, bundle["translations"], Seen())
        for example in data["examples"]:
            if example["runs"]:
                classes |= class_names(example["html"])
        files[f"{name}.json"] = _json(data)
    index = {"version": bundle["version"], "thumbnails": thumbnails(pages)}
    for html in index["thumbnails"].values():
        classes |= class_names(html)
    files["index.json"] = _json(index)
    files["classes.txt"] = "\n".join(sorted(classes)) + "\n"
    files["LICENSE.daisyui"] = bundle["licence"]
    return files


def stale(files: dict[str, str]) -> list[str]:
    """Generated files that differ from what is there, or are there no longer."""
    if not TARGET.exists():
        return sorted(files)
    different = [n for n, c in files.items() if not (TARGET / n).exists() or (TARGET / n).read_text("utf-8") != c]
    left = [path.name for path in TARGET.iterdir() if path.name not in files]
    return sorted(different + left)


def main() -> int:
    files = generate()
    if not files:
        print("no demo, so no gallery")
        return 0
    if sys.argv[1:] == []:
        TARGET.mkdir(exist_ok=True)
        for path in TARGET.iterdir():
            if path.name not in files:
                path.unlink()
        for name, content in files.items():
            (TARGET / name).write_text(content, encoding="utf-8", newline="\n")
        print(f"{len(files)} files in app/demo/examples/")
        return 0
    if sys.argv[1:] == ["check"]:
        out_of_date = stale(files)
        print("\n".join(f"out of date: app/demo/examples/{n}" for n in out_of_date) or "gallery data up to date")
        return 1 if out_of_date else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
