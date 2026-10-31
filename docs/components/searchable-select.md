---
type: reference
title: "Searchable select"
description: "A list to type in, by keyboard, that is a plain select without JavaScript."
tags: [component, data-input, available]
---

# Searchable select

**Status:** available. **Category:** data-input. **In the demo:** `/gallery/searchable-select`.

`searchable_select` writes a plain `<select>`, which is what a person gets without JavaScript. `app.js` puts ARIA's
[editable combobox with a list](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/) in its place. The select stays
underneath, hidden, and it is what the form sends, so the server sees the same field either way.

```jinja
{{ searchable_select("fault", _("Fault"), options, values.fault, "field-fault", every=_("Not known"), required=false) }}
```

| Key | What it does |
|---|---|
| Typing | Narrows the list; accents and capitals do not matter |
| Down, Up | Open the list and move through it |
| Alt+Down, Alt+Up | Open or close the list without moving |
| Enter | Chooses the option, and closes the list |
| Escape | Closes the list, and leaves the text; pressed again, empties the box |
| Tab | Chooses the option the arrows are on, and leaves |

The select follows the box at every keystroke, so a form sends what the box shows. Leaving the box settles it: an
option's own text if it is one, empty means nothing is chosen, and anything else stays, with an error at the field. If
the form is sent like that, the text goes as it is and the server refuses it, which is the check that counts.
All options are in the page, so a list must fit there, up to some hundreds. A list of 50,000 needs another answer: the
demo's work order asks for the equipment's code instead.
