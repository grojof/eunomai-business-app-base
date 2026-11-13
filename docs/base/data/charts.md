---
type: reference
title: Charts
description: "How to draw a chart: the numbers worked out on the server, the chart macro, its table and its colours"
tags: [base, data, charts]
---

# Charts

`app/core/charts.py` makes what a figure shows, and the macro `chart` draws it: a `<figure>` with its title and summary, a
canvas, and always the same numbers as a table. A route works out the numbers and passes them as `Decimal`. They travel
to the browser as text, as JSON in a `<script type="application/json">`, which nothing runs, so no float appears on the
server. `app/ui/static/charts.js` reads that JSON and loads Chart.js, once, with its integrity, when a page has a chart.

```python
data = chart_data(months, [Series(_("Planned"), planned), Series(_("Worked"), worked)], _("Month"), unit=_("h"))
```

```jinja
{{ chart(_("Hours planned and worked"), _("Hours worked stayed within 6 % of the plan."), data, "bar", "chart-hours") }}
```

| What | How |
|---|---|
| Types | `bar`, `stacked`, `line`, `area`, `pie`, `doughnut`, `radar`, `scatter`, `bubble`, `mixed` and `polar`. Scatter and bubble use `point_data`. Polar area is drawn and tested, and left out of the gallery: it says what a pie or a bar says, less well, because area grows with the square of the value |
| One axis | A mixed chart has one scale. Two measures of different size are two charts |
| Colours | Read from the theme's CSS variables, and turned to rgb by painting one pixel, because the themes use oklch and Chart.js cannot mix that. Series take `primary`, `accent`, `secondary`, `info`, in that order. A fifth series is refused: it should be another chart. `success`, `warning` and `error` are for states. `neutral` is left out: on the dark theme it cannot be told from the page |
| A change of theme | Colours follow with no reload, whether the system changes, `data-theme` does or a theme control does. A series hidden in the legend stays hidden |
| Hover | On bars and lines, the `index` interaction and a thin guide line on the month, from a small plugin of ours. On pie and doughnut the slice grows, with `hoverOffset` |
| Language | Numbers in tooltips and axes use the page's locale through `Intl`, and large axes use its compact form. Chart.js has no text of its own on these charts: every word comes from the server, translated |
| Motion | None if a person asks for `prefers-reduced-motion` |
| Without the picture | Without JavaScript the canvas is hidden and the summary and table remain. If Chart.js fails to load, or one chart fails to draw, its table opens by itself, and no other chart stops |
| What is refused | A colour outside the list and a negative value in a pie, a doughnut or a polar area are errors on the server, while the code is written. Chart.js would draw the negative as positive |
| Choosing | Optional. `links` in `chart_data`, one address of the application per label, make the table's first column links, and a click on a bar or a slice follows the link of its row: the pointer and the keyboard go to the same place, through the same element. The cursor says a part can be chosen. Each link is a path of the application, checked by the same rule as every other way back, so `//` and `/\` are refused. With `into`, a list on the same page, htmx sends that list's form with the values that change from link to link in place of the form's own, so the other filters and the order stay and the list changes in its place. The dashboard's states lead to the equipment list, and the equipment page's two charts filter it |
| On a phone | Every label that fits stays. When they do not all fit they spread evenly and the first and the last always stay, which Chart.js's own thinning does not promise: it left out October. A chart keeps its height |

daisyUI's colours pass the checks for colour blindness (neighbouring series stay apart) and normal vision, on both
themes. `accent` and `warning` are light, at 1.9:1 against white, under the 3:1 of A11Y-14. The base keeps the themes as
they come, so the legend, the summary and the table carry what those marks cannot. An organization can solve it in its
theme.
