// The tailoring steps: one screen per setting, each with My profile's title, explanation and answers, each skippable,
// which keeps the setting as it stands. Making a profile offers them after the PIN (the door asks the topics first,
// in its own picker, where the installation offers them); a profile made before this feature walks them from its
// welcome. A single answer saves and moves on; the languages save with "Done". The host draws each screen.

import { get, put } from "./api.js";
import { h, isPhone } from "./dom.js";
import { topicButton } from "./topics.js";
import { FLOORS, RATED, ROWS, SHARING, languageName, languageOrder } from "./settings.js";

// The offer while a profile is made.
export const OFFER = {
  ack: "Want me to tailor picks to you?",
  ask: "It's a few quick questions.",
  yes: "Yes, let's do it",
  no: "No, just show me movies",
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
  return { answers: [h("div", { class: "set-choices", role: "group", "aria-label": ROWS.languages.title }, any, list)], actions: [done] };
}

// Walks the steps after the topics for the profile `id`, from its settings as they stand. `show({ ack, ask, detail,
// answers, actions })` puts a screen up, its answers apart from its actions (a refusal's line, "Done" where there is
// one, and "Skip"); `done()` follows the last step.
export async function tailorSteps({ id, show, done, locale = navigator.language }) {
  const [settings, languages] = await Promise.all([get(`/api/profiles/${id}/settings`), get("/api/languages")]);
  if (!settings.ok) return done();
  const now = settings.data;
  const held = languages.ok ? languages.data : [];
  const keys = stepKeys({ dtdd: false, held });
  const at = (i) => {
    if (i >= keys.length) return done();
    const key = keys[i];
    const status = h("p", { class: "note set-status", role: "status" });
    const next = () => at(i + 1);
    const step = key === "languages" ? languagesStep({ id, now, held, locale, status, next }) : singleStep(key, { id, now, status, next });
    return show({ ack: ROWS[key].title, ask: ROWS[key].ask ?? "", detail: help(key), answers: step.answers, actions: [status, ...step.actions, skipAction(next)] });
  };
  return at(0);
}
