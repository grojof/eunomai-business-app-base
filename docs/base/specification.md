---
type: reference
title: Specification
description: "The index of how the base works: each section is a page of its own, and every link to an earlier section still leads here."
tags: [specification, components, data, demo, template]
related: [standards.md, decisions.md]
---

# Specification

`eunomai-business-app-base` is a working application that demonstrates its own components. An organization makes its
application template from it with a small layer of its own; each new application starts from that template, with the
demo deleted.

Success means three things, each testable:

| Goal | Test |
|---|---|
| Adapting it to an organization is cheap | Changing only `app/brand/` and the settings gives that organization's look |
| A new application starts clean | With `app/demo/` deleted, every tool check and the tests still pass |
| The components hold the [standards](standards.md) | Real screens pass the scan in both themes, and approved components have tests and a review. Official examples in the [gallery](gallery.md#gallery) are reference material: no gate |

Each section is a page of its own: read the section a link names, not every page.

## Structure

[Structure](structure.md): What each folder of the repository holds: app/core, app/ui, app/brand, the demo, migrations, tools and tests.

## Stack

[Stack](stack.md): The approved libraries and tools, what each is for, and what needs a decision before it is added.

## Dependencies

[Dependencies](dependencies.md): How the base's dependencies are kept current and audited: the weekly workflow, pins, hashes and the rules for a new one.

## Data

[Data](data/README.md): The databases (PostgreSQL in production, SQLite for the demo and previews), their settings, migrations, and an index of the data pages.

<a id="column-types"></a>
- [Column types](data/column-types.md): Which column type to use in a model for money, quantities, dates, times and text, and what each becomes on both databases.
<a id="decimals-on-sqlite"></a>
- [Decimals on SQLite](data/decimals-on-sqlite.md): Why exact numbers need care on SQLite, and what to use instead of SUM or a sort that would go wrong.
<a id="where-the-two-databases-differ"></a>
- [Where the two databases differ](data/where-the-two-databases-differ.md): Where PostgreSQL and SQLite behave differently, with the cost of each difference.
<a id="lists-on-the-server"></a>
- [Lists on the server](data/lists-on-the-server.md): How to build a long list with search, filters, sorting and pages on the server: ListView and its macros.
<a id="charts"></a>
- [Charts](data/charts.md): How to draw a chart: the numbers worked out on the server, the chart macro, its table and its colours.
<a id="boards"></a>
- [Boards](data/boards.md): How to show cards in columns, such as work orders by state, moved on the server.
<a id="timelines"></a>
- [Timelines](data/timelines.md): How to show rows on a calendar as bars beside their table: the gantt macro.
<a id="calendars"></a>
- [Calendars](data/calendars.md): How to show events by month, week or agenda with the calendar macro, over what the server sends.
<a id="groups-and-editing-a-row"></a>
- [Groups and editing a row](data/groups-and-editing-a-row.md): How to group rows and edit one among thousands with a native table and form, instead of a grid.
<a id="two-people-on-one-row"></a>
- [Two people on one row](data/two-people-on-one-row.md): How a row keeps the version it was read at, so a save by one person never overwrites another's.
<a id="forms"></a>
- [Forms](data/forms.md): How to build a form to add or change a row: field macros, validation, errors and what is kept after a failed save.
<a id="uploads"></a>
- [Uploads](data/uploads.md): How an attached file is checked and stored: allowed kinds, signatures, sizes and where files live.
<a id="excel"></a>
- [Excel](data/excel.md): How to export a list to Excel with its filters and order, row by row, for large lists.

## Identity

[Identity](identity.md): How a person is identified: the trusted proxy, its headers, groups mapped to roles, and a fake identity for local work.

## Layouts

[Layouts](layouts.md): The application's arrangements (menu, width, density, header, title) and how an organization and a person choose them.

## Settings menu

[Settings menu](settings-menu.md): The settings page every application has: what a person can change and how it is kept.

## Command palette

[Command palette](command-palette.md): The search box opened with Ctrl+K: what it finds, filtered by role, and how to register more with register_search.

## Components

<a id="icons-and-illustrations"></a>

[Components](components-in-screens.md): How screens use components: one macro per component, the list of macros, and how a component is approved.

## The demo

[The demo](the-demo.md): The demo's fictional company and its screens, what each exercises, and that deleting app/demo leaves a working application.

## Gallery

<a id="where-the-examples-come-from"></a>

[Gallery](gallery.md): The gallery at /gallery: every daisyUI component, live in the current theme, to see and ask for by name.

## Documentation

[Documentation](documentation.md): How the documentation is arranged: the base's in docs/base, an application's own pages, frontmatter and links.

## Documentation for assistants

[Documentation for assistants](documentation-for-assistants.md): The per-component reference pages for assistants, cut from daisyUI's documentation, and how to read only what is needed.

## Adapting it

[Adapting it](adapting-it.md): What to change, and where, to adapt the base: colours, logos, names, languages, roles, settings and your own components.

## Your theme

[Your theme](your-theme.md): An organization's look: daisyUI themes, the top bar, brand roles with their contrast checks, logos and fonts in app/brand.

## A new module

[A new module](a-new-module.md): How tools/new_module.py writes a module from a short description: list, detail, form, and optionally board, calendar and timeline.

## An organization's template

[An organization's template](an-organizations-template.md): How an organization's layer and tools/make_template.py make the application template IT starts each project from.

## Updating an application

[Updating an application](updating-an-application.md): How an application takes a newer template: tools/update_application.py, what it merges and what it keeps.

## Checks

[Checks](checks.md): Every check the base runs and what each proves: tests, accessibility and contrast scans, keyboard, languages, uploads, exports and databases.

## Registration

[Registration](registration.md): Planned: the file that will describe an application to the platform that hosts it.

## Milestones

[Milestones](milestones.md): The base's milestones and their state.
