"""Icons and illustrations: find an icon, and check every SVG the application shows.

    uv run --frozen python tools/icons.py search camión    icons by name, Lucide's tags and categories, old names,
                                                           and our Spanish and Catalan words
    uv run --frozen python tools/icons.py check            fail on anything below

Icons come from two places, and the `icon` macro finds a name in either. None is ever drawn inline:
- Lucide's whole set, in app/ui/templates/ui/icons/, pinned in vendor.json and moved by tools/vendor.py. Its index,
  tools/lucide/index.json, holds each icon's tags, categories and old names.
- The organization's own, in app/brand/icons/, with an optional tags.json in the index's form. A name Lucide already
  has is refused, so nothing is replaced in silence. Each must look like Lucide's: a 24 by 24 viewBox, drawn with
  currentColor, no colour, style, id or size of its own.

Illustrations are files in app/ui/static/illustrations/, shown with <img src> or as a CSS background, never inline: an
image runs no script and loads nothing. Each must still hold nothing that runs or loads from elsewhere, and neither may
the brand's logos or the demo's placeholders.
"""

import ast
import io
import json
import re
import sys
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from jinja2 import Environment, nodes

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
LUCIDE = APP / "ui" / "templates" / "ui" / "icons"
OWN = APP / "brand" / "icons"
INDEX = ROOT / "tools" / "lucide" / "index.json"
SYNONYMS = ROOT / "tools" / "icon-synonyms.json"
ILLUSTRATIONS = APP / "ui" / "static" / "illustrations"
SVG = "http://www.w3.org/2000/svg"
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
PLACES = (
    re.compile(r"ui/templates/ui/icons/[^/]+\.svg"),
    re.compile(r"brand/icons/[^/]+\.svg"),
    re.compile(r"brand/[^/]+\.svg"),
    re.compile(r"ui/static/illustrations/.+\.svg"),
    re.compile(r"ui/static/placeholders/[^/]+\.svg"),
)
"""Where an SVG file may be: Lucide's icons, the organization's, the brand's logos, the illustrations, and the demo's
stand-ins for the photos in daisyUI's examples."""
IMAGES = (re.compile(r"brand/[^/]+\.svg"), PLACES[3], PLACES[4])
"""SVG files shown as images, never inline: each is checked for anything that runs or loads."""
NOT_OURS = re.compile(r"(?:^|/)(?:vendor|__pycache__)/|^demo/examples/|^ui/static/app\.css$")
"""Copied or generated: daisyUI's examples keep their drawings as published, and the stylesheet is Tailwind's output."""
INLINE = re.compile(r"<svg\b|svg\+xml", re.I)
ICON_INCLUDE = re.compile(r"""["'](?:ui/icons/|brand-icons/)""")
ICON_MACRO = re.compile(r"\{%-?\s*macro\s+icon\(.*?\{%-?\s*endmacro\s*-?%\}", re.S)
DATA_PICTURE = "ui/templates/ui/macros.html"
GANTT_MACRO = re.compile(r"\{%-?\s*macro\s+gantt\(.*?\{%-?\s*endmacro\s*-?%\}", re.S)
"""The one exception to drawing no SVG inline: the `gantt` macro draws a timeline's picture from its rows, on the
server, beside the table that holds the same rows, so that its colours follow the theme. It is a chart, not an icon or
an illustration, and holds nothing that runs or loads: tests/test_icons.py renders one and checks it as an image is."""
RASTER = re.compile(r"data:image/(?:png|jpeg|gif|webp|avif)[;,]", re.I)
URL = re.compile(r"""url\(\s*(['"]?)(.*?)\1\s*\)""", re.I | re.S)
COLOURS = {"fill", "stroke", "color", "stop-color", "flood-color", "lighting-color"}
STOP_WORDS = {"a", "amb", "and", "de", "del", "el", "els", "en", "for", "i", "la", "las", "les", "los", "of", "per"}
STOP_WORDS |= {"the", "un", "una", "y"}


# The two sets


@dataclass(frozen=True)
class Icon:
    name: str
    source: str  # "lucide" or "organization"
    tags: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    deprecated: bool = False


def read_json(path: Path) -> Any:
    """A JSON file, read again only when it changes: a search reads Lucide's index of 1,600 icons, and a test runs
    hundreds of searches. Callers must not change what it returns."""
    stat = path.stat()
    return _read_json(path, stat.st_mtime_ns, stat.st_size)


@cache
def _read_json(path: Path, _modified: int, _size: int) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def svg_names(folder: Path) -> set[str]:
    return {path.stem for path in folder.glob("*.svg")}


def lucide_names(folder: Path = LUCIDE) -> set[str]:
    return svg_names(folder)


def own_tags(folder: Path = OWN) -> dict[str, Any]:
    tags = folder / "tags.json"
    return read_json(tags) if tags.exists() else {"icons": {}}


def catalogue(index: Path = INDEX, own: Path = OWN) -> dict[str, Icon]:
    """Every icon the macro can show, by name. Lucide's comes first: a clash is the check's to report."""
    found: dict[str, Icon] = {}
    for name, entry in read_json(index)["icons"].items():
        found[name] = Icon(
            name,
            "lucide",
            tuple(entry.get("tags", [])),
            tuple(entry.get("categories", [])),
            tuple(entry.get("aliases", [])),
            bool(entry.get("deprecated")),
        )
    described = own_tags(own).get("icons", {})
    for name in sorted(svg_names(own) - set(found)):
        entry = described.get(name, {}) if isinstance(described, dict) else {}
        found[name] = Icon(name, "organization", tuple(entry.get("tags", [])), tuple(entry.get("categories", [])))
    return found


def aliases(index: Path = INDEX) -> dict[str, str]:
    """Lucide's old names, each with the name that replaced it."""
    return {old: name for name, entry in read_json(index)["icons"].items() for old in entry.get("aliases", [])}


# Search


@cache  # a search reads every tag of every icon: the same few thousand texts, each time
def normalise(text: str) -> str:
    """Lowercase, without accents: `Camión` and `camion` are the same word."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9-]+", " ", plain).split())


@dataclass(frozen=True)
class Found:
    icon: Icon
    score: int
    why: str


def _close(word: str, other: str) -> bool:
    """The same word, or one with up to two more letters at its end, as a plural has: `camiones` and `camion`."""
    shorter, longer = sorted((word, other), key=len)
    return word == other or (len(shorter) >= 4 and len(longer) - len(shorter) <= 2 and longer.startswith(shorter))


def _word_score(icon: Icon, word: str, categories: dict[str, str]) -> tuple[int, str]:
    best = (0, "")
    parts = icon.name.split("-")
    tags = [normalise(tag) for tag in icon.tags]
    candidates = [
        (50 if word in parts else 25 if any(part.startswith(word) for part in parts) and len(word) >= 3 else 0, "name"),
        (45 if word in tags else 0, f"tag {word}"),
        (35 if any(word in tag.split() for tag in tags) else 0, f"tag with {word}"),
        (20 if any(_close(word, tag) for tag in tags) else 0, f"tag like {word}"),
        (
            10
            if any(word in (category, normalise(categories.get(category, ""))) for category in icon.categories)
            else 0,
            f"category {word}",
        ),
    ]
    for score, why in candidates:
        if score > best[0]:
            best = (score, why)
    return best


def search(
    query: str,
    own: Path = OWN,
    synonyms: dict[str, dict[str, list[str]]] | None = None,
    index: Path = INDEX,
    limit: int = 12,
) -> list[Found]:
    """Icons for a request in English, Spanish or Catalan, best first."""
    icons = catalogue(index, own)
    categories: dict[str, str] = read_json(index)["categories"]
    words_of = read_json(SYNONYMS) if synonyms is None else synonyms
    phrase = normalise(query)
    words = [word for word in phrase.split() if word not in STOP_WORDS]
    scores: dict[str, tuple[int, list[str]]] = {}

    def add(name: str, score: int, why: str) -> None:
        if name in icons and score:
            total, reasons = scores.get(name, (0, []))
            scores[name] = (total + score, [*reasons, why])

    for name, icon in icons.items():
        if phrase == name:
            add(name, 100, "name")
        elif phrase in icon.aliases:
            add(name, 90, f"Lucide's old name {phrase}")
        for word in words:
            score, why = _word_score(icon, word, categories)
            add(name, score, why)
    for language, entries in words_of.items():
        for key, names in entries.items():
            plain = normalise(key)
            if plain == phrase:
                score = 90
            elif len(plain.split()) == 1 and any(_close(word, plain) for word in words):
                score = 45 if plain in words else 25
            else:
                continue
            for name in names:
                add(name, score, f"{key} ({language})")
    ranked = sorted(scores.items(), key=lambda item: (-item[1][0] + 5 * icons[item[0]].deprecated, item[0]))
    return [Found(icons[name], score, ", ".join(dict.fromkeys(why))) for name, (score, why) in ranked[:limit]]


# What templates and code ask for


def _strings(node: nodes.Node) -> Iterator[str]:
    """The names an expression can give. A name built by joining text is not known until it runs."""
    if isinstance(node, nodes.Const) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, nodes.CondExpr):
        yield from _strings(node.expr1)
        if node.expr2 is not None:
            yield from _strings(node.expr2)
    elif isinstance(node, nodes.Or | nodes.And):
        yield from _strings(node.left)
        yield from _strings(node.right)


def _names_in(node: nodes.Node) -> set[str]:
    """Variables that are themselves the name: `item.icon` is a field, which the code's check reads."""
    if isinstance(node, nodes.Name):
        return {node.name}
    if isinstance(node, nodes.Compare | nodes.Concat | nodes.Getattr | nodes.Getitem):
        return set()
    return set().union(*(_names_in(child) for child in node.iter_child_nodes()))


def _loops(scope: nodes.Node) -> dict[str, tuple[str, int | None]]:
    """Each loop variable, with the list it comes from and its place in each item: `for a, b in items` gives b at 1."""
    found: dict[str, tuple[str, int | None]] = {}
    for loop in scope.find_all(nodes.For):
        if not isinstance(loop.iter, nodes.Name):
            continue
        if isinstance(loop.target, nodes.Name):
            found[loop.target.name] = (loop.iter.name, None)
        elif isinstance(loop.target, nodes.Tuple):
            for place, item in enumerate(loop.target.items):
                if isinstance(item, nodes.Name):
                    found[item.name] = (loop.iter.name, place)
    return found


def _bound(call: nodes.Call, parameters: list[str]) -> dict[str, nodes.Node]:
    bound: dict[str, nodes.Node] = {
        parameters[place]: value for place, value in enumerate(call.args) if place < len(parameters)
    }
    return bound | {keyword.key: keyword.value for keyword in call.kwargs}


def _templates(app: Path) -> list[tuple[str, nodes.Template]]:
    parser = Environment(autoescape=True, extensions=["jinja2.ext.i18n"])  # it only reads, never renders
    found = []
    for path in sorted(app.rglob("*.html")):
        where = path.relative_to(app).as_posix()
        if not NOT_OURS.search(where):
            found.append((where, parser.parse(path.read_text(encoding="utf-8"))))
    return found


def _template_requests(app: Path) -> tuple[list[tuple[str, str]], set[tuple[str, int | None]]]:
    """Names written in templates, and the lists a page receives whose items carry names, as (list, place)."""
    templates = _templates(app)
    macros = {m.name: m for _where, tree in templates for m in tree.find_all(nodes.Macro)}
    if "icon" not in macros:
        return [], set()
    parameters = {name: [argument.name for argument in macro.args] for name, macro in macros.items()}
    flows: dict[str, set[tuple[str, int | None]]] = {"icon": {(parameters["icon"][0], None)}}
    changed = True
    while changed:  # a macro that passes one of its parameters on to the icon macro, directly or through another
        changed = False
        for name, macro in macros.items():
            loops = _loops(macro)
            for call in macro.find_all(nodes.Call):
                callee = call.node.name if isinstance(call.node, nodes.Name) else ""
                for parameter, place in list(flows.get(callee, set())):
                    value = _bound(call, parameters[callee]).get(parameter)
                    if place is not None or value is None or name == "icon":
                        continue
                    for variable in _names_in(value):
                        loop = loops.get(variable)
                        flow = (variable, None) if variable in parameters[name] else loop
                        if flow and flow[0] in parameters[name] and flow not in flows.setdefault(name, set()):
                            flows[name].add(flow)
                            changed = True
    requests: list[tuple[str, str]] = []
    context: set[tuple[str, int | None]] = set()
    for where, tree in templates:
        inside = {id(call): macro for macro in tree.find_all(nodes.Macro) for call in macro.find_all(nodes.Call)}
        top_loops = _loops(tree)
        for call in tree.find_all(nodes.Call):
            callee = call.node.name if isinstance(call.node, nodes.Name) else ""
            enclosing = inside.get(id(call))
            own_parameters = set(parameters[enclosing.name]) if enclosing else set()
            loops = _loops(enclosing) if enclosing else top_loops
            for parameter, place in flows.get(callee, set()):
                value = _bound(call, parameters[callee]).get(parameter)
                if value is None:
                    continue
                if place is None:
                    requests += [(text, f"{where}:{call.lineno}") for text in _strings(value)]
                    context |= {
                        loops[variable]
                        for variable in _names_in(value)
                        if variable in loops and loops[variable][0] not in own_parameters
                    }
                elif isinstance(value, nodes.List | nodes.Tuple):
                    for item in value.items:
                        if isinstance(item, nodes.Tuple) and len(item.items) > place:
                            requests += [(text, f"{where}:{call.lineno}") for text in _strings(item.items[place])]
    return requests, context


def _python_strings(node: ast.AST | None) -> Iterator[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, ast.IfExp):
        yield from _python_strings(node.body)
        yield from _python_strings(node.orelse)
    elif isinstance(node, ast.BoolOp):
        for value in node.values:
            yield from _python_strings(value)


def _items_at(node: ast.AST | None, place: int | None) -> Iterator[str]:
    if place is None:
        yield from _python_strings(node)
    elif isinstance(node, ast.List | ast.Tuple):
        for item in node.elts:
            if isinstance(item, ast.Tuple) and len(item.elts) > place:
                yield from _python_strings(item.elts[place])


def _python_requests(app: Path, context: set[tuple[str, int | None]]) -> list[tuple[str, str]]:
    """Names written in code: a field or argument called `icon`, a class's `icon` field given by position, a dict's
    "icon", and the lists a template reads names from."""
    trees = {
        path.relative_to(app).as_posix(): ast.parse(path.read_text(encoding="utf-8")) for path in app.rglob("*.py")
    }
    trees = {where: tree for where, tree in trees.items() if not NOT_OURS.search(where)}
    with_icon: dict[str, int] = {}
    for tree in trees.values():
        for cls in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
            fields = [s.target.id for s in cls.body if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)]
            if "icon" in fields:
                with_icon[cls.name] = fields.index("icon")
    requests: list[tuple[str, str]] = []
    for where, tree in trees.items():
        for node in ast.walk(tree):
            found: list[str] = []
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "icon":
                found += _python_strings(node.value)
            elif isinstance(node, ast.Call):
                callee = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                if callee in with_icon and len(node.args) > with_icon[callee]:
                    found += _python_strings(node.args[with_icon[callee]])
                for keyword in node.keywords:
                    if keyword.arg == "icon":
                        found += _python_strings(keyword.value)
                    for variable, place in context:
                        if keyword.arg == variable:
                            found += _items_at(keyword.value, place)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if isinstance(key, ast.Constant) and key.value == "icon":
                        found += _python_strings(value)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    for variable, place in context:
                        if isinstance(target, ast.Name) and target.id == variable:
                            found += _items_at(node.value, place)
            requests += [(name, f"{where}:{getattr(node, 'lineno', 0)}") for name in found]
    return requests


def requested(app: Path = APP) -> list[tuple[str, str]]:
    """Every icon name the templates and the code ask for, with where: file and line."""
    from_templates, context = _template_requests(app)
    return [(name, where) for name, where in from_templates + _python_requests(app, context) if name]  # "": none


def unknown_names(app: Path = APP, known: set[str] | None = None, old: dict[str, str] | None = None) -> list[str]:
    known = set(catalogue()) if known is None else known
    old = aliases() if old is None else old
    problems = []
    for name, where in requested(app):
        if name not in known:
            hint = f": it is Lucide's old name for {old[name]}" if name in old else ""
            problems.append(f"{where}: no icon named {name}{hint}")
    return sorted(set(problems))


# Nothing drawn by hand


def drawn_by_hand(app: Path = APP) -> list[str]:
    """An SVG outside its places, an inline one in a template, code, script or stylesheet, or an icon included outside
    the icon macro."""
    problems = []
    for path in sorted(app.rglob("*")):
        where = path.relative_to(app).as_posix()
        if not path.is_file() or NOT_OURS.search(where):
            continue
        if path.suffix == ".svg":
            if not any(place.fullmatch(where) for place in PLACES):
                problems.append(
                    f"{where}: an SVG file outside Lucide's icons, app/brand/icons/, the brand's logos and "
                    "app/ui/static/illustrations/"
                )
        elif path.suffix in (".html", ".py", ".js", ".css"):
            text = path.read_text(encoding="utf-8")
            if where == DATA_PICTURE:
                text = GANTT_MACRO.sub("", text)
            if INLINE.search(text):
                problems.append(f"{where}: an inline SVG: icons come through the icon macro, illustrations as files")
            if path.suffix == ".html" and ICON_INCLUDE.search(ICON_MACRO.sub("", text)):
                problems.append(f"{where}: an icon outside the icon macro: call icon(name)")
    return problems


# Safety and likeness


def _outside(value: str) -> str | None:
    value = value.strip()
    if value.startswith("#") or RASTER.match(value):
        return None
    return f"a reference outside the file: {value[:60]}"


def _css_problems(text: str) -> list[str]:
    problems = ["an @import, which loads a stylesheet"] if "@import" in text else []
    return problems + [reason for found in URL.finditer(text) if (reason := _outside(found[2]))]


def _parse(text: str) -> ElementTree.Element:
    """Only after `unsafe` refused a DOCTYPE or ENTITY, which is what defusedxml guards against: expat never
    fetches an external entity, and without a DOCTYPE no entity can be declared to expand."""
    return ElementTree.fromstring(text.encode("utf-8"))  # noqa: S314


def unsafe(text: str) -> list[str]:
    """What in an SVG could run, or load something from elsewhere, if it were ever opened on its own."""
    if re.search(r"<!DOCTYPE|<!ENTITY", text, re.I):
        return ["a DOCTYPE or ENTITY, which can pull in or expand content"]
    problems = ["an xml-stylesheet instruction, which loads a stylesheet"] if "<?xml-stylesheet" in text else []
    try:
        root = _parse(text)
    except ElementTree.ParseError as error:
        return [*problems, f"not well-formed XML: {error}"]
    if root.tag != f"{{{SVG}}}svg":
        problems.append("its root is not <svg> in the SVG namespace")
    for element in root.iter():
        namespace, _, local = element.tag.rpartition("}")
        if namespace.lstrip("{") != SVG:
            problems.append(f"an element outside SVG: <{local}>")
        elif local in ("script", "foreignObject"):
            problems.append(f"a <{local}>")
        elif local == "style":
            problems += _css_problems(element.text or "")
        for attribute, value in element.attrib.items():
            name = attribute.rpartition("}")[2]
            if name.lower().startswith("on"):
                problems.append(f"an event attribute: {name}")
            if "javascript:" in re.sub(r"\s", "", value.lower()):
                problems.append(f"a javascript: address in {name}")
            elif name == "href" and (reason := _outside(value)):
                problems.append(reason)
            elif name == "style" or "url(" in value:
                problems += _css_problems(value)
    return list(dict.fromkeys(problems))


def unlike_lucide(text: str) -> list[str]:
    """What would make an icon look or behave unlike Lucide's beside them."""
    root = _parse(text)
    problems = []
    if root.get("viewBox") != "0 0 24 24":
        problems.append(f"its viewBox is {root.get('viewBox')!r}, not Lucide's '0 0 24 24'")
    for size in ("width", "height"):
        if root.get(size) not in (None, "24"):
            problems.append(f"{size}={root.get(size)!r}: the macro's classes give an icon its size")
    uses_current_colour = False
    for element in root.iter():
        if element.tag.rpartition("}")[2] == "style":
            problems.append("a <style>, which the page's policy refuses: use attributes")
        for attribute, value in element.attrib.items():
            name = attribute.rpartition("}")[2]
            if name == "style":
                problems.append("a style attribute, which the page's policy refuses: use attributes")
            elif name == "id":
                problems.append("an id, which repeats when the icon is on a page twice")
            elif name in COLOURS and value.strip().lower() == "currentcolor":
                uses_current_colour = True
            elif name in COLOURS and value.strip().lower() != "none":
                problems.append(f"a colour of its own: {name}={value!r}; use currentColor")
    if not uses_current_colour:
        problems.append("it never uses currentColor, so themes and states cannot colour it")
    return list(dict.fromkeys(problems))


def _shown(folder: Path) -> str:
    return folder.relative_to(ROOT).as_posix() if folder.is_relative_to(ROOT) else folder.name


def own_problems(folder: Path = OWN, lucide: set[str] | None = None) -> list[str]:
    """The organization's icons: their names, their safety, their likeness to Lucide's, and their tags file."""
    lucide = lucide_names() if lucide is None else lucide
    shown = _shown(folder)
    problems = []
    for path in sorted(folder.glob("*.svg")):
        name = path.stem
        if not NAME.fullmatch(name):
            problems.append(f"{shown}/{path.name}: a name of lowercase letters, digits and hyphens, as Lucide's are")
        if name in lucide:
            problems.append(
                f"{shown}/{path.name}: Lucide has an icon named {name}: give yours another name, such as {name}-ours"
            )
        text = path.read_text(encoding="utf-8")
        found = unsafe(text)
        found += [] if any("not well-formed" in reason for reason in found) else unlike_lucide(text)
        problems += [f"{shown}/{path.name}: {reason}" for reason in found]
    tags = own_tags(folder)
    described = tags.get("icons") if isinstance(tags, dict) else None
    if not isinstance(described, dict) or set(tags) != {"icons"}:
        return [*problems, f'{shown}/tags.json: not in the same form as Lucide\'s index: {{"icons": {{name: ...}}}}']
    for name, entry in described.items():
        if name not in svg_names(folder):
            problems.append(f"{shown}/tags.json: no icon named {name} in {shown}/")
        words = [entry.get(key, []) for key in ("tags", "categories")] if isinstance(entry, dict) else [None]
        if not all(isinstance(value, list) and all(isinstance(w, str) for w in value) for value in words):
            problems.append(f"{shown}/tags.json: {name}: tags and categories are each a list of words")
    return problems


def index_problems(folder: Path = LUCIDE, index: dict[str, Any] | None = None) -> list[str]:
    """Lucide's folder and its index name the same icons. One only in the folder was not Lucide's."""
    listed = set((read_json(INDEX) if index is None else index)["icons"])
    present = svg_names(folder)
    shown = _shown(folder)
    return [
        f"{shown}/{name}.svg: not in Lucide's index, so not Lucide's: the organization's icons go in app/brand/icons/"
        for name in sorted(present - listed)
    ] + [
        f"Lucide's index lists {name}, but {shown}/ has no {name}.svg: run tools/vendor.py update"
        for name in sorted(listed - present)
    ]


def synonym_problems(icons: dict[str, Icon] | None = None) -> list[str]:
    icons = catalogue() if icons is None else icons
    problems = []
    for language, words in read_json(SYNONYMS).items():
        for word, names in words.items():
            for name in names:
                if name not in icons or icons[name].deprecated:
                    problems.append(f"{SYNONYMS.name}: {language} {word}: no current icon named {name}")
    return problems


def image_problems(app: Path = APP) -> list[str]:
    """Each SVG shown as an image: the illustrations, the brand's logos and the demo's placeholders."""
    problems = []
    for path in sorted(app.rglob("*.svg")):
        where = path.relative_to(app).as_posix()
        if any(place.fullmatch(where) for place in IMAGES):
            problems += [f"{where}: {reason}" for reason in unsafe(path.read_text(encoding="utf-8"))]
    return problems


def problems() -> list[str]:
    found = [*index_problems(), *own_problems(), *synonym_problems()]
    found += [f"app/{problem}" for problem in [*image_problems(), *drawn_by_hand(), *unknown_names()]]
    return found


def describe(found: Found) -> str:
    source = found.icon.source + (", deprecated" if found.icon.deprecated else "")
    tags = ", ".join(found.icon.tags[:6])
    return f"{found.icon.name:<28} {source:<20} {found.why}" + (f"  [{tags}]" if tags else "")


def main(arguments: Iterable[str] = sys.argv[1:]) -> int:
    arguments = list(arguments)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")  # a Windows console would otherwise lose `camión`'s accent
    if arguments[:1] == ["search"] and arguments[1:]:
        results = search(" ".join(arguments[1:]))
        print("\n".join(describe(item) for item in results) or "nothing found: try an English word")
        return 0
    if arguments == ["check"]:
        found = problems()
        print("\n".join(found) or "icons and illustrations are in order")
        return 1 if found else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
