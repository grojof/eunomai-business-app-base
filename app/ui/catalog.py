"""Every component on offer, with an honest status. The gallery and docs/components/ are built from this list.

An organization adds its own components here, with their page in docs/components/ and, in its base, a specimen in
app/demo/templates/demo/gallery/specimens/.
"""

from dataclasses import dataclass

from app.core.i18n import N_

APPROVED = "approved"  # a macro, tests and a review
AVAILABLE = "available"  # an official example, shown as published, not audited here
DECORATIVE = "decorative"  # not meant for management applications
PROBLEMS = "problems"  # fails a standard: its note says why

STATUSES = {
    APPROVED: (N_("Approved"), "badge-success"),
    AVAILABLE: (N_("Available"), "badge-info"),
    DECORATIVE: (N_("Decorative"), "badge-ghost border-base-300"),
    PROBLEMS: (N_("Not recommended"), "badge-warning"),
}

MOTION = N_("Moves on its own and only a pointer can pause it: WCAG 2.2.2.")
KEYBOARD = N_("Its button is a label, which a keyboard cannot reach: WCAG 2.1.1. The shell uses a popover instead.")
LIBRARY = N_("It only styles a calendar library, which is not included. Use a date field.")
THEME = N_(
    "On its own it changes the theme without saving it, and it cannot say that the theme should follow the system. "
    "The shell uses its class inside a form that saves the choice: see Settings."
)


OWN_TITLES = (
    N_("Chart"),
    N_("Confirmation dialog"),
    N_("Conflict notice"),
    N_("Date field"),
    N_("Description list"),
    N_("Error summary"),
    N_("Field error"),
    N_("Filter bar"),
    N_("Form actions"),
    N_("Icon"),
    N_("Number field"),
    N_("Searchable select"),
)
"""Components of this base with no page in daisyUI: the gallery names them from their catalogue name."""


@dataclass(frozen=True)
class Component:
    name: str
    status: str = AVAILABLE
    note: str = ""
    macro: str = ""  # its macro, if it has one, in app/ui/templates/ui/macros.html
    icon: str = "calendar"  # what the gallery's index shows when daisyUI gives no small example


CATEGORIES: dict[str, tuple[str, tuple[Component, ...]]] = {
    "actions": (
        N_("Actions"),
        (
            Component("button", APPROVED, macro="button"),
            Component(
                "confirmation-dialog",
                note=N_("Asks before an action that cannot be undone, and names what will be lost."),
                macro="confirmation",
                icon="triangle-alert",
            ),
            Component("dropdown"),
            Component("fab"),
            Component("modal", macro="dialog"),
            Component("swap"),
            Component("theme-controller", AVAILABLE, THEME),
        ),
    ),
    "data-display": (
        N_("Data display"),
        (
            Component("accordion"),
            Component("avatar"),
            Component("badge", macro="badge"),
            Component("card", APPROVED, macro="card"),
            Component("carousel"),
            Component(
                "chart",
                note=N_("A figure with its text summary and its data as a table, drawn with Chart.js."),
                macro="chart",
                icon="chart-column",
            ),
            Component("chat"),
            Component("collapse"),
            Component("countdown"),
            Component(
                "description-list",
                note=N_("A list of terms and their values, for one record's details."),
                macro="description_list",
                icon="clipboard-list",
            ),
            Component("diff", DECORATIVE),
            Component("hover-3d", DECORATIVE),
            Component("hover-gallery", DECORATIVE),
            Component(
                "icon",
                note=N_("Any of Lucide's icons, or one of the organization's, hidden from screen readers."),
                macro="icon",
                icon="shapes",
            ),
            Component("kbd"),
            Component("list"),
            Component("stat", macro="stat"),
            Component("status", macro="status_label"),
            Component("table", macro="server_table"),
            Component("text-rotate", PROBLEMS, MOTION),
            Component("timeline"),
        ),
    ),
    "navigation": (
        N_("Navigation"),
        (
            Component("breadcrumbs", macro="breadcrumbs"),
            Component("dock"),
            Component("link"),
            Component("menu"),
            Component("navbar"),
            Component("pagination", macro="pagination"),
            Component("steps", macro="steps"),
            Component("tab", macro="tabs"),
        ),
    ),
    "feedback": (
        N_("Feedback"),
        (
            Component("alert", APPROVED, macro="message"),
            Component("loading"),
            Component("progress", macro="progress"),
            Component(
                "conflict-notice",
                note=N_("Says that someone else saved first, and what they saved, above what was typed."),
                macro="conflict_notice",
                icon="triangle-alert",
            ),
            Component("radial-progress"),
            Component("skeleton"),
            Component("toast"),
            Component("tooltip"),
        ),
    ),
    "data-input": (
        N_("Data input"),
        (
            Component("calendar", PROBLEMS, LIBRARY),
            Component("checkbox", macro="checkbox_field"),
            Component(
                "date-field",
                note=N_("The browser's own date field, read by the server in one strict form."),
                macro="date_field",
                icon="calendar",
            ),
            Component(
                "error-summary",
                note=N_("Every problem of a form in one place, each a link to its field."),
                macro="error_summary",
                icon="triangle-alert",
            ),
            Component(
                "field-error",
                note=N_("What is wrong with one field, and how to fix it, tied to that field."),
                macro="field_error",
                icon="triangle-alert",
            ),
            Component("fieldset"),
            Component("file-input", macro="file_field"),
            Component("filter"),
            Component(
                "filter-bar",
                note=N_("A plain form that filters a list on the server. daisyUI's filter is a set of radio buttons."),
                macro="filter_bar",
                icon="search",
            ),
            Component(
                "form-actions",
                note=N_("The main action of a form, the way out, and anything else at the far end."),
                macro="form_actions",
                icon="pencil",
            ),
            Component("input", macro="input_field"),
            Component("label"),
            Component(
                "number-field",
                note=N_("Text a person types as their language writes numbers. Never a float."),
                macro="number_field",
                icon="hash",
            ),
            Component("otp"),
            Component("radio", macro="radio_group"),
            Component("range"),
            Component("rating"),
            Component(
                "searchable-select",
                note=N_("A list to type in, by keyboard, that is a plain select without JavaScript."),
                macro="searchable_select",
                icon="search",
            ),
            Component("select", macro="select_field"),
            Component("textarea", macro="textarea_field"),
            Component("toggle"),
            Component("validator"),
        ),
    ),
    "layout": (
        N_("Layout"),
        (
            Component("aura", DECORATIVE),
            Component("divider"),
            Component("drawer", PROBLEMS, KEYBOARD),
            Component("footer"),
            Component("hero"),
            Component("indicator"),
            Component("join"),
            Component("mask", DECORATIVE),
            Component("megamenu"),
            Component("stack"),
        ),
    ),
    "mockups": (
        N_("Mockups"),
        (
            Component("mockup-browser", DECORATIVE),
            Component("mockup-code", DECORATIVE),
            Component("mockup-phone", DECORATIVE),
            Component("mockup-window", DECORATIVE),
        ),
    ),
}


def components() -> dict[str, Component]:
    return {component.name: component for _title, group in CATEGORIES.values() for component in group}
