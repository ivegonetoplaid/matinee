// The pick, as one motion. The wall glides far across its floor, as if going to fetch one poster.
// While the floor still coasts, that poster appears lying in it and moves with it, then tears loose,
// leaving a gap, and lifts into a spotlight while "Here. Watch this one." types out. It holds in the
// light for a beat, then travels to its resting place as the wall fades nearly away. On a desktop that
// is the foot of the left column, as large as the space allows, while the film's backdrop rises on the
// right with its title, year and synopsis. On a phone the poster fills the screen, then the page
// scrolls gently to the details.
// The film is tonight's showing, never a search result.

import { get } from "./api.js";
import { h, isPhone, prefersLessMotion, sentenceCase, wait } from "./dom.js";
import { typeLine } from "./type.js";

const APPEAR_MS = 550; // into the glide, while the floor still coasts
const BEAT_MS = 400; // the poster holds in the light once the lift ends, the pick's one deliberate stop
const STILL_HOLD_MS = 2000; // under reduced motion there is no lift; the poster holds in the light about as long
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

// A picture fetched ahead of its moment. Resolves to the image once it can be drawn, or to null when it
// fails: the server answers 404 for a picture it cannot fetch, and bounds how long it tries.
function picture(src, alt) {
  const img = new Image();
  img.alt = alt;
  img.src = src;
  return img.decode().then(
    () => img,
    () => null,
  );
}

// The lit poster in its spotlight. `poster` is a picture that can already be drawn.
function spotlight(poster) {
  const at = (isPhone() ? SPOTS.phone : SPOTS.desktop)[spotTurn % 4];
  spotTurn += 1;
  poster.className = "spot-poster";
  const spot = h("div", { class: "spot", "aria-hidden": "true" }, h("div", { class: "spot-glow" }), poster);
  spot.style.left = `${at[0] * 100}vw`;
  spot.style.top = `${at[1] * 100}vh`;
  return spot;
}

// The poster's resting box: as tall as the slot allows at 2:3, never wider than the slot.
function fit(slot) {
  const box = slot.getBoundingClientRect();
  const height = Math.min(box.width * POSTER_RATIO, Math.max(POSTER_MIN_H, box.height));
  return { width: height / POSTER_RATIO, height };
}

// Moves the lit poster into `slot` in the page's flow: the same picture, carried from where it hung in
// the light to where it rests. The slot is placed by the caller before this runs. The move starts from
// the lit poster's own box, measured from the same corner it scales from, so it never jumps.
function settle(spot, slot) {
  const poster = spot.querySelector(".spot-poster");
  const from = poster.getBoundingClientRect();
  const size = fit(slot);
  poster.className = "slot-poster";
  poster.style.width = `${size.width}px`;
  poster.style.height = `${size.height}px`;
  slot.append(poster);
  spot.remove();
  const to = poster.getBoundingClientRect();
  if (prefersLessMotion() || !to.width) return;
  const shift = `translate(${from.left - to.left}px, ${from.top - to.top}px) scale(${from.width / to.width}, ${from.height / to.height})`;
  poster.style.transformOrigin = "top left";
  poster.animate([{ transform: shift }, { transform: "none" }], {
    duration: SETTLE_MS,
    easing: "cubic-bezier(0.2, 0.7, 0.2, 1)",
  });
}

function heading(film) {
  return h("h2", { class: "film-title" }, film.title, film.year ? h("span", { class: "film-year" }, ` ${film.year}`) : null);
}

// The film's details. `backdrop` is a loaded picture, or null where there is none to show: a phone's
// resting page shows no backdrop, and a backdrop that failed is left out.
function feature(card, film, result, backdrop) {
  if (backdrop) backdrop.className = "backdrop";
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

// Keeps the spot over the same point of the floor until `until`, so the poster lying in the floor and
// the gap it leaves move with the floor while it coasts to rest.
function ride(spot, wall, until) {
  const box = spot.getBoundingClientRect();
  const point = wall.floorPoint(box.left + box.width / 2, box.top + box.height / 2);
  const [x0, y0] = point();
  const follow = () => {
    const [x, y] = point();
    spot.style.translate = `${x - x0}px ${y - y0}px`;
    if (performance.now() < until) requestAnimationFrame(follow);
  };
  requestAnimationFrame(follow);
}

// Land: the glide, and while the floor still coasts, the lit poster appears in it and starts its lift.
// A poster whose picture arrives late appears late. Resolves to the spot, or to null when the poster
// has no picture: then there is nothing to lift, and the pick goes straight to the film.
async function land(stage, wall, posterReady) {
  wall.root.classList.add("spotlit");
  await wall.ready();
  const glide = wall.travel();
  const glideEnd = performance.now() + glide;
  const [poster] = await Promise.all([posterReady, wait(Math.min(APPEAR_MS, glide))]);
  if (!poster) {
    await wait(glideEnd - performance.now());
    return null;
  }
  const spot = spotlight(poster);
  stage.append(spot);
  if (performance.now() < glideEnd) ride(spot, wall, glideEnd);
  return spot;
}

// Resolves once the poster has lifted into the light and held there for its beat. A lift cut short
// because the viewer left the pick ends the wait early; the caller sees the spot gone from the page.
async function inTheLight(spot) {
  if (!spot) return undefined;
  if (prefersLessMotion()) return wait(STILL_HOLD_MS);
  const lift = spot.querySelector(".spot-poster").getAnimations();
  const ended = (a) =>
    a.finished.catch((err) => {
      if (err.name !== "AbortError") throw err;
    });
  await Promise.all(lift.map(ended));
  await wait(BEAT_MS);
}

// What sits under the line on the resting page. The buttons come straight after the line, whose words
// never change, so "Not that one" sits in the same place for every film. The answers so far are in the
// trail at the foot of the screen.
function choices(info, film, result, actions) {
  const buttons = h(
    "div",
    { class: "choices" },
    h("button", { class: "pill velvet", type: "button", onclick: actions.notThatOne }, "Not that one"),
    info.seerr ? h("a", { class: "seerr", href: info.seerr, target: "_blank", rel: "noopener noreferrer" }, "More on Seerr") : null,
    h("button", { class: "link-button", type: "button", onclick: actions.startOver }, "Start over"),
  );
  return [buttons, result.swapped ? firstPickReveal(result) : null, actions.correction(film)].filter(Boolean);
}

// The resting page: the wall fades nearly away, the film's details rise, and the lit poster, where
// there is one, moves to its place.
async function rest({ stage, wall, frame, film, result, actions, info, backdrop, spot }) {
  wall.root.classList.add("revealed");
  stage.classList.add("revealed");
  const shown = feature(info, film, result, backdrop);
  frame.showing.append(shown);
  frame.aside.append(...choices(info, film, result, actions));
  // Measured once the aside is whole, so the poster takes only the height left beneath it.
  if (spot) {
    const slot = h("div", { class: "poster-slot" });
    frame.left.append(slot);
    settle(spot, slot);
  }
  if (isPhone()) {
    stage.scrollTop = 0;
    await wait(PHONE_HOLD_MS);
    shown.scrollIntoView({ behavior: prefersLessMotion() ? "auto" : "smooth", block: "start" });
  }
}

// Where the check turned the first pick away, the line says so before the new pick lands.
async function sayWhySwapped(line, result) {
  if (!result.swapped) return;
  await typeLine(line, result.swapped.line, "");
  await wait(900);
}

// The page's pick screen. `actions` holds notThatOne, justPick, startOver, failed and the correction panel's builder.
export async function showPick({ stage, wall, result, frame, actions }) {
  const film = result.film;
  const { line } = frame;
  if (!film) return showNoFilm(result, frame, actions);
  await sayWhySwapped(line, result);
  const cardRequest = get(`/api/film/${film.tmdb}`);
  const posterReady = picture(`/img/poster/${film.tmdb}/l`, `${film.title} poster`);
  const backdropReady = isPhone() ? null : picture(`/img/backdrop/${film.tmdb}/l`, `${film.title}, a still from the film`);
  const spot = await land(stage, wall, posterReady);
  const left = () => !frame.showing.isConnected; // the viewer took a way back out of the pick
  if (left()) return spot?.remove();
  await Promise.all([typeLine(line, HERE, ""), inTheLight(spot)]);
  if (left()) return spot?.remove();
  const [card, backdrop] = await Promise.all([cardRequest, backdropReady]);
  if (!card.ok) {
    spot?.remove();
    return actions.failed(card.data);
  }
  return rest({ stage, wall, frame, film, result, actions, info: card.data, backdrop, spot });
}
