---
type: reference
title: Gallery
description: "The gallery at /gallery: every daisyUI component, live in the current theme, to see and ask for by name"
tags: [base, gallery]
---

# Gallery

There is one gallery, at `/gallery`: every free daisyUI component, live and in the current theme, so a person can see what
is available and ask for it by name.

| Page | Shows |
|---|---|
| `/gallery` | Each component as a card with a small live example, by category, with its status and a live filter |
| `/gallery/<name>` | Name, description, status and note, our macro where there is one, the class table by group, then every official example with a Preview and Code switch and a copy button. Previous and next component, and on wide screens an index of the page |

| Status | Meaning |
|---|---|
| Approved | Our macro, tests and a review. This is what applications should use. Today: `alert`, `button` and `card` |
| Available | An official example, shown as published, not audited by us. It is not a promise of accessibility |
| Decorative | Not meant for management applications |
| Not recommended | Fails a standard, or has a better option in this base; its note states why |

A macro can exist before its component is approved: `badge`, `progress`, `stat`, `steps` and `table` have tests and are on
the dashboard, and wait for a person's review.

`app/ui/catalog.py` is the one list. It survives deleting the demo, and it feeds the gallery, the documentation and
`catalog.json`.

## Where the examples come from

Nothing in the gallery is written by hand, so a new daisyUI version updates it by itself. daisyUI's documentation pages,
at the version's git tag, hold 68 components and 590 `html` examples, and daisyUI publishes translations of them.
`tools/vendor.py` collects them into `tools/tailwind/daisyui-docs.json`, pinned in `vendor.json` at daisyUI's own version.
`tools/gallery.py` turns that file into `app/demo/examples/`: for each component its title, description, class tables and
every example, with the Spanish and Catalan daisyUI publishes, and daisyUI's MIT notice beside them. `tools/gallery.py
check` fails if that folder is out of date.

daisyUI translates nearly all descriptions and most class descriptions, but only a few example titles. Text it leaves in
English stays in English, marked with `lang="en"`. Text inside an example is left as published, as is its language.

`transform`, in `tools/gallery.py`, is the only place an example changes, and always so that it runs under the Content
Security Policy, which is not weakened for it:

| In the official example | In the gallery |
|---|---|
| `$$`, a placeholder for a class prefix | Removed |
| An image on another server | A local neutral placeholder under `app/ui/static/placeholders/`, keeping its size and classes |
| `style="..."`, or a `<style>` inside an SVG | `data-style`, applied by `app.js` through the CSSOM |
| `onclick="x.showModal()"`, `x.close()` | `data-dialog`, `data-dialog-close`, handled by `app.js` |
| A repeated id, radio group or anchor name on a page | A new name, with `for`, `popovertarget`, `aria-*`, links and calls in step |
| A `<script>` | Shown as code with a note, not run. Its text keeps the address it was published with |
| The year its documentation computes in place | `YYYY` |

The Code tab shows, and the copy button copies, the transformed code: what ran is what a person gets, and it works here.
What is fixed to the screen (dock, FAB, toast, drawer, a modal without `<dialog>`) stays inside its preview box, because
the box contains layout. A native `<dialog>` or popover opens in the browser's top layer, over the page, as a modal should.

Tailwind's own colours are [removed from this base](decisions.md), so an example that uses them, such as
`checked:bg-blue-200`, shows the theme's colour instead, and says so. Theme names other than `light` and `dark` are not in
the stylesheet, so `theme-controller` examples for them do nothing visible.

The generator stops rather than guess, and the update then holds daisyUI back:

| Case | Why it needs a person |
|---|---|
| A page with no frontmatter, title, description or class table, or a line it cannot read | The format changed |
| An example heading with no `html` block, a block with no heading, or two under one heading | The format changed |
| A documentation page with no place in `app/ui/catalog.py` | Its status is a decision |
| An inline handler other than `showModal` and `close`, an address on another server that is not an image, or a `<style>` it cannot move | It would break the policy |
