// Matinee's line types out quickly: an acknowledgement in gold, then the
// question in white. The answers appear once it finishes.

import { h, prefersLessMotion, sentenceCase } from "./dom.js";

const CHARS_PER_TICK = 2;
const TICK_MS = 24;

// Renders the line into `el` and resolves when the whole line is shown.
export function typeLine(el, ack, ask) {
  const gold = sentenceCase(ack || "");
  const white = sentenceCase(ask || "");
  const ackEl = h("span", { class: "ack" });
  const askEl = h("span", { class: "ask" });
  const caret = h("span", { class: "caret", "aria-hidden": "true" });
  el.classList.remove("done");
  el.setAttribute("aria-label", [gold, white].filter(Boolean).join(" "));
  el.replaceChildren(ackEl, askEl);
  askEl.append(caret);
  const total = gold.length + white.length;
  const paint = (n) => {
    ackEl.textContent = gold.slice(0, n);
    askEl.replaceChildren(white.slice(0, Math.max(0, n - gold.length)), caret);
  };
  return new Promise((resolve) => {
    if (prefersLessMotion() || total === 0) {
      paint(total);
      el.classList.add("done");
      resolve();
      return;
    }
    let n = 0;
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
