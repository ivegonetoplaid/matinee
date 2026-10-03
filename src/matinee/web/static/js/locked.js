// The locked door: shown in place of the poster wall when a door word is set and this device has not given
// it. Back to front: a wall of black subway tile, a wooden frame with a step, the painted door, and the
// slot's sliding cover over the password field; the marquee stands above it all and does not move.
// Matinee types its greeting beside the door (between the marquee and the door on a narrower screen), and
// the slot takes the word once the greeting is typed. Each character typed pushes the slot's cover further
// open, fully at ten. Nothing here asks the server for films, posters or the count.
//
// The right word opens it: Matinee's line goes, the cover is shut, and the door swings inward on its left
// hinge onto a warm glow (0.9 s). Then the door's whole layer, tile included, is wiped away in ten vertical
// bands, each narrowing to nothing about its own centre, the centre bands first and the outermost 0.42 s
// later, each over 0.38 s, onto the poster wall standing behind. The wipe waits for that wall to be drawn,
// so nothing passes through black. Under reduced motion the change is instant.

import { post } from "./api.js";
import { twoParts } from "./door-rules.js";
import { h, prefersLessMotion, wait } from "./dom.js";
import { typeLine } from "./type.js";

const FULL_AT = 10; // characters typed by which the cover is all the way open
const BANDS = 10;
const STAGGER_MS = 420; // the outermost bands start this long after the centre ones
const BAND_MS = 380; // each band closes over this long
const SWING_MS = 750; // the wipe starts once the swing has had this long, and the wall behind is drawn
const COUNT_AT_MS = 250; // into the wipe, the letter board turns to the film count
export const WALL_FADE_MS = 400; // the poster wall's own fade-in, once its pictures are drawn

const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);

// The door's layer as a clip path `elapsed` ms into the wipe: ten vertical bands, each narrowing about its
// own centre, the centre ones first.
export function bandsAt(elapsed) {
  const points = [];
  for (let i = 0; i < BANDS; i += 1) {
    // The centre two bands start at once, the outermost two STAGGER_MS later, the rest evenly between.
    const from = ((Math.abs(i + 0.5 - BANDS / 2) - 0.5) / (BANDS / 2 - 1)) * STAGGER_MS;
    const t = Math.min(1, Math.max(0, (elapsed - from) / BAND_MS));
    const half = (50 / BANDS) * (1 - ease(t));
    const mid = ((i + 0.5) * 100) / BANDS;
    const left = (mid - half).toFixed(3);
    const right = (mid + half).toFixed(3);
    points.push(`${left}% 100%`, `${left}% 0%`, `${right}% 0%`, `${right}% 100%`);
  }
  return `polygon(${points.join(", ")})`;
}

export const WIPE_MS = STAGGER_MS + BAND_MS;
const SHUT_MS = 420; // the cover slides shut over 0.4 s
const WRONG = ["That ain't it, pal.", "Try again, or take a walk."];

const coarse = () => window.matchMedia("(pointer: coarse)").matches;

export class LockedDoor {
  // `marquee` stands above the door; `onAdmitted(door)` is called once the right word is given.
  constructor({ stage, marquee, greeting, onAdmitted }) {
    this.stage = stage;
    this.marquee = marquee;
    this.greeting = greeting;
    this.onAdmitted = onAdmitted;
  }

  show() {
    this.line = h("p", { class: "line locked-line", "aria-live": "polite" });
    this.word = h("input", {
      class: "slot-word",
      type: "password",
      "aria-label": "The word at the door",
      autocomplete: "off",
      autocapitalize: "off",
      spellcheck: "false",
      enterkeyhint: "go",
      disabled: true,
    });
    this.cover = h("div", { class: "slot-cover", "aria-hidden": "true" });
    // The eye that shows the word stands at the slot's right end, over the cover, where a password field's
    // show control usually sits.
    this.peek = h(
      "button",
      { class: "peek", type: "button", "aria-label": "Show the word", "aria-pressed": "false", disabled: true },
      h("img", { src: "/static/door/eye.svg", alt: "", width: 20, height: 20 }),
    );
    this.slot = h("form", { class: "slot", novalidate: true }, this.word, this.cover, this.peek);
    this.door = h("div", { class: "locked-door" }, this.slot);
    this.scene = h(
      "div",
      { class: "locked" },
      h("div", { class: "subway", "aria-hidden": "true" }),
      this.line,
      h(
        "div",
        { class: "entrance" },
        h("div", { class: "door-frame" }, h("div", { class: "doorway", "aria-hidden": "true" }), this.door),
        h("div", { class: "door-step", "aria-hidden": "true" }),
      ),
    );
    this.stage.append(this.scene);
    this.place();
    new ResizeObserver(() => this.place()).observe(this.marquee);
    document.fonts.ready.then(() => this.place());
    this.word.addEventListener("input", () => this.slide());
    this.slot.addEventListener("submit", (e) => {
      e.preventDefault();
      this.give();
    });
    // A press on the eye leaves the focus in the slot, so typing carries on; a keyboard's toggle keeps it.
    this.peek.addEventListener("pointerdown", (e) => e.preventDefault());
    this.peek.addEventListener("click", () => this.toggle());
    return this.greet(twoParts(this.greeting));
  }

  // The scene hangs from the marquee's foot, wherever the marquee's own size leaves it; where the greeting
  // stands above the door, the door hangs below the taller of its two lines as they will stand typed, so
  // the door never moves while a line types and never covers its end.
  place() {
    const bottom = this.marquee.getBoundingClientRect().bottom;
    this.scene.style.setProperty("--marquee-bottom", `${Math.round(bottom)}px`);
    const tallest = Math.max(this.measure(twoParts(this.greeting)), this.measure(WRONG));
    this.scene.style.setProperty("--line-h", `${Math.ceil(tallest)}px`);
  }

  // The height a line will take once typed, laid out unseen beside the real one.
  measure([ack, ask]) {
    const probe = h(
      "p",
      { class: "line locked-line done probe", "aria-hidden": "true" },
      h("span", { class: "ack" }, ack),
      h("span", { class: "ask" }, ask, h("span", { class: "caret" })), // the caret can carry a word over
    );
    this.scene.append(probe);
    const height = probe.getBoundingClientRect().height;
    probe.remove();
    return height;
  }

  // Matinee's line types, then the slot takes the word.
  async greet([ack, ask]) {
    this.word.disabled = true;
    this.peek.disabled = true;
    await typeLine(this.line, ack, ask);
    this.word.disabled = false;
    this.peek.disabled = false;
    if (!coarse()) this.word.focus();
  }

  // The cover is pushed open by the typing: each character moves it further, until it is gone at ten.
  slide() {
    const open = Math.min(1, [...this.word.value].length / FULL_AT);
    this.cover.style.transform = `translateX(${(open * 101).toFixed(1)}%)`;
  }

  async shut() {
    this.slot.classList.add("shutting");
    this.cover.style.transform = "";
    await wait(prefersLessMotion() ? 0 : SHUT_MS);
    this.slot.classList.remove("shutting");
  }

  // The opening. `ready` resolves, to whatever the page needs next, once the poster wall behind is drawn;
  // `onCount(value)` turns the letter board to the film count while the bands close. Resolves to `ready`'s
  // value once the door's layer is gone.
  async open(ready, onCount) {
    this.word.blur();
    this.scene.classList.add("hushed");
    if (prefersLessMotion()) {
      const value = await ready;
      onCount(value);
      this.scene.remove();
      return value;
    }
    this.scene.classList.add("door-open");
    const [value] = await Promise.all([ready, wait(SWING_MS)]);
    await this.wipe(() => onCount(value));
    this.scene.remove();
    return value;
  }

  wipe(atCount) {
    return new Promise((resolve) => {
      const start = performance.now();
      let counted = false;
      const step = (now) => {
        const elapsed = now - start;
        if (!counted && elapsed >= COUNT_AT_MS) {
          counted = true;
          atCount();
        }
        this.scene.style.clipPath = bandsAt(elapsed);
        if (elapsed < WIPE_MS) requestAnimationFrame(step);
        else resolve();
      };
      requestAnimationFrame(step);
    });
  }

  toggle() {
    const showing = this.word.type === "text";
    this.word.type = showing ? "password" : "text";
    // A changed type puts the caret back at the start once it takes effect; typing goes on at the end.
    requestAnimationFrame(() => {
      const end = this.word.value.length;
      this.word.setSelectionRange(end, end);
      this.word.scrollLeft = this.word.scrollWidth;
    });
    this.peek.setAttribute("aria-pressed", String(!showing));
    this.peek.setAttribute("aria-label", showing ? "Show the word" : "Hide the word");
  }

  // The word is checked by the server, which answers a wrong one only after a wait. The right word goes in;
  // a wrong one clears the slot, shuts the cover and gets Matinee's reply; anything else says why.
  async give() {
    const word = this.word.value;
    if (!word.trim() || this.word.disabled) return undefined;
    this.word.disabled = true;
    this.peek.disabled = true;
    // The cover shuts at once, so the word is seen to be taken while the server weighs it.
    const [res] = await Promise.all([post("/api/admission", { word }), this.shut()]);
    if (res.ok) return this.onAdmitted(this);
    this.word.value = "";
    return this.greet(res.data.error === "wrong_word" ? WRONG : twoParts(res.data.message));
  }
}
