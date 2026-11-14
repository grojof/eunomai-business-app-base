---
type: reference
title: Decisions
description: "Why eunomai-business-app-base is built the way it is, and what was rejected, one family a page, and the questions still open."
tags: [decisions]
related: [specification.md, standards.md]
---

# Decisions

Each family of decisions is a page of its own: read the one a link names.

## Foundations and checks

[Foundations and checks](decisions/foundations.md): Why the base is cloned and owned, built from standards, made on the server, checked by tests and tools rather than instructions, and on which Python.

## Components and the gallery

[Components and the gallery](decisions/components.md): Why daisyUI with Tailwind, macros over classes, the component pages and their list, and how the gallery shows daisyUI's examples.

## Themes, the shell and its pieces

[Themes, the shell and its pieces](decisions/themes-and-shell.md): Why themes come from daisyUI and the server, the settings menu, the command palette, native menus, icons, illustrations and the libraries for calendars and charts.

## Language, numbers and time

[Language, numbers and time](decisions/language.md): Why language support from the first screen, Babel and CLDR for formats, translations from `.po` files, UTC, decimal contexts, rounding and identifiers.

## Data and databases

[Data and databases](decisions/data.md): Why PostgreSQL with SQLite for the demo, one exact type for money, how sessions, migrations and versions work, and how the demo's rows are made.

## Lists, forms and uploads

[Lists, forms and uploads](decisions/lists-and-forms.md): Why native tables, filters and layout in the address, forms read by small functions, limits on requests, uploads checked by their bytes, and exports.

## Detail pages, charts and boards

[Detail pages, charts and boards](decisions/screens.md): Why tabs as links, dialogs for editing, how charts get and choose their data, boards, ranks and Gantt charts drawn on the server.

## Open questions

| Question | How it is settled |
|---|---|
| Which translation tool do translators use? | Files in git work for developers; decide if non-developers translate |
| Can a person open a server running inside an assistant's sandbox? | Not documented. Until tested, the assistant shows results as screenshots or a self-contained HTML file |
| Does generating the stylesheet in an assistant's sandbox work under every organization's network rules? | Confirmed only [as far as the executable starting](stack.md#stack), on one account. Generate a full stylesheet there |
| Does the dependency workflow run on other git servers? | It is written for GitHub Actions; test it on the first clone hosted elsewhere |
| Is it worth buying ISO 9241-110 to compare the usability rules with it? | Not needed to work: no rule uses it. An organization that must show ISO conformance would buy it |
| Which licence, when it goes public? | MIT or Apache 2.0. Without a licence, nobody may legally reuse it |
| Do project skills load in every assistant? | The repository has none. Test before relying on them; the rules live in `AGENTS.md` and `docs/` |
| Which fields does the registration file need? | Milestone 6, against a real platform |
