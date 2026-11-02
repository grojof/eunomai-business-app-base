// Boards. The server draws the cards, and each card's form moves it, by keyboard or without JavaScript. Dragging, with a
// pointer or a finger, sends that same form with the card it now follows, and the server answers with the board as it
// is. SortableJS loads when a page has a board a person may change, once, with its integrity.
(() => {
  const wired = new WeakSet();
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  let library = null;

  function loadLibrary(board) {
    library ??= new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = board.dataset.boardLibrary;
      script.integrity = board.dataset.boardIntegrity;
      script.crossOrigin = "anonymous";
      script.onload = resolve;
      script.onerror = reject;
      document.head.append(script);
    });
    return library;
  }

  // Where a card landed: its column, and the card before it, if any.
  function moved(card, list) {
    let previous = card.previousElementSibling;
    while (previous && !previous.matches("[data-card]")) {
      previous = previous.previousElementSibling;
    }
    const form = card.querySelector("form[data-move]");
    form.elements.to.value = list.dataset.column;
    form.elements.after.value = previous ? previous.dataset.card : "";
    form.requestSubmit();
  }

  function wire(board) {
    board.querySelectorAll("[data-board-list]").forEach((list) => {
      if (wired.has(list)) {
        return;
      }
      wired.add(list);
      Sortable.create(list, {
        group: board.id,
        draggable: "[data-card]",
        filter: "a, select, button, input, label, summary",
        preventOnFilter: false,
        delayOnTouchOnly: true,
        delay: 150,
        animation: reducedMotion.matches ? 0 : 150,
        ghostClass: board.dataset.ghost, // the macro names it, where the stylesheet's generator looks
        onEnd(event) {
          if (event.from !== event.to || event.oldIndex !== event.newIndex) {
            moved(event.item, event.to);
          }
        },
      });
    });
  }

  async function start(root) {
    const boards = [...root.querySelectorAll("[data-board][data-can-move]")];
    if (root.matches?.("[data-board][data-can-move]")) {
      boards.push(root);
    }
    if (!boards.length) {
      return;
    }
    try {
      await loadLibrary(boards[0]);
    } catch {
      return; // the forms on each card still move it
    }
    boards.forEach(wire);
    document.documentElement.dataset.boardReady = "";
  }

  start(document);
  // A board that htmx brings is new: its lists are wired again.
  document.addEventListener("htmx:afterSettle", (event) => start(event.detail.target.isConnected ? event.detail.target : event.target));
})();
