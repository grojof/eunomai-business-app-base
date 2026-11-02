---
type: reference
title: "Event calendar"
description: "Events by month, week or agenda, drawn by FullCalendar, each a link to its form."
tags: [component, data-display, available]
---

# Event calendar

**Status:** available. **Category:** data-display. **In the demo:** `/gallery/event-calendar`, and the calendar at
`/calendar`. daisyUI's [`calendar`](calendar.md) is something else: the look of a date picker.

The server owns the events and the words; FullCalendar 7, vendored and pinned, draws them by month, week or agenda in
the application's time zone. `app/core/calendars.py` gives `CalendarEvent`, whose JSON carries moments in UTC,
`Period` for the view and the day in the address, `read_moment` and `read_day` for what a drop sends, and
`calendar_config` for everything `calendar.js` needs, words included.

```python
config = calendar_config(
    "/calendar/events", "/calendar/move", zone, Period.read(params, today), today, can_edit(request)
)
```

```jinja
{{ calendar("calendar", _("Visits and work orders"), config, agenda, steps) }}
```

| What | How |
|---|---|
| Words | Every word FullCalendar shows or announces comes from this base's catalogue, through one locale object of ours: its own Spanish and Catalan files are not used. Each hint holds its button's words, as WCAG 2.5.3 asks |
| Address | `view` and `date` are read on loading and written back with every change, so a reload or a shared link opens the same days |
| Time zone | Events travel in UTC and show in `APP_TIME_ZONE`, whatever the browser's; a drop sends its moment with its offset, and `read_moment` reads it into UTC |
| Moving | A drop is a POST of the event, its new start and its version; the route checks the role and the version and answers with what to say, and a refusal puts the event back and says why. Each event is a link to its form, the keyboard's way to move it |
| Theme | FullCalendar's classic theme on daisyUI's colours, through its own variables, following a change of theme without a reload. Events are a soft fill with the page's text, which passes the contrast check in both themes |
| Without JavaScript | The `agenda` the route writes, by day, with `steps` to other days and views. It stays if the library cannot load |
| htmx | A calendar that htmx brings is drawn again, and one it removes is taken down |
| Limits | `Limits(earliest, latest, longest)`, 2000 to 2099 and 62 days unless an application passes its own; a view at the edge may ask a little past them |
