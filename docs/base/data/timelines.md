---
type: reference
title: Timelines
description: "How to show rows on a calendar as bars beside their table: the gantt macro"
tags: [base, data, timelines]
---

# Timelines

`app/core/gantt.py` and the macro `gantt` show rows on a calendar: a native table and, beside it, the same rows as bars,
drawn on the server as SVG. Planning's Timeline tab is it, on the same page of the same filtered and sorted rows as its
table: `show=timeline` and `scale` live in the address as filters the form keeps hidden.

| What | How |
|---|---|
| A task | `Task(key, label, start, end, kind, after)`: its first and last day, both included, a state's colour, and the tasks it waits for. A row with no dates has no bar, and `None` is a group's heading. A work order lasts its hours shared by its crew, in days of eight hours |
| Scale | All dates, the default, or days, weeks or months, from the address. All dates takes the finest scale that shows every task in 800 units, about what a wide screen leaves beside the table and a filter panel. A day is 32, 12 or 4 units wide; a week starts on Monday and a month on its first. A one-day task is never narrower than 6 units |
| Width | Never past 6,000 units: a scale that would be wider gives way to a coarser one, and past what months allow the picture is a window from the first task, with what starts after it counted and not drawn. A page of tasks from 2000 to 2099 at a scale of days was 2.8 MB, and is now well under 300 KB. Each of these is said above the picture, and so is a picture wider than its box, whatever the screen, so that nothing out of sight looks absent |
| What is drawn | Each bar, the weekends shaded at the scales of days and weeks, today as an upright line, months and their days above, and an arrow from a task to one that waits for it when both are on the page. Geometry is SVG attributes, colours are classes from the theme, and a month label that the next would cover gives way. A task's label goes after its bar, and the picture grows up to 240 units past its last day so the last ones fit; where it still would not, it goes inside a bar wide enough or before it, and only when no place holds it whole is it shortened, while the table keeps it whole. A browser test checks that no label ends past the picture or covers another, at every scale, in both themes, in compact density and at twice the text |
| Rows in line | Rows are 2.5rem in the table and in the picture, which is measured in rem, so a larger text, a compact density or 200 % zoom keeps each bar beside its row; a test measures it |
| Accessibility | The table is what a keyboard and a screen reader use, and it holds every action. The picture is a named image, described by the summary above it, with nothing to reach. Its box scrolls sideways and takes the keyboard |
| Editing | Through the row's Edit, the same dialog as the table's, and the timeline comes back in place |
| Paper | The picture goes under its table, as wide as the page |
| The one inline SVG | Icons and illustrations are never inline ([COMP-05 and SEC-16](../standards.md#components)). This is a chart of data, so `tools/icons.py` allows an SVG in this macro alone, and a test checks that what it draws holds nothing that runs or loads |
