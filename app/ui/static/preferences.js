// An application exported as files has no server to remember a person's theme and language: the browser keeps them.
// Only such an application loads this, in the head and not deferred, so the kept theme is on the page before anything
// is painted. See docs/base/a-static-application.md. A browser that refuses storage still works: nothing is kept.
(() => {
  const page = document.documentElement;
  const THEMES = ["light", "dark"];
  function kept(name) {
    try {
      return localStorage.getItem(name);
    } catch {
      return null;
    }
  }
  function keep(name, value) {
    try {
      localStorage.setItem(name, value);
    } catch {
      // Without storage the choice lasts for this page: nothing breaks.
    }
  }

  // The site's first page: each language is a folder, and a person goes to theirs. Their own choice first, then the
  // first of the browser's languages that is offered, by its whole tag and then by its language alone, then the default.
  if (page.dataset.languages) {
    const offered = page.dataset.languages.split(" ");
    const wanted = [kept("language"), ...(navigator.languages ?? [navigator.language])].filter(Boolean);
    const lowered = (tag) => tag.toLowerCase();
    const primary = (tag) => lowered(tag).split("-")[0];
    let chosen;
    for (const tag of wanted) {
      chosen =
        offered.find((language) => lowered(language) === lowered(tag)) ??
        offered.find((language) => primary(language) === primary(tag));
      if (chosen) {
        break;
      }
    }
    location.replace(`/${chosen ?? page.dataset.defaultLanguage}/${location.search}${location.hash}`);
  }

  // The theme a person chose, before the page is painted. Without a choice, the browser's own preference applies.
  const theme = kept("theme");
  if (THEMES.includes(theme)) {
    page.dataset.theme = theme;
  }

  // Every copy of the control says the same: daisyUI's theme controller wins over the page's theme while it is checked,
  // so a copy left behind would change the page back. A two-state control without a choice shows the system's theme.
  function show(chosen) {
    document.querySelectorAll("[data-theme-control] input.theme-controller").forEach((input) => {
      if (input.type === "checkbox") {
        input.checked = THEMES.includes(chosen) ? chosen === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      } else {
        input.checked = input.value === chosen;
      }
    });
    document.querySelectorAll("[data-theme-icon]").forEach((icon) => {
      icon.hidden = icon.dataset.themeIcon !== chosen;
    });
  }
  document.addEventListener("DOMContentLoaded", () => show(THEMES.includes(theme) ? theme : "system"));
  document.addEventListener("change", (event) => {
    const input = event.target;
    if (!input.matches?.("[data-theme-control] input.theme-controller")) {
      return;
    }
    const chosen = input.type === "checkbox" ? (input.checked ? "dark" : "light") : input.value;
    keep("theme", chosen);
    if (THEMES.includes(chosen)) {
      page.dataset.theme = chosen;
    } else {
      delete page.dataset.theme;
    }
    show(chosen);
  });

  // A language chosen by its link is the one the first page goes to next time.
  document.addEventListener("click", (event) => {
    const link = event.target.closest?.("[data-language-control] a[hreflang]");
    if (link) {
      keep("language", link.hreflang);
    }
  });
})();
