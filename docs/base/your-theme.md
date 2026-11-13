---
type: reference
title: Your theme
description: "An organization's look: daisyUI themes, the top bar, brand roles with their contrast checks, logos and fonts in app/brand"
tags: [base, your-theme]
---

# Your theme

Everything a brand sets lives in `app/brand/`, and nothing else changes: daisyUI's themes, a few CSS variables, the
logos and the fonts. `tests/test_brand.py` checks what the browser draws: the built stylesheet's themes, daisyUI's
values with the brand's, the default theme under the others, and the bar on each page theme, as it inherits what it
leaves out, each role as the stylesheet falls back without it. Text at 4.5:1 and what shows a state at 3:1. A colour is written as `#rrggbb`, `#rgb`,
`oklch(L C H)` or `var(--color-...)`.

**Themes**, made with [daisyUI's theme generator](https://daisyui.com/theme-generator/) and pasted into
`app/brand/theme.css`: `light`, `dark`, and `bar` for the top bar and the menu when `APP_LAYOUT_BAR` is `brand`. A
theme also holds daisyUI's radii (`--radius-field`, `--radius-box`, `--radius-selector`), border (`--border`), depth
(`--depth`) and sizes (`--size-field`, `--size-selector`); square corners on the bar alone, for instance, are
`--radius-field: 0rem` in `bar`. A value a theme leaves out is the page's, which may not show on the bar: set each one
the bar uses.

**Roles**, CSS variables a theme sets inside its block. The default theme's block is also the page's (`:root`), so a
role it sets reaches every other theme that does not set it again: give each theme its own, or `initial` to take the
role away there and fall back to the default below.


| Variable | Default | Where | Checked against |
|---|---|---|---|
| `--app-focus-color` | `primary` | The keyboard's focus | `base-100`, `base-200` at 3:1 |
| `--app-focus-width` | `2px` | The focus's line | — |
| `--app-selected`, `--app-selected-content` | `base-content`, `base-100`: the page turned round | The menu's current item, the option the arrow keys are on | Each other at 4.5:1; `base-100` at 3:1 |
| `--app-hover`, `--app-hover-content` | `base-200`, the text's | An option under the pointer | Each other at 4.5:1 |
| `--app-icon-tile`, `--app-icon-tile-content` | `base-200`, the text's | An option's icon and its tile, turned round on the selected one | Each other at 3:1 |
| `--app-tab-indicator` | The tab's text | The current tab's line | `base-100`, `base-200` at 3:1 |
| `--app-event`, `--app-event-content` | `primary` at 22% on `base-100`, `base-content` | Calendar events | Each other at 4.5:1 |
| `--app-chart-1` to `--app-chart-4` | `primary`, `accent`, `secondary`, `info` | A chart's series, in order | `base-100` at 3:1, where the brand sets them: daisyUI's own are not, and a chart's table carries its numbers |
| `--app-link-color` | The text's | daisyUI's `.link`; not menus, breadcrumbs or plain links | `base-100`, `base-200` at 4.5:1 |
| `--app-table-head`, `--app-table-head-content` | daisyUI's: none, the text at 60% | A table's header, its pinned first cell and its sorted column | Each other at 4.5:1 |

**On `:root`**, for every theme: `--app-heading-font`, the headings' font (a list of fonts, which Tailwind would split
inside a theme's block); `--app-bar-height` (the bar's least height, 3.75rem, which the side menu's logo shares, so the two line up), `--app-nav-width` (16rem), `--app-nav-width-compact`
(4rem), `--app-logo-height` (2rem). The bar is `.app-bar`, the menu `.app-nav`, the logo `.app-logo`, for anything
else a brand adds to them.

**Logos**, SVG files of any proportion; only `logo.svg` is required, and each falls back as the table says:

| File | What | Without it |
|---|---|---|
| `logo.svg` | The logomark, the symbol, on a light background | — |
| `logo-full.svg` | The logotype, the whole logo, on a light background | `logo.svg` |
| `logo-bar.svg` | The logomark on the bar | `logo.svg` |
| `logo-bar-full.svg` | The logotype on the bar | `logo-bar.svg`, then `logo-full.svg` |
| `favicon.svg` | The browser's tab | `logo.svg` |

The whole logo goes where it fits: the top bar on a wide screen and the side menu. The symbol goes where room is
short: the icons-only menu and a phone. The application's name follows the logo.

**Arrangement.** The side menu folds to its icons and back from a button at its foot, which is the same choice as the
settings menu's. In the icons-only menu a link's name shows beside it on hover and on keyboard focus, stays while the
pointer moves onto it, and Escape hides it. With the page's title in the top bar, its breadcrumb trail goes there
too, and the title takes the place of the trail's last item, the page itself; a phone keeps the trail in the page.

**The organization's arrangement**, in `app/brand/layout.toml`: each key a layout's name, and `choices`, what each
person may change; a value the settings do not offer stops the application. The settings read it below the
environment and `.env`, so an application changes what it needs and keeps the rest. "In the brand's colours" is
offered only where the brand has a `bar` theme.

```toml
bar = "brand"            # the top bar and the menu in the brand's colours
page_title = "header"    # the page's title, with its trail, in the top bar
choices = ["navigation", "bar", "width", "density", "theme_control", "language_control", "page_title", "list_width", "list_density"]
```

**Files are linked with a stamp of their content** (`app.css?v=…`): a browser fetches one again as soon as it
changes and never keeps an old script after an update. The copied libraries take their pinned hash as their stamp:
an old copy would fail the new integrity and not run.
