// "Films I've picked for you": the viewer's kept runs on one shelf per day, newest first. The newest day stands open;
// every earlier day is folded, its head showing a few of its posters and "Show". Inside a day each run is captioned
// with what the viewer asked for, and its films stand in the order shown, each in its case (its rating's, when the
// viewer has rated it) and captioned with what the viewer did with it.

import { filmCase } from "./cases.js";
import { h } from "./dom.js";
import { answerOf } from "./ratings.js";

const PEEK = 6; // posters a folded day's head shows

// What a run asked for: the door's and each answer's words, "Cowboys › Old", or "Just pick one!" with none.
export function runCaption(walk) {
  const words = walk.says.map((say) => say.trim().replace(/\.+$/, "")).filter(Boolean);
  return words.length ? words.map((w) => w[0].toUpperCase() + w.slice(1)).join(" › ") : "Just pick one!";
}

// What the viewer did with a film a run showed: its mark, else whether the run stopped on it. A film marked rated
// reads its current rating; one whose rating has since been cleared reads as if unmarked.
export function didWith(film, last, scoreOf) {
  if (film.mark === "hid") return "You hid it";
  if (film.mark === "reported") return "You reported it";
  if (film.mark === "rated" && scoreOf(film.tmdb)) return `You rated it: ${answerOf(scoreOf(film.tmdb))}`;
  return last ? "You landed on this one" : "You rolled past it";
}

// The runs on their days, in the viewer's own time (or `timeZone`'s), newest first, as the server lists them.
export function byDay(runs, timeZone = undefined) {
  const days = new Map();
  for (const run of runs) {
    const began = new Date(run.began);
    const key = began.toLocaleDateString("en-CA", { timeZone });
    if (!days.has(key)) days.set(key, { date: began, runs: [] });
    days.get(key).runs.push(run);
  }
  return [...days.values()];
}

const say = (date, how) => date.toLocaleDateString("en-GB", how);

const sameWalk = (a, b) => JSON.stringify([a.tree, a.answers, a.says, a.rushed]) === JSON.stringify([b.tree, b.answers, b.says, b.rushed]);

// A run as it is shown: one group per stretch of films reached by the same walk, since a viewer may change the door
// or an answer mid-run, each with what was asked for and each film with what the viewer did with it. Only the run's
// last film is the one it stopped on.
export function runGroups(run, scoreOf = () => null) {
  const groups = [];
  run.films.forEach((film, i) => {
    const last = groups.at(-1);
    const shown = { film, did: didWith(film, i === run.films.length - 1, scoreOf), score: scoreOf(film.tmdb) };
    if (last && sameWalk(last.walk, film.walk)) last.films.push(shown);
    else groups.push({ walk: film.walk, caption: runCaption(film.walk), films: [shown] });
  });
  return groups;
}

// A day's count, one ask for each "You asked for": "You asked once, 2 films" or "You asked 3 times, 9 films".
export function dayCount(day) {
  const n = day.runs.reduce((sum, r) => sum + r.films.length, 0);
  const asks = day.runs.reduce((sum, r) => sum + runGroups(r).length, 0);
  const asked = asks === 1 ? "You asked once" : `You asked ${asks} times`;
  return `${asked}, ${n} ${n === 1 ? "film" : "films"}`;
}

// A run inside an open day: for each walk in it, what was asked for, then its films in their cases, each captioned.
// A case tabbed to past the edge of a phone's row is brought into view.
function runShelf(run, { poster, scoreOf, phone, onOpen }) {
  const groups = runGroups(run, scoreOf).map((g) => {
    const films = g.films.map(({ film, did, score }) =>
      h(
        "div",
        { class: "shown-film" },
        filmCase({ tmdb: film.tmdb, title: film.title, poster: poster(film.tmdb, "m"), score, label: `${film.title}, ${did}`, onOpen: (opener) => onOpen(film, did, opener) }),
        h("p", { class: "shown-did", "aria-hidden": "true" }, did),
      ),
    );
    const row = h("div", { class: "run-films" }, films);
    row.addEventListener("focusin", (e) => e.target.scrollIntoView({ block: "nearest", inline: "nearest" }));
    return [h("p", { class: "run-asked" }, h("span", { class: "run-asked-lead" }, "You asked for"), " ", g.caption), row];
  });
  return h("div", { class: phone ? "run run-phone" : "run" }, groups);
}

// Every "You asked for" of the day, in one line for its head.
const captions = (day) => day.runs.flatMap((r) => runGroups(r).map((g) => g.caption)).join("   ·   ");

// One day's shelf: its head opens and folds it. A phone's folded head shows no date, but still says it.
function dayShelf(day, open, { poster, scoreOf, phone, onOpen }) {
  const peek = day.runs.flatMap((r) => r.films).slice(0, PEEK);
  const verb = h("span", { class: "day-verb" });
  const peeks = h("span", { class: "day-peek", "aria-hidden": "true" }, peek.map((f) => h("img", { src: poster(f.tmdb, "xs"), alt: "", loading: "lazy" })));
  const long = say(day.date, { weekday: "long", day: "numeric", month: "long" });
  const stub = h(
    "span",
    { class: "day-stub", "aria-hidden": "true" },
    h("span", { class: "stub-dow" }, say(day.date, { weekday: "short" })),
    h("span", { class: "stub-date" }, say(day.date, { day: "numeric" })),
    h("span", { class: "stub-month" }, say(day.date, { month: phone ? "short" : "long" })),
  );
  const said = phone
    ? [h("span", { class: "day-count" }, dayCount(day)), peeks, h("span", { class: "day-long" }, long)]
    : [h("span", { class: "day-long" }, long, " ", h("span", { class: "day-count" }, `· ${dayCount(day)}`)), h("span", { class: "day-caps" }, captions(day))];
  const head = h(
    "button",
    { class: "day-head", type: "button" },
    phone ? stub : null,
    h("span", { class: "day-words" }, said),
    phone ? null : peeks,
    h("span", { class: "day-toggle" }, verb, h("span", { class: "chev", "aria-hidden": "true" })),
  );
  const runs = h("div", { class: "day-runs" });
  const node = h("div", { class: "day" }, phone ? null : h("span", { class: "day-side" }, stub), h("div", { class: "day-body" }, head, runs));
  const set = (opened) => {
    node.classList.toggle("open", opened);
    head.setAttribute("aria-expanded", String(opened));
    verb.textContent = opened ? "Hide" : "Show";
    runs.hidden = !opened;
    if (phone) said.at(-1).classList.toggle("sr-only", !opened);
    runs.replaceChildren(...(opened ? day.runs.map((r) => runShelf(r, { poster, scoreOf, phone, onOpen })) : []));
  };
  head.addEventListener("click", () => set(!node.classList.contains("open")));
  if (!phone) stub.addEventListener("click", () => set(!node.classList.contains("open")));
  set(open);
  return node;
}

// Fills "Films I've picked for you" from the viewer's runs; `ratings` gives each film's current rating.
// `onOpen(film, did, opener)` opens a film, with what the viewer did with it.
export function shownPart(body, runs, ratings, { poster, phone, onOpen }) {
  const scores = new Map(ratings.map((r) => [r.tmdb, r.score]));
  const scoreOf = (tmdb) => scores.get(tmdb) ?? null;
  body.append(...byDay(runs).map((day, i) => dayShelf(day, i === 0, { poster, scoreOf, phone, onOpen })));
}
