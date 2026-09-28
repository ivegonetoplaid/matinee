// The pick. The wall hunts across itself to the picked film's poster and lands it at the centre of the
// screen, and "Here. Watch this one." types out. After a beat the poster travels from exactly where it
// hangs to its resting place. On a desktop that is the foot of the left column, as large as the space
// allows, while the film's backdrop rises on the right with its title, year and synopsis. On a phone the
// poster fills the screen, then the page scrolls gently to the details.
// The film is tonight's showing, never a search result.

import { get } from "./api.js";
import { h, isPhone, prefersLessMotion, sentenceCase, wait } from "./dom.js";
import { typeLine } from "./type.js";

const BEAT_MS = 500; // the landed poster holds for one beat before it moves to rest
const STILL_HOLD_MS = 2000; // under reduced motion there is no hunt; the landed poster holds about as long
const SETTLE_MS = 1300;
const PHONE_HOLD_MS = 2200;
const POSTER_RATIO = 1.5; // height over width
const POSTER_MIN_H = 160; // below this the page scrolls rather than shrink the poster further
const HERE = "Here. Watch this one.";

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

// The poster's resting box: as tall as the slot allows at 2:3, never wider than the slot.
function fit(slot) {
  const box = slot.getBoundingClientRect();
  const height = Math.min(box.width * POSTER_RATIO, Math.max(POSTER_MIN_H, box.height));
  return { width: height / POSTER_RATIO, height };
}

// Moves `poster` into `slot` in the page's flow, carried from `from`, the screen box where it hung on the
// wall. The slot is placed by the caller before this runs. The move starts from that box, measured from
// the same corner it scales from, so it never jumps.
function settle(poster, from, slot) {
  const size = fit(slot);
  poster.className = "slot-poster";
  poster.style.width = `${size.width}px`;
  poster.style.height = `${size.height}px`;
  slot.append(poster);
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

// The resting page: the film's details rise, and the landed poster, where there is one, moves from the
// wall to its place and leaves its cell empty until the pick ends.
async function rest({ stage, wall, frame, film, result, actions, info, backdrop, poster }) {
  stage.classList.add("revealed");
  const shown = feature(info, film, result, backdrop);
  frame.showing.append(shown);
  frame.aside.append(...choices(info, film, result, actions));
  // Measured once the aside is whole, so the poster takes only the height left beneath it.
  const from = wall.landedTile()?.img.getBoundingClientRect();
  if (poster && from) {
    const slot = h("div", { class: "poster-slot" });
    frame.left.append(slot);
    settle(poster, from, slot);
    wall.lift(true);
  }
  if (isPhone()) {
    stage.scrollTop = 0;
    await wait(PHONE_HOLD_MS);
    shown.scrollIntoView({ behavior: prefersLessMotion() ? "auto" : "smooth", block: "start" });
  }
}

// The poster to carry to rest: the sharp picture when it has loaded, else the wall's own picture of
// the film when it has one, else null, and no poster rests.
function restingPoster(sharp, wall, film) {
  if (sharp) return sharp;
  const tile = wall.landedTile()?.img;
  if (!tile?.currentSrc || tile.currentSrc.endsWith("/blank.svg") || !tile.naturalWidth) return null;
  const copy = new Image();
  copy.alt = `${film.title} poster`;
  copy.src = tile.currentSrc;
  return copy;
}

// Where the check turned the first pick away, the line says so before the new pick lands.
async function sayWhySwapped(line, result) {
  if (!result.swapped) return;
  await typeLine(line, result.swapped.line, "");
  await wait(900);
}

// The page's pick screen. `actions` holds notThatOne, justPick, startOver, failed and the correction
// panel's builder. `readUntil` (a performance.now() time) holds the hunt until the line on screen has
// been read. After every wait the pick checks that its screen is still showing and that the pick was
// not ended on the wall: a trail answer or the name tag can end it at any moment, and a pick the viewer
// has left changes nothing further.
export async function showPick({ stage, wall, result, frame, readUntil = 0, actions }) {
  const film = result.film;
  if (!film) return showNoFilm(result, frame, actions);
  const round = wall.round;
  const left = () => !frame.showing.isConnected || wall.round !== round;
  await sayWhySwapped(frame.line, result);
  if (left()) return undefined;
  const cardRequest = get(`/api/film/${film.tmdb}`);
  const posterReady = picture(`/img/poster/${film.tmdb}/l`, `${film.title} poster`);
  const backdropReady = isPhone() ? null : picture(`/img/backdrop/${film.tmdb}/l`, `${film.title}, a still from the film`);
  // The words fade as the drift stops; the reason a film was turned away stays on screen.
  const onStop = () => {
    if (!result.swapped) frame.line.classList.add("hushed");
  };
  const pause = await wall.hunt(film.tmdb, { notBefore: readUntil, onStop });
  if (pause === null || left()) return undefined;
  frame.line.classList.remove("hushed");
  const hold = prefersLessMotion() ? STILL_HOLD_MS : pause * 1000 + BEAT_MS;
  const [card, backdrop, sharp] = await Promise.all([cardRequest, backdropReady, posterReady, typeLine(frame.line, HERE, ""), wait(hold)]);
  if (left()) return undefined;
  if (!card.ok) return actions.failed(card.data);
  const poster = restingPoster(sharp, wall, film);
  return rest({ stage, wall, frame, film, result, actions, info: card.data, backdrop, poster });
}
