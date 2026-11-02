---
type: reference
title: "Gantt"
description: "A table and, beside it, the same rows as bars on a calendar, drawn on the server."
tags: [component, data-display, available]
---

# Gantt

**Status:** available. **Category:** data-display. **In the demo:** `/gallery/gantt`, and Planning's Timeline tab.

A native table and, beside it, a picture of the same rows on a calendar: each task a bar from its first day to its last,
the weekends shaded, today marked, and an arrow from a task to the one that waits for it. `timeline` in
`app/core/gantt.py` lays it out on the server, at a scale of days, weeks or months, or `fit`, the finest that shows
every task without scrolling, and never wider than 6,000 units: past that the scale coarsens, then the picture is a
window from the first task and counts what it leaves out, and says so; the macro writes the geometry as SVG
attributes and the colours as classes, read from the theme. Nothing runs in the browser.

```python
plan = timeline([None, Task(order.id, order.title, start, end, "info", (order.after_id,)), ...], "week", today)
```

```jinja
{% call gantt("planning-timeline", caption, plan, [(_("Work"), false), (_("Starts"), true)], summary) %}
<tbody>...one row per task, and a rowgroup heading for each None...</tbody>
{% endcall %}
```

Each label goes after its bar, inside it when there is no room after and the bar is wide enough, or before it, and
the picture leaves room past its last day for the last labels. Only a label no place can hold is shortened.

The table is what a keyboard and a screen reader use, and it holds every action, as editing. The picture is named by
the summary written above it, and holds nothing to reach. Rows are 2.5rem in both, and the picture is measured in rem,
so a larger text or a compact density keeps them in line. Its box scrolls sideways by itself, and on paper the picture
goes under its table, as wide as the page.

It is the one SVG drawn inline in this base: a chart of data, not an icon or an illustration. `tools/icons.py` allows it
in this macro alone, and a test checks that what it draws holds nothing that runs or loads, as
[COMP-05 and SEC-16](../standards.md#components) ask of every other SVG.
