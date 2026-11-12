"""The brand's colours keep their contrast in both themes. This is what an organization's theme is checked against."""

import math
import mimetypes
import re

import pytest

from tests.helpers import ROOT

THEME = ROOT / "app" / "brand" / "theme.css"
PAIRED = ("primary", "secondary", "accent", "neutral", "info", "success", "warning", "error")
BASES = ("base-100", "base-200", "base-300")
TEXT_CONTRAST = 4.5
STATE_CONTRAST = 3.0
"""WCAG 1.4.11: what shows a control's state, such as the keyboard's focus, against what it sits on."""
TEXT_PAIRS = (
    ("app-selected", "app-selected-content"),
    ("app-event", "app-event-content"),
    ("app-link-color", "base-100"),
)
STATE_PAIRS = (
    ("primary", "base-100"),
    ("primary", "base-200"),
    ("app-focus-color", "base-100"),
    ("app-focus-color", "base-200"),
    ("app-tab-indicator", "base-100"),
    *((f"app-chart-{n}", "base-100") for n in range(1, 5)),
)
"""The roles a brand may set, besides daisyUI's. A theme's value for each, where it has both, is checked."""


def themes(css: str) -> dict[str, dict[str, str]]:
    """Each theme's colours, by name, without `--color-`, and the brand's roles, as `app-...`."""
    found = {}
    for block in re.findall(r"@plugin[^{]*\{(.*?)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S), re.S):
        name = re.search(r'^\s*name:\s*"([^"]+)"', block, re.M)
        if name:
            colours = re.findall(r"^\s*--color-([a-z0-9-]+):\s*([^;]+);", block, re.M)
            roles = re.findall(r"^\s*--(app-[a-z0-9-]+):\s*([^;]+);", block, re.M)
            found[name[1]] = dict(colours) | dict(roles)
    return found


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def linear_rgb(colour: str) -> tuple[float, float, float]:
    """A hexadecimal colour, or the oklch() that daisyUI's theme generator writes, in linear light from 0 to 1."""
    text = colour.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        red, green, blue = (_linear(int(text[i : i + 2], 16) / 255) for i in (1, 3, 5))
        return red, green, blue
    match = re.fullmatch(r"oklch\(\s*([\d.]+)(%?)\s+([\d.]+)\s+([\d.]+)(?:deg)?\s*\)", text)
    if match is None:
        raise ValueError(f"not a colour this check can read: {colour}")
    lightness = float(match[1]) / (100 if match[2] else 1)
    a = float(match[3]) * math.cos(math.radians(float(match[4])))
    b = float(match[3]) * math.sin(math.radians(float(match[4])))
    long = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    medium = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    short = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        min(1.0, max(0.0, 4.0767416621 * long - 3.3077115913 * medium + 0.2309699292 * short)),
        min(1.0, max(0.0, -1.2684380046 * long + 2.6097574011 * medium - 0.3413193965 * short)),
        min(1.0, max(0.0, -0.0041960863 * long - 0.7034186147 * medium + 1.7076147010 * short)),
    )


def luminance(colour: str) -> float:
    red, green, blue = linear_rgb(colour)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first: str, second: str) -> float:
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def failures(colours: dict[str, str]) -> list[str]:
    """Text against what it sits on at 4.5:1, and what shows a state at 3:1, for each pair the theme sets both of."""
    text = [(name, f"{name}-content") for name in PAIRED] + [(base, "base-content") for base in BASES]
    checked = [(pair, TEXT_CONTRAST) for pair in (*text, *TEXT_PAIRS)]
    checked += [(pair, STATE_CONTRAST) for pair in STATE_PAIRS]
    return [
        f"{first} and {second}: {contrast(colours[first], colours[second]):.2f}"
        for (first, second), least in checked
        if first in colours and second in colours and contrast(colours[first], colours[second]) < least
    ]


@pytest.mark.rule("A11Y-05")
def test_every_theme_an_organization_adds_keeps_its_contrast():
    """The base uses daisyUI's themes as they come, so this applies once an organization adds its own."""
    for colours in themes(THEME.read_text(encoding="utf-8")).values():
        assert failures(colours) == []


@pytest.mark.rule("A11Y-05")
def test_a_theme_that_fails_is_caught():
    own = """@plugin "x" {
  name: "own";
  --color-primary: #ffffff;
  --color-primary-content: #eeeeee;
}"""
    colours = themes(own)["own"]
    assert [failure.split(":")[0] for failure in failures(colours)] == ["primary and primary-content"]


@pytest.mark.rule("A11Y-05")
def test_what_shows_a_state_is_checked_at_three_to_one():
    """A bar theme that left out its primary showed the keyboard's focus at 1.76:1 on the bar."""
    own = """@plugin "x" {
  name: "bar";
  --color-base-100: #1f2937;
  --color-base-200: #374151;
  --color-primary: #4338ca;
  --app-chart-1: #e5e7eb;
  --app-selected: #fbbf24;
  --app-selected-content: #78350f;
}"""
    assert [failure.split(":")[0] for failure in failures(themes(own)["bar"])] == [
        "primary and base-100",
        "primary and base-200",
    ]


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("#000000", "#ffffff", 21.0),
        ("#777777", "#ffffff", 4.48),
        ("oklch(0 0 0)", "oklch(1 0 0)", 21.0),
        ("oklch(100% 0 0)", "#000000", 21.0),
        ("oklch(62.8% 0.2577 29.23)", "#ff0000", 1.0),
    ],
)
def test_contrast_follows_the_wcag_formula(first, second, expected):
    assert contrast(first, second) == pytest.approx(expected, abs=0.02)


def test_the_organizations_fonts_go_out_with_their_own_type_on_every_system():
    """Starlette names a file's type from Python's table, which Windows leaves without fonts."""
    from app.core.application import FONT_TYPES

    for extension, kind in FONT_TYPES.items():
        assert mimetypes.guess_type(f"brand{extension}")[0] == kind


def test_a_brands_own_font_for_its_headings_wins_over_the_base():
    """The brand's theme.css comes before the base's rules: had the base named the headings' font with any weight, a
    brand's own `h1 { font-family: ... }` would have lost to it."""
    built = (ROOT / "app" / "ui" / "static" / "app.css").read_text(encoding="utf-8")
    assert ":where(h1,h2){font-family:var(--app-heading-font,inherit)}" in built
    assert not re.search(r"(?<![\w:(,-])h[12]\{[^}]*font-family", built)
