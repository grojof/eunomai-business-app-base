---
type: reference
title: Documentation for assistants
description: "The per-component reference pages for assistants, cut from daisyUI's documentation, and how to read only what is needed"
tags: [base, documentation-for-assistants]
---

# Documentation for assistants

An assistant should load only what it needs. The pages below come from daisyUI's `llms.txt` and are a reference for
assistants; the [gallery](gallery.md#gallery)'s examples come from daisyUI's documentation source. `tools/components.py` cuts
`llms.txt`, about 20,000 tokens, into one page per component of about 375 tokens on average, counting 4 characters per token, each with OKF-style
frontmatter. Nothing is interpreted: the file is cut at its headings, and a test fails if a page drifts from it.

| File | Read |
|---|---|
| `docs/base/components/README.md` | First: what exists, with its status and use |
| `docs/base/components/rules.md` | Once: how classes and colours are used |
| `docs/base/components/<name>.md` | Only for the components in use |
| `docs/base/components/catalog.json` | The same list, for programs |

daisyui.com serves only the latest `llms.txt`, so `tools/vendor.py` rebuilds it from the files at the version's git tag,
the way the site builds it. For the pinned version, the result is identical to the site's file. If the site's build file
changes, the hash in `vendor.json` refuses the rebuild until a person has compared the two.

The generator stops rather than guesses, in each of these cases:

| Case | Why it needs a person |
|---|---|
| A component in the official file but not in `app/ui/catalog.py` | Its status is a decision |
| A generated page whose component left the official file | It is stale |
| A hand-written page on an official name | Generating would overwrite it |
| A catalogue entry with no official section and no page of its own | There is nothing to read |
| A page with no description, or an official section with no description or documentation link | The index would be empty, or the format changed. A description may be plain or quoted YAML |

Where daisyUI's text disagrees with this repository, such as its advice to use a CDN or `npm`, this repository wins, and
each page says so.
