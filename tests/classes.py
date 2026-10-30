"""For the check that no class is invented: what pages really use, and what the stylesheet really defines."""

import ast
import re
from collections.abc import Iterable, Iterator
from html.parser import HTMLParser

from jinja2 import nodes

from app.core.templating import environment
from app.ui.catalog import STATUSES, components

NO_CSS_OF_THEIR_OWN = {"drawer-button", "theme-controller"}
"""Real names in daisyUI's documentation that only mark an element: no rule needs them in this stylesheet."""
_ESCAPE = r"\\[0-9a-fA-F]{1,6}\s?|\\[^0-9a-fA-F\n]"
_START = rf"-{{0,2}}(?:[A-Za-z_]|[^\x00-\x7f]|{_ESCAPE})"
_CLASS = re.compile(rf"(?<![\w.%\\])\.({_START}(?:[\w-]|[^\x00-\x7f]|{_ESCAPE})*)")
_INVENTED_VALUE = re.compile(r"-\[[^\]]*\]|(?:^|:)!?\[[a-zA-Z-]+:[^\]]+\]")
_OUTSIDE_TAILWINDS_SIGHT = re.compile(
    "^(?:" + "|".join(sorted(map(re.escape, {*components(), "btn"}))) + r")-[a-z0-9-]+$"
)


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.classes: set[str] = set()
        self.links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag != "svg":  # the names icons bring from their library style nothing
            self.classes |= set((values.get("class") or "").split())
        self.links |= {values[name] or "" for name in ("href", "hx-get") if name in values}


def read_page(html: str) -> tuple[set[str], set[str]]:
    """The classes in a page, and the addresses it leads to."""
    page = _Page()
    page.feed(html)
    return page.classes, page.links


def _decoded(name: str) -> str:
    return re.sub(
        r"\\([0-9a-fA-F]{1,6})\s?|\\(.)",
        lambda found: chr(int(found[1], 16)) if found[1] else found[2],
        name,
        flags=re.S,
    )


def defined_classes(css: str) -> set[str]:
    """Each class a selector names, decoded: `.\\32 xl\\:flex` is `2xl:flex`. A value like `.125rem` is no selector."""
    plain = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    plain = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '""', plain)
    found: set[str] = set()
    for prelude in re.findall(r"[^{}]+(?=\{)", plain):
        selector = prelude.rsplit(";", 1)[-1].strip()  # a rule nested after declarations
        if not selector.startswith("@"):
            found |= {_decoded(name) for name in _CLASS.findall(selector)}
    return found


def invented(classes: Iterable[str], css: str) -> set[str]:
    """Classes that produce no CSS: Tailwind generates only what is real, so these were invented or mistyped."""
    return set(classes) - defined_classes(css) - NO_CSS_OF_THEIR_OWN


def invented_values(classes: Iterable[str]) -> set[str]:
    """Classes that smuggle in a value: `bg-[#ff0000]`, `text-[13px]`, `[color:#ff0000]`. Tailwind accepts these."""
    return {name for name in classes if _INVENTED_VALUE.search(name)}


def _strings(node: nodes.Node) -> Iterator[str]:
    """The texts an expression can give, leaving out what it only compares, looks up or translates."""
    if isinstance(node, nodes.Compare | nodes.Call | nodes.Getitem):
        return
    if isinstance(node, nodes.Const) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, nodes.Pair):
        yield from _strings(node.value)
    else:
        for child in node.iter_child_nodes():
            yield from _strings(child)


def _class_parameters(macro: nodes.Macro) -> set[str]:
    """The macro's parameters written inside a class attribute."""
    names = {argument.name for argument in macro.args}
    found: set[str] = set()
    for output in macro.find_all(nodes.Output):
        inside = False
        for part in output.nodes:
            if isinstance(part, nodes.TemplateData):
                opened = part.data.rpartition('class="')
                inside = '"' not in opened[2] if opened[1] else inside and '"' not in part.data
            elif inside and isinstance(part, nodes.Name) and part.name in names:
                found.add(part.name)
    return found


def template_literals(sources: Iterable[str]) -> set[str]:
    """Classes written in {% set %} values and in the macro arguments that end up in a class attribute."""
    trees = [environment.parse(source) for source in sources]
    macros: dict[str, tuple[list[str], set[str]]] = {}
    texts: set[str] = set()
    for tree in trees:
        for macro in tree.find_all(nodes.Macro):
            parameters = _class_parameters(macro)
            macros[macro.name] = ([argument.name for argument in macro.args], parameters)
            defaults = zip(macro.args[-len(macro.defaults) :] if macro.defaults else [], macro.defaults, strict=True)
            for argument, default in defaults:
                if argument.name in parameters:
                    texts |= set(_strings(default))
    for tree in trees:
        for assignment in tree.find_all(nodes.Assign):
            texts |= set(_strings(assignment.node))
        for call in tree.find_all(nodes.Call):
            if not isinstance(call.node, nodes.Name) or call.node.name not in macros:
                continue
            names, parameters = macros[call.node.name]
            arguments = [(names[i], value) for i, value in enumerate(call.args)]
            arguments += [(keyword.key, keyword.value) for keyword in call.kwargs]
            for name, value in arguments:
                if name in parameters:
                    texts |= set(_strings(value))
    return {word for text in texts for word in text.split() if not word.startswith("/")}


def catalogue_classes() -> set[str]:
    return {name for _label, classes in STATUSES.values() for name in classes.split()}


def misplaced_classes(source: str, python: bool) -> set[str]:
    """Class names in a file Tailwind does not read: their CSS would never be generated."""
    if python:
        constants = [n.value for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Constant)]
        texts = [value for value in constants if isinstance(value, str)]
    else:
        texts = re.findall(r"\"([^\"]*)\"|'([^']*)'", source)
        texts = [first or second for first, second in texts]
    return {word for text in texts for word in text.split() if _OUTSIDE_TAILWINDS_SIGHT.match(word)}
