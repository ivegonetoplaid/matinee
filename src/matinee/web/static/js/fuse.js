// A reply that self-destructs. The pick's line counts down whole seconds, each number fading in and out in
// the same place over the last, then the line burns away and leaves a scorch where it stood. The fuse
// keeps its own clock, whatever the hunt is doing. At most one answer across the trees carries it.

import { h, prefersLessMotion } from "./dom.js";

export const TICK_MS = 1000;
const BURN_MS = 1400; // the burn's length in matinee.css

// When each number shows and when the line burns, in ms from the fuse being lit: `seconds` down to 1,
// one per tick, then the burn one tick after the last number.
export function fuseTimeline(seconds, tickMs = TICK_MS) {
  const numbers = Array.from({ length: seconds }, (_, k) => ({ at: k * tickMs, show: seconds - k }));
  return [...numbers, { at: seconds * tickMs, burn: true }];
}

// A scorch for each line box the text filled, placed in `line`'s own coordinates. Its box is set through
// the element's style properties: the page's content policy refuses a written style attribute.
function scorches(line, text) {
  const home = line.getBoundingClientRect();
  return [...text.getClientRects()].map((r) => {
    const mark = h("span", { class: "scorch", "aria-hidden": "true" });
    Object.assign(mark.style, {
      left: `${r.left - home.left}px`,
      top: `${r.top - home.top}px`,
      width: `${r.width}px`,
      height: `${r.height}px`,
    });
    return mark;
  });
}

// Lights the fuse on `line`, the pick's line with the reply already typed in it. `live()` turns false
// once the viewer has left the screen, and the fuse stops there. Returns { lit, cancel }: `lit()` is true
// while the fuse owns the line; `cancel()` puts the line back as it was typed, for a line that must be
// read (the check's explanation), and hands it back.
export function lightFuse(line, seconds, live) {
  const text = line.querySelector(".ack");
  const number = h("span", { class: "countdown", "aria-hidden": "true" });
  line.append(number);
  const start = performance.now();
  let timer = null;
  let lit = true;

  const cancel = () => {
    clearTimeout(timer);
    lit = false;
    number.remove();
    line.querySelectorAll(".scorch").forEach((s) => s.remove());
    line.classList.remove("burning", "burnt");
  };

  const burn = () => {
    number.remove();
    if (!text) return;
    line.append(...scorches(line, text));
    line.removeAttribute("aria-label");
    const burnt = () => line.classList.replace("burning", "burnt");
    line.classList.add("burning");
    if (prefersLessMotion()) burnt();
    else timer = setTimeout(burnt, BURN_MS);
  };

  const run = (steps) => {
    if (!lit) return;
    if (!live()) {
      cancel();
      return;
    }
    const [step, ...rest] = steps;
    if (step.burn) {
      burn();
      return;
    }
    number.textContent = String(step.show);
    // Restarting the fade: the class comes off, the layout is read, and the class goes back on.
    number.classList.remove("tick");
    void number.offsetWidth;
    number.classList.add("tick");
    timer = setTimeout(() => run(rest), Math.max(0, start + rest[0].at - performance.now()));
  };

  run(fuseTimeline(seconds));
  return { lit: () => lit, cancel };
}
