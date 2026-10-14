// My profile: the viewer's own page. A full page over the theatre, which stays as the viewer left it, with its own
// entry in the browser's history: "‹ Back to picking", the browser's back and Escape all return to the picker where
// it stood. It holds four parts, in order: "How I pick films for you", "Films you've rated", "Films you've hidden"
// and "Films I've picked for you"; each part brings its own body (`parts`), and until then shows its empty line.
// Beside them a pinned menu (on a phone, the page's head and a jump bar pinned to the top) holds "‹ Back to
// picking", the avatar, which changes it, the name, which renames, a jump to each part with its count, "Switch
// profiles" and "Delete this profile". Everything on the page is the viewer's own; nothing sets or changes a PIN.

import { get, put } from "./api.js";
import { h, isPhone, sentenceCase } from "./dom.js";
import { cornerMark } from "./flight.js";
import { avatarChoices, mark } from "./mark.js";

// The four parts. `jump` names a part in the menu and `short` on a phone's jump bar; `phoneMeta` is the heading's
// side line on a phone, where it differs; `note` is a line beneath the heading; `count` reads its count from the viewer's records, where the part shows one.
export const PARTS = [
  { id: "tailor", jump: "How I pick for you", short: "How I pick", title: "How I pick films for you", meta: "Changes apply from your next pick", empty: null },
  {
    id: "rated",
    jump: "Your ratings",
    short: "Ratings",
    title: "Films you've rated",
    meta: "Best first. The case around each poster shows how you rated it.",
    phoneMeta: "Best first",
    note: "Your ratings stay in Matinee for now. We’re exploring syncing them with services like Trakt in the near future.",
    empty: "Nothing rated yet. After a film, tap Rate it and it lands here.",
    count: (mine) => mine.ratings.length,
  },
  {
    id: "hidden",
    jump: "Hidden films",
    short: "Hidden",
    title: "Films you've hidden",
    meta: "I won't pick these until the date under each one",
    empty: "Nothing hidden. Hide a film from its pick and it waits here until it comes back.",
    count: (mine) => mine.hidden.length,
  },
  {
    id: "shown",
    jump: "Past picks",
    short: "Past picks",
    title: "Films I've picked for you",
    meta: "Your last 50 picks, by day. Open a day to see the films.",
    empty: "No picks yet. Once I pick something for you, it shows up here.",
    count: (mine) => mine.runs.length,
  },
];

const HINT = "Tap your picture or name to change it";
const EDITING = "Enter to save · Esc to cancel";
const LONG_NAME = 14; // a name longer than this is set smaller in the menu, so it wraps between words

export const DELETE_LINE = "Your ratings, hidden films, history and settings go with it. Any notes you sent stay with whoever runs Matinee.";
const TAKEN = "name_taken";

let shown = null; // { layer, opener, then } while My profile is open

// Closes My profile and shows the theatre as it stood. Runs on the browser's back, which "‹ Back to picking" and
// Escape also go through; `then` is what the viewer chose to do next (switching profiles, after a delete).
function close() {
  if (!shown) return;
  const { layer, opener, then } = shown;
  shown = null;
  layer.remove();
  cover(false);
  if (then) return then();
  // The top bar's viewer may have been drawn again since (a new name or picture), so it is found afresh.
  return (opener?.isConnected ? opener : document.querySelector(".topbar .viewer-button"))?.focus({ preventScroll: true });
}

// The browser's back and Escape close the page; listened for from the first time it opens.
let listening = false;
function listen() {
  if (listening) return;
  listening = true;
  window.addEventListener("popstate", close);
  window.addEventListener("keydown", (e) => {
    if (shown && e.key === "Escape" && !e.target.closest?.("input")) history.back();
  });
}

// The theatre beneath the page: covered by it, and out of reach of the keyboard and of a screen reader while it is.
function cover(on) {
  for (const id of ["stage", "wall"]) {
    const part = document.getElementById(id);
    if (part) part.inert = on;
  }
}

// Leaves My profile, then does `then`.
function leave(then = null) {
  if (shown) shown.then = then;
  history.back();
}

export const isOpen = () => Boolean(shown);

// The viewer's records, for the counts and the parts: ratings, hidden films and runs. A part whose records cannot
// be read shows as empty, and the page says so once.
async function records(id) {
  const [ratings, hidden, runs] = await Promise.all(["ratings", "hidden", "runs"].map((what) => get(`/api/profiles/${id}/${what}`)));
  const failed = [ratings, hidden, runs].find((r) => !r.ok);
  return {
    ratings: ratings.ok ? ratings.data : [],
    hidden: hidden.ok ? hidden.data : [],
    runs: runs.ok ? runs.data : [],
    problem: failed ? failed.data.message : null,
  };
}

function part(p, phone) {
  const body = h("div", { class: "part-body" }, p.empty ? h("p", { class: "part-empty" }, p.empty) : null);
  const section = h(
    "section",
    { class: "part", id: `mine-${p.id}`, "aria-labelledby": `mine-${p.id}-title` },
    h("div", { class: "placard" }, h("h2", { id: `mine-${p.id}-title` }, p.title), h("span", { class: "placard-meta" }, (phone && p.phoneMeta) || p.meta)),
    p.note ? h("p", { class: "part-note" }, p.note) : null,
    h("div", { class: "part-rule" }),
    body,
  );
  return { section, body };
}

// A jump to a part, with its count once the records arrive.
function jump(p, phone) {
  const count = h("span", { class: "jump-count" });
  const link = h(
    "button",
    {
      class: "jump",
      type: "button",
      onclick: () => document.getElementById(`mine-${p.id}`)?.scrollIntoView({ block: "start" }),
    },
    h("span", {}, phone ? p.short : p.jump),
    count,
  );
  return { link, count };
}

// The name, which becomes a field when activated: Enter saves under the rules a new profile's name follows, Escape
// cancels, and a taken name keeps the field open with the existing message beside it.
function nameEditor(viewer, actions, hint) {
  const holder = h("div", { class: "name-holder" });
  const status = h("p", { class: "name-status", role: "status" });
  const showName = () => {
    const button = h("button", { class: "name-button", type: "button", "aria-label": `Change your name, ${viewer.name}`, onclick: edit }, viewer.name, h("span", { class: "name-pencil", "aria-hidden": "true" }, "✎"));
    button.classList.toggle("long", [...viewer.name].length > LONG_NAME);
    holder.replaceChildren(button, status);
    hint.textContent = HINT;
    return button;
  };
  function edit() {
    const field = h("input", { class: "name-field", type: "text", maxlength: 80, "aria-label": "Your name", autocomplete: "off", spellcheck: "false" });
    field.value = viewer.name;
    const done = (focusName = true) => {
      status.textContent = "";
      const button = showName();
      if (focusName) button.focus({ preventScroll: true });
    };
    field.addEventListener("keydown", async (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        return done();
      }
      if (e.key !== "Enter") return undefined;
      e.preventDefault();
      if (field.value.trim() === viewer.name) return done();
      const res = await put(`/api/profiles/${viewer.id}/name`, { name: field.value });
      if (!res.ok) {
        status.textContent = res.data.message;
        if (res.data.code !== TAKEN) field.select();
        return undefined;
      }
      viewer.name = res.data.name;
      actions.renamed(res.data);
      return done();
    });
    holder.replaceChildren(field, status);
    hint.textContent = EDITING;
    field.focus();
    field.select();
  }
  showName();
  return holder;
}

// The avatar, which opens the avatars to choose from beneath it; a tap saves the choice and the page shows it.
function avatarEditor(viewer, avatars, actions) {
  const holder = h("div", { class: "avatar-holder" });
  const status = h("p", { class: "name-status", role: "status" });
  const button = h("button", { class: "avatar-button", type: "button", "aria-label": "Change your picture", "aria-expanded": "false" });
  let choices = null;
  const draw = () => button.replaceChildren(mark(viewer, "panel"));
  const shut = () => {
    choices?.remove();
    choices = null;
    button.setAttribute("aria-expanded", "false");
  };
  const save = async (avatar) => {
    const res = await actions.saveAvatar(avatar);
    if (!res.ok) {
      status.textContent = res.data.message;
      return;
    }
    viewer.avatar = res.data.avatar;
    draw();
    shut();
    button.focus({ preventScroll: true });
  };
  button.addEventListener("click", () => {
    if (choices) return shut();
    choices = h(
      "div",
      { class: "avatar-picker", role: "group", "aria-label": "Your picture" },
      avatarChoices(avatars, save, viewer.avatar),
      h("button", { class: "letterbox", type: "button", onclick: () => save(null) }, "Just my initials"),
    );
    holder.closest(".who").after(choices); // a row of its own beneath the picture and the name
    button.setAttribute("aria-expanded", "true");
    return choices.querySelector("button")?.focus({ preventScroll: true });
  });
  draw();
  holder.append(button, status);
  return holder;
}

// "Delete this profile", asking first in the menu delete dialog's form.
function deleter(viewer, actions) {
  const holder = h("div", { class: "delete-holder" });
  const start = h("button", { class: "action rose", type: "button" }, "Delete this profile");
  start.addEventListener("click", () => {
    const status = h("p", { class: "name-status", role: "status" });
    const yes = h("button", { class: "letterbox danger", type: "button" }, "Yes, delete it");
    const no = h("button", { class: "letterbox", type: "button" }, "No, keep it");
    const ask = h(
      "div",
      { class: "delete-ask", role: "group", "aria-label": `Delete ${viewer.name}?` },
      h("p", { class: "line viewer-line delete-line" }, h("span", { class: "ack" }, `Delete ${viewer.name}?`), " ", h("span", { class: "ask" }, DELETE_LINE)),
      yes,
      no,
      status,
    );
    no.addEventListener("click", () => {
      ask.replaceWith(start);
      start.focus({ preventScroll: true });
    });
    yes.addEventListener("click", async () => {
      yes.disabled = no.disabled = true;
      const res = await actions.deleteProfile({ leaving: (then) => leave(then) });
      if (res.ok) return;
      status.textContent = res.data.message;
      yes.disabled = no.disabled = false;
    });
    start.replaceWith(ask);
    no.focus(); // brought into view, the menu's foot being lower than the screen's when the page is short
  });
  holder.append(start);
  return holder;
}

// The page's frame: the corner mark and the curtains behind, the menu, and the four parts' headings.
function frame({ viewer, avatars, actions, phone }) {
  const back = h("button", { class: "action gold back-to-picking", type: "button", onclick: () => history.back() }, "‹ Back to picking");
  const switcher = h("button", { class: "action cream", type: "button", onclick: () => leave(actions.switchProfiles) }, "Switch profiles");
  const built = PARTS.map((p) => part(p, phone));
  const jumps = PARTS.map((p) => jump(p, phone));
  const hint = h("p", { class: "who-hint" });
  const who = h("div", { class: "who" }, avatarEditor(viewer, avatars, actions), h("div", { class: "who-words" }, nameEditor(viewer, actions, hint), hint));
  const ways = [switcher, deleter(viewer, actions)];
  const menu = phone
    ? [h("div", { class: "mine-head" }, who, h("div", { class: "mine-ways" }, ways)), h("nav", { class: "jump-bar", "aria-label": "Jump to" }, jumps.map((j) => j.link))]
    : [h("nav", { class: "pin", "aria-label": "My profile" }, back, who, jumps.map((j) => j.link), h("div", { class: "pin-rule" }), ways)];
  const top = h("header", { class: "mine-top" }, h("div", { class: "mine-mark", "aria-hidden": "true" }, cornerMark()), phone ? back : null);
  const notice = h("p", { class: "part-empty mine-problem", role: "status", hidden: true });
  const layer = h(
    "div",
    { class: "my-profile", role: "dialog", "aria-modal": "true", "aria-label": "My profile" },
    h("div", { class: "curtain", "aria-hidden": "true" }),
    top,
    h("div", { class: "shell" }, menu, h("main", { class: "parts" }, notice, built.map((b) => b.section))),
  );
  return { layer, back, built, jumps, notice };
}

// Each part's count in its jump, and each part's body, from the viewer's records. A phone's jump bar names past picks
// without a count, as its board draws it.
function fill({ built, jumps, notice }, mine, { parts, viewer, phone }) {
  if (mine.problem) {
    notice.textContent = sentenceCase(mine.problem);
    notice.hidden = false;
  }
  PARTS.forEach((p, i) => {
    const n = p.count?.(mine) ?? 0;
    if (p.count && !(phone && p.id === "shown")) jumps[i].count.textContent = String(n);
    if (n) built[i].body.querySelector(".part-empty")?.remove(); // the part has records, though no body shows them yet
    parts[p.id]?.(built[i].body, mine, viewer);
  });
}

// Puts the page over the theatre, on an entry of its own in the browser's history, at the part `at` when one is named.
function showPage(page, opener, at, then) {
  listen();
  shown = { layer: page.layer, opener, then };
  history.pushState({ profile: true }, "");
  document.body.append(page.layer);
  cover(true);
  page.back.focus({ preventScroll: true });
  if (at) document.getElementById(`mine-${at}`)?.scrollIntoView({ block: "start" });
}

// Opens My profile for `viewer` ({ id, name, avatar }) over the theatre. `actions` holds saveAvatar(avatar),
// deleteProfile({ leaving }), switchProfiles() and renamed(seat), as the top bar's menu has them. `parts` maps a
// part's id to a function that fills its body from the viewer's records; `at` is the part to open at, if any.
// `opener` gets the focus back when the page closes, unless `then` is given, which runs instead.
export async function openProfile({ viewer, avatars, actions, parts = {}, at = null, opener = null, then = null }) {
  if (shown) return;
  const phone = isPhone();
  const page = frame({ viewer, avatars, actions, phone });
  showPage(page, opener, at, then);
  const mine = await records(viewer.id);
  if (shown?.layer === page.layer) fill(page, mine, { parts, viewer, phone });
}
