---
type: reference
title: "Chart"
description: "A figure with its text summary and its data as a table, drawn with Chart.js."
tags: [component, data-display, available]
---

# Chart

**Status:** available. **Category:** data-display. **In the demo:** `/gallery/chart`.

The [specification](../specification.md#charts) says how it works and which types to use.

```python
data = chart_data(months, [Series(_("Planned"), planned), Series(_("Worked"), worked)], _("Month"), unit=_("h"))
```

```jinja
{{ chart(_("Hours planned and worked"), _("Hours worked stayed within 6 % of the plan."), data, "bar", "chart-hours") }}
```

The summary is required, and says what the chart shows, not what it is. Every figure brings its table, so a person who
cannot see the canvas misses nothing.
