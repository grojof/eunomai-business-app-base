---
type: reference
title: "Number field"
description: "Text a person types as their language writes numbers. Never a float."
tags: [component, data-input, available]
---

# Number field

**Status:** available. **Category:** data-input. **In the demo:** `/gallery/number-field`.

`number_field` is a text box with the right keyboard on a phone: `decimals=0` asks for a whole number. It is never
`type="number"`, which refuses a decimal comma in some browsers, sends the browser's own form, and lets a mouse wheel
change a value in passing. The server reads it with `read_decimal` or `read_whole`, from `app/core/forms.py`, through
`parse_decimal`, so `1234,5` is a number in Spanish and an error in English, and nothing becomes a float.

```jinja
{{ number_field("hours", _("Hours"), values.hours, "field-hours", error=errors.get("hours", ""), required=true) }}
{{ number_field("crew", _("People needed"), values.crew, "field-crew", decimals=0, error=errors.get("crew", ""), required=true) }}
```
