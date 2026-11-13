# Changelog

## 0.2.3 (2026-11-13)

`tests/test_brand.py` checks each theme on top of the default one, as the browser draws it. daisyUI writes the default
theme for the page itself too, so a role a brand set only there, such as navy links in `light`, also reached `dark`,
where it did not show; the check took each theme alone and passed. A theme takes a role away with `initial`. The
specification's *Your theme* says so.

## 0.2.2 (2026-11-12)

`tools/translations.py update` changes a catalogue only when its texts change, and keeps the date in its header. A
module's new texts used to give every catalogue, the base's included, a new date: an application's catalogues then
differed from its template's, and an update of the template found a change on both sides that nobody had made, so it
could not come in on its own.

## 0.2.1 (2026-11-12)

Two tests that failed in an organization's template, though nothing was wrong:

- The side menu's tests wait for an application that has a menu. A template, or an application before its first
  module, has none, and they failed there instead of being skipped.
- The palette's test asked for the selected option's icon in the option's own colour. With a brand's icon tile
  (`--app-icon-tile`) it is in the tile's, turned round, as it should be.

## 0.2.0 (2026-11-12)

An organization can now make its applications look clearly its own with its brand files and a few settings, and
every colour it sets has its contrast checked. See [Your theme](docs/base/specification.md#your-theme).

- **The top bar and the menu in the brand's colours.** A new layout choice, `APP_LAYOUT_BAR` (`plain` or `brand`),
  which a person can also change in the settings menu. With `brand` they are drawn in a daisyUI theme called `bar`
  that the brand defines like its other themes, so everything on them, the menus they open included, takes its
  colours. The bar's height, the menu's width (wide and icons only) and the logo's height are the brand's to set.
- **Logos.** The logotype and the logomark, each for a light background and for the bar (`logo.svg`,
  `logo-full.svg`, `logo-bar.svg`, `logo-bar-full.svg`), and a favicon: the whole logo where it fits, the symbol in
  the icons-only menu and on a phone. Only `logo.svg` is required. The base has its own, "EB".
- **The brand's roles as CSS variables**, each with the base's value as its fallback: the keyboard's focus, the
  selected item (the menu's current item and the option the arrow keys are on), the current tab's line, calendar
  events, the four chart series, the headings' font and weight, and links.
- **The contrast check reads what the browser draws**: the built stylesheet's themes, daisyUI's values with the
  brand's, and the bar on each page theme, as it inherits what it leaves out. It covers what shows a state at 3:1
  (WCAG 1.4.11): the focus, the selected item and the tab's line against the backgrounds, and the chart series a
  brand sets. It found daisyUI's dark primary button at 4.14:1: its text is now white (4.65:1). The base's own bar
  theme sets its primary, so the focus shows on it.
- **Selected, by default, is the page turned round**, which shows on every theme; daisyUI's neutral nearly matched
  the dark theme's background. A brand also sets hover, an option's icon tile and a table's header.
- **The side menu folds to its icons and back**, from a button in the menu, remembered like the other choices.
  In the icons-only menu, a link's name shows on hover and on keyboard focus, and Escape hides it (WCAG 1.4.13).
- **The breadcrumb trail goes to the top bar** with the page's title, when the title is there.
- **An organization's arrangement.** `app/brand/layout.toml`, which a layer brings like the rest of the brand, sets
  what its applications start with (such as `bar = "brand"`) and what each person may change (`choices`). The
  settings read it below the environment, so an application still changes what it needs. "In the brand's colours"
  is offered only where the brand has a `bar` theme.
- **Files linked with a stamp of their content.** The application's scripts, stylesheet and logos, and the copied
  libraries, so a browser never keeps an old one after an update; an old library would even fail its new integrity.
- **Fixed:** the command palette's selected option kept the page's light grey under the pointer, behind its light
  text, and its icon stayed dark.

## 0.1.3 (2026-11-12)

A test of the rule report wrote its sample in the system's temporary folder. pytest lists each folder on its way to a
path, so it listed that folder too, where the browser tests running beside it create and delete profiles: when one went
while it was being listed, the collection stopped and the test failed. It failed every time in an application's suite,
which has fewer tests to spread them. The sample is now written in `tests/.samples/`, inside the repository.

## 0.1.2 (2026-11-12)

The `badge` macro takes `strong=true` for a badge that must stand out from the others. It adds `badge-strong`, which the
base's themes draw with bold text and a brand's theme can draw solid, for example when its normal badges are tinted.

## 0.1.1 (2026-11-12)

`tools/update_application.py` needs git 2.40 or later and says so when there is none or an older one; its tests are skipped there. In a test of an application on a person's computer, which has no git on purpose, and in an assistant's sandbox, whose git is older, they failed with nine errors that were not the application's.

## 0.1.0 (2026-11-11)

The first version, for organizations to make their template from: a working demo of its components, lists, forms,
boards, calendars, timelines, charts and Excel exports on SQLite and PostgreSQL, identity from a trusted proxy with
roles from groups, two themes and three languages, accessibility and contrast checked in both themes, a module
generator (`tools/new_module.py`), an organization's template (`tools/make_template.py`) and the update of an
application made from it (`tools/update_application.py`). See [the specification](docs/base/specification.md).
