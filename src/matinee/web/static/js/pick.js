// The pick. The wall hunts across itself to the picked film's poster and lands it at the centre of the
// screen. The poster brightens as the rest of the wall dims, then grows in place while the pick's line
// types out. After a beat it travels from exactly where it hangs to its resting place. On a desktop
// that is the foot of the left column, as large as the space allows, while the film's backdrop rises on
// the right with its title, year and synopsis. On a phone Matinee's line keeps the foot of the screen;
// above it the hunt lands, the poster fills the space, and after a hold that space scrolls gently to the
// details.
// The film is tonight's showing, never a search result.

import { get } from "./api.js";
import { h, isPhone, prefersLessMotion, sentenceCase, wait } from "./dom.js";
import { typeLine } from "./type.js";

const BEAT_MS = 500; // the grown poster holds for one beat before it moves to rest
const STILL_HOLD_MS = 2000; // under reduced motion there is no hunt or growth; the grown poster holds about as long
const SETTLE_MS = 1300;
const PHONE_HOLD_MS = 2200;
const POSTER_RATIO = 1.5; // height over width
const POSTER_MIN_H = 160; // below this the page scrolls rather than shrink the poster further

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
// the same corner it scales from, so it never jumps. It keeps the glow it wore on the wall, `glow(width)`.
function settle(poster, from, slot, glow) {
  const size = fit(slot);
  poster.className = "slot-poster";
  poster.style.width = `${size.width}px`;
  poster.style.height = `${size.height}px`;
  poster.style.boxShadow = `${glow(size.width)}, 0 24px 60px rgba(0, 0, 0, 0.6)`;
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

// DoesTheDogDie's credit beneath the line in `aside`, placed before a line built on its data starts to
// type, so the credit is on screen for as long as that line is. At rest it moves beneath the buttons.
function creditBeneath(aside, result) {
  const note = h("div", { class: "swap-note" }, h("p", { class: "note" }, credit(result)));
  aside.append(note);
  return note;
}

// Adds "What were you going to show me?", which reveals the film the check turned away, to `note`, the
// swap reason's credit.
function firstPickReveal(result, note) {
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
  // The reason itself is the pick's line; the note carries its credit and the way to see the film.
  note.append(ask, shown);
  return note;
}

// No film: every film left tripped the list, or three in a row did and the viewer
// may roll again or have one picked without the check turning any away.
async function showNoFilm(result, { line, aside }, actions) {
  const note = h("p", { class: "note" }, credit(result));
  aside.append(note);
  await typeLine(line, result.tired || result.exhausted, "");
  const startOver = h("button", { class: "pill gold", type: "button", onclick: actions.startOver }, "Start over");
  if (!result.tired) {
    aside.append(startOver, note);
    return;
  }
  aside.append(
    h(
      "div",
      { class: "choices" },
      h("button", { class: "pill gold", type: "button", onclick: actions.rollAgain }, "Roll again"),
      h("button", { class: "pill velvet", type: "button", onclick: actions.justPick }, "Just pick one"),
    ),
    h("button", { class: "link-button", type: "button", onclick: actions.startOver }, "Start over"),
    note,
  );
}

// What sits under the line on the resting page. The buttons come straight after the line, which keeps
// four lines of room whatever its words, so "Not that one" sits in the same place for every film. The
// swap reason's credit, `note`, moves beneath them. The answers so far are in the trail at the foot of
// the screen.
function choices(info, film, result, actions, note) {
  const buttons = h(
    "div",
    { class: "choices" },
    h("button", { class: "pill velvet", type: "button", onclick: actions.notThatOne }, "Not that one"),
    info.seerr ? h("a", { class: "seerr", href: info.seerr, target: "_blank", rel: "noopener noreferrer" }, "More on Seerr") : null,
    h("button", { class: "link-button", type: "button", onclick: actions.startOver }, "Start over"),
  );
  return [buttons, note ? firstPickReveal(result, note) : null, actions.correction(film)].filter(Boolean);
}

// The resting page: the film's details rise, and the landed poster, where there is one, moves from the
// wall to its place and leaves its cell empty until the pick ends.
async function rest({ stage, wall, frame, film, result, actions, info, backdrop, poster }) {
  stage.classList.add("revealed");
  const shown = feature(info, film, result, backdrop);
  frame.showing.append(shown);
  frame.aside.append(...choices(info, film, result, actions, frame.aside.querySelector(".swap-note")));
  // Measured once the aside is whole, so the poster takes only the height left beneath it.
  const from = wall.landedTile()?.img.getBoundingClientRect();
  if (poster && from) {
    const slot = h("div", { class: "poster-slot" });
    frame.left.append(slot);
    settle(poster, from, slot, (w) => wall.glowAt(w));
    wall.lift(true);
  }
  if (isPhone()) {
    frame.showing.scrollTop = 0;
    await wait(PHONE_HOLD_MS);
    if (frame.showing.isConnected) shown.scrollIntoView({ behavior: prefersLessMotion() ? "auto" : "smooth", block: "start" });
  }
}

// The poster to carry to rest: the sharp picture when it has loaded, else a copy of the wall's own
// picture of the film once that copy can be drawn, else null, and no poster rests.
async function restingPoster(sharp, wall, film) {
  if (sharp) return sharp;
  const tile = wall.landedTile()?.img;
  if (!tile?.currentSrc || tile.currentSrc.endsWith("/blank.svg") || !(tile.naturalWidth > 1)) return null;
  const copy = new Image();
  copy.alt = `${film.title} poster`;
  copy.src = tile.currentSrc;
  return copy.decode().then(
    () => copy,
    () => null,
  );
}

// Where the check turned the first pick away, the line says so before the new pick lands.
// Where the check turned a film away, its reason takes the nope line's place in gold at once, with
// DoesTheDogDie's credit beneath it, and only the reveal line is redealt to fit beneath it. Resolves to
// the gold line that stays through the hunt: the reason, or the nope line, or "" when nothing stays.
async function goldLine({ line, aside }, result, lines, fuse) {
  if (!result.swapped) return lines.gold || "";
  fuse?.cancel();
  lines.reveal = lines.beneath(result.swapped.line);
  creditBeneath(aside, result);
  await typeLine(line, result.swapped.line, "");
  return result.swapped.line;
}

// The line as the poster lands. A reply read before the hunt is cleared before the line comes back, so it
// never shows again; a gold line that stayed through the hunt stays, and the reveal line types beneath it
// after `wait` ms. A lit fuse owns the line: it counts down and burns on its own clock, and no reveal
// line follows. Resolves once the line is whole.
function revealLine({ line, gold, lines, wait: ms, fuse }) {
  line.classList.remove("hushed");
  if (fuse?.lit()) return Promise.resolve();
  if (!gold) line.replaceChildren();
  return wait(ms).then(() => typeLine(line, gold, lines.reveal, { shown: gold.length }));
}

// On a phone, how far above the screen's centre the hunt lands: at the middle of the space between the
// top bar and Matinee's line, which keeps the foot. On a desktop, 0.
function huntLift(stage, frame) {
  if (!isPhone()) return 0;
  const top = stage.querySelector(".topbar")?.getBoundingClientRect().bottom || 0;
  const foot = frame.aside.getBoundingClientRect().top;
  return window.innerHeight / 2 - (top + foot) / 2;
}

// From the landing to the grown poster. The sharp picture takes the wall picture's place as soon as it
// can be drawn, on the wall and later at rest. A poster that landed without a picture waits for its
// sharp one; with neither, nothing grows and the wall steps back for the resting page. The line types
// while the poster grows. Resolves to { shown, sharp, typing }, or null when the viewer left.
async function bringOut({ wall, frame, pause, posterReady, left, lines, gold, fuse }) {
  const sharp = { img: null, resting: null };
  const sharpShown = posterReady.then(async (img) => {
    if (!img || left()) return;
    sharp.img = img;
    await wall.useSharp(img.src);
    if (sharp.resting && sharp.resting !== img) sharp.resting.src = img.src;
  });
  if (!wall.landedHasPicture()) await sharpShown;
  if (left()) return null;
  const shown = wall.landedHasPicture();
  const typing = revealLine({ line: frame.line, gold, lines, wait: prefersLessMotion() || !shown ? 0 : pause * 1000, fuse });
  if (!shown) wall.stepBack();
  else if (!(await wall.bringForward(pause))) return null;
  return { shown, sharp, typing };
}

// The page's pick screen. `actions` holds notThatOne, rollAgain, justPick, startOver, failed and the correction
// panel's builder. `readUntil` (a performance.now() time) holds the hunt until the line on screen has
// been read. After every wait the pick checks that its screen is still showing and that the pick was
// not ended on the wall: a trail answer or the name tag can end it at any moment, and a pick the viewer
// has left changes nothing further.
export async function showPick({ stage, wall, result, frame, readUntil = 0, lines, fuse = null, actions }) {
  const film = result.film;
  if (!film) {
    fuse?.cancel();
    return showNoFilm(result, frame, actions);
  }
  const round = wall.round;
  const left = () => !frame.showing.isConnected || wall.round !== round;
  const gold = await goldLine(frame, result, lines, fuse);
  if (left()) return undefined;
  const { cardRequest, posterReady, backdropReady } = fetchFilm(film);
  // The words fade as the drift stops; a gold line (a nope line, or why a film was turned away) stays.
  const onStop = () => {
    if (!gold && !fuse?.lit()) frame.line.classList.add("hushed");
  };
  const pause = await wall.hunt(film.tmdb, { notBefore: readUntil, onStop, lift: huntLift(stage, frame) });
  if (pause === null || left()) return undefined;
  const out = await bringOut({ wall, frame, pause, posterReady, left, lines, gold, fuse });
  if (!out) return undefined;
  return toRest({ stage, wall, frame, film, result, actions, left, out, cardRequest, backdropReady });
}

// After the beat, once the film's details and backdrop have arrived, the poster moves to rest.
async function toRest({ stage, wall, frame, film, result, actions, left, out, cardRequest, backdropReady }) {
  const beat = wait(prefersLessMotion() ? STILL_HOLD_MS : BEAT_MS);
  const [card, backdrop] = await Promise.all([cardRequest, backdropReady, out.typing, beat]);
  if (left()) return undefined;
  if (!card.ok) return actions.failed(card.data);
  const poster = out.shown ? await restingPoster(out.sharp.img, wall, film) : null;
  if (left()) return undefined;
  out.sharp.resting = poster;
  return rest({ stage, wall, frame, film, result, actions, info: card.data, backdrop, poster });
}

// What the pick fetches as soon as it knows the film: its details, its sharp poster and, on a desktop,
// its backdrop. A phone's resting page shows no backdrop, so a phone fetches none.
function fetchFilm(film) {
  return {
    cardRequest: get(`/api/film/${film.tmdb}`),
    posterReady: picture(`/img/poster/${film.tmdb}/l`, `${film.title} poster`),
    backdropReady: isPhone() ? null : picture(`/img/backdrop/${film.tmdb}/l`, `${film.title}, a still from the film`),
  };
}
