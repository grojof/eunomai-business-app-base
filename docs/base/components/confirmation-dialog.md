---
type: reference
title: "Confirmation dialog"
description: "Asks before an action that cannot be undone, and names what will be lost."
tags: [component, actions, available]
---

# Confirmation dialog

**Status:** available. **Category:** actions. **In the demo:** `/gallery/confirmation-dialog`.

A native `<dialog>` with `role="alertdialog"`. The link that opens it is a real link: with htmx its address fills the
dialog, and without JavaScript the same address is a page of its own, with the same words and the same form. So the
route answers one address in two ways, as the [planning editor](../data/groups-and-editing-a-row.md#groups-and-editing-a-row) does.

```jinja
{{ confirm_link(_("Delete"), address, "confirm") }}
{{ dialog("confirm", _("Close"), alert=true) }}
```

```jinja
{# In the dialog #}
{{ confirmation("confirm", title, consequence, lost, _("Delete it"), _("Keep it"), action, fields) }}
{# As a page #}
{{ confirmation("confirm", title, consequence, lost, _("Delete it"), _("Keep it"), action, fields, back=address, level=1) }}
```

| What | How |
|---|---|
| What will be lost | `lost` names it, as [USE-04](../standards.md#usability) asks. Say what is in this row, not *Are you sure?* |
| Focus | Starts on the way out, so Enter does not delete by accident. The browser gives it back to the link when it closes |
| Keyboard | The browser keeps it inside, and Escape closes it |
| The action | A plain POST, in the dialog too: a whole new page answers, with a message, and no focus is left to look after |

The buttons name the action, *Delete it* and *Keep it*, rather than *Yes* and *No*.
