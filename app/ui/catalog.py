"""Every component on offer, with an honest status. The gallery and docs/components/ are built from this list.

An organization adds its own components here, with their page in docs/components/ and their specimen in the gallery.
"""

from dataclasses import dataclass

from app.core.i18n import N_

APPROVED = "approved"  # a macro, tests and a review
AVAILABLE = "available"  # passes the automatic scan: use with care
DECORATIVE = "decorative"  # not meant for management applications
PROBLEMS = "problems"  # fails a standard: its note says why

STATUSES = {
    APPROVED: (N_("Approved"), "badge-success"),
    AVAILABLE: (N_("Available"), "badge-info"),
    DECORATIVE: (N_("Decorative"), "badge-ghost"),
    PROBLEMS: (N_("Not recommended"), "badge-warning"),
}

MOTION = N_("Moves on its own and only a pointer can pause it: WCAG 2.2.2.")
KEYBOARD = N_("Its button is a label, which a keyboard cannot reach: WCAG 2.1.1. The shell uses a popover instead.")
LIBRARY = N_("It only styles a calendar library, which is not included. Use a date field.")
THEME = N_("It changes the theme without saving it. The user menu does this properly.")


@dataclass(frozen=True)
class Component:
    name: str
    status: str = AVAILABLE
    note: str = ""
    macro: str = ""  # an approved component's macro, in app/ui/templates/ui/macros.html


CATEGORIES: dict[str, tuple[str, tuple[Component, ...]]] = {
    "actions": (
        N_("Actions"),
        (
            Component("button", APPROVED, macro="button"),
            Component("dropdown"),
            Component("fab"),
            Component("modal"),
            Component("swap"),
            Component("theme-controller", PROBLEMS, THEME),
        ),
    ),
    "data-display": (
        N_("Data display"),
        (
            Component("accordion"),
            Component("avatar"),
            Component("badge"),
            Component("card", APPROVED, macro="card"),
            Component("carousel"),
            Component("chat"),
            Component("collapse"),
            Component("countdown"),
            Component("diff", DECORATIVE),
            Component("hover-3d", DECORATIVE),
            Component("hover-gallery", DECORATIVE),
            Component("kbd"),
            Component("list"),
            Component("stat"),
            Component("status"),
            Component("table"),
            Component("text-rotate", PROBLEMS, MOTION),
            Component("timeline"),
        ),
    ),
    "navigation": (
        N_("Navigation"),
        (
            Component("breadcrumbs"),
            Component("dock"),
            Component("link"),
            Component("menu"),
            Component("navbar"),
            Component("pagination"),
            Component("steps"),
            Component("tab"),
        ),
    ),
    "feedback": (
        N_("Feedback"),
        (
            Component("alert", APPROVED, macro="message"),
            Component("loading"),
            Component("progress"),
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
            Component("checkbox"),
            Component("fieldset"),
            Component("file-input"),
            Component("filter"),
            Component("input"),
            Component("label"),
            Component("otp"),
            Component("radio"),
            Component("range"),
            Component("rating"),
            Component("select"),
            Component("textarea"),
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
