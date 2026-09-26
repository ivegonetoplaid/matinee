// The iris: leaving the box office, the booth closes into a shrinking circle
// to black, and the poster wall opens from a growing one. It is the only
// transition in Matinee that passes through black.

import { prefersLessMotion, wait } from "./dom.js";

const CLOSE_MS = 600;
const SHUT_MS = 60;
const TYPE_AFTER_MS = 520; // the first question starts typing while the iris is still opening
const OPEN_MS = 750;

const body = document.body;

export async function closeIris() {
  if (prefersLessMotion()) return;
  body.dataset.iris = "open";
  body.getBoundingClientRect(); // the open circle is painted before it starts to close
  body.dataset.iris = "closed";
  await wait(CLOSE_MS + SHUT_MS);
}

// Opens a closed iris and resolves when the line may start typing. Does nothing when the iris is not closed.
export async function openIris() {
  if (body.dataset.iris !== "closed") return;
  body.dataset.iris = "opening";
  setTimeout(() => {
    if (body.dataset.iris === "opening") delete body.dataset.iris;
  }, OPEN_MS);
  await wait(TYPE_AFTER_MS);
}
