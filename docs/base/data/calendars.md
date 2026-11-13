---
type: reference
title: Calendars
description: "How to show events by month, week or agenda with the calendar macro, over what the server sends"
tags: [base, data, calendars]
---

# Calendars

`app/core/calendars.py`, the macro `calendar` and `calendar.js` show events by month, week or agenda, drawn by
FullCalendar 7.1.3 over what the server sends. The demo's calendar, at `/calendar`, holds the inspection team's visits,
at their times, and the planned work orders, over their days. The [component page](../components/event-calendar.md) says
what each part does.

| What | How |
|---|---|
| Views | Month, with multi-day events as one bar and, past three, a "+ more" link to the agenda of that week, which lists everything: FullCalendar's own box lay over the month and hid part of the events under it, by an amount that depended on the font, so it failed WCAG 2.5.8 on Linux and passed on Windows; week, with events at the same time side by side and the working hours of `hours`; agenda |
| Address | `view` and `date`, read on loading and written back with every change |
| Time zone | Events travel as JSON with moments in UTC and show in `APP_TIME_ZONE`, whatever the browser's. A drop sends its moment with its offset, and `read_moment` reads it into UTC: a test drags an event in a browser set to New York on a server in Madrid. A visit's form reads wall-clock times: one the clocks skip is refused and says why, one that happens twice is its first, and the end is compared with the start in UTC. The feed looks back as far as the longest work order can last |
| Moving | By dragging, which the server decides on: role, a moment it can read, and the version, so a move after someone else's is refused, put back and said. A drop moves a visit and keeps its length, whatever end it sends, and only a planned work order moves. An answer that is not the route's JSON, such as a proxy's error page, is said in the calendar's own words. By keyboard, through each event's link: a visit has a form of its own, a work order the planning editor. A timed event cannot become all-day, nor the reverse |
| Words | Every word FullCalendar shows or announces is ours, through one locale object built from the catalogue; its own locale files are not used, because its Spanish said "Vista del semana" and its "Hoy" was named "Este mes". A hint holds its button's words, as WCAG 2.5.3 asks |
| Accessibility | No failure of the scan in month, week, agenda and after "+ more", in both themes and three languages, also with a fallback font forced, which is how a Linux machine's fonts were reproduced on Windows. Events and "+ more" are 24 pixels high at least, and events are a soft fill with the page's text, so they pass in the dark theme too, without turning any check off |
| Theme | FullCalendar's classic theme reads its own variables, set from daisyUI's colours, so it follows a change of theme with no reload. Its classes are hashed, so nothing else of it is styled here |
| Without JavaScript | The agenda the route writes, by day, with links to other days and views. It stays if the library cannot load |
| htmx | A calendar that htmx brings is drawn again, as the location filter does, and one it removes is taken down |
| A phone | The toolbar wraps and the page never scrolls sideways |
| Limits | `Limits`: the days a calendar accepts, by default 2000 to 2099, and the longest range of events asked for at once, 62 days. A view at the edge asks for a little past them, as January 2000's month asks from 27 December 1999, and gets it. An application whose dates go further passes its own |
