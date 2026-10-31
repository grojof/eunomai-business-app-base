---
type: reference
title: "Error summary"
description: "Every problem of a form in one place, each a link to its field."
tags: [component, data-input, available]
---

# Error summary

**Status:** available. **Category:** data-input. **In the demo:** `/gallery/error-summary`.

GOV.UK's pattern: at the top of a form that comes back, with focus on it, so a screen reader reads it at once. Each
line is a link to its field, in the order of the page, and uses the same words as the error beside the field.

```jinja
{% if errors %}{{ error_summary(_("Check what you entered"), summary) }}{% endif %}
```

`summary` is a list of (field's identifier, error).
