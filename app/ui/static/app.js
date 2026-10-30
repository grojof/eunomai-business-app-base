// After htmx replaces content, keep keyboard and screen-reader users in the right place.
// New content marks where focus goes with data-focus, and what to announce with data-announce.
document.addEventListener("htmx:afterSettle", (event) => {
  const content = event.detail.target;
  const announcement = content.querySelector("[data-announce]");
  if (announcement) {
    document.getElementById("announcements").textContent = announcement.dataset.announce;
  }
  content.querySelector("[data-focus]")?.focus();
  applyValues(content);
});

// What daisyUI writes inline, which the Content Security Policy refuses: style="--value" and onclick="showModal()".
function applyValues(root) {
  root.querySelectorAll("[data-value]").forEach((element) => {
    element.style.setProperty("--value", element.dataset.value);
  });
}
applyValues(document);
document.addEventListener("click", (event) => {
  const opener = event.target.closest("[data-dialog]");
  if (opener) {
    document.getElementById(opener.dataset.dialog).showModal();
  }
});

// Menus: Escape closes them and returns to their button; so does a click elsewhere.
document.addEventListener("keydown", (event) => {
  const menu = document.querySelector("details[data-menu][open]");
  if (event.key === "Escape" && menu) {
    menu.open = false;
    menu.querySelector("summary").focus();
  }
});
document.addEventListener("click", (event) => {
  const menu = document.querySelector("details[data-menu][open]");
  if (menu && !menu.contains(event.target)) {
    menu.open = false;
  }
});
