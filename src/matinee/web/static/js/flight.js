// The name's flight: a copy of the marquee's "Matinee" travels between the sign and the corner mark's
// place at the top left, growing or shrinking to the size it lands at, over 0.9 s. The copy is placed so its
// letters sit exactly over the letters it leaves and land exactly over the letters it replaces.

import { h, prefersLessMotion, wait } from "./dom.js";

export const FLIGHT_MS = 900;
export const HANDOVER_MS = 300; // the corner mark fading in under the landed name; matinee.css's mark-in runs as long
const EASE = "cubic-bezier(0.2, 0.7, 0.2, 1)";
const NO_GLOW = "0 0 0 rgba(242, 179, 61, 0)";

// How far below its top a copy's baseline sits, per pixel of size, found by laying out an unpainted copy.
function baselineRatio() {
  const mark = h("span");
  mark.style.display = "inline-block";
  const probe = h("div", { class: "flying-name", "aria-hidden": "true" }, "M", mark);
  probe.style.fontSize = "100px";
  document.body.append(probe);
  const ratio = (mark.getBoundingClientRect().bottom - probe.getBoundingClientRect().top) / 100;
  probe.remove();
  return ratio;
}

// Where the letters of `el`, a plain-text name with its line height at its font size, are drawn.
function textAt(el) {
  const box = el.getBoundingClientRect();
  const range = document.createRange();
  range.selectNodeContents(el);
  return { left: range.getBoundingClientRect().left, top: box.top, size: box.height, spacing: "0.12em", glow: NO_GLOW };
}

// Where the marquee's lettering is drawn: the left and top of the copy that lies over it, and its size. `el` is
// the drawing's <text>; the drawing scales as one piece, so its font size and baseline scale with it.
export function nameAt(el) {
  if (!(el instanceof SVGTextElement)) return textAt(el);
  const svg = el.ownerSVGElement;
  const view = svg.viewBox.baseVal;
  const scale = svg.getBoundingClientRect().width / view.width;
  const size = parseFloat(getComputedStyle(el).fontSize) * scale;
  const baseline = svg.getBoundingClientRect().top + (el.y.baseVal[0].value - view.y) * scale;
  const left = el.getBoundingClientRect().left;
  return { left, top: baseline - baselineRatio() * size, size, spacing: "0.12em", glow: NO_GLOW };
}

// The corner mark, the theatre's mark at the top left: a drawing 84 by 40 with the name in outlined capitals
// 11 units tall, its ink starting 17.14 units in and standing on a baseline 33 units down.
const MARK = { src: "/static/marquee/mark-corner.svg", width: 84, height: 40 };
export const MARK_NAME = { left: 17.14, baseline: 33, cap: 11 };
export const CAP_HEIGHT = 0.8; // Big Shoulders Display's capitals stand 0.8 of its size
export const M_BEARING = 0.0432; // the space before the M's ink, per pixel of size

// The corner mark as a picture. `alt` names it where it is a link's only content.
export function cornerMark(alt = "") {
  return h("img", { class: "corner-mark", src: MARK.src, alt, width: MARK.width, height: MARK.height });
}

// Where the corner mark's lettering is drawn, found by laying out, and removing unpainted, a page top of the
// same shape: `beside` is what the top bar will also hold (a name tag moves the mark). The copy lands letter
// for letter on the mark's own name.
export function markAt(beside = []) {
  const mark = h("div", { class: "wordmark" }, cornerMark());
  const probe = h("div", { class: "stage" }, h("header", { class: "topbar" }, mark, beside));
  document.body.append(probe);
  const box = mark.firstChild.getBoundingClientRect();
  probe.remove();
  const scale = box.height / MARK.height;
  const size = (MARK_NAME.cap / CAP_HEIGHT) * scale;
  const left = box.left + MARK_NAME.left * scale - M_BEARING * size;
  const top = box.top + MARK_NAME.baseline * scale - baselineRatio() * size;
  return { left, top, size, spacing: "0.12em", glow: NO_GLOW };
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
