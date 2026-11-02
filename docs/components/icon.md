---
type: reference
title: "Icon"
description: "Any of Lucide's icons, or one of the organization's, hidden from screen readers."
tags: [component, data-display, available]
---

# Icon

**Status:** available. **Category:** data-display. **In the demo:** `/gallery/icon`.

The one way to show an icon. The macro includes that one icon's SVG in the page, inside a box that gives it its size and
hides it from screen readers, so the words beside it carry the meaning. Buttons, links, stats and empty states take an
icon's name and call it themselves.

```jinja
{{ icon("truck") }}
{{ icon("truck", "size-4") }}
{{ button(_("Print"), name="printer") }}
```

## Finding one

Every icon of [Lucide](https://lucide.dev/icons/) is in the repository, about 1,900 of them, and the search works
without network. It reads each icon's name, Lucide's own tags and categories, Lucide's old names, and a list of common
business words in Spanish and Catalan kept in `tools/icon-synonyms.json`:

```bash
uv run --frozen python tools/icons.py search camión
uv run --frozen python tools/icons.py search albarà
uv run --frozen python tools/icons.py search "orden de trabajo"
```

Lucide's tags are in English: alone they find the right icon for 3 of our 108 Spanish words and 4 of 108 Catalan
ones. A word the search does not know is a reason to add it to `tools/icon-synonyms.json`, pointing at icons that exist: a
test checks that.

## Where icons come from

| Source | Where | Rule |
|---|---|---|
| Lucide | `app/ui/templates/ui/icons/`, with its index in `tools/lucide/index.json` | Pinned in `vendor.json`: a file added, changed or removed fails `tools/vendor.py check`. Never edit it |
| The organization | `app/brand/icons/`, with an optional `tags.json` in the index's form | 24 by 24 viewBox, drawn with `currentColor`, no colour, `style`, `id` or size of its own. `tools/icons.py check` names the file and the reason |

A name is in one source only: the check refuses an organization's icon with a name Lucide has, so nothing is replaced
in silence. For the organization's own version of a concept, use another name, such as `truck-ours`, and say in its tags
what it is for.

Never draw an icon inline, and never use another collection: a test refuses an `<svg>` in a template, code, script or
stylesheet, an SVG file outside these places, and a name that does not exist. Illustrations are not icons: they are
files in `app/ui/static/illustrations/`, shown with `<img>`, as
[the specification](../specification.md#icons-and-illustrations) says.
