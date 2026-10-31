---
type: reference
title: "Description list"
description: "A list of terms and their values, for one record's details."
tags: [component, data-display, available]
---

# Description list

**Status:** available. **Category:** data-display. **In the demo:** `/gallery/description-list`.

A native `<dl>`, in two columns where there is room. daisyUI has no component for this. Each term and value is an `(term,
description)` pair, and a description can be another macro's result.

```jinja
{{ description_list([(_("Location"), _(item.location)), (_("State"), status_label(label, kind))]) }}
```

Use it for the fields of one record. For many records, use a table.
