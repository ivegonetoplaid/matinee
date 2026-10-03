// The locked door: shown in place of the poster wall when a door word is set and this device has not given
// it. Back to front: a wall of black subway tile, a wooden frame with a step, the painted door, and the
// slot's sliding cover over the password field; the marquee stands above it all and does not move.
// Matinee types its greeting beside the door (between the marquee and the door on a narrower screen), and
// the slot takes the word once the greeting is typed. Each character typed pushes the slot's cover further
// open, fully at ten. Nothing here asks the server for films, posters or the count.

import { post } from "./api.js";
import { twoParts } from "./door-rules.js";
import { h, prefersLessMotion, wait } from "./dom.js";
import { typeLine } from "./type.js";

const FULL_AT = 10; // characters typed by which the cover is all the way open
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
    this.slot = h("form", { class: "slot", novalidate: true }, this.word, this.cover);
    this.peek = h(
      "button",
      { class: "peek", type: "button", "aria-label": "Show the word", "aria-pressed": "false", disabled: true },
      h("img", { src: "/static/door/eye.svg", alt: "", width: 20, height: 20 }),
    );
    this.door = h("div", { class: "locked-door" }, this.slot, this.peek);
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
    this.word.addEventListener("input", () => this.slide());
    this.slot.addEventListener("submit", (e) => {
      e.preventDefault();
      this.give();
    });
    this.peek.addEventListener("click", () => this.toggle());
    return this.greet(twoParts(this.greeting));
  }

  // The scene hangs from the marquee's foot, wherever the marquee's own size leaves it.
  place() {
    const bottom = this.marquee.getBoundingClientRect().bottom;
    this.scene.style.setProperty("--marquee-bottom", `${Math.round(bottom)}px`);
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

  toggle() {
    const showing = this.word.type === "text";
    this.word.type = showing ? "password" : "text";
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
    const res = await post("/api/admission", { word });
    if (res.ok) return this.onAdmitted(this);
    this.word.value = "";
    await this.shut();
    return this.greet(res.data.error === "wrong_word" ? WRONG : twoParts(res.data.message));
  }
}
