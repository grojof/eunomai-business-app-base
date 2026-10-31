---
type: reference
title: "Filter bar"
description: "A plain form that filters a list on the server. daisyUI's filter is a set of radio buttons."
tags: [component, data-input, available]
---

# Filter bar

**Status:** available. **Category:** data-input. **In the demo:** `/gallery/filter-bar`.

A GET form with a search box and one select per `Filter` of a `ListView`, from `app/core/tables.py`. With JavaScript, htmx
sends it as it changes and replaces only the results. Without it, an Apply button appears and the form works alone. The
[specification](../specification.md#lists-on-the-server) describes the whole list.

```jinja
{{ filter_bar(view) }}
```

daisyUI's own [`filter`](filter.md) is something else: a group of radio buttons with a reset button.
