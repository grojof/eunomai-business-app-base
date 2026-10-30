---
type: reference
title: Decisions
description: "Why business-app-base is built the way it is, what was rejected, and the questions still open."
tags: [decisions]
related: [specification.md, standards.md]
---

# Decisions

| Decision | Why | Rejected |
|---|---|---|
| Clone and own, not a dependency | Each organization and application is free to change anything, with nothing to stay tied to | A versioned component package: updates reach everyone, but it ties applications to the package and limits changes |
| One repository is both demo and starting point | Simple: clone it and delete one folder | A separate demo and template: two things to keep in step |
| The demo is deleted, the components stay | An application keeps no screens it does not use, and a small set of macros costs little | Copying components on demand: slower, and easy to miss one |
| Built from zero against published standards | Existing applications differ from each other, so copying them would copy the differences | Deriving the component list from existing applications |
| Pages made on the server | One language, no build step and a small supply chain; AI assistants produce reviewable code | A React client: a large npm tree, and more than most internal applications need |
| Language support from the first screen | Adding it later touches every text | Single language first |
| Checks over instructions | Long instructions are followed unevenly; a failing check is not | Extensive rule documents |
| `AGENTS.md` and few skills | The rules and procedures work with any assistant, and can be removed freely | Binding the repository to one assistant or method |

## Open questions

| Question | How it is settled |
|---|---|
| Does Tabulator pass with keyboard and screen reader? | Test it in milestone 2. If not, use the server table with row editing, and accept losing grouping or build it on the server |
| Are ECharts' keyboard and screen-reader options enough? | Test it in milestone 2. The text summary and data table are required either way |
| How does focus behave across htmx swaps? | Define one pattern in milestone 1 and test it in every component |
| Which translation tool do translators use? | Files in git work for developers; decide if non-developers translate |
| Does the dependency workflow run on other git servers? | It is written for GitHub Actions; test it on the first clone hosted elsewhere |
| Which licence, when it goes public? | MIT or Apache 2.0. Without a licence, nobody may legally reuse it |
| Do project skills load in every assistant? | Test before relying on them; the rules live in `AGENTS.md` and `docs/` |
| Which fields does the registration file need? | Milestone 5, against a real platform |
