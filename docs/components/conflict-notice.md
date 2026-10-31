---
type: reference
title: "Conflict notice"
description: "Says that someone else saved first, and what they saved, above what was typed."
tags: [component, feedback, available]
---

# Conflict notice

**Status:** available. **Category:** feedback. **In the demo:** `/gallery/conflict-notice`.

The form comes back with what was typed, and this at the top, with focus on it. `changes` is a list of (label, what is
saved now), for the fields that differ from what the person sent, so they can decide without another screen. The
[specification](../specification.md#two-people-on-one-row) says how a route finds out.

```jinja
{% if conflict %}{{ conflict_notice(title, advice, conflict) }}{% endif %}
```
