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
