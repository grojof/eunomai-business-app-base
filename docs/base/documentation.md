---
type: reference
title: Documentation
description: "How the documentation is arranged: the base's in docs/base, an application's own pages, frontmatter and links"
tags: [base, documentation]
---

# Documentation

The base's documentation is in `docs/base/`, and an application keeps it there as it is: it is how the base works,
which whoever builds a screen reads, offline. An application documents itself apart from it.

| Part | Where | Rule |
|---|---|---|
| The base's reference | `docs/base/`: the [specification](specification.md), an index of one page per topic, the [standards](standards.md), the [decisions](decisions.md), the component pages | An application never edits it: an update of its organization's template replaces it. Its pages link to it instead of restating it. Each page says in its `description` what it holds, so a reader or an assistant opens the page and the section a link names, not all of them |
| The application's map | `README.md`, which `tools/remove_demo.py` writes with places to fill in | What the application is, for whom and why, a diagram where it helps, how to run it and its tests, and a link to every page |
| The application's pages | Any other file under `docs/`, in the application's documentation language | Each starts with frontmatter, `type` (`tutorial`, `how-to`, `reference`, `explanation` or `decision`), `title`, `description` and, if it has them, `tags`: lowercase words joined by hyphens, on one line. What the business said has a page per kind, marked by a tag: `context`, `glossary`, `decision`, `open-question`. The README reaches every page, directly or through the page a folder is named after: a page that grows becomes the index of a folder of its name. When behaviour changes, the page and the README change with it |

`tests/test_docs.py` checks every relative link of `README.md`, `AGENTS.md` and `docs/`, headings included, and, in an
application, each page's frontmatter and its link from the README.

| Decision | Why | Instead of |
|---|---|---|
| The base's pages under `docs/base/`, in the base itself | Every path in code, tools and tests stays the same in an application, with nothing rewritten when the demo goes. What is the base's and what is the application's is plain from the path | Moving them when the demo goes: rewriting paths in code and tests, a fragile step. Leaving them in `docs/`: an application's own pages drowned among a thousand lines that are not about it |
| Frontmatter on an application's pages, checked by a test | A page says what it is for, a reader and an assistant find it from the README, and nothing needs Node to check it | No check: pages nobody reaches |
