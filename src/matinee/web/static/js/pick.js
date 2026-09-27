// The pick, in two beats. Land: one poster tears loose from the floor of the wall,
// leaving a gap, and comes up into a spotlight while "Here. Watch this one."
// types out. Reveal: after about two and a half seconds the wall
// fades nearly away and the lit poster itself travels to its resting place. On a
// desktop that is the foot of the left column, as large as the space allows, while
// the film's backdrop rises on the right with its title, year and synopsis. On a
// phone the poster fills the screen, then the page scrolls gently to the details.
// The film is tonight's showing, never a search result.

import { get } from "./api.js";
import { h, isPhone, sentenceCase, wait } from "./dom.js";
import { typeLine } from "./type.js";

const REVEAL_AFTER_MS = 2400; // the rip takes 1.3 s, then the poster holds in the light
const SETTLE_MS = 1300;
const PHONE_HOLD_MS = 2200;
const POSTER_RATIO = 1.5; // height over width
const POSTER_MIN_H = 160; // below this the page scrolls rather than shrink the poster further
const HERE = "Here. Watch this one.";
// Where the lit poster lands, as fractions of the screen: the right two-thirds on desktop, the upper half on a phone.
const SPOTS = {
  desktop: [
    [0.625, 0.19],
    [0.75, 0.33],
    [0.47, 0.4],
    [0.69, 0.14],
  ],
  phone: [
    [0.3, 0.1],
    [0.52, 0.16],
    [0.22, 0.2],
    [0.45, 0.08],
  ],
};

let spotTurn = 0;

function spotlight(tmdb, title) {
  const at = (isPhone() ? SPOTS.phone : SPOTS.desktop)[spotTurn % 4];
  spotTurn += 1;
  const spot = h(
    "div",
    { class: "spot", "aria-hidden": "true" },
    h("div", { class: "spot-hole" }),
    h("div", { class: "spot-glow" }),
    h("img", { class: "spot-poster", src: `/img/poster/${tmdb}/l`, alt: `${title} poster` }),
  );
  spot.style.left = `${at[0] * 100}vw`;
  spot.style.top = `${at[1] * 100}vh`;
  return spot;
}

const still = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// The poster's resting box: as tall as the slot allows at 2:3, never wider than the slot.
function fit(slot) {
  const box = slot.getBoundingClientRect();
  const height = Math.min(box.width * POSTER_RATIO, Math.max(POSTER_MIN_H, box.height));
  return { width: height / POSTER_RATIO, height };
}

// Moves the lit poster into `slot` in the page's flow: the same picture, carried from where it
// landed on the wall to where it rests. The slot is placed by the caller before this runs.
function settle(spot, slot, film) {
  const from = spot.querySelector(".spot-poster").getBoundingClientRect();
  const poster = h("img", { class: "slot-poster", src: `/img/poster/${film.tmdb}/l`, alt: `${film.title} poster` });
  poster.addEventListener("error", () => slot.remove());
  const size = fit(slot);
  poster.style.width = `${size.width}px`;
  poster.style.height = `${size.height}px`;
  slot.append(poster);
  spot.remove();
  const to = poster.getBoundingClientRect();
  if (still() || !to.width) return;
  const shift = `translate(${from.left - to.left}px, ${from.top - to.top}px) scale(${from.width / to.width})`;
  poster.animate([{ transform: shift }, { transform: "none" }], {
    duration: SETTLE_MS,
    easing: "cubic-bezier(0.2, 0.7, 0.2, 1)",
  });
}

function heading(film) {
  return h("h2", { class: "film-title" }, film.title, film.year ? h("span", { class: "film-year" }, ` ${film.year}`) : null);
}

function feature(card, film, result) {
  const backdrop = h("img", {
    class: "backdrop",
    src: `/img/backdrop/${film.tmdb}/${isPhone() ? "m" : "l"}`,
    alt: `${film.title}, a still from the film`,
  });
  backdrop.addEventListener("error", () => backdrop.remove());
  const unchecked = result.unchecked ? h("p", { class: "note" }, result.unchecked, " ", credit(result)) : null;
  return h(
    "div",
    { class: "feature" },
    backdrop,
    h("div", { class: "feature-text" }, heading(film), h("p", { class: "synopsis" }, card.synopsis || ""), unchecked),
  );
}

// DoesTheDogDie's credit, shown wherever its data is.
function credit(result) {
  return h("a", { href: result.link, target: "_blank", rel: "noopener noreferrer" }, result.credit);
}

// Why the first pick was turned away, and "What were you going to show me?", which reveals it.
function firstPickReveal(result) {
  const swapped = result.swapped;
  const shown = h("p", { class: "note", hidden: true });
  shown.textContent = `${swapped.film.title}${swapped.film.year ? ` (${swapped.film.year})` : ""}: ${swapped.topics
    .map((t) => sentenceCase(t))
    .join(", ")}.`;
  const ask = h(
    "button",
    {
      class: "link-button",
      type: "button",
      onclick: () => {
        shown.hidden = false;
        ask.remove();
      },
    },
    swapped.reveal,
  );
  return h("div", { class: "swap-note" }, h("p", { class: "note" }, swapped.line, " ", credit(result)), ask, shown);
}

// No film: every film left tripped the list, or three in a row did and the viewer
// may roll again or have one picked without the check turning any away.
async function showNoFilm(result, { line, aside }, actions) {
  await typeLine(line, result.tired || result.exhausted, "");
  const startOver = h("button", { class: "pill gold", type: "button", onclick: actions.startOver }, "Start over");
  if (!result.tired) {
    aside.append(startOver, h("p", { class: "note" }, credit(result)));
    return;
  }
  aside.append(
    h(
      "div",
      { class: "choices" },
      h("button", { class: "pill gold", type: "button", onclick: actions.notThatOne }, "Roll again"),
      h("button", { class: "pill velvet", type: "button", onclick: actions.justPick }, "Just pick one"),
    ),
    h("button", { class: "link-button", type: "button", onclick: actions.startOver }, "Start over"),
    h("p", { class: "note" }, credit(result)),
  );
}

// The page's pick screen. `actions` holds notThatOne, justPick, startOver, failed and the correction panel's builder.
export async function showPick({ stage, wall, pool, result, frame, actions }) {
  const film = result.film;
  const { line, aside } = frame;
  if (!film) return showNoFilm(result, frame, actions);
  if (result.swapped) {
    await typeLine(line, result.swapped.line, "");
    await wait(900);
  }
  wall.show(pool, { spotlight: true });
  wall.root.classList.add("spotlit");
  const spot = spotlight(film.tmdb, film.title);
  stage.append(spot);
  const cardRequest = get(`/api/film/${film.tmdb}`);
  await Promise.all([typeLine(line, HERE, ""), wait(REVEAL_AFTER_MS)]);
  const card = await cardRequest;
  if (!card.ok) {
    spot.remove();
    return actions.failed(card.data);
  }
  const info = card.data;
  wall.root.classList.add("revealed");
  stage.classList.add("revealed");
  const shown = feature(info, film, result);
  frame.showing.append(shown);
  // The buttons come straight after the line, whose words never change, so "Not that one" sits in
  // the same place for every film. The answers so far are in the trail at the foot of the screen.
  const buttons = h(
    "div",
    { class: "choices" },
    h("button", { class: "pill velvet", type: "button", onclick: actions.notThatOne }, "Not that one"),
    info.seerr ? h("a", { class: "seerr", href: info.seerr, target: "_blank", rel: "noopener noreferrer" }, "More on Seerr") : null,
    h("button", { class: "link-button", type: "button", onclick: actions.startOver }, "Start over"),
  );
  const parts = [buttons, result.swapped ? firstPickReveal(result) : null, actions.correction(film)];
  aside.append(...parts.filter(Boolean));
  // Measured once the aside is whole, so the poster takes only the height left beneath it.
  const slot = h("div", { class: "poster-slot" });
  frame.left.append(slot);
  settle(spot, slot, film);
  if (isPhone()) {
    stage.scrollTop = 0;
    await wait(PHONE_HOLD_MS);
    shown.scrollIntoView({ behavior: still() ? "auto" : "smooth", block: "start" });
  }
}
