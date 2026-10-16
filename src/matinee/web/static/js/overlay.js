// My profile's poster overlay: activating a film's poster in recent picks, rated films or hidden films opens one wide
// surface over the page. Its poster stands on the left in the film's case, at the overlay's full height, with the
// pick's "More on" link beneath; its right side holds the film's title, rank, the household's shared ratings,
// synopsis, how the viewer found it and what they did with it, then "Rate it", "Hide film" and "Something wrong?", each
// opening the pick's own panel over that side (over the whole sheet on a phone). It offers neither "‹ Back" nor
// "Show me another", and never makes the film the pick: a rating, hide or note made here names no run, so the history
// stays as it was. Escape closes an open panel first, then the overlay; closing gives the focus back to the poster.

import { get, put } from "./api.js";
import { filmCase, hiddenUntil } from "./cases.js";
import { h, isPhone } from "./dom.js";
import { hideLink } from "./hide.js";
import { focusShown, householdLine, readingPanel } from "./household.js";
import { noteLink } from "./note.js";
import { pickPanel } from "./panel.js";
import { rateLink } from "./rate.js";
import { runCaption } from "./shelves.js";

// How the viewer found a film no kept run shows.
export const FROM_PICKS = "From what I showed you";

const HERE = (title) => `Matinee won't pick ${title} for you until then. You can bring it back any time from My profile.`;

// The walk kept with `tmdb` in the newest run that showed it, or null when no kept run did.
export function keptWalk(tmdb, runs) {
  for (const run of runs) {
    const film = run.films.find((f) => f.tmdb === tmdb);
    if (film) return film.walk;
  }
  return null;
}

// A kept walk as "Something wrong?" takes it: the door's words apart from the answers', and no run, so a note made here
// marks nothing in the history.
export function noteWalk(walk, profileId) {
  const said = walk.tree ? walk.says.slice(1) : walk.says;
  return { profileId, run: null, tree: walk.tree, answers: walk.answers, says: said, rushed: walk.rushed, firstSay: walk.tree ? walk.says[0] : null };
}

// The film's card, ranked among its door's films; ranked among every film when the door has gone since.
async function card(tmdb, door) {
  const ranked = door ? await get(`/api/film/${tmdb}?door=${encodeURIComponent(door)}`) : null;
  return ranked?.ok ? ranked : get(`/api/film/${tmdb}`);
}

function said(lead, words) {
  return h("p", { class: "overlay-said" }, h("span", { class: "overlay-lead" }, lead), " ", words);
}

// The film's details and the household's ratings of it: { info, household }. `household.mine` is the viewer's own.
async function load(film, walk, viewer) {
  const [info, shared, ratings] = await Promise.all([
    card(film.tmdb, walk?.tree),
    get(`/api/profiles/${viewer.id}/shared/${film.tmdb}`),
    get(`/api/profiles/${viewer.id}/ratings`),
  ]);
  const mine = ratings.ok ? ratings.data.find((r) => r.tmdb === film.tmdb) : null;
  return { info, household: { shared: shared.ok ? shared.data : [], mine: mine ?? null, viewer: { name: viewer.name, avatar: viewer.avatar } } };
}

// The panel stands over the overlay's right side and its × on a desktop, and over the whole sheet on a phone.
function overlayPanel(box, words) {
  return pickPanel(box, null, undefined, {
    covers: () => [...box.children].filter((c) => !c.classList.contains("pick-panel") && (isPhone() || !c.classList.contains("overlay-poster"))),
    place: (node) => {
      const r = (isPhone() ? box : words).getBoundingClientRect();
      Object.assign(node.style, { top: `${r.top}px`, left: `${r.left}px`, width: `${r.width}px`, height: `${r.height}px` });
    },
  });
}

// The left side: the film in its case, and the pick's "More on" link beneath.
function posterSide(film, info, household, poster) {
  const site = info.ok && info.data.link_to === "seerr" ? "Seerr" : "TMDB";
  const link = info.ok
    ? h("a", { class: "overlay-link", href: info.data.link, target: "_blank", rel: "noopener noreferrer", "aria-label": `${film.title}: more on ${site} (opens a new tab)` }, `More on ${site} ↗`)
    : null;
  const shown = filmCase({ title: film.title, poster: poster(film.tmdb, "l"), score: household.mine?.score ?? null, label: film.title });
  return h("div", { class: "overlay-poster" }, shown, link);
}

// "Rate it", "Hide film" and, where the film's walk came through a door, "Something wrong?". A hide made here is said on
// `status`, in the words the hidden films part uses.
function overlayActions({ film, walk, viewer, household, panel, trees, changed, status }) {
  const hide = async (length) => {
    const res = await put(`/api/profiles/${viewer.id}/hidden/${film.tmdb}`, { length });
    if (res.ok) {
      status.textContent = `${hiddenUntil(res.data.until)}.`;
      panel.close();
      changed();
    }
    return res;
  };
  return [
    rateLink({ film, panel, profileId: viewer.id, run: null, household, saved: changed }),
    hideLink({ film, panel, lede: HERE, hide }),
    walk ? noteLink({ walk: noteWalk(walk, viewer.id), film, trees: trees(), panel }) : null,
  ];
}

// The right side's words: title, rank, the household's line, synopsis, how the viewer found it and what they did.
function aboutFilm({ film, info, household, panel, box, walk, did }) {
  const year = film.year ? h("span", { class: "film-year" }, ` ${film.year}`) : null;
  const title = h("h2", { class: "overlay-title", id: "overlay-title", tabindex: "-1" }, film.title, year);
  const ranked = info.ok && info.data.rank;
  const rank = ranked ? h("p", { class: "rank" }, h("span", { class: "rank-words" }, info.data.rank), " ", h("span", { class: "rank-by" }, info.data.standing)) : null;
  const line = householdLine(household.shared, (from, first) => {
    panel.open(from, "Household reviews", readingPanel({ ...household, first }));
    focusShown(box.querySelector(".pick-panel"));
  });
  const synopsis = h("p", { class: "overlay-synopsis" }, info.ok ? info.data.synopsis || "" : info.data.message);
  const found = said("How you found it:", walk ? runCaption(walk) : FROM_PICKS);
  return [title, rank, line, synopsis, h("div", { class: "overlay-rule" }), found, said("What you did:", did)];
}

// Opens the overlay over My profile's `layer` for `film` ({ tmdb, title, year }). `did` is what the viewer did with
// it; `walk` the walk kept with it, or null. `viewer` is { id, name, avatar }; `poster(tmdb, size)` gives its poster;
// `trees()` the doors as the page knows them, for "Something wrong?"; `changed()` runs after a rating or hide is saved.
export async function openOverlay({ layer, film, did, walk, opener, viewer, poster, trees, changed }) {
  const { info, household } = await load(film, walk, viewer);
  if (!layer.isConnected) return;
  const back = h("div", { class: "overlay-back" });
  const words = h("div", { class: "overlay-words" });
  const box = h("div", { class: "overlay", role: "dialog", "aria-modal": "true", "aria-labelledby": "overlay-title" });
  const under = [...layer.children];
  const panel = overlayPanel(box, words);
  const part = opener.closest(".part")?.id;
  // The poster gets the focus back; when a rating or hide made here has drawn its part again, the film's new poster
  // in that part, or the part's heading when the film has left it.
  const close = () => {
    window.removeEventListener("keydown", escape, true);
    panel.close();
    back.remove();
    box.remove();
    for (const node of under) node.inert = false;
    const again = layer.querySelector(`#${part} [data-tmdb="${film.tmdb}"]`) ?? layer.querySelector(`#${part} h2`);
    (opener.isConnected ? opener : again)?.focus({ preventScroll: true });
  };
  // Escape closes an open panel, then the overlay, wherever the focus is (a click on the words leaves it on the
  // page's body); caught before My profile's own Escape, which would close the page.
  const escape = (e) => {
    if (e.key !== "Escape") return;
    e.stopImmediatePropagation();
    if (panel.isOpen()) panel.close();
    else close();
  };
  window.addEventListener("keydown", escape, true);
  back.addEventListener("click", close);
  const status = h("p", { class: "overlay-status", role: "status" });
  const actions = overlayActions({ film, walk, viewer, household, panel, trees, changed, status });
  words.append(...aboutFilm({ film, info, household, panel, box, walk, did }).filter(Boolean), status, h("div", { class: "overlay-actions" }, actions));
  const shut = h("button", { class: "overlay-close", type: "button", "aria-label": "Close", onclick: close }, "×");
  box.append(posterSide(film, info, household, poster), words, shut);
  for (const node of under) node.inert = true;
  layer.append(back, box);
  words.querySelector(".overlay-title").focus({ preventScroll: true });
}
