---
type: reference
title: "Date field"
description: "The browser's own date field, read by the server in one strict form."
tags: [component, data-input, available]
---

# Date field

**Status:** available. **Category:** data-input. **In the demo:** `/gallery/date-field`.

`date_field` is an `input_field` with `type="date"`, and `earliest` and `latest` become its `min` and `max`. The
browser shows the date as the person's system writes it and sends `YYYY-MM-DD`, the one form `parse_date` reads, so a
value never depends on a language. The server decides: `read_date` in `app/core/forms.py`.

```jinja
{{ date_field("planned_on", _("Planned for"), values.planned_on, "field-planned", error=errors.get("planned_on", ""), required=false) }}
```

A date typed halfway reaches a form as nothing, which would clear an optional date in silence. `app.js` tells the server
instead, and the server asks for the date.
