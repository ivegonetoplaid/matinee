// The name's flight: a copy of the marquee's "Matinee" travels between the sign and the wordmark's place
// at the top left, growing or shrinking to the size it lands at, over 0.9 s. The copy is placed so its
// letters sit exactly over the letters it leaves and land exactly over the letters it replaces.

import { h, prefersLessMotion, wait } from "./dom.js";

export const FLIGHT_MS = 900;
const EASE = "cubic-bezier(0.2, 0.7, 0.2, 1)";
const GLOW = "0 0 22px rgba(242, 179, 61, 0.6)";
const NO_GLOW = "0 0 0 rgba(242, 179, 61, 0)";

// Where the letters of `el` are drawn: the left and top of the copy that lies over them, and their size.
// `el` sets its line height to its font size, so its box is as tall as its letters are large.
export function nameAt(el) {
  const box = el.getBoundingClientRect();
  const range = document.createRange();
  range.selectNodeContents(el);
  return { left: range.getBoundingClientRect().left, top: box.top, size: box.height, spacing: "0.12em", glow: GLOW };
}

// Where the theatre's wordmark is drawn, found by laying out, and removing unpainted, a page top of the
// same shape: `beside` is what the top bar will also hold (a name tag moves the wordmark). `rise` is how
// far the copy's letters sit below its top, per pixel of size.
export function wordmarkAt(rise, beside = []) {
  const mark = h("div", { class: "wordmark" }, "Matinee");
  const probe = h("div", { class: "stage" }, h("header", { class: "topbar" }, mark, beside));
  document.body.append(probe);
  const range = document.createRange();
  range.selectNodeContents(mark);
  const text = range.getBoundingClientRect();
  const size = parseFloat(getComputedStyle(mark).fontSize);
  probe.remove();
  return { left: text.left, top: text.top - rise * size, size, spacing: "0.08em", glow: NO_GLOW };
}

// How far below its top the copy's letters sit, per pixel of size.
export function riseOf(el) {
  const range = document.createRange();
  range.selectNodeContents(el);
  const box = el.getBoundingClientRect();
  return (range.getBoundingClientRect().top - box.top) / box.height;
}

const frame = (at) => ({ left: `${at.left}px`, top: `${at.top}px`, fontSize: `${at.size}px`, letterSpacing: at.spacing, textShadow: at.glow });

// A copy of the name, laid over `at`.
export function copyAt(at) {
  const copy = h("div", { class: "flying-name", "aria-hidden": "true" }, "Matinee");
  Object.assign(copy.style, frame(at));
  document.body.append(copy);
  return copy;
}

// Where `copy` is drawn now, mid-flight or at rest.
export function copyNow(copy) {
  const s = getComputedStyle(copy);
  return { left: parseFloat(s.left), top: parseFloat(s.top), size: parseFloat(s.fontSize), spacing: s.letterSpacing, glow: s.textShadow };
}

// Flies `copy` to `to` and resolves once it has landed, or once the flight's time has passed, whichever
// comes first: a landing that never reports must not hold up what waits for it. Under reduced motion, or
// when `instant`, it is there at once. A flight cancelled by a later one resolves early.
export async function fly(copy, to, { instant = false } = {}) {
  const from = copyNow(copy);
  for (const earlier of copy.getAnimations()) earlier.cancel();
  Object.assign(copy.style, frame(to));
  if (instant || prefersLessMotion()) return;
  const flight = copy.animate([frame(from), frame(to)], { duration: FLIGHT_MS, easing: EASE });
  await Promise.race([flight.finished.catch(() => undefined), wait(FLIGHT_MS + 50)]);
}
