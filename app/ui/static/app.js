// After htmx replaces content, keep keyboard and screen-reader users in the right place.
// New content marks where focus goes with data-focus, and what to announce with data-announce.
document.addEventListener("htmx:afterSettle", (event) => {
  const content = event.detail.target;
  const announcement = content.querySelector("[data-announce]");
  if (announcement) {
    document.getElementById("announcements").textContent = announcement.dataset.announce;
  }
  content.querySelector("[data-focus]")?.focus();
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
