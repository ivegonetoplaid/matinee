// The front door: the marquee, a stepped crown over a lit sign, stands at the top
// centre over the poster wall, and Matinee greets a viewer on the wall below it.
// Every question at the door types straight onto the wall, with nothing behind
// Matinee's words; the marquee stays until the viewer goes in.

import { get, post, put } from "./api.js";
import { credits } from "./credits.js";
import { clear, h, isPhone, prefersLessMotion, sentenceCase, wait } from "./dom.js";
import { FLIGHT_MS, copyAt, fly, nameAt, riseOf, wordmarkAt } from "./flight.js";
import { mark } from "./mark.js";
import { typeLine } from "./type.js";

// Bulbs round the sign and the gap between them, as on the design boards. Two dark bulbs chase clockwise,
// half a lap apart, one lap every CHASE_S seconds.
const BULBS = { desktop: { count: 156, inset: 9 }, phone: { count: 64, inset: 6 } };
const CHASE_S = 12;
const PIN_LENGTH = 4;

const NOTE_REMEMBER = "Keeps your list for next time. Add a PIN to keep it private.";

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

// The sign: "Matinee", the largest thing on it, over a small letter board with the live film count,
// inside a thin gold frame and a ring of bulbs.
function sign(count) {
  const films = `${count.toLocaleString("en")} ${count === 1 ? "film" : "films"}`;
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

function linkButton(text, onclick) {
  return h("button", { class: "link-button", type: "button", onclick }, text);
}

function strip(text, onclick) {
  return h("button", { class: "answer", type: "button", onclick }, text);
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

// What the front door says over the tiles: a device holding a profile is welcomed back without a name.
function doorLines(profiles) {
  if (!profiles.length) {
    return ["Welcome.", "Nobody has a seat yet. Introduce yourself. One profile the whole house shares works fine too."];
  }
  if (profiles.some((p) => p.held)) return ["Welcome back.", "Who's watching?"];
  return ["Welcome.", "Pick your seat, or introduce yourself and I'll find you something to watch."];
}

function field(props) {
  return h("input", { class: "field", autocomplete: "off", spellcheck: "false", ...props });
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
  async open({ door, screen = null, profileId = null, said = null }) {
    this.profiles = door.profiles;
    this.held = door.profiles.filter((p) => p.held);
    this.wall = h("div", { class: "door-wall" });
    this.marquee = h("div", { class: "marquee" }, h("div", { class: "marquee-glow", "aria-hidden": "true" }), crown(), sign(door.now_showing));
    clear(this.stage).append(
      h("h1", { class: "sr-only" }, "Matinee box office"),
      this.marquee,
      this.wall,
      h("footer", { class: "door-foot" }, credits({ around: this })),
    );
    if (screen === "new") return this.first();
    const tile = this.held.find((p) => p.id === profileId);
    const profile = screen === "list" && tile ? await this.seatOf(tile) : null;
    if (profile) return this.picker({ editing: profile });
    return this.greet(said);
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
    if (profile.held || !profile.has_pin) return this.enterAs(profile);
    return this.pin(profile);
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

  // Every viewing runs under a profile: a viewer new to this device makes one on the picker.
  first() {
    return this.picker({});
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
      status.textContent = res.data.message;
      entry.value = "";
      entry.disabled = false;
      entry.focus();
    });
    return this.talk(`Hi, ${suggestion.name}.`, "What's your PIN?", [
      h("div", { class: "door-form narrow" }, entry, status),
      linkButton("That's not me", () => this.greet()),
    ]);
  }

  // A profile as the door's list names it carries no exclusions: a held one opens without its PIN to fetch them.
  async seatOf(tile) {
    if (tile.topics) return tile;
    const res = await post(`/api/profiles/${tile.id}/open`, { pin: null });
    return res.ok ? res.data : null;
  }

  async enterAs(profile) {
    const seat = await this.seatOf(profile);
    if (!seat) return this.greet();
    return this.enter({ viewer: { profile_id: seat.id }, name: seat.name, profileTopics: seat.topics.length > 0 });
  }

  // A door is entered once: a second tap or Enter before its buttons are disabled changes nothing.
  enter({ viewer = {}, name = null, profileTopics = false }) {
    if (this.entered) return;
    this.entered = true;
    for (const b of this.stage.querySelectorAll("button, input")) b.disabled = true;
    this.onEnter({ viewer, name, profileTopics, door: this });
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

  // The trigger picker, which is also the preferences page when `editing` names a held profile.
  async picker({ editing = null }) {
    this.picked = new Set(editing ? editing.topics : []);
    this.excluded = new Set(editing ? editing.exclusions : []);
    this.marquee.classList.add("compact");
    const heading = h(
      "p",
      { class: "line door-line done" },
      h("span", { class: "ack" }, editing ? "Your list." : "No problem."),
      h("span", { class: "ask" }, "What should I steer around?"),
    );
    this.status = h("p", { class: "note picker-status", role: "status" });
    const topics = h("div", { class: "picker-topics" }, h("p", { class: "note" }, "Fetching the list…"));
    // In reading order, which is also the Tab order; the desktop layout places the topics beside the rest.
    const parts = [
      heading,
      h("p", { class: "note picker-lead" }, "I'll check each pick against these and pass on any that hits one."),
      topics,
      editing ? null : this.who(),
      this.status,
      h(
        "div",
        { class: "picker-actions" },
        this.saveButton(editing, this.status),
        editing ? linkButton("Never mind, keep my list", () => this.enterAs(editing)) : null,
      ),
    ];
    clear(this.wall).append(h("div", { class: "picker" }, parts));
    await this.fillTopics(topics, editing);
  }

  // The new profile's name and optional PIN.
  who() {
    const note = h("p", { class: "note remember-note" }, NOTE_REMEMBER);
    this.nameField = field({ type: "text", maxlength: 40, placeholder: "Your name", "aria-label": "Your name" });
    this.pinField = field({
      type: "password",
      inputmode: "numeric",
      maxlength: PIN_LENGTH,
      placeholder: "PIN",
      "aria-label": "PIN, optional, four digits",
      autocomplete: "new-password",
    });
    this.pinField.addEventListener("input", () => {
      this.pinField.value = this.pinField.value.replace(/\D/g, "").slice(0, PIN_LENGTH);
    });
    return h("div", { class: "remember" }, note, h("div", { class: "remember-who" }, this.nameField, this.pinField));
  }

  saveButton(editing, status) {
    this.saveLabel = h("span", {}, editing ? "Save my list" : "Save and continue");
    const button = h("button", { class: "pill solid", type: "button" }, this.saveLabel);
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

  // Saves and goes in, or returns what to tell the viewer.
  async save(editing) {
    const topics = [...this.picked];
    const exclusions = [...this.excluded];
    if (editing) {
      const res = await put(`/api/profiles/${editing.id}/exclusions`, { topics, exclusions });
      return res.ok ? this.enterAs(res.data) : res.data.message;
    }
    const name = this.nameField.value.trim();
    if (!name) {
      this.nameField.focus();
      return "I'll need a name to remember you.";
    }
    const pin = this.pinField.value || null;
    const res = await post("/api/profiles", { name, pin, topics, exclusions });
    return res.ok ? this.enterAs(res.data) : res.data.message;
  }

  // Matinee's own exclusions first, then DoesTheDogDie's topics, fetched now and never kept.
  async fillTopics(box, editing) {
    const [own, dtdd] = await Promise.all([get("/api/exclusions"), get("/api/topics")]);
    const search = field({ type: "text", placeholder: "Search, like spiders or needles", "aria-label": "Search topics" });
    const pills = h("div", { class: "topic-pills" });
    const tally = h("span", {});
    const nothing = h("p", { class: "note", hidden: true }, "Nothing by that name. Try another word.");
    const count = () => {
      const n = this.picked.size + this.excluded.size;
      tally.textContent = n ? `${n} chosen` : "Nothing chosen yet";
    };
    const mine = own.ok ? own.data.map((x) => this.pill(sentenceCase(x.say), x.say, this.excluded, x.id, count)) : [];
    const theirs = dtdd.ok ? dtdd.data.topics.map((t) => this.pill(sentenceCase(t.short), `${t.name} ${t.keywords}`, this.picked, t.id, count)) : [];
    pills.append(...mine, ...theirs, nothing);
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
    clear(box).append(search, ...trouble, pills, h("p", { class: "note small" }, tally, credit));
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
        editing ? strip("Never mind, keep my list", () => this.enterAs(editing)) : null,
        linkButton("Try again", () => this.fillTopics(box, editing)),
      ),
    );
  }

  pill(label, find, chosen, id, count) {
    const on = chosen.has(id);
    const b = h("button", { class: "topic", type: "button", "aria-pressed": String(on) }, label);
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
