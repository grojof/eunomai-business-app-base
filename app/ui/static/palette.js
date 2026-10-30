// The command palette: a native dialog that holds a combobox and its listbox. See ui/palette.html.
// Options come ready-made from the server, the first time it opens; here they are only filtered and ordered.
(() => {
  const dialog = document.getElementById("palette");
  if (!dialog) {
    return;
  }
  const input = dialog.querySelector("#palette-input");
  const results = dialog.querySelector("#palette-results");
  const empty = dialog.querySelector("[data-palette-empty]");
  const failed = dialog.querySelector("[data-palette-failed]");
  const count = dialog.querySelector("[data-palette-count]");
  const status = dialog.querySelector("[data-palette-status]");
  let loaded = false;
  let shown = [];
  let active = -1;

  // Apple's keyboards say Cmd, everyone else's Ctrl.
  if (/mac|iphone|ipad/i.test(navigator.userAgentData?.platform ?? navigator.platform)) {
    document.querySelectorAll("[data-shortcut]").forEach((key) => {
      key.textContent = "⌘ K";
    });
  }

  const plain = (text) =>
    text
      .normalize("NFD")
      .replace(/\p{Diacritic}/gu, "")
      .toLowerCase();

  // A smaller number comes first: the name itself, then how it starts, then a word in it, then anything else.
  function rank(option, words) {
    const label = plain(option.querySelector("[data-palette-label]").textContent);
    const everything = plain(option.dataset.search);
    if (!words.every((word) => everything.includes(word))) {
      return null;
    }
    const whole = words.join(" ");
    if (label === whole) {
      return 0;
    }
    if (label.startsWith(whole)) {
      return 1;
    }
    if (words.every((word) => label.split(/[\s/-]+/).some((part) => part.startsWith(word)))) {
      return 2;
    }
    return words.every((word) => label.includes(word)) ? 3 : 4;
  }

  function highlight(option, words) {
    const label = option.querySelector("[data-palette-label]");
    const text = label.textContent;
    const lowered = plain(text);
    const marks = [];
    for (const word of words) {
      const start = lowered.indexOf(word);
      // Folding accents can change a text's length; then it is left without a mark rather than marked wrongly.
      if (start >= 0 && lowered.length === text.length) {
        marks.push([start, start + word.length]);
      }
    }
    marks.sort((a, b) => a[0] - b[0]);
    const parts = [];
    let position = 0;
    for (const [start, end] of marks) {
      if (start >= position) {
        parts.push(text.slice(position, start));
        const mark = document.createElement("mark");
        mark.textContent = text.slice(start, end);
        parts.push(mark);
        position = end;
      }
    }
    parts.push(text.slice(position));
    label.replaceChildren(...parts);
  }

  function setActive(position) {
    shown[active]?.setAttribute("aria-selected", "false");
    active = shown.length ? position : -1;
    const option = shown[active];
    if (option) {
      option.setAttribute("aria-selected", "true");
      input.setAttribute("aria-activedescendant", option.id);
      option.scrollIntoView({ block: "nearest" });
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function filter() {
    const words = plain(input.value).split(/\s+/).filter(Boolean);
    shown = [];
    for (const group of results.querySelectorAll("[data-palette-group]")) {
      const options = [...group.querySelectorAll("[data-palette-option]")];
      const matches = [];
      options.forEach((option, order) => {
        const score = words.length ? rank(option, words) : 4;
        option.hidden = score === null;
        option.setAttribute("aria-selected", "false");
        highlight(option, words);
        if (score !== null) {
          matches.push([score, order, option]);
        }
      });
      matches.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
      group.append(...matches.map(([, , option]) => option));
      group.hidden = matches.length === 0;
      shown.push(...matches.map(([, , option]) => option));
    }
    empty.hidden = shown.length > 0 || !loaded;
    results.hidden = shown.length === 0;
    const text = dialog.dataset.results.replace("{count}", shown.length);
    count.textContent = text;
    status.textContent = text;
    active = -1;
    setActive(0);
  }

  async function load() {
    if (loaded) {
      return;
    }
    try {
      const response = await fetch(dialog.dataset.url);
      if (!response.ok) {
        throw new Error(String(response.status));
      }
      results.innerHTML = await response.text();
      loaded = true;
      failed.hidden = true;
    } catch {
      failed.hidden = false;
      results.hidden = true;
    }
  }

  async function open() {
    if (dialog.open) {
      return;
    }
    dialog.showModal();
    input.value = "";
    await load();
    if (loaded) {
      filter();
    }
  }

  document.addEventListener("keydown", (event) => {
    if (event.key.toLowerCase() === "k" && (event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey) {
      event.preventDefault();
      if (dialog.open) {
        dialog.close();
      } else {
        open();
      }
    }
  });
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-palette-open]")) {
      open();
    }
    if (event.target.closest("[data-palette-close]")) {
      dialog.close();
    }
  });
  input.addEventListener("input", filter);
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (shown.length) {
        const step = event.key === "ArrowDown" ? 1 : -1;
        setActive((active + step + shown.length) % shown.length);
      }
    } else if (event.key === "Enter" && shown[active]) {
      event.preventDefault();
      shown[active].click();
    }
  });
})();
