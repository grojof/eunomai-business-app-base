// Calendars. The server sends events and every word; FullCalendar draws them in the application's time zone. The
// view and the day live in the address. A drop is a POST of the same fields a form would send, and the server decides:
// if it refuses, the event goes back and the reason is said. Each event is a link to its form, the keyboard's way to
// move it. Without JavaScript, or if the library cannot load, the agenda the server wrote stays.
(() => {
  const VIEWS = { month: "dayGridMonth", week: "timeGridWeek", agenda: "listWeek" };
  const NAMES = Object.fromEntries(Object.entries(VIEWS).map(([name, view]) => [view, name]));
  const UNITS = { dayGridMonth: "month", timeGridWeek: "week", listWeek: "list" };
  const DAY = /^\d{4}-\d{2}-\d{2}$/;
  const mounted = new Map();
  let library = null;

  function load(src, integrity) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.integrity = integrity;
      script.crossOrigin = "anonymous";
      script.onload = resolve;
      script.onerror = reject;
      document.head.append(script);
    });
  }

  // The library, then its theme, which reads the library as it starts.
  function loadLibrary(box) {
    library ??= load(box.dataset.calendarLibrary, box.dataset.calendarIntegrity).then(() =>
      load(box.dataset.calendarTheme, box.dataset.calendarThemeIntegrity),
    );
    return library;
  }

  const fill = (text, values) => text.replace(/%\((\w+)\)s|\{(\w+)\}/g, (_, named, braced) => values[named ?? braced]);

  // A whole locale of ours: FullCalendar's own Spanish and Catalan files are not used.
  function localeOf(words) {
    return {
      code: words.code,
      week: { dow: 1, doy: 4 },
      ...Object.fromEntries(
        [
          "prevText", "nextText", "todayText", "prevYearText", "nextYearText", "yearText", "monthText", "weekTextLong",
          "weekTextShort", "dayText", "listText", "allDayText", "timedText", "moreLinkText", "noEventsText", "closeHint",
          "eventsHint", "viewChangeHint",
        ].map((name) => [name, words[name]]),
      ),
      prevHint: (_text, unit) => words.prevHint[unit] ?? words.prevText,
      nextHint: (_text, unit) => words.nextHint[unit] ?? words.nextText,
      todayHint: (_text, unit) => words.todayHint[unit] ?? words.todayText,
      viewHint: (text, view) => words.viewHint[UNITS[view]] ?? text,
      navLinkHint: (day) => fill(words.navLinkHint, { date: day }),
      moreLinkHint: (count) => (count === 1 ? words.moreLinkHintOne : fill(words.moreLinkHint, { n: count })),
    };
  }

  function announce(text) {
    document.getElementById("announcements").textContent = text;
  }

  // The address says what is on screen, so a reload or a shared link opens the same days.
  function remember(calendar) {
    const address = new URL(location.href);
    address.searchParams.set("view", NAMES[calendar.view.type] ?? "month");
    address.searchParams.set("date", calendar.formatIso(calendar.getDate()).slice(0, 10));
    if (address.href !== location.href) {
      history.replaceState(history.state, "", address);
    }
  }

  async function moved(config, info) {
    const { event } = info;
    const form = new URLSearchParams({
      ...config.extra,
      event: event.id,
      start: event.startStr,
      end: event.endStr,
      version: String(event.extendedProps.version),
    });
    try {
      const response = await fetch(config.move, { method: "POST", body: form, headers: { Accept: "application/json" } });
      const answer = await response.json();
      if (!response.ok) {
        throw new Error(answer.message);
      }
      event.setExtendedProp("version", answer.version);
      announce(answer.message);
    } catch (error) {
      info.revert();
      announce(error.message || config.words.refused);
    }
  }

  function mount(box) {
    const host = box.querySelector("[data-calendar-host]");
    const config = JSON.parse(box.querySelector('script[type="application/json"]').textContent);
    const asked = new URLSearchParams(location.search);
    const day = DAY.test(asked.get("date") ?? "") ? asked.get("date") : config.date;
    // The macro names the classes, where the stylesheet's generator looks: frame, button, event, more, dot, popover.
    const [frame, button, item, more, dot, popover] = box.dataset.calendarClasses.split(" ");
    const calendar = new FullCalendar.Calendar(host, {
      locale: localeOf(config.words),
      timeZone: config.timeZone,
      initialView: VIEWS[asked.get("view")] ?? VIEWS[config.view],
      initialDate: day,
      headerToolbar: { start: "prev,next today", center: "title", end: "dayGridMonth,timeGridWeek,listWeek" },
      events: Array.isArray(config.events) ? config.events : { url: config.events, extraParams: config.extra },
      editable: config.canMove,
      eventDurationEditable: false,
      slotMinTime: config.hours[0],
      slotMaxTime: config.hours[1],
      eventAllow: (drop, event) => drop.allDay === event.allDay,
      dayMaxEvents: 3,
      eventMinHeight: 24,
      navLinks: false,
      height: "auto",
      class: frame,
      buttonClass: button,
      eventClass: item,
      moreLinkClass: more,
      listItemEventBeforeClass: dot,
      popoverClass: popover,
      eventDidMount: (info) => {
        info.el.dataset.kind = info.event.extendedProps.kind;
      },
      datesSet: () => remember(calendar),
      eventDrop: (info) => moved(config, info),
    });
    calendar.render();
    mounted.set(box, calendar);
    box.querySelector("[data-calendar-fallback]").hidden = true;
    document.documentElement.dataset.calendarReady = "";
  }

  async function start(root) {
    const found = [...root.querySelectorAll("[data-calendar]")];
    if (root.matches?.("[data-calendar]")) {
      found.push(root);
    }
    const boxes = found.filter((box) => !mounted.has(box));
    if (!boxes.length) {
      return;
    }
    try {
      await loadLibrary(boxes[0]);
    } catch {
      return; // the agenda the server wrote stays
    }
    boxes.forEach((box) => {
      try {
        mount(box);
      } catch (error) {
        console.warn("A calendar could not be drawn: its agenda stays", error);
      }
    });
  }

  start(document);
  document.addEventListener("htmx:afterSettle", (event) =>
    start(event.detail.target.isConnected ? event.detail.target : event.target),
  );
  document.addEventListener("htmx:beforeCleanupElement", (event) => {
    const calendar = mounted.get(event.detail.elt);
    if (calendar) {
      calendar.destroy();
      mounted.delete(event.detail.elt);
    }
  });
})();
