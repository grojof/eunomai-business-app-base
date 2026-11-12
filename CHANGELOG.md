# Changelog

## 0.2.0 (2026-11-12)

The command palette's selected option kept the page's light grey under the pointer, behind its light text, and its icon
stayed dark: it now keeps its own colours, and its icon takes the option's, on a veil of that colour.

The top bar and the menu can take the brand's colours: a new layout choice, `APP_LAYOUT_BAR` (`plain` or `brand`), which a person can also change in the settings menu. With `brand` they are drawn in a daisyUI theme called `bar`, which the brand defines in `app/brand/theme.css` with the same generator as its other themes, so everything on them, the menus they open included, takes its colours and has its contrast checked. A brand can add a logo for the bar, `app/brand/logo-bar.svg`, of any proportion, and set the bar's height, the menu's width and the logo's height with `--app-bar-height`, `--app-nav-width` and `--app-logo-height`. The bar and the menu are `.app-bar` and `.app-nav`. Nothing changes for an application that does not choose it.

An organization's layer can set the arrangement its applications start with, in a `[layout]` table of `layer.toml` (such as `bar = "brand"`): `tools/make_template.py` writes it as the settings' defaults, so it holds on any server with nothing to remember in its environment.

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
