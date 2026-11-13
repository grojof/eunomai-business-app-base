---
type: reference
title: Command palette
description: "The search box opened with Ctrl+K: what it finds, filtered by role, and how to register more with register_search"
tags: [base, command-palette]
---

# Command palette

Ctrl+K, Cmd+K or the header's search button open a native `<dialog>` with the ARIA combobox and listbox pattern: arrow
keys, Enter, Escape, focus returned, grouped results, a state for no results, by click and by touch, translated. It is
part of the shell, so every application has it, and it calls no service: `/search` gives the options, ready-made and
already filtered by role, the first time it opens, and `palette.js` filters them in the page.

It finds navigation items, the settings menu, and whatever is registered:

```python
register_search(application.state, lambda: [SearchItem(_("Invoices"), "/invoices", _("Records"), _("Sent and paid"))])
```

The function runs inside each request, so it can use the person's language. The demo registers every component this way,
with daisyUI's translated names and descriptions, and its class names as keywords.
