// After htmx replaces content, keep keyboard and screen-reader users in the right place.
// New content marks where focus goes with data-focus, and what to announce with data-announce. htmx puts focus back on
// an element that kept its id; if none did, as when the Next link is gone on the last page, data-focus-fallback takes it.
// An outerHTML swap replaces its target, so what arrived is then the element the event comes from.
document.addEventListener("htmx:afterSettle", (event) => {
  const content = event.detail.target.isConnected ? event.detail.target : event.target;
  const announcement = content.querySelector("[data-announce]");
  if (announcement) {
    announce(announcement.dataset.announce);
  }
  upgradeComboboxes(content);
  settleDialog(content, event.detail.requestConfig?.elt);
  content.querySelector("[data-focus]")?.focus();
  if (document.activeElement === document.body) {
    content.querySelector("[data-focus-fallback]")?.focus();
  }
  applyStyles(content);
  showFilterPanels();
  noteWideTimelines();
});

// A timeline wider than its box says so, whatever the screen: what is out of sight must not look absent.
function noteWideTimelines() {
  document.querySelectorAll("[data-gantt-box]").forEach((box) => {
    const note = box.closest("[data-results], main")?.querySelector("[data-gantt-wider]");
    if (note) {
      note.hidden = box.scrollWidth <= box.clientWidth + 1;
    }
  });
}
addEventListener("load", noteWideTimelines);
addEventListener("resize", noteWideTimelines);

// A dialog whose body arrives with htmx opens then. `data-close-dialog` in what arrives closes it, and names where focus
// goes: the row that opened it was replaced, so the browser cannot return there by itself.
function settleDialog(content, opener) {
  const dialog = content.closest("dialog");
  if (!dialog) {
    return;
  }
  const done = content.querySelector("[data-close-dialog]");
  if (done) {
    const row = document.getElementById(done.dataset.closeDialog);
    dialog.close();
    content.replaceChildren();
    (row ?? document.querySelector("[data-focus-fallback]"))?.focus();
  } else if (!dialog.open && content.children.length) {
    opener?.focus(); // what has focus now is where the browser returns it, and not every browser focuses a clicked link
    dialog.showModal();
  }
}

// A request that fails says so, in words, in one place for every screen. An open dialog is in the browser's top layer,
// so the message goes inside it, or it would be behind it. role="alert" reads it out.
const requestProblem = document.getElementById("request-problem");
const PROBLEMS = { 403: "forbidden", 404: "gone", 409: "gone", 413: "tooLarge" };
function showProblem(kind) {
  (document.querySelector("dialog[open]") ?? document.body).append(requestProblem);
  requestProblem.querySelector("[data-problem-text]").textContent = requestProblem.dataset[kind];
  requestProblem.hidden = false;
}
function hideProblem() {
  requestProblem.hidden = true;
  document.body.append(requestProblem);
}
document.addEventListener("htmx:responseError", (event) => {
  showProblem(PROBLEMS[event.detail.xhr.status] ?? "failed");
});
document.addEventListener("htmx:sendError", () => showProblem("unreachable"));
document.addEventListener("htmx:beforeRequest", hideProblem);
document.addEventListener("click", (event) => {
  if (event.target.closest("[data-problem-close]")) {
    hideProblem();
  }
});
document.addEventListener("close", hideProblem, true);

// A list's filter panel. Its button says whether the panel is on screen, which on a narrow screen it is not until asked
// for, and a press asks the server for the other state: the address and every link of the list then keep it.
function showFilterPanels() {
  document.querySelectorAll("[data-filter-toggle]").forEach((button) => {
    const panel = document.getElementById(button.getAttribute("aria-controls"));
    button.setAttribute("aria-expanded", String(Boolean(panel?.checkVisibility())));
  });
}
showFilterPanels();
matchMedia("(width >= 80rem)").addEventListener("change", showFilterPanels);
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-filter-toggle]");
  if (button) {
    const address = button.getAttribute("aria-expanded") === "true" ? button.dataset.hide : button.dataset.show;
    if (button.closest("[hx-disable]")) {
      location.assign(address); // where htmx is turned off, as in the gallery, the page itself goes there
    } else {
      htmx.ajax("GET", address, { source: button, target: button.dataset.target });
    }
  }
});

// A message that came in the address is said once: a reload, or a change of theme, must not say it again.
// `data-once` names the parameters to take out. Without JavaScript they stay, and the message with them.
document.addEventListener("DOMContentLoaded", () => {
  const marked = document.querySelector("[data-once]");
  if (marked) {
    const address = new URL(location.href);
    marked.dataset.once.split(" ").forEach((name) => address.searchParams.delete(name));
    history.replaceState(history.state, "", address);
  }
});

function announce(text) {
  document.getElementById("announcements").textContent = text;
}

// What daisyUI writes inline, which the Content Security Policy refuses: style="..." and onclick="x.showModal()".
// A style set through the CSSOM is allowed, so data-style holds what the attribute would have held.
function applyStyles(root) {
  root.querySelectorAll("[data-style]").forEach((element) => {
    for (const declaration of element.dataset.style.split(/;(?![^(]*\))/)) {
      const colon = declaration.indexOf(":");
      if (colon > 0) {
        element.style.setProperty(declaration.slice(0, colon).trim(), declaration.slice(colon + 1).trim());
      }
    }
  });
}
applyStyles(document);
document.addEventListener("click", (event) => {
  const opener = event.target.closest("[data-dialog]");
  if (opener) {
    document.getElementById(opener.dataset.dialog).showModal();
  }
  const closer = event.target.closest("[data-dialog-close]");
  if (closer) {
    document.getElementById(closer.dataset.dialogClose).close();
  }
});

// Printing. Paper is white whatever the theme, and a browser leaves out backgrounds, so a dark theme's light text would
// vanish: the page wears the light theme for as long as it prints. daisyUI's theme controller wins over data-theme while
// it is checked, so for that time its inputs stop being controllers.
document.addEventListener("click", (event) => {
  if (event.target.closest("[data-print]")) {
    print();
  }
});
const page = document.documentElement;
let themeOnScreen;
let themeControllers = [];
addEventListener("beforeprint", () => {
  themeOnScreen = page.dataset.theme;
  page.dataset.theme = "light";
  themeControllers = [...document.querySelectorAll("input.theme-controller")];
  themeControllers.forEach((input) => input.classList.remove("theme-controller"));
});
addEventListener("afterprint", () => {
  themeControllers.forEach((input) => input.classList.add("theme-controller"));
  if (themeOnScreen) {
    page.dataset.theme = themeOnScreen;
  } else {
    delete page.dataset.theme;
  }
});

// Menus: Escape closes the innermost one and returns to its button; a click elsewhere closes them.
document.addEventListener("keydown", (event) => {
  const menus = document.querySelectorAll("details[data-menu][open]");
  if (event.key === "Escape" && menus.length) {
    const menu = menus[menus.length - 1];
    menu.open = false;
    menu.querySelector("summary").focus();
  }
});
document.addEventListener("click", (event) => {
  document.querySelectorAll("details[data-menu][open]").forEach((menu) => {
    if (!menu.contains(event.target)) {
      menu.open = false;
    }
  });
});

// Tabs, as the ARIA pattern says: one tab in the Tab order, arrow keys move between them.
function selectTab(tab) {
  const list = tab.closest("[role=tablist]");
  list.querySelectorAll("[role=tab]").forEach((other) => {
    const selected = other === tab;
    other.setAttribute("aria-selected", String(selected));
    other.tabIndex = selected ? 0 : -1;
    document.getElementById(other.getAttribute("aria-controls")).hidden = !selected;
  });
}
document.addEventListener("click", (event) => {
  const tab = event.target.closest("[role=tab]");
  if (tab) {
    selectTab(tab);
  }
});
document.addEventListener("keydown", (event) => {
  const tab = event.target.closest?.("[role=tab]");
  if (!tab) {
    return;
  }
  const tabs = [...tab.closest("[role=tablist]").querySelectorAll("[role=tab]")];
  const position = tabs.indexOf(tab);
  const next = {
    ArrowRight: tabs[(position + 1) % tabs.length],
    ArrowLeft: tabs[(position - 1 + tabs.length) % tabs.length],
    Home: tabs[0],
    End: tabs[tabs.length - 1],
  }[event.key];
  if (next) {
    event.preventDefault();
    selectTab(next);
    next.focus();
  }
});

// A copy button: data-copy names the element whose text it copies. Without a secure context the browser has no
// clipboard API, so a hidden text box does it the old way.
async function copyText(text) {
  if (navigator.clipboard) {
    return navigator.clipboard.writeText(text);
  }
  const box = document.createElement("textarea");
  box.value = text;
  box.setAttribute("readonly", "");
  box.classList.add("sr-only");
  document.body.append(box);
  box.select();
  document.execCommand("copy");
  box.remove();
}
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) {
    return;
  }
  const label = button.querySelector("[data-copy-label]");
  const idle = button.dataset.idle ?? label.textContent;
  button.dataset.idle = idle;
  await copyText(document.getElementById(button.dataset.copy).textContent);
  label.textContent = button.dataset.copied;
  announce(button.dataset.copied);
  setTimeout(() => {
    label.textContent = idle;
  }, 2000);
});

// A control that applies at once: its form goes to the server. `form` also finds a control placed outside the form with
// the form attribute. A search box sends itself while typing, so leaving it must not send it again.
document.addEventListener("change", (event) => {
  const form = event.target.form ?? event.target.closest("form");
  if (form?.matches("[data-autosubmit]") && event.target.type !== "search") {
    form.requestSubmit();
  }
});

// The page reloads after each preference, so focus comes back to the control that was used.
const FOCUS_KEY = "preference-focus";
function remember(value) {
  try {
    sessionStorage.setItem(FOCUS_KEY, value);
  } catch {
    // Without storage, focus starts from the top of the page: nothing breaks.
  }
}
function recall() {
  try {
    const value = sessionStorage.getItem(FOCUS_KEY);
    sessionStorage.removeItem(FOCUS_KEY);
    return value;
  } catch {
    return null;
  }
}
document.addEventListener("submit", (event) => {
  const place = event.target.dataset.preferences;
  if (place && !event.defaultPrevented) {
    const control = event.submitter ?? document.activeElement;
    remember(JSON.stringify([place, control?.name ?? "", event.submitter ? control.value : ""]));
  }
});
function restoreFocus() {
  const saved = recall();
  if (!saved) {
    return;
  }
  const [place, name, value] = JSON.parse(saved);
  const form = document.querySelector(`form[data-preferences="${CSS.escape(place)}"]`);
  if (!form) {
    return;
  }
  const controls = [...form.elements].filter((element) => element.name === name && element.type !== "hidden");
  const control =
    controls.find((element) => element.checked) ??
    controls.find((element) => element.value === value) ??
    controls[0];
  const menu = control?.closest("details");
  if (menu) {
    menu.open = true;
  }
  control?.focus();
}
restoreFocus();

// A two-state theme control shows what is on screen, also when the theme follows the system.
document.querySelectorAll("input[data-follows-system]").forEach((input) => {
  if (!document.documentElement.dataset.theme) {
    input.checked = matchMedia("(prefers-color-scheme: dark)").matches;
  }
});

// A searchable select: ARIA's editable combobox with a list. The select stays, hidden, and it is what the form sends; the
// input takes its id, so its label and the error summary's link land there. The select follows the box at every moment,
// so what is sent is always what is shown: text that matches no option goes as it is, in an option of its own, and the
// server refuses it. Nothing is dropped. What arrives in the template is what the macro wrote, so no class lives here.
// See `searchable_select` in ui/macros.html.
const plainText = (text) =>
  text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();

function upgradeCombobox(box) {
  const select = box.querySelector("select");
  const parts = box.querySelector("template").content.cloneNode(true);
  const input = parts.querySelector("[role=combobox]");
  const list = parts.querySelector("[role=listbox]");
  const popup = parts.querySelector("[data-combobox-popup]");
  const nothing = parts.querySelector("[data-combobox-none]");
  const toggle = parts.querySelector("[data-combobox-toggle]");
  const refused = parts.querySelector("[data-combobox-refused]");
  const typed = document.createElement("option");
  const identifier = select.id;
  const options = [...select.options].map((option, position) => {
    const item = document.createElement("li");
    const label = document.createElement("span");
    item.id = `${identifier}-option-${position}`;
    item.setAttribute("role", "option");
    item.setAttribute("aria-selected", "false");
    label.textContent = option.text;
    item.append(label);
    return { item, option, text: plainText(option.text) };
  });
  list.id = `${identifier}-options`;
  list.append(...options.map(({ item }) => item));
  input.setAttribute("aria-controls", list.id);
  for (const name of ["aria-describedby", "aria-invalid", "required"]) {
    if (select.hasAttribute(name)) {
      input.setAttribute(name, select.getAttribute(name));
    }
  }
  const describedBy = input.getAttribute("aria-describedby");
  const invalid = input.getAttribute("aria-invalid");
  select.removeAttribute("id");
  select.tabIndex = -1;
  select.hidden = true;
  input.id = identifier;
  refused.id = `${identifier}-refused`;

  let shown = options;
  let active = -1;
  let sent = select.value;

  function follow() {
    const text = input.value.trim();
    const plain = plainText(text);
    const match = options.find((entry) => (plain ? entry.text === plain : !entry.option.value));
    typed.remove();
    if (match) {
      select.value = match.option.value;
    } else {
      typed.value = text;
      typed.text = text;
      select.append(typed);
      typed.selected = true;
    }
    return match;
  }
  function report(wrong) {
    refused.hidden = !wrong;
    if (wrong) {
      input.setAttribute("aria-invalid", "true");
      input.setAttribute("aria-describedby", [describedBy, refused.id].filter(Boolean).join(" "));
      announce(refused.textContent.trim());
      return;
    }
    for (const [name, value] of [["aria-invalid", invalid], ["aria-describedby", describedBy]]) {
      if (value === null) {
        input.removeAttribute(name);
      } else {
        input.setAttribute(name, value);
      }
    }
  }
  function changed() {
    if (select.value !== sent) {
      sent = select.value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  input.value = box.dataset.typed ?? (select.value ? select.selectedOptions[0].text : "");
  follow();
  sent = select.value;

  function show(position) {
    shown[active]?.item.setAttribute("aria-selected", "false");
    active = position;
    const entry = shown[active];
    if (entry) {
      entry.item.setAttribute("aria-selected", "true");
      entry.item.scrollIntoView({ block: "nearest" });
      input.setAttribute("aria-activedescendant", entry.item.id);
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }
  function filter(words) {
    show(-1);
    shown = options.filter(({ item, text }) => {
      const matches = words.every((word) => text.includes(word));
      item.hidden = !matches;
      return matches;
    });
    list.hidden = shown.length === 0;
    nothing.hidden = shown.length > 0;
    announce(box.dataset.count.replace("{count}", shown.length));
  }
  const words = () => plainText(input.value).split(/\s+/).filter(Boolean);
  function open(everything = false) {
    filter(everything ? [] : words());
    popup.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }
  function close() {
    show(-1);
    popup.hidden = true;
    input.setAttribute("aria-expanded", "false");
  }
  function choose(entry) {
    input.value = entry.option.value ? entry.option.text : "";
    follow();
    close();
    report(false);
    changed();
  }
  // Leaving the field settles it: an option's own text if it is one, an empty box means nothing is chosen, and anything
  // else stays, with an error at the field.
  function settle() {
    if (active >= 0) {
      choose(shown[active]);
      return;
    }
    const match = follow();
    if (match) {
      choose(match);
    } else {
      close();
      report(true);
      changed();
    }
  }

  input.addEventListener("input", () => {
    follow();
    report(false);
    open();
  });
  input.addEventListener("blur", settle);
  input.addEventListener("keydown", (event) => {
    const isOpen = !popup.hidden;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (event.altKey) {
        (event.key === "ArrowDown" ? open : close)(true);
      } else {
        if (!isOpen) {
          open(input.value === select.selectedOptions[0]?.text);
        }
        const step = event.key === "ArrowDown" ? 1 : -1;
        const from = active < 0 && step < 0 ? 0 : active;
        if (shown.length) {
          show((from + step + shown.length) % shown.length);
        }
      }
    } else if (event.key === "Enter" && isOpen) {
      event.preventDefault();
      settle();
    } else if (event.key === "Escape") {
      if (isOpen) {
        event.preventDefault(); // otherwise a dialog around it would close too
        close();
      } else if (input.value) {
        event.preventDefault();
        input.value = "";
        follow();
        report(false);
      }
    }
  });
  toggle.addEventListener("click", () => {
    if (popup.hidden) {
      open(true);
    } else {
      close();
    }
    input.focus();
  });
  // Keeps focus in the box, so a click chooses before the box is settled. The list's scroll bar counts as the list.
  popup.addEventListener("mousedown", (event) => event.preventDefault());
  toggle.addEventListener("mousedown", (event) => event.preventDefault());
  list.addEventListener("click", (event) => {
    const item = event.target.closest("[role=option]");
    if (item) {
      choose(options.find((entry) => entry.item === item));
    }
  });
  select.after(parts);
  box.dataset.ready = "";
}
function upgradeComboboxes(root) {
  root.querySelectorAll("[data-combobox]:not([data-ready])").forEach(upgradeCombobox);
}
upgradeComboboxes(document);

// A date typed halfway reaches the form as nothing, and an optional date would then be cleared in silence. Its text cannot
// be read, so the server is told something it will refuse, and it asks for the date as for any other wrong value.
document.addEventListener("formdata", (event) => {
  event.target.querySelectorAll("input[type=date]").forEach((input) => {
    if (input.validity.badInput) {
      event.formData.set(input.name, "incomplete");
    }
  });
});

// A long navigation opens with the current page in sight.
const navigation = document.getElementById("navigation");
const currentLink = navigation?.querySelector("[aria-current]");
if (currentLink && navigation.scrollHeight > navigation.clientHeight) {
  navigation.scrollTop = currentLink.offsetTop - navigation.clientHeight / 2;
}

// The icons-only menu: each link's name shows beside it on hover and on keyboard focus, stays while the pointer moves
// onto it, and Escape hides it (WCAG 1.4.13). The link already has its name for a screen reader, so this one is hidden.
(() => {
  const tip = document.createElement("div");
  tip.className = "nav-tip";
  tip.setAttribute("aria-hidden", "true");
  tip.hidden = true;
  document.body.append(tip);
  const wide = matchMedia("(width >= 64rem)");
  const linkOf = (target) => (wide.matches ? target?.closest?.(".app-nav-compact a, .app-nav-compact button") : null);
  let leaving;
  const hide = () => {
    clearTimeout(leaving);
    tip.hidden = true;
  };
  const show = (link) => {
    clearTimeout(leaving);
    const box = link.getBoundingClientRect();
    tip.textContent = link.textContent.trim();
    tip.style.top = `${box.top + box.height / 2}px`;
    tip.style.left = `${box.right + 8}px`;
    tip.hidden = false;
  };
  document.addEventListener("pointerover", (event) => {
    const link = linkOf(event.target);
    if (link) {
      show(link);
    }
  });
  document.addEventListener("pointerout", (event) => {
    if (linkOf(event.target) && !tip.contains(event.relatedTarget)) {
      leaving = setTimeout(hide, 200);
    }
  });
  tip.addEventListener("pointerenter", () => clearTimeout(leaving));
  tip.addEventListener("pointerleave", hide);
  document.addEventListener("focusin", (event) => {
    const link = linkOf(event.target);
    if (link) {
      show(link);
    } else {
      hide();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      hide();
    }
  });
  document.addEventListener("htmx:beforeSwap", hide);
})();

// The side menu folds to its icons and back at once, and the server remembers it for the next page. Without this,
// its form sends the choice and the page comes back folded. Capturing, so it runs before focus is kept for a reload.
document.addEventListener(
  "submit",
  (event) => {
    const form = event.target.closest?.('form[data-preferences="navigation-fold"]');
    const menu = document.getElementById("navigation");
    if (!form || !menu) {
      return;
    }
    event.preventDefault();
    const folded = menu.classList.toggle("app-nav-compact");
    const button = form.querySelector("button");
    button.setAttribute("aria-pressed", String(folded));
    button.value = folded ? "side" : "compact";
    const data = new FormData(form);
    data.set("layout_navigation", folded ? "compact" : "side");
    fetch(form.action, { method: "POST", body: data, redirect: "manual", credentials: "same-origin" }).catch(() => {});
  },
  true,
);
