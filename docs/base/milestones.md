---
type: reference
title: Milestones
description: "The base's milestones and their state"
tags: [base, milestones]
---

# Milestones

| # | Milestone | Done when | State |
|---|---|---|---|
| 0 | Specification | Reviewed | Done |
| 1 | Skeleton | Identity, languages, themes, every check and the dependency workflow running on one screen | Done |
| 1 | Shell and layouts | The application's shell behind macros, with every layout setting shown live | Done |
| 1 | Gallery and generated documentation | Every free daisyUI component shown with its status and every official example, and one generated page for each | Done |
| 1 | Settings and search | A settings menu to try layouts and control styles live, and a command palette, both in the shell | Done |
| 2 | Data layer | PostgreSQL and SQLite, exact decimals, migrations on both, 50,000 generated rows | Done |
| 2 | Data | Server table with 50,000 rows, filters, export, indicators, charts | Done |
| 3 | Forms | Every field, with validation in three languages | In review |
| 4 | Views | Dense lists with a title in the top bar, filters in a side panel, charts that filter, a board, a Gantt and a calendar, each a macro an application can reuse | In progress |
| 5 | Feedback and long tasks | Every state in the catalogue | Planned |
| 6 | Registration | Deployed behind a real identity proxy | Planned |
| 7 | Proof | One organization's copy made by changing only its brand and settings | Planned |

The accessibility and language checks run from milestone 1, so nothing is built without them.

Also planned, outside any milestone:

| Idea | Note |
|---|---|
| A screen reader pass on the shell | A scan cannot tell how it sounds: the [standards](standards.md#accessibility) ask for this by hand |
| A glossary per organization, fixing key terms and tone | It belongs to each organization's copy |
| The organization's own MCP server | The pages and `catalog.json` may be enough. If not, a small server can serve the same files |
| The gallery as an application of its own | It is this demo, deployed behind the organization's identity proxy: people browse and ask their assistant by name. It is also a first real case for registration |
