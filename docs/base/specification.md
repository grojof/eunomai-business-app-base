---
type: reference
title: Specification
description: "The index of how the base works: each section is a page of its own, and every link to an earlier section still leads here."
tags: [specification, components, data, demo, template]
related: [standards.md, decisions.md]
---

# Specification

`eunomai-business-app-base` is a working application that demonstrates its own components. An organization clones it once and
adds its brand; each new application is then a clone of that copy, with the demo deleted.

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

<a id="column-types"></a>
<a id="decimals-on-sqlite"></a>
<a id="where-the-two-databases-differ"></a>
<a id="lists-on-the-server"></a>
<a id="charts"></a>
<a id="boards"></a>
<a id="timelines"></a>
<a id="calendars"></a>
<a id="groups-and-editing-a-row"></a>
<a id="two-people-on-one-row"></a>
<a id="forms"></a>
<a id="uploads"></a>
<a id="excel"></a>

[Data](data/README.md): The databases (PostgreSQL in production, SQLite for the demo and previews), their settings, migrations, and an index of the data pages.

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
