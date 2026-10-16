// The tailoring steps: one screen per setting, each with My profile's title, explanation and answers, each skippable,
// which keeps the setting as it stands. Making a profile offers them after the PIN (the door asks the topics first,
// in its own picker, where the installation offers them); a profile made before this feature walks them from its
// welcome. A single answer saves and moves on; the languages save with "Done". The host draws each screen.

import { get, put } from "./api.js";
import { h, isPhone } from "./dom.js";
import { topicButton } from "./topics.js";
import { FLOORS, RATED, ROWS, SHARING, languageName, languageOrder, languagesFirst, moreLanguages, topicList } from "./settings.js";

// The offer while a profile is made.
export const OFFER = {
  ack: "Want me to tailor picks to you?",
  ask: "It's a few quick questions.",
  yes: "Yes, let's do it",
  no: "No, just show me movies",
};

// The welcome a profile made before My profile sees once, the first time it enters the theatre, and the first screen
// of the tailoring steps it leads to.
export const WELCOME = "New: you can now rate films, hide films, and see what I've picked for you.";
export const WHATS_NEW = [
  "Welcome back.",
  "You could already tell me what to steer around. Now you can rate films, hide the ones you don't want, look back at what I've picked, and tell me how well rated a film needs to be and which languages you watch in.",
];

// The screen after the welcome's last step: its line, then its two ways on.
export const ALL_SET = {
  ack: "You're all set up.",
  ask: "You can see and change these settings on My profile.",
  profile: "My profile",
  watch: "Let's find something to watch",
};

// The steps after the topics, in My profile's order.
export const STEPS = ["floor", "languages", "rated", "sharing"];

// The steps to ask: the topics first where the installation offers them, and the languages only where the film
// table holds any.
export function stepKeys({ dtdd, held }) {
  return [...(dtdd ? ["topics"] : []), ...STEPS.filter((key) => key !== "languages" || held.length)];
}
const OPTIONS = { floor: FLOORS, rated: RATED, sharing: SHARING };
const FIELDS = { floor: "floor", rated: "rated_out", sharing: "sharing" };

const help = (key) => (isPhone() ? ROWS[key].short : ROWS[key].help);

function skipAction(next) {
  return h("button", { class: "action cream", type: "button", onclick: next }, "Skip");
}

// A single-answer step: the answers, the current one checked; choosing one saves it and moves on.
function singleStep(key, { id, now, status, next }) {
  const answers = OPTIONS[key].map((o) => {
    const b = h("button", { class: "letterbox ticked setting-answer", type: "button", "aria-pressed": String(o.value === now[FIELDS[key]]) }, o.say);
    if (o.band) b.append(h("span", { class: "set-band" }, o.band));
    b.addEventListener("click", async () => {
      const res = await put(`/api/profiles/${id}/settings`, { [FIELDS[key]]: o.value });
      if (!res.ok) {
        status.textContent = res.data.message;
        return;
      }
      next();
    });
    return b;
  });
  return { answers: [h("div", { class: `set-choices${ROWS[key].column ? " column" : ""}`, role: "group", "aria-label": ROWS[key].title }, answers)], actions: [] };
}

// The languages step: "Any language" or languages ticked, saved with "Done".
function languagesStep({ id, now, held, locale, status, next }) {
  const chosen = new Set(now.languages);
  const ordered = languageOrder(held, locale);
  const any = h("button", { class: "letterbox ticked setting-answer", type: "button" }, "Any language");
  const list = ordered.map((l) => topicButton({ label: languageName(l.code, locale), find: l.code, chosen, id: l.code, onToggle: () => mark() }));
  const mark = () => {
    any.setAttribute("aria-pressed", String(chosen.size === 0));
    list.forEach((b, i) => b.setAttribute("aria-pressed", String(chosen.has(ordered[i].code))));
  };
  any.addEventListener("click", () => {
    chosen.clear();
    mark();
  });
  mark();
  const done = h("button", { class: "action gold", type: "button" }, "Done");
  done.addEventListener("click", async () => {
    const res = await put(`/api/profiles/${id}/settings`, { languages: [...chosen] });
    if (!res.ok) {
      status.textContent = res.data.message;
      return;
    }
    next();
  });
  const more = moreLanguages(list, languagesFirst(ordered, held, locale, chosen));
  return { answers: [h("div", { class: "set-choices", role: "group", "aria-label": ROWS.languages.title }, any, list, more)], actions: [done] };
}

function stepFor(key, args) {
  if (key === "topics") return topicsStep(args);
  if (key === "languages") return languagesStep(args);
  return singleStep(key, args);
}

// The topics step, where the host has no picker of its own: the topics ticked, saved with "Save and continue".
function topicsStep({ id, now, topics, credit, status, next }) {
  if (!topics.ok) return { answers: [h("p", { class: "note" }, topics.data.message)], actions: [] };
  const ticks = topicList({ list: topics.data.topics, chosen: new Set(now.topics), saves: false, onToggle: () => {} });
  const save = h("button", { class: "action gold", type: "button" }, "Save and continue");
  save.addEventListener("click", async () => {
    const chosen = topics.data.topics.filter((t, i) => ticks.buttons[i].getAttribute("aria-pressed") === "true");
    const res = await put(`/api/profiles/${id}/topics`, { topics: chosen.map((t) => t.id) });
    if (!res.ok) {
      status.textContent = res.data.message;
      return;
    }
    next();
  });
  ticks.nodes.at(-1).classList.add("note"); // the tally stands on the wall, so it wears the wall's scrim
  return { answers: ticks.nodes, actions: [save], credit: credit() };
}

// Walks the steps for the profile `id`, from its settings as they stand: the topics too when `dtdd` (a host with no
// picker of its own; `credit()` builds DoesTheDogDie's credit for them). `show({ ack, ask, detail, answers, actions })`
// puts a screen up, its answers apart from its actions (a refusal's line, "Done" or "Save and continue" where there
// is one, and "Skip"); `done()` follows the last step.
export async function tailorSteps({ id, show, done, dtdd = false, credit = null, locale = navigator.language }) {
  const [settings, languages, topics] = await Promise.all([
    get(`/api/profiles/${id}/settings`),
    get("/api/languages"),
    dtdd ? get("/api/topics") : null,
  ]);
  if (!settings.ok) return done();
  const now = settings.data;
  const held = languages.ok ? languages.data : [];
  const keys = stepKeys({ dtdd, held });
  const at = (i) => {
    if (i >= keys.length) return done();
    const key = keys[i];
    const status = h("p", { class: "note set-status", role: "status" });
    const next = () => at(i + 1);
    const step = stepFor(key, { id, now, held, topics, credit, locale, status, next });
    const actions = [status, ...step.actions, skipAction(next)];
    return show({ ack: ROWS[key].title, ask: ROWS[key].ask ?? "", detail: help(key), answers: step.answers, actions, credit: step.credit ?? null });
  };
  return at(0);
}
