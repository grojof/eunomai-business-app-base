"""The gallery's pages: the data tools/gallery.py generates from daisyUI's documentation, in the person's language."""

import json
import re
from collections.abc import Iterator, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from markupsafe import Markup, escape

from app.core.i18n import N_, _, current_language
from app.core.tables import Column, Filter, ListView
from app.core.templating import NavigationGroup, SearchItem, add_templates, environment, register_search, render
from app.demo.charts import chart_examples
from app.ui.catalog import CATEGORIES, STATUSES, Component, components

DATA = Path(__file__).resolve().parent / "examples"
TEMPLATES = Path(__file__).resolve().parent / "templates"
GROUPS = {
    "component": N_("Component"),
    "part": N_("Part"),
    "style": N_("Style"),
    "color": N_("Colour"),
    "size": N_("Size"),
    "modifier": N_("Modifier"),
    "behavior": N_("Behaviour"),
    "placement": N_("Placement"),
    "direction": N_("Direction"),
}
SAMPLE_MACROS = {"filter_bar", "filter_panel", "pagination", "server_table"}
"""Macros whose specimen is a list. It keeps its state in the page's own address, on three fixed rows."""
SAMPLE_ROWS = (
    ("A-100", N_("Air compressor"), "in_service", N_("In service"), "success"),
    ("B-200", N_("Conveyor belt"), "due_soon", N_("Due soon"), "warning"),
    ("C-300", N_("Cooling tower"), "stopped", N_("Stopped"), "danger"),
)
_TAG = re.compile(r"(<!--.*?-->|<[^>]+>)", re.S)
_ATTRIBUTE = re.compile(r"""([^\s=/>]+)(=)("[^"]*"|'[^']*')""")


class Official(NamedTuple):
    """A text from daisyUI, with `lang` set when it stays in English on a page in another language."""

    text: str
    lang: str


def official(value: Mapping[str, str]) -> Official:
    language = current_language()
    if language != "en" and language in value:
        return Official(value[language], "")
    english = value["en"]
    return Official(_(english), "" if language == "en" else "en")


def inline_code(text: str) -> Markup:
    """daisyUI's headings mark code with backticks."""
    return Markup(re.sub(r"`([^`]+)`", r"<code>\1</code>", str(escape(text))))  # noqa: S704  # escaped on this line


@lru_cache(maxsize=2048)
def highlight(source: str) -> Markup:
    """Example code with its parts marked for colour. Its text is exactly `source`, which is what gets copied."""

    def span(kind: str, text: str) -> str:
        return f'<span class="code-{kind}">{escape(text)}</span>'

    def tag(text: str) -> str:
        if text.startswith("<!--"):
            return span("comment", text)
        name = re.match(r"</?[^\s/>]+", text)
        assert name is not None  # noqa: S101  # _TAG matched a tag
        rest = _ATTRIBUTE.sub(lambda found: "\0" + found[0] + "\0", text[name.end() :])
        parts = [span("tag", name[0])]
        for part in rest.split("\0"):
            found = _ATTRIBUTE.fullmatch(part)
            if found:
                parts.append(span("attribute", found[1]) + str(escape(found[2])) + span("value", found[3]))
            else:
                parts.append(str(escape(part)))
        return "".join(parts)

    pieces = _TAG.split(source)
    return Markup(  # noqa: S704  # every piece is escaped above
        "".join(tag(piece) if number % 2 else str(escape(piece)) for number, piece in enumerate(pieces))
    )


@lru_cache
def data() -> dict[str, dict[str, Any]]:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(DATA.glob("*.json"))
        if path.name != "index.json"
    }


@lru_cache
def index_data() -> dict[str, Any]:
    result: dict[str, Any] = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    return result


def title_of(name: str) -> Official:
    page = data().get(name)
    if page:
        return official(page["title"])
    own = name.replace("-", " ").capitalize()  # an organization's own component, named in its catalogue line
    return Official(_(own), "")


def ordered() -> Iterator[tuple[str, Component]]:
    for category, (_title, group) in CATEGORIES.items():
        for component in group:
            yield category, component


def badge_of(component: Component) -> dict[str, str]:
    label, classes = STATUSES[component.status]
    return {"label": _(label), "classes": classes, "status": component.status}


def card_of(component: Component) -> dict[str, Any]:
    page = data().get(component.name)
    return {
        "name": component.name,
        "title": title_of(component.name),
        "description": official(page["description"]) if page else Official(_(component.note), ""),
        "status": badge_of(component),
        "examples": len(page["examples"]) if page else 0,
        "thumbnail": Markup(index_data()["thumbnails"].get(component.name, "")),  # noqa: S704  # generated, see tools/gallery.py
        "icon": component.icon,
    }


async def gallery(request: Request) -> Response:
    every = list(components().values())
    legend = [
        (_(label), badge, status, sum(1 for component in every if component.status == status))
        for status, (label, badge) in STATUSES.items()
    ]
    categories = [
        (slug, _(title), [card_of(component) for component in group]) for slug, (title, group) in CATEGORIES.items()
    ]
    return render(
        request,
        "demo/gallery/index.html",
        legend=legend,
        categories=categories,
        component_count=len(every),
        example_count=sum(len(page["examples"]) for page in data().values()),
        daisyui_version=index_data()["version"],
    )


def example_view(example: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": example["id"],
        "section": official(example["section"]) if example["section"] else None,
        "title": official(example["title"]),
        "subtitle": official(example["subtitle"]) if example["subtitle"] else None,
        "html": Markup(example["html"]),  # noqa: S704  # generated from pinned files, never from a person's input
        "code": highlight(example["html"]),
        "runs": example["runs"],
        "kind": example["kind"],
        "palette": example["palette"],
    }


def sample_view(path: str, params: Mapping[str, str], panelled: bool = False) -> ListView:
    """A list without a database, so a macro can be tried here. The rows are filtered and sorted in Python, which a real
    screen must not do: see app/demo/equipment.py for that."""
    view = ListView.read(
        "sample",
        path,
        params,
        (
            Column("code", _("Code"), "code"),
            Column("name", _("Name"), "name"),
            Column("status", _("State"), "status"),
        ),
        None,
        "code",
        (
            Filter(
                "status",
                _("State"),
                [(row[2], _(row[3])) for row in SAMPLE_ROWS],
                every=_("All states"),
                condition=lambda _value: None,  # type: ignore[arg-type,return-value]
            ),
        ),
        ("name",),
        _("Code or name"),
        panelled,
    )
    term = view.term.casefold()
    rows = [
        {"code": code, "name": _(name), "status": status, "label": _(label), "kind": kind}
        for code, name, status, label, kind in SAMPLE_ROWS
        if status == (view.chosen["status"] or status) and term in f"{code} {_(name)}".casefold()
    ]
    rows.sort(key=lambda row: row[view.sort], reverse=view.direction == "desc")
    view.rows, view.total = rows, len(rows)
    return view


async def gallery_component(request: Request, name: str) -> Response:
    every = list(ordered())
    position = next((number for number, (_category, item) in enumerate(every) if item.name == name), None)
    if position is None:
        raise HTTPException(status_code=404)
    category, item = every[position]
    page = data().get(name, {})
    specimen = f"demo/gallery/specimens/{name}.html"
    neighbours = [every[position - 1][1] if position else None, every[(position + 1) % len(every)][1]]
    neighbours[1] = neighbours[1] if position + 1 < len(every) else None
    examples = [example_view(example) for example in page.get("examples", [])]
    panelled = item.macro == "filter_panel"
    sample = sample_view(request.url.path, request.query_params, panelled) if item.macro in SAMPLE_MACROS else None
    return render(
        request,
        "demo/gallery/component.html",
        title=title_of(name),
        description=official(page["description"]) if page else None,
        status=badge_of(item),
        note=_(item.note) if item.note else "",
        macro=item.macro,
        specimen=specimen if (TEMPLATES / specimen).exists() else None,
        category=_(CATEGORIES[category][0]),
        classes=[
            (
                _(GROUPS.get(group["group"], group["group"].capitalize())),
                [(row["class"], official(row["description"])) for row in group["items"]],
            )
            for group in page.get("classes", [])
        ],
        examples=examples,
        sample=sample,
        chart_figures=chart_examples() if name == "chart" else [],
        previous=(neighbours[0].name, title_of(neighbours[0].name)) if neighbours[0] else None,
        following=(neighbours[1].name, title_of(neighbours[1].name)) if neighbours[1] else None,
    )


def navigation_groups() -> list[NavigationGroup]:
    return [
        NavigationGroup(_(title), [(title_of(item.name).text, f"/gallery/{item.name}") for item in group])
        for title, group in CATEGORIES.values()
    ]


def search_results() -> list[SearchItem]:
    results = []
    for _category, item in ordered():
        page = data().get(item.name)
        classes = " ".join(row["class"] for group in page["classes"] for row in group["items"]) if page else ""
        results.append(
            SearchItem(
                title_of(item.name).text,
                f"/gallery/{item.name}",
                _("Components"),
                official(page["description"]).text if page else "",
                f"{item.name} {classes}",
                "component",
            )
        )
    return results


def install(application: FastAPI) -> None:
    add_templates(TEMPLATES)
    environment.filters["inline_code"] = inline_code
    register_search(application.state, search_results)
    application.add_api_route("/gallery", gallery, include_in_schema=False)
    application.add_api_route("/gallery/{name}", gallery_component, include_in_schema=False)
