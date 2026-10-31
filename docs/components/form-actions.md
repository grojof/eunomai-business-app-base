---
type: reference
title: "Form actions"
description: "The main action of a form, the way out, and anything else at the far end."
tags: [component, data-input, available]
---

# Form actions

**Status:** available. **Category:** data-input. **In the demo:** `/gallery/form-actions`.

The submit button first, the way out beside it, and what the caller adds at the far end, out of the way. `loading` is
what the button says while htmx is sending the form. In a dialog, use `dialog_buttons`.

```jinja
{% call form_actions(_("Save"), back, _("Cancel"), loading=_("Saving…")) %}
{{ link_button(_("Delete"), delete_address, "danger") }}
{% endcall %}
```
