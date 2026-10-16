// "Rate it": the pick's panel with the five answers, best first, and beneath them a three-line box for a short
// review. An answer saves at once. The short review waits for a rating, is one line however it is typed or pasted,
// takes at most MAX_REVIEW characters (counted as the store counts them, by code point, so an emoji is one), always
// shows how many remain at the box's bottom right, and saves itself: PAUSE_MS after typing stops, on leaving the box,
// or on Enter, then says "✓ Saved" at its bottom left. A keystroke past the limit is refused: the box's edge turns
// rose and fades, it shakes (not under reduced motion), and a line asks for about 15 words. A review is shown and
// kept as plain text.

import { put } from "./api.js";
import { h } from "./dom.js";
import { panelAction } from "./panel.js";
import { ANSWERS } from "./ratings.js";

export const MAX_REVIEW = 100; // the store's limit (matinee.records.MAX_REVIEW)
const TRIP_MS = 2200; // how long the rose edge and the line stay before they fade
const FADE_MS = 400;
const TOO_LONG = "Short and sweet, please. About 15 words.";
const PAUSE_MS = 1000; // how long typing must stop before the short review saves itself

// The length of a short review as the store counts it.
export const length = (text) => [...text].length;

// What a typed value becomes: itself when it fits, else the last value that did; `tripped` when a keystroke was
// refused.
export function fitted(value, before) {
  return length(value) <= MAX_REVIEW ? { value, tripped: false } : { value: before, tripped: true };
}

// What the box says about room left, always: "12 left".
export const roomLeft = (value) => `${MAX_REVIEW - length(value)} left`;

// A short review is one line: a line break typed or pasted into the box becomes a space.
export const oneLine = (value) => value.replace(/\s*[\r\n\u2028\u2029]+\s*/g, " ");

// The short review's saving. `soon(text)` after each keystroke saves once typing has paused for `wait`; `now(text)`
// (leaving the field, Enter) saves at once. Saves run one at a time in the order asked, and a text the store already
// holds is not sent again. `save(text)` resolves to the page's { ok, data } answer, which `done(res, text)` hears.
export function autosaver(save, done, kept, wait = PAUSE_MS) {
  let timer = 0;
  let queue = Promise.resolve();
  const now = (text) => {
    clearTimeout(timer);
    queue = queue.then(async () => {
      if (text === kept) return;
      const res = await save(text);
      if (res.ok) kept = text;
      done(res, text);
    });
    return queue;
  };
  const soon = (text) => {
    clearTimeout(timer);
    timer = setTimeout(() => now(text), wait);
  };
  return { soon, now };
}

function answerButtons(current, onPick) {
  const buttons = ANSWERS.map((a) =>
    h("button", { class: "letterbox ticked", type: "button", "aria-pressed": String(a.score === current), onclick: () => onPick(a.score) }, a.say),
  );
  return buttons;
}

// The panel's body for `film`. `rating` is the viewer's current one or null; `save` holds score(score) and
// review(text), each resolving to the page's { ok, data } answer; `onSaved(rating)` hears every saved change.
export function ratePanel({ film, rating, save, onSaved }) {
  let current = rating;
  const status = h("p", { class: "rate-status", role: "status" });
  const input = h("textarea", {
    class: "review-input",
    id: "short-review",
    rows: 3,
    autocomplete: "off",
    placeholder: "This movie will melt your brain",
    "aria-describedby": "review-room review-trip",
  });
  input.value = rating?.review ?? "";
  const room = h("span", { class: "review-room", id: "review-room" });
  const trip = h("p", { class: "review-trip", id: "review-trip", role: "alert" });
  const saved = h("span", { class: "review-saved", role: "status" });
  const box = h("div", { class: "review-field" }, input, saved, room);
  let typed = input.value;
  let tripTimer = 0;
  const say = (text) => {
    status.textContent = text;
  };
  const ready = () => {
    const off = !current;
    input.disabled = off;
    box.classList.toggle("off", off);
  };
  const tripped = () => {
    clearTimeout(tripTimer);
    box.classList.remove("tripped");
    void box.offsetWidth; // restart the edge and the shake for every refused keystroke
    box.classList.add("tripped");
    trip.textContent = TOO_LONG;
    trip.classList.remove("leaving");
    tripTimer = setTimeout(() => {
      box.classList.remove("tripped");
      trip.classList.add("leaving"); // the line fades out, then goes
      tripTimer = setTimeout(() => {
        trip.textContent = "";
        trip.classList.remove("leaving");
      }, FADE_MS);
    }, TRIP_MS);
  };
  input.addEventListener("input", () => {
    if (oneLine(input.value) !== input.value) input.value = oneLine(input.value);
    const fit = fitted(input.value, typed);
    if (fit.tripped) {
      input.value = fit.value;
      tripped();
    }
    typed = input.value;
    room.textContent = roomLeft(typed);
    saved.textContent = "";
    if (current) review.soon(typed);
  });
  input.addEventListener("beforeinput", (e) => {
    if (e.inputType.startsWith("insert") && e.data && length(typed) + length(e.data) > MAX_REVIEW && input.selectionStart === input.selectionEnd) {
      e.preventDefault();
      tripped();
    }
  });
  const review = autosaver(
    save.review,
    (res, text) => {
      if (!res.ok) return say(res.data.message);
      current = res.data;
      onSaved(current);
      if (text === input.value) saved.textContent = text ? "✓ Saved" : "✓ Cleared"; // not over newer typing
      return say("");
    },
    input.value,
  );
  const saveReview = () => {
    if (current) review.now(input.value);
  };
  // A phone's keyboard can cover the field: it scrolls into the panel's view as it takes the focus.
  input.addEventListener("focus", () => box.scrollIntoView({ block: "nearest" }));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      saveReview();
    }
  });
  input.addEventListener("blur", saveReview);
  const answers = answerButtons(current?.score ?? null, async (score) => {
    const res = await save.score(score);
    if (!res.ok) return say(res.data.message);
    current = res.data;
    for (const [i, b] of answers.entries()) b.setAttribute("aria-pressed", String(ANSWERS[i].score === score));
    ready();
    onSaved(current);
    return say("Saved. Add a short review if you like.");
  });
  room.textContent = roomLeft(typed);
  ready();
  return [
    h("p", { class: "panel-lede" }, `Seen ${film.title}? Your answer is kept on My profile, where you can change it.`),
    h("div", { class: "rate-answers", role: "group", "aria-label": "Your answer" }, answers),
    status,
    h("label", { class: "review-label", for: "short-review" }, "Short review ", h("span", { class: "review-optional" }, "(optional)")),
    box,
    trip,
  ];
}

// "Rate it" on the pick: opens the panel for `film`. `household` is the pick's shared ratings and the viewer's own
// (`mine`), kept current as the viewer rates, so the reading panel shows the new rating. A rating made here names the
// run, where the film is marked rated; My profile's overlay names none. `saved(rating)` hears each saved change.
export function rateLink({ film, panel, profileId, run, household, saved = () => {} }) {
  const path = `/api/profiles/${profileId}/ratings/${film.tmdb}`;
  const save = {
    score: (score) => put(path, { score, run }),
    review: (text) => put(`${path}/review`, { review: text }),
  };
  const open = panelAction("Rate it", () =>
    panel.open(open, "Rate it", ...ratePanel({ film, rating: household.mine, save, onSaved: (r) => saved(Object.assign(household, { mine: r }).mine) })),
  );
  return open;
}
