---
type: reference
title: "Field error"
description: "What is wrong with one field, and how to fix it, tied to that field."
tags: [component, data-input, available]
---

# Field error

**Status:** available. **Category:** data-input. **In the demo:** `/gallery/field-error`.

Every field macro writes it from its `error` argument, between the hint and the control, and ties it to the control
with `aria-describedby`, beside `aria-invalid`. It has an icon and words, so it does not depend on colour.

```jinja
{{ field_error(identifier, error) }}
```

Say what to do, as [USE-02](../standards.md#usability) asks: *Enter the hours as a number, such as 7.50*, not *Invalid
value*.
