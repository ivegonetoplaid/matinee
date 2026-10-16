// The household's shared ratings of a film: a line under the pick's rank naming the first profiles that shared one,
// and the reading panel that shows each one's rating and short review. Short reviews are shown as text, never markup.

import { h } from "./dom.js";
import { mark } from "./mark.js";
import { OPENER } from "./panel.js";
import { said } from "./ratings.js";

// How many sharing profiles the line names before "+ N more".
const NAMED = 2;

// One name on the line, as a sentence: "Alex loved it", a ✎ after the name of one who left a short review.
function nameButton(r, onOpen) {
  const words = `${r.name}${r.review ? " ✎" : ""} ${said(r.score)}`;
  return h("button", { class: "household-name", type: "button", [OPENER]: true, "aria-expanded": "false", onclick: (e) => onOpen(e.currentTarget, r.name) }, words);
}

// The line under the rank, in the household's colour: the first NAMED sharing profiles, newest rating first, then
// "+ N more" when more have shared. Null when no other profile has shared a rating of the film.
export function householdLine(shared, onOpen) {
  if (!shared.length) return null;
  const named = shared.slice(0, NAMED).map((r) => nameButton(r, onOpen));
  const more =
    shared.length > NAMED
      ? h("button", { class: "household-more", type: "button", [OPENER]: true, "aria-expanded": "false", onclick: (e) => onOpen(e.currentTarget, shared[0].name) }, `+ ${shared.length - NAMED} more`)
      : null;
  const parts = [...named, more].filter(Boolean).map((part, i) => (i ? h("span", { class: "household-part" }, h("span", { "aria-hidden": "true" }, "·"), part) : part));
  return h("p", { class: "household", "aria-label": "Shared by your household" }, parts);
}

// The reading panel's body: the chosen profile's mark, name, rating as a sentence and short review, then every
// profile that shared a rating of the film, "My review" first, each a row that shows theirs. `mine` is the viewer's
// own rating or null; `viewer` is { name, avatar }.
export function readingPanel({ shared, mine, viewer, first }) {
  const me = { name: "My review", avatar: viewer.avatar, initialsOf: viewer.name, score: mine?.score ?? null, review: mine?.review ?? null, own: true };
  const people = [me, ...shared.map((r) => ({ ...r, initialsOf: r.name }))];
  const card = h("div", { class: "reading-card", "aria-live": "polite" });
  const rows = people.map((p) => personRow(p, () => show(p)));
  function show(p) {
    card.replaceChildren(...readingCard(p));
    rows.forEach((row, i) => row.setAttribute("aria-current", String(people[i] === p)));
  }
  show(people.find((p) => !p.own && p.name === first) ?? people[1] ?? me);
  return [card, h("p", { class: "panel-section" }, "Others in the house who shared a rating"), h("div", { class: "people" }, rows)];
}

// The panel's own focus goes to the row whose rating the card shows, as it opens (panel.js focuses its first row).
export function focusShown(panel) {
  panel?.querySelector(".person-row[aria-current='true']")?.focus({ preventScroll: true });
}

function readingCard(p) {
  const who = mark({ name: p.initialsOf, avatar: p.avatar }, "panel");
  const sentence = p.score ? `${p.own ? "You" : p.name} ${said(p.score)}` : null;
  const words = [
    h("span", { class: "reading-name" }, p.name),
    sentence ? h("span", { class: "reading-said" }, sentence) : null,
    p.review ? h("span", { class: "reading-review" }, `“${p.review}”`) : null,
    p.own && !p.score ? h("span", { class: "reading-empty" }, "You haven't rated this one yet.") : null,
  ];
  return [who, h("div", { class: "reading-words" }, words)];
}

function personRow(p, onclick) {
  return h(
    "button",
    { class: "panel-row person-row", type: "button", onclick },
    mark({ name: p.initialsOf, avatar: p.avatar }, "bar"),
    h("span", { class: "row-title" }, p.name),
    h("span", { class: "person-said" }, p.score ? said(p.score) : "—"),
  );
}
