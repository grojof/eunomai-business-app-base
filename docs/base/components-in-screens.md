---
type: reference
title: Components
description: "How screens use components: one macro per component, the list of macros, and how a component is approved"
tags: [base, components]
---

# Components

A component is one Jinja macro or one piece of the shell, using only the brand's colours. Screens call macros, not
daisyUI classes, so the look can change in one place. Each macro appears on the page of its component in the
[gallery](gallery.md#gallery), and has tests. The macros today are `icon`, `page_heading`, `message`, `button`, `link_button`, `card`,
`panel`, `stats`, `stat`, `badge`, `status_label`, `progress`, `steps`, `table`, `empty_state`, `command`, `select_field`, `item_list`,
`breadcrumbs`, `description_list`, `tabs`, `chart`, `dialog`, `dialog_buttons`, `input_field`, `field_error`,
`error_summary`, `textarea_field`, `date_field`, `number_field`, `checkbox_field`, `radio_group`, `searchable_select`,
`file_field`, `form_actions`, `confirmation`, `confirm_link`, `conflict_notice`, `grouped_table`, `dialog_action`, `filter_bar`, `filter_panel`,
`list_with_filters`, `list_summary`, `server_table`, `row_header`, `cell`, `row_actions`, `pagination`, `board`, `gantt` and
`calendar`.

Tabs come in two kinds. `tabs` are links, one address each, as on the equipment detail: they work without JavaScript and
with the back button, so they are a navigation with `aria-current`. The server reads what every panel needs and sends them
all, with the closed one hidden, so that paper can show both. Where panels are switched in the browser, as the gallery's
Preview and Code switch, `app.js` gives ARIA's tab pattern with its arrow keys.

Printing belongs to the shell: navigation, header and actions leave, a table's scrolling box opens, its header repeats on
each page, and a row stays whole. The page wears the light theme while it prints, because paper is white and a browser
leaves out backgrounds. The equipment detail prints both of its tabs.

| Group | Components | Since |
|---|---|---|
| Structure | Page layout, header, navigation, skip link, page heading, user menu (identity, settings, version), theme control, language control, settings menu, command palette, button, card, icon | Milestone 1 |
| Data | Stat, badge, progress, steps, table with a caption | Milestone 1 |
| Feedback | Message banner, announcement region, empty state | Milestone 1 |
| Pages | No identity (401), no permission, not found, server error | Milestone 1 |
| Structure | Breadcrumbs | Milestone 2 |
| Data | Server table (paging, sorting, filtering, state in the URL, row actions), rich table, filter bar, pagination, description list, tabs, status label, chart with its data table | Milestone 2 |
| Output | Excel export, print style | Milestone 2 |
| Forms | Text, text area, select, checkbox, radio, date, number and decimal, searchable select, file upload, error summary, field error, form actions | Milestone 3 |
| Feedback | Confirmation dialog, conflict notice | Milestone 3 |
| Data | Dense and wide lists, filter panel, a chart that filters a list, board, Gantt, event calendar | Milestone 4 |
| Feedback | Loading state, progress of a long task | Milestone 5 |
| Pages | Service unavailable | Milestone 5 |

A component is left out until a real need appears for it. The base stays small enough to read.

## Icons and illustrations

An icon is a small symbol beside words; an illustration is a picture that stands on its own. They are kept apart:

| | Icons | Illustrations |
|---|---|---|
| Where | Lucide's in `app/ui/templates/ui/icons/`; the organization's in `app/brand/icons/` | `app/ui/static/illustrations/` |
| Shown | Only by the `icon` macro, which writes that one icon into the page, hidden from screen readers | Only with `<img src>`, with its `alt`, or as a CSS background: never inline |
| Made by | Lucide; the organization's designer or tools | The organization's own tools, animated ones included |
| Checked by | `tools/vendor.py check` for Lucide's folder; `tools/icons.py check` and the tests for the rest, [COMP-05](standards.md#components) | `tools/icons.py check` and the tests, [SEC-16](standards.md#security) |

**Lucide.** Every icon of `lucide-static`, as published, about 1,900, with its ISC licence beside them in `LICENSE`.
Lucide accepts no brand logos. The package's folder also holds each old name as a copy of the new one: those stay out,
and the index keeps them, so `tools/icons.py search trash-2` answers `trash`. A page grows only by the icons it shows.
`tools/lucide/index.json` holds, for each icon, Lucide's tags and categories from its repository at the same version,
one line per icon. Both are [copied files](dependencies.md#dependencies), updated by the same weekly workflow.

**Search.** `uv run --frozen python tools/icons.py search <words>` reads names, tags, categories, old names, the
organization's tags, and `tools/icon-synonyms.json`: about a hundred common business words in Spanish and in Catalan,
kept here, each pointing at icons that exist. Lucide's English tags alone find the right icon for 3 of 108 Spanish
words and 4 of 108 Catalan ones, which is why the list exists. The search needs no network.

**The organization's icons.** SVG files in `app/brand/icons/`, named like Lucide's, with an optional `tags.json` in the
index's form: `{"icons": {"pallet-jack": {"tags": ["forklift"], "categories": ["transportation"]}}}`. The search shows
them as the organization's. Each must look like Lucide's: viewBox `0 0 24 24`, drawn in `currentColor` so themes and
states colour it, and no colour, `style`, `<style>`, `id`, or size other than 24 of its own, since the page's policy
refuses inline style and the macro's classes size it. A name Lucide already has is refused, so nothing is replaced in
silence: an organization's version of a concept takes its own name, such as `truck-ours`.

**Illustrations.** A file shown as an image runs no script and loads nothing else, which inline SVG cannot promise.
Each SVG there, the brand's logos and the demo's placeholders are still checked for what would matter if one were opened
on its own: no `<script>`, event attribute, `javascript:` address, `<foreignObject>`, element outside SVG, DOCTYPE, or
reference outside the file, in `href`, `url()` or `@import`, except an embedded PNG, JPEG, GIF, WebP or AVIF. The check
names the file and the reason. Measured in Chrome 156 with the page's own policy on the page and on the SVG, served as
the application serves static files: SMIL and CSS animations in a `<style>` block both play, in `<img>` and as a CSS
background, so no policy changes. Opened directly as a page, the same SVG loses its `<style>`, which the policy refuses.
A browser test keeps that measurement.
