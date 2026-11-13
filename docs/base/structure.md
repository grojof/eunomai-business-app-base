---
type: reference
title: Structure
description: "What each folder of the repository holds: app/core, app/ui, app/brand, the demo, migrations, tools and tests"
tags: [base, structure]
---

# Structure

```text
app/
  core/      identity, roles, settings, database, exact column types, server lists, reading forms, languages, formatters, errors, health
  ui/        components: catalog.py, Jinja macros, settings, palette, the stylesheet's source, app.js, charts.js, board.js,
             calendar.js, vendored htmx, Chart.js, SortableJS and FullCalendar, Lucide's icons in templates/ui/icons/, illustrations in static/illustrations/
  brand/     theme.css with the light and dark themes and the fonts, logo.svg, fonts/, the organization's own icons in icons/
  demo/      screens, their fixed values, models and generated data, the gallery with its generated examples/, translations
locales/     the translations of core and ui
migrations/  Alembic: how it reaches the database, the template of a migration, and versions/
tests/
tools/       stylesheet, component pages, gallery data, translations, CLDR data, copied files, icon search and checks, dependency update, demo removal, an organization's template
docs/
  base/        this documentation, which every application keeps as it is
    components/  one page per component, generated, and catalog.json
```

Planned, and not there today:

| Folder | Contents | Arrives in |
|---|---|---|
| `deploy/` | Example service files and the [registration](registration.md#registration) file | Milestone 6 |
