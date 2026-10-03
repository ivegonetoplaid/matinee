// The front door: the marquee, a stepped crown over a lit sign, stands at the top
// centre over the poster wall, and Matinee greets a viewer on the wall below it.
// Every question at the door types straight onto the wall, with nothing behind
// Matinee's words; the marquee stays until the viewer goes in.

import { get, post, put } from "./api.js";
import { credits } from "./credits.js";
import { clear, h, isPhone, prefersLessMotion, sentenceCase, wait } from "./dom.js";
import { FLIGHT_MS, copyAt, fly, nameAt, riseOf, wordmarkAt } from "./flight.js";
import { doorLines, findTaken, opensAtOnce, twoParts } from "./door-rules.js";
import { avatarChoices, mark } from "./mark.js";
import { typeLine } from "./type.js";

// Bulbs round the sign and the gap between them, as on the design boards. Two dark bulbs chase clockwise,
// half a lap apart, one lap every CHASE_S seconds.
const BULBS = { desktop: { count: 156, inset: 9 }, phone: { count: 64, inset: 6 } };
const CHASE_S = 12;
const PIN_LENGTH = 4;


// Where each bulb sits on a ring `inset` pixels inside a w × h sign, walking clockwise from the top left.
function ringAt(k, n, w, h, inset) {
  const rw = w - 2 * inset;
  const rh = h - 2 * inset;
  const s = (k * 2 * (rw + rh)) / n;
  if (s < rw) return [inset + s, inset];
  if (s < rw + rh) return [inset + rw, inset + s - rw];
  if (s < 2 * rw + rh) return [inset + rw - (s - rw - rh), inset + rh];
  return [inset, inset + rh - (s - 2 * rw - rh)];
}

// Each bulb's place in the chase. A lap starts with the dark bulbs at the top and bottom middles: the
// top middle lies `start` of the way round the ring from the top left, where bulb 0 sits. Set once,
// from the sign's first size, so the chase keeps its step when a phone's picker shrinks the sign.
function time(spans, w, hgt, inset) {
  const rw = w - 2 * inset;
  const rh = hgt - 2 * inset;
  const start = rw / 2 / (2 * (rw + rh));
  spans.forEach((b, k) => {
    const twinkle = (1.3 + ((k * 7) % 13) / 10).toFixed(2);
    const lap = (((k / spans.length - start) % 1) + 1) % 1;
    b.style.animationDuration = `${CHASE_S}s, ${twinkle}s`;
    b.style.animationDelay = `${(lap * CHASE_S - CHASE_S).toFixed(3)}s, ${(-((k * 5) % 11) / 10).toFixed(2)}s`;
  });
}

function bulbs(sign) {
  const { count, inset } = isPhone() ? BULBS.phone : BULBS.desktop;
  const layer = h("div", { class: "bulbs", "aria-hidden": "true" });
  const spans = Array.from({ length: count }, () => h("span", { class: "bulb" }));
  layer.append(...spans);
  let timed = false;
  const place = () => {
    const w = sign.clientWidth;
    const hgt = sign.clientHeight;
    if (!timed && w > 0) {
      time(spans, w, hgt, inset);
      timed = true;
    }
    spans.forEach((b, k) => {
      const [x, y] = ringAt(k, count, w, hgt, inset);
      b.style.left = `${Math.round(x)}px`;
      b.style.top = `${Math.round(y)}px`;
    });
  };
  new ResizeObserver(place).observe(sign);
  return layer;
}

function crown() {
  const parts = ["step s1", "step s2", "step s3", "sunburst", "sun-core", "spire left", "spire right", "spire middle"];
  return h("div", { class: "crown", "aria-hidden": "true" }, parts.map((p) => h("div", { class: p })));
}

function filmCount(count) {
  return `${count.toLocaleString("en")} ${count === 1 ? "film" : "films"}`;
}

// The sign: "Matinee", the largest thing on it, over a small letter board with the live film count, or
// "Private screening" before the device is admitted, inside a thin gold frame and a ring of bulbs.
function sign(count) {
  const films = count === null ? "Private screening" : filmCount(count);
  const face = h(
    "div",
    { class: "sign" },
    h("div", { class: "sign-frame", "aria-hidden": "true" }),
    h("div", { class: "sign-rule left", "aria-hidden": "true" }),
    h("div", { class: "sign-rule right", "aria-hidden": "true" }),
    h("div", { class: "sign-name" }, "Matinee"),
    h("p", { class: "letterboard" }, h("span", { class: "board-small" }, "Now showing"), " ", h("span", { class: "board-big" }, films)),
  );
  face.prepend(bulbs(face));
  return face;
}

// A neutral way on or back: a cream action.
function creamAction(text, onclick) {
  return h("button", { class: "action cream", type: "button", onclick }, text);
}

function strip(text, onclick) {
  return h("button", { class: "letterbox", type: "button", onclick }, text);
}

// A profile's tile: its mark, and its name in large type beneath.
function tile(profile, onclick) {
  return h(
    "button",
    { class: "seat", type: "button", onclick },
    mark(profile, "door"),
    h("span", { class: "seat-name" }, profile.name),
  );
}

function newTile(onclick) {
  return h(
    "button",
    { class: "seat new", type: "button", "aria-label": "+ New", onclick },
    h("span", { class: "mark door", "aria-hidden": "true" }, h("span", { class: "mark-initials" }, "+")),
    h("span", { class: "seat-name", "aria-hidden": "true" }, "New"),
  );
}

function field(props) {
  return h("input", { class: "field", autocomplete: "off", spellcheck: "false", ...props });
}

// The marquee: the crown over the lit sign. `count` null shows "Private screening".
export function buildMarquee(count) {
  return h("div", { class: "marquee" }, h("div", { class: "marquee-glow", "aria-hidden": "true" }), crown(), sign(count));
}

// The letter board shows the library's film count.
export function showCount(marquee, count) {
  marquee.querySelector(".board-big").textContent = filmCount(count);
}

// The door and what it asks. `onEnter` takes the viewer into the theatre, and is handed this door, whose
// name has flown to the wordmark's place by then.
export class Door {
  constructor({ stage, onEnter }) {
    this.stage = stage;
    this.onEnter = onEnter;
    this.profiles = [];
    this.held = [];
    this.picked = new Set();
    this.excluded = new Set();
    this.copy = null; // the name while it is away from the sign: flying, or landed at the wordmark's place
  }

  // Build the door and open on the front door's tiles, or on `screen` when given: a new profile ("new"),
  // or the viewer's list ("list"). `said` replaces the front door's line, as after a profile is deleted.
  // `marquee` is one already standing (the locked door's), kept in place rather than built again.
  async open({ door, screen = null, profileId = null, said = null, marquee = null }) {
    this.profiles = door.profiles;
    this.avatars = door.avatars;
    this.held = door.profiles.filter((p) => p.held);
    this.build(door.now_showing, marquee);
    if (screen === "new") return this.first();
    const tile = this.held.find((p) => p.id === profileId);
    const profile = screen === "list" && tile ? (await this.seatOf(tile)).seat : null;
    if (profile) return this.picker({ editing: profile });
    return this.greet(said);
  }

  // The stage: the marquee, the wall where Matinee's words are typed, and the credit line. A marquee already
  // standing keeps its place, and its letter board turns to the film count.
  build(count, marquee) {
    this.wall = h("div", { class: "door-wall" });
    const foot = h("footer", { class: "door-foot" }, credits({ around: this }));
    if (!marquee) {
      this.marquee = buildMarquee(count);
      clear(this.stage).append(h("h1", { class: "sr-only" }, "Matinee box office"), this.marquee, this.wall, foot);
      return;
    }
    this.marquee = marquee;
    showCount(marquee, count);
    for (const node of [...this.stage.children]) if (node !== marquee && node.tagName !== "H1") node.remove();
    this.stage.append(this.wall, foot);
  }

  // The front door: every profile's tile, sorted by name as the server sends them, then "+ New".
  greet(said = null) {
    const [ack, ask] = said ?? doorLines(this.profiles);
    const tiles = h(
      "div",
      { class: "seats", role: "group", "aria-label": "Profiles" },
      this.profiles.map((p) => tile(p, () => this.choose(p))),
      newTile(() => this.first()),
    );
    return this.talk(ack, ask, [tiles], { tiles: true });
  }

  // A tile opens its profile at once when this device holds it or it has no PIN; otherwise it asks the PIN.
  choose(profile) {
    if (opensAtOnce(profile)) return this.enterAs(profile);
    return this.pin(profile);
  }

  // The first action on a door screen wins: its buttons and fields are disabled at once.
  lock() {
    for (const b of this.wall.querySelectorAll("button, input")) b.disabled = true;
  }

  // The door's list of profiles as the server holds it now; kept as it was when the server cannot be read.
  async refresh() {
    const res = await get("/api/door");
    if (!res.ok) return;
    this.profiles = res.data.profiles;
    this.held = this.profiles.filter((p) => p.held);
  }

  // A profile that could not be opened: the door says why, over its tiles as they stand now.
  async refused(message) {
    await this.refresh();
    return this.greet(twoParts(message));
  }

  // One question on the wall: the line types out, then its controls appear. `tiles` lets the profile tiles
  // take the width the line keeps.
  async talk(ack, ask, controls, { tiles = false } = {}) {
    this.marquee.classList.remove("compact");
    const line = h("p", { class: "line door-line", "aria-live": "polite" });
    const below = h("div", { class: "door-controls", hidden: true }, controls);
    clear(this.wall).append(h("div", { class: tiles ? "door-talk at-seats" : "door-talk" }, line, below));
    await typeLine(line, ack, ask);
    below.hidden = false;
    const first = below.querySelector("input, button");
    first?.focus({ preventScroll: true, focusVisible: first.tagName === "INPUT" });
  }

  // Making a profile: its name, then its avatar or initials, then an optional PIN. The profile is made once
  // those are known; the list question follows, then "Find me something to watch".
  first() {
    return this.askName("Pull up a chair.", "What should I call you?");
  }

  askName(ack, ask, said = "") {
    const name = field({ type: "text", maxlength: 40, placeholder: "Your name", "aria-label": "Your name", autocomplete: "nickname" });
    const status = h("p", { class: "note", role: "status" }, said);
    const go = () => {
      const typed = name.value.trim().replace(/\s+/g, " ");
      if (!typed) return name.focus();
      const taken = findTaken(this.profiles, typed);
      if (taken) return this.taken(taken);
      return this.askAvatar({ name: typed });
    };
    // Enter is spent here, so it never also presses the next screen's first button; an IME's Enter is its own.
    name.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || e.isComposing) return;
      e.preventDefault();
      go();
    });
    const form = h("div", { class: "door-form" }, name, status, h("button", { class: "action gold", type: "button", onclick: go }, "Continue"));
    return this.talk(ack, ask, [form, creamAction("Never mind", () => this.greet())]);
  }

  // The name typed is already a profile's: "Yes" opens that profile, asking its PIN when it has one.
  taken(profile) {
    return this.talk(`I already have a ${profile.name}.`, "Is that you?", [
      strip("Yes, that's me", () => this.choose(profile)),
      strip("No, someone else", () => this.askName("Then I'll need another name,", "so I can tell you two apart.")),
    ]);
  }

  askAvatar(draft) {
    return this.talk(`Nice to meet you, ${draft.name}.`, "Would you like to set an avatar?", [
      avatarChoices(this.avatars, (avatar) => this.askPin({ ...draft, avatar })),
      strip("Just my initials", () => this.askPin({ ...draft, avatar: null })),
    ]);
  }

  // "Set a PIN" opens the PIN's field in place, "No PIN" staying beside it; four digits make the profile.
  // `said` is why an earlier attempt to make it failed.
  askPin(draft, said = "") {
    const entry = field({
      type: "password",
      inputmode: "numeric",
      maxlength: PIN_LENGTH,
      placeholder: "4 digits",
      "aria-label": "PIN, four digits",
      autocomplete: "new-password",
      class: "field pin",
    });
    const form = h("div", { class: "door-form narrow", hidden: true }, entry);
    const set = strip("Set a PIN", () => {
      set.hidden = true;
      form.hidden = false;
      entry.focus();
    });
    const status = h("p", { class: "note", role: "status" }, said);
    entry.addEventListener("input", () => {
      entry.value = entry.value.replace(/\D/g, "").slice(0, PIN_LENGTH);
      if (entry.value.length === PIN_LENGTH) {
        entry.disabled = true;
        this.create({ ...draft, pin: entry.value });
      }
    });
    const none = strip("No PIN", () => this.create({ ...draft, pin: null }));
    return this.talk("Want a PIN?", "Four digits keeps your list private.", [set, none, form, status]);
  }

  // Makes the profile. A name taken meanwhile asks "Is that you?" of the profile now holding it; a full
  // theatre goes back to the tiles with why; any other failure keeps the draft and says why.
  async create(draft) {
    this.lock();
    const res = await post("/api/profiles", draft);
    if (res.ok) return this.askList(res.data);
    const { code, message } = res.data;
    if (code === "full") return this.refused(message);
    if (code === "bad_name") return this.askName("Pull up a chair.", "What should I call you?", message);
    if (code !== "name_taken") return this.askPin(draft, message);
    await this.refresh();
    const holder = findTaken(this.profiles, draft.name);
    return holder ? this.taken(holder) : this.askName("Pull up a chair.", "What should I call you?", message);
  }

  askList(seat) {
    return this.talk("", "Anything you never want to see?", [
      strip("Nope, show me everything.", () => this.done(seat)),
      strip("Yes, there are a few things.", () => this.picker({ editing: seat, fresh: true })),
    ]);
  }

  done(seat) {
    const go = h("button", { class: "action gold find-me", type: "button", onclick: () => this.enterAs(seat) }, "Find me something to watch");
    return this.talk(`You're all set, ${seat.name}.`, "", [go]);
  }

  pin(suggestion) {
    const entry = field({
      type: "password",
      inputmode: "numeric",
      maxlength: PIN_LENGTH,
      placeholder: "4 digits",
      "aria-label": "PIN",
      class: "field pin",
    });
    const status = h("p", { class: "note", role: "status" });
    entry.addEventListener("input", async () => {
      entry.value = entry.value.replace(/\D/g, "").slice(0, PIN_LENGTH);
      status.textContent = "";
      if (entry.value.length < PIN_LENGTH) return;
      entry.disabled = true;
      const res = await post(`/api/profiles/${suggestion.id}/open`, { pin: entry.value });
      if (res.ok) return this.enterAs(res.data);
      if (res.data.code === "no_profile") return this.refused(res.data.message);
      status.textContent = res.data.message;
      entry.value = "";
      entry.disabled = false;
      entry.focus();
    });
    return this.talk(`Hi, ${suggestion.name}.`, "What's your PIN?", [
      h("div", { class: "door-form narrow" }, entry, status),
      creamAction("That's not me", () => this.greet()),
    ]);
  }

  // A profile as the door's list names it carries no exclusions: a held or PIN-less one opens without a PIN
  // to fetch them. `seat` is null when it could not be opened, and `message` says why.
  async seatOf(tile) {
    if (tile.topics) return { seat: tile, message: "" };
    const res = await post(`/api/profiles/${tile.id}/open`, { pin: null });
    return res.ok ? { seat: res.data, message: "" } : { seat: null, message: res.data.message };
  }

  async enterAs(profile) {
    this.lock();
    const { seat, message } = await this.seatOf(profile);
    if (!seat) return this.refused(message);
    const profileTopics = seat.topics.length > 0;
    return this.enter({ viewer: { profile_id: seat.id }, name: seat.name, avatar: seat.avatar, profileTopics });
  }

  // A door is entered once: a second tap or Enter before its buttons are disabled changes nothing.
  enter({ viewer = {}, name = null, avatar = null, profileTopics = false }) {
    if (this.entered) return;
    this.entered = true;
    for (const b of this.stage.querySelectorAll("button, input")) b.disabled = true;
    this.onEnter({ viewer, name, avatar, profileTopics, door: this });
  }

  // The marquee leaves: the door's words fade, the rest of the marquee lifts and fades, and the name flies
  // to the wordmark's place, beside `beside` (what the theatre's top bar will also hold). Resolves once it
  // has landed; it stays there until `settle()`. A phone's lit strip draws no name, so from the picker the
  // name is at the wordmark's place at once while the strip lifts away.
  async leave(beside = []) {
    const name = this.marquee.querySelector(".sign-name");
    if (!this.copy) {
      const at = nameAt(name); // measured before the marquee lifts, which moves the sign
      this.home = at.size > 0 ? at : null;
      this.copy = copyAt(this.home ?? { ...at, size: 30 });
      this.rise = riseOf(this.copy);
    }
    name.classList.add("away");
    this.stage.classList.add("leaving");
    this.marquee.classList.add("lifted");
    const to = wordmarkAt(this.rise, beside);
    if (this.home) return fly(this.copy, to);
    await fly(this.copy, to, { instant: true });
    if (!prefersLessMotion()) await wait(FLIGHT_MS);
  }

  // The landed name gives way to a wordmark standing in its place.
  settle() {
    this.copy?.remove();
    this.copy = null;
  }

  // The marquee returns: the name flies back to the sign from wherever it is, and the rest of the marquee
  // and the door's words come back. Resolves once the name is home. With no name on the sign to return to
  // (a phone's lit strip), the copy simply goes.
  async bringBack() {
    this.stage.classList.remove("leaving");
    this.marquee.classList.remove("lifted");
    const name = this.marquee.querySelector(".sign-name");
    if (!this.home) {
      name.classList.remove("away");
      this.settle();
      return;
    }
    this.copy ??= copyAt(wordmarkAt(this.rise));
    await fly(this.copy, this.home);
    if (this.marquee.classList.contains("lifted")) return; // it left again before it was home
    name.classList.remove("away");
    this.settle();
  }

  // The trigger picker, which is also the preferences page, for `editing`, a held profile. `fresh` is a
  // profile just made, whose list saved leads to "Find me something to watch".
  async picker({ editing, fresh = false }) {
    this.fresh = fresh;
    this.picked = new Set(editing.topics);
    this.excluded = new Set(editing.exclusions);
    this.marquee.classList.add("compact");
    const heading = h(
      "p",
      { class: "line door-line done" },
      h("span", { class: "ack" }, fresh ? "No problem." : "Your list."),
      h("span", { class: "ask" }, "What should I steer around?"),
    );
    this.status = h("p", { class: "note picker-status", role: "status" });
    const topics = h("div", { class: "picker-topics" }, h("p", { class: "note" }, "Fetching the list…"));
    // In reading order, which is also the Tab order; the desktop layout places the topics beside the rest.
    const parts = [
      heading,
      h("p", { class: "note picker-lead" }, "I'll check each pick against these and pass on any that hits one."),
      topics,
      this.status,
      h("div", { class: "picker-actions" }, this.saveButton(editing, this.status), this.neverMind(editing, creamAction)),
    ];
    clear(this.wall).append(h("div", { class: "picker" }, parts));
    await this.fillTopics(topics, editing);
  }

  // The way out of the picker without saving: back to a just-made profile's last step, or into the theatre.
  neverMind(editing, as) {
    if (this.fresh) return as("Never mind, show me everything", () => this.done(editing));
    return as("Never mind, keep my list", () => this.enterAs(editing));
  }

  saveButton(editing, status) {
    const button = h("button", { class: "action gold", type: "button" }, this.fresh ? "Save and continue" : "Save my list");
    button.addEventListener("click", async () => {
      button.disabled = true;
      const said = await this.save(editing);
      if (said) {
        status.textContent = said;
        button.disabled = false;
      }
    });
    return button;
  }

  // Saves the list and moves on, or returns what to tell the viewer.
  async save(editing) {
    const body = { topics: [...this.picked], exclusions: [...this.excluded] };
    const res = await put(`/api/profiles/${editing.id}/exclusions`, body);
    if (!res.ok) return res.data.message;
    return this.fresh ? this.done(res.data) : this.enterAs(res.data);
  }

  // Matinee's own exclusions first, then DoesTheDogDie's topics, fetched now and never kept.
  async fillTopics(box, editing) {
    const [own, dtdd] = await Promise.all([get("/api/exclusions"), get("/api/topics")]);
    const search = field({ type: "text", placeholder: "Search, like spiders or needles", "aria-label": "Search topics" });
    const list = h("div", { class: "topic-list" });
    const tally = h("span", {});
    const nothing = h("p", { class: "note", hidden: true }, "Nothing by that name. Try another word.");
    const count = () => {
      const n = this.picked.size + this.excluded.size;
      tally.textContent = n ? `${n} chosen` : "Nothing chosen yet";
    };
    const mine = own.ok ? own.data.map((x) => this.topic(sentenceCase(x.say), x.say, this.excluded, x.id, count)) : [];
    const theirs = dtdd.ok ? dtdd.data.topics.map((t) => this.topic(sentenceCase(t.short), `${t.name} ${t.keywords}`, this.picked, t.id, count)) : [];
    list.append(...mine, ...theirs, nothing);
    search.addEventListener("input", () => {
      const needle = search.value.trim().toLowerCase();
      let shown = 0;
      for (const p of [...mine, ...theirs]) {
        p.hidden = !p.dataset.find.includes(needle);
        if (!p.hidden) shown += 1;
      }
      nothing.hidden = shown > 0;
    });
    count();
    const credit = dtdd.ok
      ? [" · Best effort, from crowd votes · ", h("a", { href: dtdd.data.link, target: "_blank", rel: "noopener noreferrer" }, dtdd.data.credit)]
      : [];
    const trouble = dtdd.ok ? [] : [this.topicsTrouble(box, dtdd.data.message, editing)];
    clear(box).append(search, ...trouble, list, h("p", { class: "note small" }, tally, credit));
    count();
  }

  // The topic list could not be fetched: say so, offer everything and a retry.
  topicsTrouble(box, message, editing) {
    return h(
      "div",
      { class: "topics-trouble" },
      h("p", { class: "note" }, message || "I can't load the topic list right now."),
      h(
        "div",
        { class: "picker-actions" },
        creamAction("Try again", () => this.fillTopics(box, editing)),
      ),
    );
  }

  // A topic is a letterbox that toggles: chosen, it shows a check mark before its words.
  topic(label, find, chosen, id, count) {
    const on = chosen.has(id);
    const b = h("button", { class: "letterbox topic", type: "button", "aria-pressed": String(on) }, label);
    b.dataset.find = `${label} ${find}`.toLowerCase();
    b.addEventListener("click", () => {
      if (chosen.has(id)) chosen.delete(id);
      else chosen.add(id);
      b.setAttribute("aria-pressed", String(chosen.has(id)));
      count();
    });
    return b;
  }
}
