// Matinee's line types out quickly: an acknowledgement in gold, then the
// question in white. The answers appear once it finishes.

import { h, prefersLessMotion, sentenceCase } from "./dom.js";

const CHARS_PER_TICK = 2;
const TICK_MS = 24;

// Renders the line into `el` and resolves when the whole line is shown. `shown` characters are on
// screen already and are not typed again: a gold line typed earlier stays while the rest types below it.
export function typeLine(el, ack, ask, { shown = 0 } = {}) {
  const gold = sentenceCase(ack || "");
  // A cream part that carries on the gold part's sentence, after a comma, keeps its first letter as written.
  const white = /,\s*$/.test(gold) ? ask || "" : sentenceCase(ask || "");
  const ackEl = h("span", { class: "ack" });
  const askEl = h("span", { class: "ask" });
  const caret = h("span", { class: "caret", "aria-hidden": "true" });
  el.classList.remove("done");
  el.setAttribute("aria-label", [gold, white].filter(Boolean).join(" "));
  el.replaceChildren(ackEl, white ? askEl : "");
  const total = gold.length + white.length;
  // With no question to follow, the caret stays on the acknowledgement's line.
  const caretHome = white ? askEl : ackEl;
  const paint = (n) => {
    ackEl.replaceChildren(gold.slice(0, n));
    askEl.replaceChildren(white.slice(0, Math.max(0, n - gold.length)));
    caretHome.append(caret);
  };
  return new Promise((resolve) => {
    if (prefersLessMotion() || total === 0) {
      paint(total);
      el.classList.add("done");
      resolve();
      return;
    }
    let n = Math.min(shown, total);
    paint(n);
    const timer = setInterval(() => {
      n = Math.min(total, n + CHARS_PER_TICK);
      paint(n);
      if (n >= total) {
        clearInterval(timer);
        el.classList.add("done");
        resolve();
      }
    }, TICK_MS);
  });
}
