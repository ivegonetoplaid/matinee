// A film on My profile stands in a case: its title on the case's plate, its poster in the window. A rated film's case
// shows how the viewer rated it, gold for "Loved it!" down to distressed for "Hated it"; every case and poster is
// still except the gold case, whose light comes from within. A gold case shimmers once, the first time most of it is
// on screen (never under reduced motion), and where a pointer can hover it glows softly under the pointer. The light
// brightens what is behind it and lays nothing over it, so a poster's dark areas stay dark.

import { del } from "./api.js";
import { h, prefersLessMotion } from "./dom.js";
import { ANSWERS } from "./ratings.js";

// Each rating's case, best first.
export const CASES = { 5: "gold", 4: "silver", 3: "neutral", 2: "weathered", 1: "distressed" };

const MOST = 0.75; // the share of a gold case on screen that sets off its shimmer
const STAGGER_S = 0.35; // seconds between the shimmers of gold cases that come into view together
// A case must still be in view this long after it comes into view: My profile's parts fill as their records arrive,
// so a part lower down can stand on screen for a moment before the parts above it push it away.
const SETTLE_MS = 400;
let watcher = null;

function mostlyOnScreen(box) {
  const r = box.getBoundingClientRect();
  const high = Math.min(r.bottom, innerHeight) - Math.max(r.top, 0);
  const wide = Math.min(r.right, innerWidth) - Math.max(r.left, 0);
  return high > 0 && wide > 0 && (high * wide) / (r.height * r.width) >= MOST;
}

// Sets off a gold case's one shimmer the first time most of it is on screen and stays there.
function shimmerOnce(box) {
  if (prefersLessMotion() || typeof IntersectionObserver === "undefined") return;
  watcher ??= new IntersectionObserver(
    (entries) => {
      // Cases coming into view together shimmer one after another, four apart at most; one alone starts at once.
      for (const [i, e] of entries.filter((x) => x.isIntersecting).entries()) {
        e.target.style.setProperty("--d", `${(i % 4) * STAGGER_S}s`);
        setTimeout(() => {
          if (!mostlyOnScreen(e.target) || e.target.classList.contains("glint")) return;
          e.target.classList.add("glint");
          watcher.unobserve(e.target);
        }, SETTLE_MS);
      }
    },
    { threshold: MOST },
  );
  watcher.observe(box);
}

// Where a pointer can hover, a gold case glows under it.
function glowUnder(box) {
  if (!window.matchMedia("(hover: hover)").matches) return;
  box.addEventListener("pointermove", (e) => {
    const r = box.getBoundingClientRect();
    box.style.setProperty("--bx", `${Math.round(((e.clientX - r.left) / r.width) * 100)}%`);
    box.style.setProperty("--by", `${Math.round(((e.clientY - r.top) / r.height) * 100)}%`);
    box.classList.add("hov");
  });
  box.addEventListener("pointerleave", () => box.classList.remove("hov"));
}

// A film's case. `score` picks a rating's case, or none for a bare frame; `poster` is the poster's address; `label`
// is what a screen reader hears. With `onOpen(opener)` the case is a button that opens the film; without, a picture.
export function filmCase({ tmdb = null, title, poster, score = null, label, onOpen = null }) {
  const kind = CASES[score] ? `case case-${CASES[score]}` : "case bare";
  const parts = [
    h("span", { class: "plate", "aria-hidden": "true" }, title),
    h("span", { class: "win" }, h("img", { src: poster, alt: "", loading: "lazy", decoding: "async" })),
    score === 5 ? ["sheen", "edge warm", "edge cool", "bloom"].map((light) => h("span", { class: light })) : null,
  ];
  const box = onOpen
    ? h("button", { class: kind, type: "button", "aria-label": label, "data-tmdb": tmdb, onclick: (e) => onOpen(e.currentTarget) }, parts)
    : h("div", { class: kind, role: "img", "aria-label": label }, parts);
  if (score === 5) {
    shimmerOnce(box);
    glowUnder(box);
  }
  return box;
}

// The viewer's ratings in tiers, best first; within a tier, newest first, as the server lists them. Only ratings
// that hold a film have a row.
export function tiers(ratings) {
  return ANSWERS.map((a) => ({ ...a, films: ratings.filter((r) => r.score === a.score) })).filter((t) => t.films.length);
}

const filmsCount = (n) => `${n} ${n === 1 ? "film" : "films"}`;

// "Films you've rated": a row per rating, its words and count beside (above, on a phone) its films in their cases,
// each with the viewer's short review beneath on a wider screen. `poster(id)` gives a film's poster address.
export function ratedPart(body, ratings, { poster, phone, onOpen = null }) {
  const rows = tiers(ratings).map((t) => {
    const cases = t.films.map((r) => {
      const open = onOpen ? (opener) => onOpen(r, opener) : null;
      const box = filmCase({ tmdb: r.tmdb, title: r.title, poster: poster(r.tmdb), score: r.score, label: `${r.title}, ${t.say}`, onOpen: open });
      return h("div", { class: "rated-film" }, box, !phone && r.review ? h("p", { class: "rated-review" }, r.review) : null);
    });
    return h(
      "div",
      { class: "tier" },
      h("div", { class: "tier-head" }, h("h3", { class: "tier-say" }, t.say), h("span", { class: "tier-count" }, filmsCount(t.films.length))),
      h("div", { class: "tier-films" }, cases),
    );
  });
  body.append(...rows);
}

// When a hidden film comes back: "Back on 10 January" in the viewer's own time, or "Hidden for good". The year is
// said when the day and month alone would read as this year's: a year's hide made today comes back on today's date.
export function hiddenUntil(until, today = new Date()) {
  if (!until) return "Hidden for good";
  const back = new Date(until);
  const later = back.getFullYear() > today.getFullYear() && back.getMonth() >= today.getMonth();
  return `Back on ${back.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: later ? "numeric" : undefined })}`;
}

// "Films you've hidden": each film in a bare case, greyed, with when it comes back and "Bring back", which brings it
// back at once and takes it off the part. `recount(n)` hears how many are left; `onOpen(film, opener)` opens a film.
export function hiddenPart(body, hidden, { id, poster, recount, onOpen }) {
  const row = h("div", { class: "hidden-films" });
  const status = h("p", { class: "set-status", role: "status" });
  const items = hidden.map((f) => {
    const back = h("button", { class: "action gold", type: "button" }, "Bring back");
    const item = h(
      "div",
      { class: "hidden-film" },
      filmCase({ tmdb: f.tmdb, title: f.title, poster: poster(f.tmdb), label: `${f.title}, ${hiddenUntil(f.until)}`, onOpen: (opener) => onOpen(f, opener) }),
      h("p", { class: "hidden-until" }, hiddenUntil(f.until)),
      back,
    );
    back.addEventListener("click", async () => {
      back.disabled = true;
      const res = await del(`/api/profiles/${id}/hidden/${f.tmdb}`);
      if (!res.ok) {
        status.textContent = res.data.message;
        back.disabled = false;
        return;
      }
      status.textContent = "";
      const next = item.nextElementSibling ?? item.previousElementSibling;
      item.remove();
      recount(row.children.length);
      // The focus goes to the next film's "Bring back", or the part's heading when none is left.
      (next?.querySelector("button.action") ?? document.getElementById("mine-hidden-title"))?.focus({ preventScroll: true });
    });
    return item;
  });
  row.append(...items);
  body.append(status, row);
}
