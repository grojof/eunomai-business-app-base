---
type: reference
title: "Standards: Components"
description: "The rules components follow, each with its source and check."
tags: [components, standards]
---

# Components

| ID | Rule | Source | Check |
|---|---|---|---|
| COMP-01 | The catalogue lists every official component, plus an organization's own, each of those with a hand-written page; official pages match the official file. These pages are a reference for assistants; the gallery's examples come from daisyUI's documentation source | [daisyUI llms.txt](https://daisyui.com/llms.txt) | Automatic |
| COMP-02 | Every component has a page with frontmatter and a description; each official page shows its status; one with problems says why | Project decision | Automatic |
| COMP-03 | The gallery shows every component with its status and every official example, counted from daisyUI's documentation, and generated data matches that documentation. A macro appears on the page of its component | Project decision | Automatic |
| COMP-04 | A class in use must exist, read from real pages, macro arguments, `{% set %}` values and the catalogue; values such as `[color:#ff0000]` are refused. Component classes outside what Tailwind reads are caught; Tailwind utilities in Python files are not | Project decision | Automatic |
| COMP-05 | An icon comes from Lucide's pinned set or the organization's own, only through the `icon` macro: no SVG is drawn inline in a template, code, script or stylesheet, and no SVG file lies outside its place. Every name a template or the code asks for exists, no name is in both sets, and the organization's icons are drawn like Lucide's: 24 by 24, in `currentColor`, with no colour, style, id or size of their own. The one exception is the `gantt` macro's picture, a chart of data drawn on the server, which holds nothing that runs or loads either: see [Timelines](../data/timelines.md#timelines) | Project decision | Automatic |
