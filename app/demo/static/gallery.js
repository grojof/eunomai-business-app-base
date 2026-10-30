// The gallery's own behaviour. It goes with the demo.

// The index: a live filter over the cards.
const filter = document.querySelector("[data-gallery-filter]");
if (filter) {
  const cards = [...document.querySelectorAll("[data-gallery-card]")];
  const sections = [...document.querySelectorAll("[data-gallery-section]")];
  const count = document.querySelector("[data-gallery-count]");
  const empty = document.querySelector("[data-gallery-empty]");
  const plain = (text) =>
    text
      .normalize("NFD")
      .replace(/\p{Diacritic}/gu, "")
      .toLowerCase();
  const initial = count.textContent;
  filter.addEventListener("input", () => {
    const words = plain(filter.value).split(/\s+/).filter(Boolean);
    let shown = 0;
    for (const card of cards) {
      const text = plain(card.dataset.search);
      card.hidden = !words.every((word) => text.includes(word));
      shown += card.hidden ? 0 : 1;
    }
    for (const section of sections) {
      section.hidden = !section.querySelector("[data-gallery-card]:not([hidden])");
    }
    empty.hidden = shown > 0;
    count.textContent = words.length ? count.dataset.template.replace("{count}", shown) : initial;
  });
}

// A component's page: the index beside it marks the example in view.
const index = document.querySelector("[data-gallery-index]");
if (index && "IntersectionObserver" in window) {
  const links = new Map([...index.querySelectorAll("a")].map((link) => [link.hash.slice(1), link]));
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        const link = links.get(entry.target.id);
        if (entry.isIntersecting) {
          link?.setAttribute("aria-current", "location");
        } else {
          link?.removeAttribute("aria-current");
        }
      }
    },
    { rootMargin: "-20% 0px -70% 0px" },
  );
  for (const id of links.keys()) {
    observer.observe(document.getElementById(id));
  }
}

// Examples are not forms or links to anywhere: trying one must not leave the page.
document.addEventListener("click", (event) => {
  if (event.target.closest?.('[data-official] a[href="#"]')) {
    event.preventDefault();
  }
});
document.addEventListener("submit", (event) => {
  if (event.target.closest("[data-official]") && event.target.method !== "dialog") {
    event.preventDefault();
  }
});
