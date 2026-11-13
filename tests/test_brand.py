"""The brand's colours keep their contrast in both themes. This is what an organization's theme is checked against."""

import math
import mimetypes
import re

import pytest

from tests.helpers import ROOT

THEME = ROOT / "app" / "brand" / "theme.css"
BUILT = ROOT / "app" / "ui" / "static" / "app.css"
PAIRED = ("primary", "neutral", "info", "success", "warning", "error")
"""The colours the base draws text on: buttons, badges and alerts. Secondary and accent are a chart's series only."""
BASES = ("base-100", "base-200", "base-300")
TEXT_CONTRAST = 4.5
STATE_CONTRAST = 3.0
"""WCAG 1.4.11: what shows a control's state, such as the keyboard's focus, against what it sits on."""
ROLES = {
    "app-focus-color": "primary",
    "app-selected": "base-content",
    "app-selected-content": "base-100",
    "app-hover-content": "base-content",
    "app-tab-indicator": "base-content",
    "app-link-color": "base-content",
    "app-event-content": "base-content",
    "app-table-head-content": "base-content",
}
"""Each role and what the base's stylesheet falls back to without it, as the page draws it."""
COMBINATIONS = {"light": ("light",), "dark": ("dark",), "light, bar": ("light", "bar"), "dark, bar": ("dark", "bar")}
"""The page's themes, and the bar on each: the bar takes from the page what its own theme leaves out."""
READABLE = "#rrggbb, #rgb, oklch(L C H) or var(--color-...)"


def themes(css: str) -> dict[str, dict[str, str]]:
    """Each theme's colours as a source writes them, by name, without `--color-`, and the brand's roles, `app-...`."""
    found = {}
    for block in re.findall(r"@plugin[^{]*\{(.*?)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S), re.S):
        name = re.search(r'^\s*name:\s*"([^"]+)"', block, re.M)
        if name:
            colours = re.findall(r"^\s*--color-([a-z0-9-]+):\s*([^;]+);", block, re.M)
            roles = re.findall(r"^\s*--(app-[a-z0-9-]+):\s*([^;]+);", block, re.M)
            found[name[1]] = dict(colours) | dict(roles)
    return found


def built_themes(css: str) -> dict[str, dict[str, str]]:
    """Each theme as the built stylesheet holds it: daisyUI writes light and dark whole, its values and the brand's,
    and any other theme with only what the brand gave it."""
    found: dict[str, dict[str, str]] = {}
    for name, body in re.findall(r"[^{}]*\[data-theme=([\w-]+)\][^{}]*\{([^{}]*)\}", css):
        pairs = re.findall(r"--((?:color|app)-[\w-]+):([^;]+)", body)
        values = {key.removeprefix("color-"): value.strip() for key, value in pairs}
        if values:
            found.setdefault(name, {}).update(values)
    return found


def default_theme(css: str) -> str | None:
    """The theme daisyUI also writes for `:root`, the page itself: what it sets reaches every other theme that does not
    set it again."""
    found = re.search(r":where\(:root\)[^{}]*\[data-theme=([\w-]+)\]", css)
    return found[1] if found else None


def effective(
    found: dict[str, dict[str, str]], combination: tuple[str, ...], default: str | None = None
) -> dict[str, str]:
    """What a combination draws: the default theme under it, then each theme on the one before. A role set to
    `initial` is taken away, and the stylesheet falls back as it would without it."""
    colours = dict(found.get(default, {})) if default else {}
    for name in combination:
        colours |= found.get(name, {})
    return {key: value for key, value in colours.items() if value.strip() != "initial"}


def resolve(colours: dict[str, str], value: str, where: str) -> str:
    """A colour as the browser would draw it: var(--color-x) followed within the same theme."""
    text = value.strip()
    for _ in range(10):
        found = re.fullmatch(r"var\(--((?:color|app)-[\w-]+)(?:,\s*(.+))?\)", text)
        if not found:
            break
        key = found[1].removeprefix("color-")
        if key in colours:
            text = colours[key].strip()
        elif found[2]:
            text = found[2].strip()
        else:
            raise AssertionError(f"{where}: {value} names --{found[1]}, which this theme does not have")
    return text


def failures(colours: dict[str, str], where: str = "", bar: bool = False) -> list[str]:
    """Text against what it sits on at 4.5:1, and what shows a state at 3:1, with each role as the stylesheet resolves
    it. A pair whose colours the theme does not have is left out. The bar is checked for what it draws: its
    backgrounds and their text, the keyboard's focus and the menu's current item."""

    def colour(name: str) -> str | None:
        value = colours.get(name, colours.get(ROLES.get(name, ""), None))
        return resolve(colours, value, where) if value is not None else None

    def has(name: str) -> bool:
        return name in colours

    text = [(name, f"{name}-content") for name in PAIRED] + [(base, "base-content") for base in BASES]
    text += [("app-selected", "app-selected-content")]
    text += [("app-hover", "app-hover-content")] if has("app-hover") else []
    text += [("app-event", "app-event-content")] if has("app-event") else []
    text += [("app-table-head-content", "app-table-head")] if has("app-table-head") else []
    text += [("app-link-color", base) for base in ("base-100", "base-200")] if has("app-link-color") else []
    state = [("app-focus-color", base) for base in ("base-100", "base-200")]
    state += [("app-selected", "base-100")]
    state += [("app-tab-indicator", base) for base in ("base-100", "base-200")]
    tile = has("app-icon-tile") and has("app-icon-tile-content")
    state += [("app-icon-tile-content", "app-icon-tile")] if tile else []
    state += [(f"app-chart-{n}", "base-100") for n in range(1, 5) if has(f"app-chart-{n}")]
    if bar:
        text = [(base, "base-content") for base in BASES] + [("app-selected", "app-selected-content")]
        state = [("app-focus-color", base) for base in ("base-100", "base-200")] + [("app-selected", "base-100")]
    found = []
    for pairs, least in ((text, TEXT_CONTRAST), (state, STATE_CONTRAST)):
        for first, second in pairs:
            one, other = colour(first), colour(second)
            if one is None or other is None:
                continue
            try:
                ratio = contrast(one, other)
            except ValueError:
                said = f"{where}: {first} or {second} is not written as {READABLE}: {one}, {other}"
                raise AssertionError(said) from None
            if ratio < least:
                found.append(f"{first} and {second}: {ratio:.2f}")
    return found


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def linear_rgb(colour: str) -> tuple[float, float, float]:
    """A hexadecimal colour, or the oklch() that daisyUI's theme generator writes, in linear light from 0 to 1."""
    text = colour.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3}", text):
        text = "#" + "".join(digit * 2 for digit in text[1:])
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


@pytest.mark.rule("A11Y-05")
@pytest.mark.parametrize("combination", COMBINATIONS)
def test_every_colour_the_page_draws_keeps_its_contrast(combination):
    """What the browser draws: the built stylesheet's themes, daisyUI's values with the brand's, the default theme
    under the others, and the bar on each page theme, as it inherits what it leaves out. Each role as the stylesheet
    falls back without it."""
    built = BUILT.read_text(encoding="utf-8")
    found = built_themes(built)
    if "bar" in COMBINATIONS[combination] and "bar" not in found:
        pytest.skip("the brand has no theme called bar")
    where = f"the {combination} theme"
    bar = "bar" in COMBINATIONS[combination]
    colours = effective(found, COMBINATIONS[combination], default_theme(built))
    assert failures(colours, where, bar=bar) == [], where


@pytest.mark.rule("A11Y-05")
def test_a_theme_that_fails_is_caught():
    built = (
        ":root,[data-theme=light]{--color-base-100:#ffffff;--color-base-content:#000000;"
        "--color-primary:#ffffff;--color-primary-content:#eeeeee}"
    )
    colours = effective(built_themes(built), ("light",))
    assert [failure.split(":")[0] for failure in failures(colours)] == [
        "primary and primary-content",
        "app-focus-color and base-100",
    ]


@pytest.mark.rule("A11Y-05")
def test_the_bar_is_checked_with_what_it_takes_from_the_page():
    """A bar theme that left out its primary showed the keyboard's focus at 1.76:1 on the bar; one that leaves out its
    selected takes the page's, which may vanish there."""
    built = (
        "[data-theme=light]{--color-base-100:#ffffff;--color-base-200:#f4f6fa;--color-base-content:#000000;"
        "--color-primary:#4338ca;--color-primary-content:#ffffff;--app-selected:#1e3a8a;--app-selected-content:#ffffff}"
        "[data-theme=bar]{--color-base-100:#1f2937;--color-base-200:#374151;--color-base-content:#f9fafb}"
    )
    found = built_themes(built)
    assert failures(effective(found, ("light",))) == []
    assert [failure.split(":")[0] for failure in failures(effective(found, ("light", "bar")), bar=True)] == [
        "app-focus-color and base-100",
        "app-focus-color and base-200",
        "app-selected and base-100",
    ]


@pytest.mark.rule("A11Y-05")
def test_a_role_the_default_theme_sets_reaches_the_other_themes():
    """A brand gave its light theme navy links and left them out of dark: the browser drew them navy on the dark page,
    since the default theme's block is also the page's, and this check, theme by theme, did not see it."""
    light = (
        ":where(:root),[data-theme=light]{--color-base-100:#ffffff;--color-base-200:#f4f6fa;--color-base-content:#000;"
        "--app-link-color:#263a77}"
    )
    dark = "[data-theme=dark]{--color-base-100:#1d232a;--color-base-200:#191e24;--color-base-content:#ecf0f4%s}"
    built = light + dark % ""
    assert default_theme(built) == "light"
    assert [failure.split(":")[0] for failure in failures(effective(built_themes(built), ("dark",), "light"))] == [
        "app-link-color and base-100",
        "app-link-color and base-200",
    ]
    for own in (";--app-link-color:#7cc4ec", ";--app-link-color:initial"):
        assert failures(effective(built_themes(light + dark % own), ("dark",), "light")) == []


def test_a_role_names_a_colour_of_its_theme_and_short_hex_reads():
    built = (
        "[data-theme=light]{--color-base-100:#fff;--color-base-content:#000;--color-secondary:#1e3a8a;"
        "--app-focus-color:var(--color-secondary)}"
    )
    colours = effective(built_themes(built), ("light",))
    assert failures(colours) == []
    with pytest.raises(AssertionError, match="is not written as"):
        failures(colours | {"app-focus-color": "color-mix(in oklab, red, blue)"}, "a theme")


def test_a_theme_block_holds_no_role_with_a_list():
    """Tailwind splits a theme's value at its commas: a list of fonts there would leave only the last one."""
    for name, values in themes(THEME.read_text(encoding="utf-8")).items():
        lists = [key for key, value in values.items() if re.search(r",(?![^(]*\))", value)]
        assert lists == [], f"theme {name}: {', '.join(lists)} hold a list; set them on :root"


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
