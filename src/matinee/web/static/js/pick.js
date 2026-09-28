// The pick. The film's poster appears in a searchlight and lifts into it while "Here. Watch this
// one." types out. It holds in the light for a beat, then travels to its resting place. On a desktop that
// is the foot of the left column, as large as the space allows, while the film's backdrop rises on the
// right with its title, year and synopsis. On a phone the poster fills the screen, then the page
// scrolls gently to the details.
// The film is tonight's showing, never a search result.

import { get } from "./api.js";
import { h, isPhone, prefersLessMotion, sentenceCase, wait } from "./dom.js";
import { typeLine } from "./type.js";

const LIGHT_FADE_MS = 400; // the light leaves early in the move to rest, before the backdrop rises over it
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

// Where this pick lands on the screen, in px; the places take turns.
function nextPlace() {
  const at = (isPhone() ? SPOTS.phone : SPOTS.desktop)[spotTurn % 4];
  spotTurn += 1;
  return [at[0] * window.innerWidth, at[1] * window.innerHeight];
}

function placed(el, [x, y]) {
  el.style.left = `${x}px`;
  el.style.top = `${y}px`;
  return el;
}

// The lit poster. `poster` is a picture that can already be drawn.
function spotlight(poster, place) {
  poster.className = "spot-poster";
  return placed(h("div", { class: "spot", "aria-hidden": "true" }, poster), place);
}

// The searchlight: one soft pool of warm light over the landing place.
function searchlight(place) {
  const pool = h("div", { class: "spot-glow" });
  return placed(h("div", { class: "searchlight", "aria-hidden": "true" }, pool), place);
}

function glideEase() {
  return getComputedStyle(document.documentElement).getPropertyValue("--glide-ease");
}

// Fades the light out over `ms`, fastest at first, then removes it.
function fadeAway(light, ms) {
  if (prefersLessMotion()) return light.remove();
  const fade = light.animate([{ opacity: 1 }, { opacity: 0 }], { duration: ms, easing: glideEase(), fill: "forwards" });
  fade.onfinish = () => light.remove();
  return undefined;
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

// Land: the searchlight comes up at the landing place and the lit poster appears in it and starts
// its lift. A poster whose picture arrives late appears late. Resolves to the spot and the light; the
// spot is null when the poster has no picture (then there is nothing to lift, the light fades, and the
// pick goes straight to the film) or when `left()` says the viewer has left the pick while the picture
// was on its way.
async function land(stage, posterReady, left) {
  const place = nextPlace();
  const light = searchlight(place);
  stage.append(light);
  const poster = await posterReady;
  if (left()) return { spot: null, light };
  if (!poster) {
    fadeAway(light, LIGHT_FADE_MS);
    return { spot: null, light: null };
  }
  const spot = spotlight(poster, place);
  stage.append(spot);
  return { spot, light };
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

// The resting page: the film's details rise, and the lit poster, where
// there is one, moves to its place.
async function rest({ stage, frame, film, result, actions, info, backdrop, spot, light }) {
  stage.classList.add("revealed");
  const shown = feature(info, film, result, backdrop);
  frame.showing.append(shown);
  frame.aside.append(...choices(info, film, result, actions));
  // Measured once the aside is whole, so the poster takes only the height left beneath it.
  if (spot) {
    const slot = h("div", { class: "poster-slot" });
    frame.left.append(slot);
    settle(spot, slot);
    fadeAway(light, LIGHT_FADE_MS);
  }
  if (isPhone()) {
    stage.scrollTop = 0;
    await wait(PHONE_HOLD_MS);
    shown.scrollIntoView({ behavior: prefersLessMotion() ? "auto" : "smooth", block: "start" });
  }
}

// "Here. Watch this one." types while the poster lifts and holds for its beat; then resolves to what
// `pending` resolves to: the film's details and its backdrop.
async function inTheLightThen(line, spot, pending) {
  await Promise.all([typeLine(line, HERE, ""), inTheLight(spot)]);
  return Promise.all(pending);
}

// Takes the lit poster and the light off the page when the pick ends early.
function leave(spot, light) {
  spot?.remove();
  light?.remove();
}

// Where the check turned the first pick away, the line says so before the new pick lands.
async function sayWhySwapped(line, result) {
  if (!result.swapped) return;
  await typeLine(line, result.swapped.line, "");
  await wait(900);
}

// The page's pick screen. `actions` holds notThatOne, justPick, startOver, failed and the correction
// panel's builder. After every wait the pick checks that its screen is still showing: a trail answer or
// the name tag can replace it at any moment, and a pick the viewer has left changes nothing further.
export async function showPick({ stage, result, frame, actions }) {
  const film = result.film;
  if (!film) return showNoFilm(result, frame, actions);
  const left = () => !frame.showing.isConnected;
  await sayWhySwapped(frame.line, result);
  if (left()) return undefined;
  const cardRequest = get(`/api/film/${film.tmdb}`);
  const posterReady = picture(`/img/poster/${film.tmdb}/l`, `${film.title} poster`);
  const backdropReady = isPhone() ? null : picture(`/img/backdrop/${film.tmdb}/l`, `${film.title}, a still from the film`);
  const { spot, light } = await land(stage, posterReady, left);
  const [card, backdrop] = left() ? [] : await inTheLightThen(frame.line, spot, [cardRequest, backdropReady]);
  if (left()) return leave(spot, light);
  if (!card.ok) {
    leave(spot, light);
    return actions.failed(card.data);
  }
  return rest({ stage, frame, film, result, actions, info: card.data, backdrop, spot, light });
}
