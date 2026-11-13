---
type: reference
title: Dependencies
description: "How the base's dependencies are kept current and audited: the weekly workflow, pins, hashes and the rules for a new one"
tags: [base, dependencies]
---

# Dependencies

A weekly workflow keeps the base's dependencies current, on GitHub; an organization's template leaves the base's workflows out, and its layer brings its own CI if it wants one. It updates to the newest version the rules
allow, runs the tests and proposes one pull request, which a person merges. While a problem remains, an issue stays
open. *Reported* below means exactly that: the problem goes to the issue, the version stays and the update goes on.

| Rule | Python packages, `uv.lock` | Copied files, `vendor.json` |
|---|---|---|
| Known vulnerability | Moves to the newest version without one; if none exists, or the limits refuse it, Reported | A vulnerable version is never chosen; if nothing else qualifies, Reported |
| Pre-release | Reported if locked | Never chosen |
| Yanked | Reported if locked | Not checked: npm has no such state |
| Deprecated | Not checked: PyPI has no such state | Never chosen; Reported if it is the current version and nothing newer qualifies |
| Released less than two weeks ago | Waits, unless it fixes a vulnerability in the locked version | Waits, unless it fixes a vulnerability in the current version and every settled newer version has one too |
| No release in three years | Reported, unless listed in `EXCEPTIONS` in `tools/update_dependencies.py` | Not checked |
| No `https` address in its published metadata | Reported, unless listed in `EXCEPTIONS` in `tools/update_dependencies.py` | Not checked |
| New major version | Never automatic for a direct dependency: `pyproject.toml` sets its upper limit, except for tzdata, whose versions are dates. A package only others need moves as far as they allow | Never automatic: it takes a decision, as htmx 4 does |
| Older version | Not checked | Never: a file stays where it is rather than go back |

If a new daisyUI file breaks `docs/base/components/` or the [gallery](gallery.md#gallery), such as a new or removed component or a
changed format, every daisyUI file stays at its version, an issue says why, and everything else goes ahead. They move
together or not at all, and so do Lucide's icons and their index. A Lucide version that would remove an icon is
refused, because a screen may use it: a person decides. One that renames an icon goes ahead, since Lucide still ships
the old name and `tools/icons.py check` tells a screen that asks for it its new one. A person holds a copied file back
with `"held": {"below": "<version>", "reason": "..."}` in its entry of `vendor.json`; every weekly summary repeats the
reason, so the hold stays a decision someone keeps making. Any failed update opens the issue too. The job that
runs upgraded code can only read; a separate job, which runs no project code, opens the pull request, and accepts only
the files the update produces.

Each copied file is pinned, and the same version with different bytes is refused:

| File | Pinned by |
|---|---|
| A package from npm | The integrity the registry publishes |
| Tailwind's executables | The release's `sha256sums.txt` |
| daisyUI's `.mjs` files | A hash recorded on first download: daisyUI publishes no checksum for them |
| daisyUI's `llms.txt` | A hash of what [the rebuild](documentation-for-assistants.md#documentation-for-assistants) gives |
| daisyUI's documentation source | A hash of the file collected from the version's tag, for the [gallery](gallery.md#gallery) |
| Lucide's icons | The integrity npm publishes for `lucide-static`, then one hash of the whole folder: every file's name and content |
| Lucide's index | A hash of the file collected from the version's tag: Lucide publishes no checksum for it |

A new version of any of these files is accepted on the two-week rule. Its checksum proves it is what was published, not
that it is good, and the `.mjs` files do not have even that.

The PostgreSQL image the tests run on is pinned by digest in `tests.yml`, at the newest one past the two weeks. No
workflow moves it: a person does.
