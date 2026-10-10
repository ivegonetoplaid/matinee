// The pick. The wall hunts across itself to the picked film's poster and lands it at the centre of the
// screen. The poster brightens as the rest of the wall dims, then grows in place while the pick's line
// types out. After a beat it travels from exactly where it hangs to its resting place. On a desktop
// that is the foot of the left column, as large as the space allows, while the film's backdrop rises on
// the right with its title, year and synopsis. On a phone Matinee's line keeps the foot of the screen;
// above it the hunt lands, the poster fills the space, and after a hold that space scrolls gently to the
// details.
// The film is tonight's showing, never a search result.

import { get } from "./api.js";
import { twoParts } from "./door-rules.js";
import { h, isPhone, prefersLessMotion, sentenceCase, wait } from "./dom.js";
import { dtddBeside } from "./credits.js";
import { backdropUrl, corsImage } from "./pictures.js";
import { panelAction } from "./panel.js";
import { typeLine } from "./type.js";

const BEAT_MS = 500; // the grown poster holds for one beat before it moves to rest
const STILL_HOLD_MS = 2000; // under reduced motion there is no hunt or growth; the grown poster holds about as long
const SETTLE_MS = 1300;
const PHONE_HOLD_MS = 2200;
const POSTER_RATIO = 1.5; // height over width
const POSTER_MIN_H = 160; // below this the page scrolls rather than shrink the poster further
const PICTURE_WAIT_MS = 10000; // a picture not drawable by then is given up, as the server gives up on the media server

// A picture fetched ahead of its moment. Resolves to the image once it can be drawn, or to null when it
// fails or has not arrived within PICTURE_WAIT_MS. A picture given up on is stopped and never shown.
function picture(src, alt) {
  const img = corsImage();
  img.alt = alt;
  img.src = src;
  const drawn = img.decode().then(
    () => img,
    () => null,
  );
  const late = wait(PICTURE_WAIT_MS).then(() => null);
  return Promise.race([drawn, late]).then((got) => {
    if (got) return got;
    img.removeAttribute("src");
    console.warn("a picture failed or took too long; the pick goes on without it", src);
    return null;
  });
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

// How well audiences regard the film, as its card ranks it: a line in the display face, with what it is counted by
// beside it in quiet text. Null when the film has no rank.
function rankLine(card) {
  if (!card.rank) return null;
  return h("p", { class: "rank" }, h("span", { class: "rank-words" }, card.rank), " ", h("span", { class: "rank-by" }, "by audience votes"));
}

// The film's tags, its strongest genome words, as outlined chips; null when it has none. They describe the film
// and never say why it was picked.
function tagList(card) {
  if (!card.tags?.length) return null;
  return h("ul", { class: "tags", "aria-label": "Tags" }, card.tags.map((tag) => h("li", { class: "tag" }, sentenceCase(tag))));
}

// What the pick says about the film beyond its title: its rank, then its tags. Null when there is nothing to say,
// so the layout closes up. On a desktop it stands under Matinee's line; on a phone, under the film's title.
function facts(card) {
  const said = [rankLine(card), tagList(card)].filter(Boolean);
  return said.length ? h("div", { class: "facts" }, said) : null;
}

function heading(film) {
  return h("h2", { class: "film-title" }, film.title, film.year ? h("span", { class: "film-year" }, ` ${film.year}`) : null);
}

// The film's details. `backdrop` is a loaded picture, or null where there is none to show: a phone's
// resting page shows no backdrop, and a backdrop that failed is left out.
function feature(card, film, result, backdrop) {
  if (backdrop) backdrop.className = "backdrop";
  const unchecked = result.unchecked ? [h("p", { class: "note" }, result.unchecked), dtddBeside(), lookUp(result)] : [];
  const phoneFacts = isPhone() ? facts(card) : null;
  return h(
    "div",
    { class: "feature" },
    backdrop,
    h("div", { class: "feature-text" }, heading(film), phoneFacts, h("p", { class: "synopsis" }, card.synopsis || ""), unchecked),
  );
}

// A film the check could not answer for: its own page on DoesTheDogDie when the reply carries its item,
// else DoesTheDogDie's main page, where the viewer can search for it. The address depends on the item alone.
function lookUp(result) {
  const href = result.dtdd_item ? `${result.link}/media/${Number(result.dtdd_item)}` : result.link;
  return h("a", { class: "action petrol", href, target: "_blank", rel: "noopener noreferrer" }, "Look it up on DoesTheDogDie ↗");
}

// DoesTheDogDie's credit for a line built on its data: directly beneath Matinee's line, before the line starts to
// type, so it is on screen for as long as the line is. Once per pick.
function creditLine(frame) {
  if (frame.aside.querySelector(":scope > .beside-credit")) return;
  frame.line.after(dtddBeside());
}

// Adds "What were you going to show me?", which reveals the film the check turned away, to `note`, the
// place beneath the actions kept for it.
function firstPickReveal(result, note) {
  const swapped = result.swapped;
  const shown = h("p", { class: "note", hidden: true });
  shown.textContent = `${swapped.film.title}${swapped.film.year ? ` (${swapped.film.year})` : ""}: ${swapped.topics
    .map((t) => sentenceCase(t))
    .join(", ")}.`;
  const ask = h(
    "button",
    {
      class: "action cream",
      type: "button",
      onclick: () => {
        shown.hidden = false;
        ask.remove();
      },
    },
    swapped.reveal,
  );
  // The reason itself is the pick's line; the note carries the way to see the film.
  note.append(ask, shown);
  return note;
}

// No film: every film left tripped the list, or three in a row did and the viewer may roll again or see
// the last of them, its trip named.
async function showNoFilm(result, frame, actions) {
  const { line, aside } = frame;
  creditLine(frame);
  const [said, more] = twoParts(result.tired || result.exhausted); // first sentence gold, the rest cream
  await typeLine(line, said, more);
  const startOver = h("button", { class: "action cream start-over", type: "button", onclick: actions.startOver }, "Start over");
  // A phone sets "Start over" beside "Roll again", so all three fit its foot.
  const choices = result.tired
    ? h(
        "div",
        { class: "choices" },
        h("button", { class: "action gold", type: "button", onclick: actions.rollAgain }, "Roll again"),
        h(
          "button",
          { class: "action gold show-picked", type: "button", onclick: () => actions.showPicked(result) },
          "Just show me what you picked",
        ),
        startOver,
      )
    : startOver;
  aside.append(choices);
  fillBar(frame, [backAction(frame, actions)]);
}

// The pick's link reads by where it goes: the configured Seerr, or TMDB without one.
function moreOn(info) {
  if (info.link_to === "seerr") {
    return h("a", { class: "action petrol", href: info.link, target: "_blank", rel: "noopener noreferrer" }, "More on Seerr ↗");
  }
  return h("a", { class: "action petrol", href: info.link, target: "_blank", rel: "noopener noreferrer" }, "More on TMDB ↗");
}

// What sits under the line and its facts on the resting page: the film's link, then the swap reason's credit,
// `note`, beneath it.
function underLine(info, result, note) {
  return [info.link ? h("div", { class: "choices" }, moreOn(info)) : null, note ? firstPickReveal(result, note) : null].filter(Boolean);
}

// "‹ Back", which opens the panel with the way back.
function backAction(frame, actions) {
  const back = panelAction("‹ Back", () => frame.panel.open(back, "Go back to…", actions.backPanel()));
  return back;
}

// The pick's foot bar: `left` at its left, `centre` at its exact centre, its right end empty. On a phone the bar
// stands at the foot of Matinee's words.
function fillBar(frame, left, centre = null) {
  frame.bar.replaceChildren(h("div", { class: "bar-left" }, left), h("div", { class: "bar-centre" }, centre), h("div"));
  if (isPhone()) frame.aside.append(frame.bar);
}

// The resting pick's actions: "‹ Back" and "Wrong pick?" at the bar's left, "Not that one" at its centre.
function pickBar(frame, film, actions) {
  const nope = h("button", { class: "action rose lead", type: "button", onclick: actions.notThatOne }, "Not that one");
  fillBar(frame, [backAction(frame, actions), actions.noteLink(film, frame.panel)], nope);
}

// On a desktop the facts stand under Matinee's line, and the resting line gives up the room it kept for four lines
// so they stand one gap under its words; a lit fuse keeps that room, since its countdown still changes the line.
function factsUnderLine(frame, info, fuse) {
  if (!fuse?.lit()) frame.line.classList.add("rested");
  const said = facts(info);
  if (said) (frame.aside.querySelector(":scope > .beside-credit") ?? frame.line).after(said);
}

// The resting page: the film's details rise, and the landed poster, where there is one, moves from the
// wall to its place and leaves its cell empty until the pick ends.
async function rest({ stage, wall, frame, film, result, actions, info, backdrop, poster, fuse }) {
  stage.classList.add("revealed");
  const shown = feature(info, film, result, backdrop);
  frame.showing.append(shown);
  if (!isPhone()) factsUnderLine(frame, info, fuse);
  frame.aside.append(...underLine(info, result, frame.aside.querySelector(".swap-note")));
  pickBar(frame, film, actions);
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
  const copy = corsImage();
  copy.alt = `${film.title} poster`;
  copy.src = tile.currentSrc;
  return copy.decode().then(
    () => copy,
    () => null,
  );
}

// Where the check turned the first pick away, the line says so before the new pick lands.
// Where the check turned a film away, its reason takes the nope line's place in gold at once, with
// DoesTheDogDie's credit in the foot band, and only the reveal line is redealt to fit beneath it. Resolves to
// the gold line that stays through the hunt: the reason, or the nope line, or "" when nothing stays.
async function goldLine(frame, result, lines, fuse) {
  const { line, aside } = frame;
  // A film shown after three tripped the list names its trip from DoesTheDogDie's data.
  if (result.last) creditLine(frame);
  if (!result.swapped) return lines.gold || "";
  fuse?.cancel();
  lines.reveal = lines.beneath(result.swapped.line);
  // The reason and the turned-away film are DoesTheDogDie's data: its credit stands in the note that reveals the film.
  aside.append(h("div", { class: "swap-note" }, dtddBeside()));
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

// The page's pick screen. `door` is the tree the film was drawn through, which its rank counts among (null before
// a door). `actions` holds notThatOne, rollAgain, showPicked, startOver, backPanel (what the Back panel holds),
// failed and the note link panel's builder. `readUntil` (a performance.now() time) holds the hunt until the line on screen has
// been read. After every wait the pick checks that its screen is still showing and that the pick was
// not ended on the wall: a way back or the name tag can end it at any moment, and a pick the viewer
// has left changes nothing further.
export async function showPick({ stage, wall, result, frame, readUntil = 0, lines, fuse = null, actions, door }) {
  const film = result.film;
  if (!film) {
    fuse?.cancel();
    return showNoFilm(result, frame, actions);
  }
  const round = wall.round;
  const left = () => !frame.showing.isConnected || wall.round !== round;
  const gold = await goldLine(frame, result, lines, fuse);
  if (left()) return undefined;
  const { cardRequest, posterReady, backdropReady } = fetchFilm(film, wall, door);
  // The words fade as the drift stops; a gold line (a nope line, or why a film was turned away) stays.
  const onStop = () => {
    if (!gold && !fuse?.lit()) frame.line.classList.add("hushed");
  };
  const pause = await wall.hunt(film.tmdb, { notBefore: readUntil, onStop, lift: huntLift(stage, frame) });
  if (pause === null || left()) return undefined;
  const out = await bringOut({ wall, frame, pause, posterReady, left, lines, gold, fuse });
  if (!out) return undefined;
  return toRest({ stage, wall, frame, film, result, actions, left, out, cardRequest, backdropReady, fuse });
}

// After the beat, once the film's details and backdrop have arrived, the poster moves to rest.
async function toRest({ stage, wall, frame, film, result, actions, left, out, cardRequest, backdropReady, fuse }) {
  const beat = wait(prefersLessMotion() ? STILL_HOLD_MS : BEAT_MS);
  const [card, backdrop] = await Promise.all([cardRequest, backdropReady, out.typing, beat]);
  if (left()) return undefined;
  if (!card.ok) return actions.failed(card.data);
  const poster = out.shown ? await restingPoster(out.sharp.img, wall, film) : null;
  if (left()) return undefined;
  out.sharp.resting = poster;
  return rest({ stage, wall, frame, film, result, actions, info: card.data, backdrop, poster, fuse });
}

// What the pick fetches as soon as it knows the film: its details, ranked among `door`'s films (null before a
// door), its sharp poster and, on a desktop, its backdrop. With TMDB as the image source the backdrop waits for the details, which carry its TMDB
// path; otherwise it is fetched at once. A phone's resting page shows no backdrop, so a phone fetches none.
function fetchFilm(film, wall, door) {
  const cardRequest = get(`/api/film/${film.tmdb}${door ? `?door=${encodeURIComponent(door)}` : ""}`);
  const still = `${film.title}, a still from the film`;
  let backdropReady = null;
  if (!isPhone() && wall.fromTmdb) {
    backdropReady = cardRequest.then((card) => picture(backdropUrl(film.tmdb, "l", card.ok ? card.data.backdrop_path : null), still));
  } else if (!isPhone()) {
    backdropReady = picture(backdropUrl(film.tmdb, "l", null), still);
  }
  return { cardRequest, posterReady: picture(wall.posterUrl(film.tmdb, "l"), `${film.title} poster`), backdropReady };
}
