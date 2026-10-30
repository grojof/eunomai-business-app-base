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
| Pages made on the server | One language, no npm and a small supply chain; AI assistants produce reviewable code | A React client: a large npm tree, and more than most internal applications need |
| Tailwind with daisyUI, as a recommended layer | Components with free customisation: a utility overrides a component without fighting global styles. Themes are variables, and daisyUI's generator writes them. No Node: one executable, checked by hash, and the generated CSS is committed. Both are MIT; no paid part is used | Bootstrap: its look and global styles force custom classes for anything different. Writing every component by hand: all behaviour and accessibility to maintain |
| Screens call macros, not daisyUI classes | An organization can replace the CSS library in `app/ui/` without touching a screen | Classes written directly in each screen |
| Component documentation split into small pages by a script | About 375 tokens per component against 20,000 for the whole file. The official file has a regular structure, so it can be cut at its headings. Whatever code can do with certainty is not left to an assistant | Reading the whole file each time; pages written by hand |
| `llms.txt` rebuilt from the version's git tag | The site serves only the latest, so a download could not be repeated for a pinned version. The hash of the site's build file guards the recipe: if it changes, a person compares them | Downloading it from the site: its bytes change with no version to pin |
| `app/ui/catalog.py` as the one list of components | The gallery, the documentation and `catalog.json` cannot disagree, and it survives deleting the demo | A list in the demo |
| daisyUI held back when its new file breaks `docs/components/` | Whether a new component is good for applications is a person's decision, and it must not delay a security update elsewhere. daisyUI stays at its version, an issue says why, the rest goes ahead | Stopping the whole update |
| A class with no CSS counts as invented | Tailwind generates only what exists, so the check covers daisyUI and Tailwind alike, for the classes it can read | Comparing with daisyUI's class lists, which would not cover Tailwind |
| What daisyUI writes inline moves to `app.js` | `style="--value"` and `onclick` break the Content Security Policy | Weakening the policy |
| Native browser features for menus: `popover` and `details` | Escape, focus and outside clicks with almost no JavaScript | daisyUI's hidden-checkbox drawer, whose button cannot be reached by keyboard |
| Tailwind's own palette removed, invented values refused by a test | Colours exist only in the brand; an organization wanting more freedom removes the test | Trusting each author |
| Language support from the first screen | Adding it later touches every text | Single language first |
| UTC as the default time zone | The base belongs to no place; an application sets its own in `APP_TIME_ZONE` | The time zone of whoever wrote it |
| Checks over instructions | Long instructions are followed unevenly; a failing check is not | Extensive rule documents |
| `--no-proxy-headers` as a flag on the start command | Uvicorn reads it before the application loads, so no code setting can reach it. Forgetting it fails closed, with 401 for everyone, and a test checks every documented command | A start script of our own: one more file, for one flag |
| `ONLY_ON_DEMO` rows become *By hand* in a clone | Deleting the demo deletes their only proof, and *Automatic* must keep meaning a test exists | Leaving them *Automatic*, which the tracing test would refuse; keeping demo tests in every application |
| `AGENTS.md`, and skills only if a procedure needs one | The rules and procedures work with any assistant, and can be removed freely | Binding the repository to one assistant or method |
| Rules in one page, each with its official source and its check | Quality follows published standards, not an assistant's judgement, and every rule can be traced to its test. What no source requires says *Project decision* | Sources kept in skills: they load only sometimes and can be removed |
| Themes set by the server | No JavaScript: without a choice, the browser's own preference applies | A script reading the preference |
| Translations read directly from `.po` files | Nothing to compile | Compiled `.mo` files |
| Browser tests on the installed Chrome | Nothing is downloaded | Playwright's own browsers |
| Babel for formats and translations | Pure Python, one dependency for both jobs, and the usual choice for Python web applications | PyICU: closer to CLDR, but it has no ready package, must be compiled on each server, ties its version to the system, and handles no `.po` files |
| CLDR's `minimumGroupingDigits` applied through Babel's own `group_separator` | The standard says 1250 and 12.500 in Spanish, and Babel ignores that field. The values come from Unicode's data for the CLDR version Babel uses (`tools/cldr_grouping.py`), and a test fails if they part ways. Delete it if Babel adds support | A list written by hand, which was wrong for regional variants; accepting the difference, which only affects how numbers look |
| Decimal context sized to each value | Python's default of 28 digits, or any fixed limit, cuts longer values without an error | A fixed precision |

## Open questions

| Question | How it is settled |
|---|---|
| Does Tabulator pass with keyboard and screen reader? | Test it in milestone 2. If not, use the server table with row editing, and accept losing grouping or build it on the server |
| Are ECharts' keyboard and screen-reader options enough? | Test it in milestone 2. The text summary and data table are required either way |
| Which translation tool do translators use? | Files in git work for developers; decide if non-developers translate |
| Can a person open a server running inside an assistant's sandbox? | Not documented. Until tested, the assistant shows results as screenshots or a self-contained HTML file |
| Does generating the stylesheet in an assistant's sandbox work under every organization's network rules? | Confirmed only [as far as the executable starting](specification.md#stack), on one account. Generate a full stylesheet there |
| Does the dependency workflow run on other git servers? | It is written for GitHub Actions; test it on the first clone hosted elsewhere |
| Is it worth buying ISO 9241-110 to compare the usability rules with it? | Not needed to work: no rule uses it. An organization that must show ISO conformance would buy it |
| Which licence, when it goes public? | MIT or Apache 2.0. Without a licence, nobody may legally reuse it |
| Do project skills load in every assistant? | The repository has none. Test before relying on them; the rules live in `AGENTS.md` and `docs/` |
| Which fields does the registration file need? | Milestone 5, against a real platform |
