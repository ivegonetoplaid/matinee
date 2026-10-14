// My profile's "How I pick films for you": each tailoring setting rests as a row with a gold title, one quieter line
// of explanation, a small picture of its open panel with the chosen answers ringed in gold, and "Change". "Change" or
// the picture opens the panel full size; one row is open at a time. A single-answer setting saves and closes when an
// answer is chosen; the topics and the languages save each tick at once and close with "Done". There is no Save.
// A choice takes effect on the viewer's next pick.

import { get, put } from "./api.js";
import { h, isPhone, sentenceCase } from "./dom.js";
import { topicButton } from "./topics.js";

// The rating floor's choices, best first, as the store keeps them, with the share of a door's films each keeps.
export const FLOORS = [
  { value: "well_liked", say: "Well liked or better", band: "Top 25%" },
  { value: "above_middle", say: "Above the middle or better", band: "Top 40%" },
  { value: "middle", say: "Middle of the pack or better", band: "Top 60%" },
  { value: "above_bottom", say: "Above the bottom 10%", band: "Top 90%" },
  { value: "anything", say: "Anything", band: "Every film" },
];

// The rated-films setting's choices, best first: films rated this or lower stay out of the viewer's picks.
export const RATED = [
  { value: 5, say: "Loved it!", band: "Everything I've rated" },
  { value: 4, say: "Really liked it" },
  { value: 3, say: "It was ok, I guess" },
  { value: 2, say: "Didn't like it" },
  { value: 1, say: "Hated it" },
  { value: 0, say: "None, keep them coming" },
];

export const SHARING = [
  { value: false, say: "Keep them to myself" },
  { value: true, say: "Share with my household" },
];

// Each row's words, with `short` the explanation a phone's board gives. `field` is the setting the row saves; `column`
// stacks its answers one per line.
export const ROWS = {
  topics: {
    title: "Scenes you don't want to see",
    help: "Choose topics like spiders or needles. Before I show you any film, I look it up and skip it if it has one of them.",
    short: "Choose topics like spiders or needles. I look up each film first and skip it if it has one.",
  },
  floor: {
    title: "How well rated a film needs to be",
    help: "I compare each film's audience rating with the other films behind the same door, and only pick films that rank this high or better. Films too new or too little-known to have many ratings are always included.",
    short: "I compare each film's audience rating with the other films behind the same door. Films too new or too little-known to have many ratings are always included.",
    field: "floor",
    options: FLOORS,
    column: true,
  },
  languages: {
    title: "Language preferences",
    ask: "I'll only show you films in these languages:",
    help: "Choose the languages you're happy to watch a film in. I check the audio in your library too, so a film dubbed into your language counts.",
    short: "I check the audio in your library too, so a film dubbed into your language counts.",
  },
  rated: {
    title: "Films you've already rated",
    ask: "Stop picking films I gave this rating or lower:",
    help: "Rating a film doesn't stop me picking it. Choose which of your ratings mean “don't pick this again”. Loved it? I can still offer it for a rewatch.",
    short: "Rating a film doesn't stop me picking it. Choose which ratings mean \u201cdon't pick this again\u201d.",
    field: "rated_out",
    options: RATED,
    column: true,
  },
  sharing: {
    title: "Sharing your ratings with your household",
    help: "If you share, the other people on Matinee in your home see your ratings and short reviews when I pick that film for them. You see theirs either way.",
    short: "If you share, the others on Matinee in your home see your ratings and short reviews. You see theirs either way.",
    field: "sharing",
    options: SHARING,
  },
};

const NAMES_MISSING = { cn: "Cantonese" }; // TMDB's own code, which a browser's language names do not hold

// A language's name for the viewer, in the viewer's own language where the browser can say it; its code otherwise.
export function languageName(code, locale) {
  if (NAMES_MISSING[code]) return NAMES_MISSING[code];
  try {
    const name = new Intl.DisplayNames([locale, "en"], { type: "language" }).of(code);
    return name && name !== code ? sentenceCase(name) : code;
  } catch {
    return code;
  }
}

// The languages to offer, as the server lists them (most films first), with the browser's own language first.
export function languageOrder(held, locale) {
  const own = String(locale || "").split("-")[0].toLowerCase();
  return [...held.filter((l) => l.code === own), ...held.filter((l) => l.code !== own)];
}

// An answer in a row's picture: a letterbox that does nothing, ringed in gold and checked when chosen.
function shown({ say, band = "", chosen, ticked = false }) {
  const classes = `letterbox setting-answer ${ticked ? "topic" : "ticked"}`;
  return h("span", { class: classes, "aria-pressed": String(chosen) }, say, band ? h("span", { class: "set-band" }, band) : null);
}

// A single answer the viewer can choose, ringed in gold and checked while it is the setting's value, as Rate it
// marks its chosen answer, so the keyboard's focus ring is never the only ring.
function chooser({ say, band = "", chosen, onPick }) {
  const b = h("button", { class: "letterbox setting-answer ticked", type: "button", "aria-pressed": String(chosen), onclick: onPick }, say);
  if (band) b.append(h("span", { class: "set-band" }, band));
  return b;
}

// A row: its words, its picture and "Change", and the line that says a refused save beneath them. `panel()` builds
// the open panel's nodes; `picture()` the small copy's.
function row({ key, words, panel, picture, credit, onToggle }) {
  const status = h("p", { class: "set-status", role: "status" });
  const change = h("button", { class: "action gold", type: "button", "aria-expanded": "false" }, "Change");
  const thumb = h("div", { class: "thumb", "aria-hidden": "true" });
  const body = h("div", { class: "setbody", hidden: true });
  const words_ = h("div", {}, h("h3", { class: "stitle" }, words.title), h("p", { class: "set-help" }, isPhone() ? words.short : words.help), credit, thumb);
  const node = h("div", { class: "set", id: `set-${key}` }, h("div", { class: "sethead" }, words_, change), status, body);
  const self = {
    node,
    status,
    open: false,
    draw() {
      if (!self.open && body.contains(document.activeElement)) change.focus({ preventScroll: true });
      thumb.replaceChildren(h("div", { class: `thumb-inner${words.column ? " column" : ""}` }, picture()));
      thumb.hidden = self.open;
      body.hidden = !self.open;
      body.replaceChildren(...(self.open ? panel().filter(Boolean) : []));
      change.textContent = self.open ? "Done" : "Change";
      change.setAttribute("aria-expanded", String(self.open));
    },
  };
  change.addEventListener("click", () => onToggle(self));
  thumb.addEventListener("click", () => onToggle(self));
  return self;
}

// A single-answer row: choosing an answer saves it and closes the row.
function singleRow(key, { now, save, onToggle }) {
  // A phone's board stacks the sharing answers too.
  const words = { ...ROWS[key], column: ROWS[key].column || (key === "sharing" && isPhone()) };
  const self = row({
    key,
    words,
    onToggle,
    picture: () => [words.ask ? h("p", { class: "set-ask" }, words.ask) : null, words.options.map((o) => shown({ ...o, chosen: o.value === now[words.field] }))],
    panel: () => [
      words.ask ? h("p", { class: "set-ask" }, words.ask) : null,
      h(
        "div",
        { class: `set-choices${words.column ? " column" : ""}`, role: "group", "aria-label": words.title },
        words.options.map((o) =>
          chooser({
            ...o,
            chosen: o.value === now[words.field],
            onPick: async () => {
              if (await save({ [words.field]: o.value }, self.status)) onToggle(self);
            },
          }),
        ),
      ),
    ],
  });
  return self;
}

// "Language preferences": "Any language", or one or more languages ticked; each tick saves at once.
function languagesRow({ now, held, save, locale, onToggle }) {
  const named = held.map((l) => ({ code: l.code, say: languageName(l.code, locale) }));
  let saved = new Set(now.languages);
  const panel = () => {
    const list = named.map((l) => topicButton({ label: l.say, find: l.code, chosen: now.languages, id: l.code, onToggle: () => sync() }));
    const any = chooser({
      say: "Any language",
      chosen: now.languages.size === 0,
      onPick: () => {
        now.languages.clear();
        sync();
      },
    });
    const mark = () => {
      any.setAttribute("aria-pressed", String(now.languages.size === 0));
      for (const b of list) b.setAttribute("aria-pressed", String(now.languages.has(b.dataset.code)));
    };
    // A refused save puts back the ticks last saved.
    async function sync() {
      mark();
      const wanted = new Set(now.languages);
      if (await save({ languages: [...wanted] }, self.status)) saved = wanted;
      else {
        now.languages.clear();
        for (const code of saved) now.languages.add(code);
        mark();
      }
    }
    named.forEach((l, i) => (list[i].dataset.code = l.code));
    return [h("p", { class: "set-ask" }, ROWS.languages.ask), h("div", { class: "set-choices", role: "group", "aria-label": ROWS.languages.title }, any, list)];
  };
  const picture = () => [
    h("p", { class: "set-ask" }, ROWS.languages.ask),
    shown({ say: "Any language", chosen: now.languages.size === 0 }),
    named.filter((l) => now.languages.has(l.code)).map((l) => shown({ say: l.say, chosen: true, ticked: true })),
  ];
  const self = row({ key: "languages", words: ROWS.languages, onToggle, panel, picture });
  return self;
}

// "Scenes you don't want to see": DoesTheDogDie's topics, searched and ticked; each tick saves at once.
function topicsRow({ topics, now, saveTopics, credit, onToggle }) {
  const list = topics.ok ? topics.data.topics : [];
  const panel = () => {
    if (!topics.ok) return [h("p", { class: "set-help" }, topics.data.message)];
    const search = h("input", { class: "field", type: "text", placeholder: "Search, like spiders or needles", "aria-label": "Search topics", autocomplete: "off" });
    const nothing = h("p", { class: "set-help", hidden: true }, "Nothing by that name. Try another word.");
    const tally = h("p", { class: "set-help set-tally" });
    const count = () => {
      const chosen = now.topics.size ? `${now.topics.size} chosen.` : "Nothing chosen yet.";
      tally.textContent = `${chosen} Each tick saves straight away. The checks are best effort, from votes on DoesTheDogDie.com.`;
    };
    const buttons = list.map((t) =>
      topicButton({
        label: sentenceCase(t.short),
        find: `${t.name} ${t.keywords}`,
        chosen: now.topics,
        id: t.id,
        onToggle: async (id, on) => {
          count();
          if (await saveTopics(self.status)) return;
          if (on) now.topics.delete(id);
          else now.topics.add(id);
          buttons.forEach((b, i) => b.setAttribute("aria-pressed", String(now.topics.has(list[i].id))));
          count();
        },
      }),
    );
    search.addEventListener("input", () => {
      const needle = search.value.trim().toLowerCase();
      for (const b of buttons) b.hidden = !b.dataset.find.includes(needle);
      nothing.hidden = buttons.some((b) => !b.hidden);
    });
    count();
    return [search, h("div", { class: "topic-list set-topics" }, buttons), nothing, tally];
  };
  // The picture: the search box and the first ten topics (four on a phone), the chosen ones first.
  const picture = () => {
    const ordered = [...list.filter((t) => now.topics.has(t.id)), ...list.filter((t) => !now.topics.has(t.id))];
    const ten = ordered.slice(0, isPhone() ? 4 : 10).map((t) => shown({ say: sentenceCase(t.short), chosen: now.topics.has(t.id), ticked: true }));
    return [h("span", { class: "field" }, "Search, like spiders or needles"), h("div", { class: "thumb-topics" }, ten)];
  };
  const self = row({ key: "topics", words: ROWS.topics, onToggle, panel, picture, credit: credit() });
  return self;
}

// Fills `body` with the rows for the viewer `id`. `dtdd` says whether the installation offers DoesTheDogDie's
// topics, and `credit()` builds DoesTheDogDie's credit for their row. Each change is saved at once, one after
// another in the order made; a refusal is said in the row that made the change.
export async function settingsPart(body, { id, dtdd, credit, locale = navigator.language }) {
  const [settings, languages, topics] = await Promise.all([
    get(`/api/profiles/${id}/settings`),
    get("/api/languages"),
    dtdd ? get("/api/topics") : null,
  ]);
  if (!settings.ok) {
    body.replaceChildren(h("p", { class: "part-empty" }, settings.data.message));
    return;
  }
  const now = { ...settings.data, topics: new Set(settings.data.topics), languages: new Set(settings.data.languages) };
  let queue = Promise.resolve(true);
  // Saves wait their turn, so a quick run of ticks reaches the server in the order the viewer made them.
  const send = (path, change, status) => {
    queue = queue.then(async () => {
      const res = await put(path, change);
      status.textContent = res.ok ? "" : res.data.message;
      return res.ok;
    });
    return queue;
  };
  const save = async (change, status) => {
    const ok = await send(`/api/profiles/${id}/settings`, change, status);
    if (ok && "floor" in change) now.floor = change.floor;
    if (ok && "rated_out" in change) now.rated_out = change.rated_out;
    if (ok && "sharing" in change) now.sharing = change.sharing;
    return ok;
  };
  const rows = [];
  const onToggle = (self) => {
    for (const r of rows) {
      const wanted = r === self ? !r.open : false;
      if (r.open !== wanted) {
        r.open = wanted;
        r.draw();
      }
    }
  };
  const held = languages.ok ? languageOrder(languages.data, locale) : [];
  if (dtdd) rows.push(topicsRow({ topics, now, credit, saveTopics: (status) => send(`/api/profiles/${id}/topics`, { topics: [...now.topics] }, status), onToggle }));
  rows.push(
    singleRow("floor", { now, save, onToggle }),
    languagesRow({ now, held, save, locale, onToggle }),
    singleRow("rated", { now, save, onToggle }),
    singleRow("sharing", { now, save, onToggle }),
  );
  for (const r of rows) r.draw();
  body.replaceChildren(...rows.map((r) => r.node));
}
