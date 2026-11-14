---
type: reference
title: "Decisions: Components and the gallery"
description: "Why daisyUI with Tailwind, macros over classes, the component pages and their list, and how the gallery shows daisyUI's examples."
tags: [decisions, components]
---

# Components and the gallery

| Decision | Why | Rejected |
|---|---|---|
| Tailwind with daisyUI, as a recommended layer | Components with free customisation: a utility overrides a component without fighting global styles. Themes are variables, and daisyUI's generator writes them. No Node: one executable, checked by hash, and the generated CSS is committed. Both are MIT; no paid part is used | Bootstrap: its look and global styles force custom classes for anything different. Writing every component by hand: all behaviour and accessibility to maintain |
| Screens call macros, not daisyUI classes | An organization can replace the CSS library in `app/ui/` without touching a screen | Classes written directly in each screen |
| Component documentation split into small pages by a script | About 375 tokens per component against 20,000 for the whole file. The official file has a regular structure, so it can be cut at its headings. Whatever code can do with certainty is not left to an assistant | Reading the whole file each time; pages written by hand |
| `llms.txt` rebuilt from the version's git tag | The site serves only the latest, so a download could not be repeated for a pinned version. The hash of the site's build file guards the recipe: if it changes, a person compares them | Downloading it from the site: its bytes change with no version to pin |
| `app/ui/catalog.py` as the one list of components | The gallery, the documentation, `catalog.json` and the search cannot disagree, and it survives deleting the demo | A list in the demo |
| daisyUI held back when its new files break `docs/base/components/` or the gallery | Whether a new component is good for applications is a person's decision, and it must not delay a security update elsewhere. All of daisyUI's files stay at their version, an issue says why, the rest goes ahead | Stopping the whole update |
| A class with no CSS counts as invented | Tailwind generates only what exists, so the check covers daisyUI and Tailwind alike, for the classes it can read | Comparing with daisyUI's class lists, which would not cover Tailwind |
| What daisyUI writes inline moves to `app.js` | `style="..."` and `onclick` break the Content Security Policy. `data-style` goes through the CSSOM, which the policy allows | Weakening the policy |
| The gallery is generated from daisyUI's documentation source | 590 official examples cannot be kept by hand, and a new version must update them by itself. The source is pinned to daisyUI's version and hash-checked, and one tested function changes the examples. The pages' structure is checked by the parser, not by a hash of daisyUI's renderer: a refactor there must not hold daisyUI back, a changed page must | Specimens written by hand, which showed a fraction of each component; downloading from daisyui.com, which serves only the latest |
| `llms.txt` for assistants, the documentation source for the gallery | They have different jobs: the first is short and cut into pages to read, the second has every example with its translations | One source for both: `llms.txt` has a handful of examples, the documentation is too long to read |
| One gallery, no separate catalogue | Two lists of components disagree. Our macros appear on the pages of their components | A *Component catalogue* page beside the gallery |
| Accessibility scan as a gate on real screens, not on official examples | Examples are reference material, published by someone else, and hiding the ones that fail would hide what daisyUI offers. Available says so: it is not a promise. Screens are what people use, so they stay gated | Keeping the scan on the gallery, which decided what could be shown and left it half empty |
| Example previews fixed to their box with `contain: layout` | One rule keeps dock, FAB, toast and drawer inside, for every example, with no change to what is published. A native dialog stays in the top layer: containing it would stop it being modal | Wrappers per example, as daisyUI's site writes by hand; opening dialogs as non-modal |
| Copied code is the transformed code | It works here as it is. The published form breaks the policy, and daisyUI's site is one click away | Showing the published code, then running something else |
| daisyUI's `theme-controller` inside a form, moved to Available | daisyUI says to save its state yourself, and a form does: the class changes the theme at once, the server saves it. On its own it still saves nothing and has no *system*, so its note stays. Not Approved until a person reviews it | Our own control with the same looks, which would show less of what daisyUI offers |
| Examples that use Tailwind's own colours stay without them, and say so | The palette stays out of the stylesheet so that a screen cannot use it. Bringing it back for 19 examples would undo that rule | Restoring the palette in the demo |
