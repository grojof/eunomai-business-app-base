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


def themes(css: str) -> dict[str, dict[str, str]]:
    """Each theme's colours, by name, without `--color-`."""
    found = {}
    for block in re.findall(r"@plugin[^{]*\{(.*?)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S), re.S):
        name = re.search(r'^\s*name:\s*"([^"]+)"', block, re.M)
        if name:
            found[name[1]] = dict(re.findall(r"^\s*--color-([a-z0-9-]+):\s*([^;]+);", block, re.M))
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
    pairs = [(name, f"{name}-content") for name in PAIRED] + [(base, "base-content") for base in BASES]
    return [
        f"{back} and {text}: {contrast(colours[back], colours[text]):.2f}"
        for back, text in pairs
        if back in colours and text in colours and contrast(colours[back], colours[text]) < TEXT_CONTRAST
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
