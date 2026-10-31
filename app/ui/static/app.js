// After htmx replaces content, keep keyboard and screen-reader users in the right place.
// New content marks where focus goes with data-focus, and what to announce with data-announce. htmx puts focus back on
// an element that kept its id; if none did, as when the Next link is gone on the last page, data-focus-fallback takes it.
document.addEventListener("htmx:afterSettle", (event) => {
  const content = event.detail.target;
  const announcement = content.querySelector("[data-announce]");
  if (announcement) {
    announce(announcement.dataset.announce);
  }
  settleDialog(content);
  content.querySelector("[data-focus]")?.focus();
  if (document.activeElement === document.body) {
    content.querySelector("[data-focus-fallback]")?.focus();
  }
  applyStyles(content);
});

// A dialog whose body arrives with htmx opens then. `data-close-dialog` in what arrives closes it, and names where focus
// goes: the row that opened it was replaced, so the browser cannot return there by itself.
function settleDialog(content) {
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
    dialog.showModal();
  }
}

// A request that fails says so, in words, in one place for every screen. An open dialog is in the browser's top layer,
// so the message goes inside it, or it would be behind it. role="alert" reads it out.
const requestProblem = document.getElementById("request-problem");
const PROBLEMS = { 403: "forbidden", 404: "gone", 409: "gone" };
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
  if (place) {
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

// A long navigation opens with the current page in sight.
const navigation = document.getElementById("navigation");
const currentLink = navigation?.querySelector("[aria-current]");
if (currentLink && navigation.scrollHeight > navigation.clientHeight) {
  navigation.scrollTop = currentLink.offsetTop - navigation.clientHeight / 2;
}
