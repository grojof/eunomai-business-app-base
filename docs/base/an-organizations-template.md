---
type: reference
title: An organization's template
description: "How an organization's layer and tools/make_template.py make the application template IT starts each project from"
tags: [base, an-organizations-template]
---

# An organization's template

An organization keeps a small layer, and `tools/make_template.py` makes its application template from the base and that
layer. The template is what IT starts each project from; nobody edits it by hand.

```bash
uv run --frozen python tools/make_template.py --layer ../our-layer --out ../our-template --ref <a tag of the base>
```

| Part | What it holds |
|---|---|
| `layer.toml` | `name`, which applications show until they are given their own; `languages`, kept besides English; `default_language`, optional |
| `files/` | Copied onto the template, under `app/brand/` (themes, logo, fonts, icons) and a CI folder (`.gitea/`, `.github/`, `.forgejo/`) only. A file anywhere else is refused, before anything is written |

Each run starts from an empty folder, or from a clone of the template's repository with nothing uncommitted, which keeps
its history. It exports the base at `--ref`, or this folder as it is without one, runs `tools/remove_demo.py` with the
layer's languages, leaves out the base's own workflows, changelog and security policy (the licence and the third-party
notices stay), copies the layer, writes the name into `.env.example` and the
preview, builds the stylesheet, runs the icon and translation checks and the template's own tests, unless
`--skip-tests`, and writes `.template-source`: the base's commit and the layer's hash. It never commits or pushes. A
person reviews the difference in the clone and merges it through a pull request.

| Decision | Why | Instead of |
|---|---|---|
| The template is made, never edited | Every fix of the base reaches the organization by running the tool again, and the pull request shows exactly what changed. The same base and layer give the same files | A copy edited by hand, where each fix is repeated by hand and the two drift apart; a fork that merges the base, where each merge meets the files `remove_demo.py` deleted |
| The layer writes only its brand and its CI | What it may change is short and reviewable; anything else is a change to the base, made once for every organization | A layer that patches any file, which would break with the next version of the base |
| The base's workflows stay out | They maintain the base on GitHub, with a weekly dependency job no application needs; each organization's CI depends on its server and its runners | Shipping them to every project, where they queue forever without runners or repeat the base's work every day |
| The name goes into `.env.example` and the preview | Local work and a preview show the organization's name; production sets `APP_NAME` as it sets everything else | Changing the settings' default in the code |
