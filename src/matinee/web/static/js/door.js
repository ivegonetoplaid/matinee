// The box office: an art deco booth with a lit sign, where Matinee greets a
// viewer before the poster wall. Every question at the door is asked on the
// booth's back wall, between the velvet columns; the booth never leaves the
// screen until the viewer goes in.

import { get, post, put } from "./api.js";
import { credits } from "./credits.js";
import { clear, h, isPhone, sentenceCase } from "./dom.js";
import { typeLine } from "./type.js";

// Bulbs round the sign and the gap between them, as on the design boards; one dark bulb chases clockwise.
const BULBS = { desktop: { count: 132, inset: 7 }, phone: { count: 60, inset: 6 } };
const CHASE_S = 7;
const LOOKUP_AFTER_MS = 200;
const PIN_LENGTH = 4;

const NOTE_REMEMBER = "Keeps your list for next time. Add a PIN to keep it private.";
const NOTE_FORGET = "Nothing saved. You'll pick again next time.";

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

function bulbs(sign) {
  const { count, inset } = isPhone() ? BULBS.phone : BULBS.desktop;
  const layer = h("div", { class: "bulbs", "aria-hidden": "true" });
  const spans = Array.from({ length: count }, (_, k) => {
    const b = h("span", { class: "bulb" });
    const twinkle = (1.3 + ((k * 7) % 13) / 10).toFixed(2);
    b.style.animationDuration = `${CHASE_S}s, ${twinkle}s`;
    b.style.animationDelay = `${((k / count) * CHASE_S - CHASE_S).toFixed(3)}s, ${(-((k * 5) % 11) / 10).toFixed(2)}s`;
    return b;
  });
  layer.append(...spans);
  const place = () => {
    const w = sign.clientWidth;
    const hgt = sign.clientHeight;
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

function sign(count) {
  const films = `${count.toLocaleString("en")} ${count === 1 ? "film" : "films"}`;
  const face = h(
    "div",
    { class: "sign" },
    h("div", { class: "sign-rule" }),
    h(
      "div",
      { class: "sign-face" },
      h("div", { class: "sign-name" }, "Matinee"),
      h("p", { class: "letterboard" }, h("span", { class: "board-small" }, "Now showing"), " ", h("span", { class: "board-big" }, films)),
    ),
    h("div", { class: "sign-rule" }),
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

function field(props) {
  return h("input", { class: "field", autocomplete: "off", spellcheck: "false", ...props });
}

// The booth and what it asks. `onEnter` takes the viewer into the theatre.
export class Door {
  constructor({ stage, onEnter }) {
    this.stage = stage;
    this.onEnter = onEnter;
    this.held = [];
    this.picked = new Set();
    this.excluded = new Set();
  }

  // Build the booth and open on the screen this device's tokens call for, or on `screen` when given.
  async open({ door, screen = null, profileId = null }) {
    this.held = door.profiles;
    this.wall = h("div", { class: "backwall" });
    this.booth = h(
      "div",
      { class: "booth" },
      h("div", { class: "booth-glow", "aria-hidden": "true" }),
      crown(),
      sign(door.now_showing),
      h("div", { class: "booth-middle" }, h("div", { class: "column", "aria-hidden": "true" }), this.wall, h("div", { class: "column", "aria-hidden": "true" })),
      h("footer", { class: "counter" }, h("div", { class: "counter-top", "aria-hidden": "true" }), h("div", { class: "counter-front" }, credits({ full: true }))),
    );
    clear(this.stage).append(h("h1", { class: "sr-only" }, "Matinee box office"), this.booth);
    if (screen === "known") return this.known();
    const profile = this.held.find((p) => p.id === profileId);
    if (screen === "list" && profile) return this.picker({ editing: profile });
    return this.greet();
  }

  greet() {
    if (this.held.length === 1) return this.welcome(this.held[0]);
    if (this.held.length > 1) return this.back();
    return this.first();
  }

  // One question on the back wall: the line types out, then its controls appear.
  async talk(ack, ask, controls) {
    this.booth.classList.remove("compact");
    const line = h("p", { class: "line door-line", "aria-live": "polite" });
    const below = h("div", { class: "door-controls", hidden: true }, controls);
    clear(this.wall).append(h("div", { class: "door-talk" }, line, below));
    await typeLine(line, ack, ask);
    below.hidden = false;
    const first = below.querySelector("input, button");
    first?.focus({ preventScroll: true, focusVisible: first.tagName === "INPUT" });
  }

  first() {
    return this.talk("Hi! A few questions before I show you to your seats.", "Anything you never want to see?", [
      strip("Nope, show me all the movies.", () => this.enter({})),
      strip("Yes, there are a few things.", () => this.picker({})),
      linkButton("I've been here before", () => this.known()),
    ]);
  }

  welcome(profile) {
    return this.talk(`Welcome back, ${profile.name}.`, "Your seats are waiting.", [
      strip("Take me in", () => this.enterAs(profile)),
      linkButton(`Not ${profile.name}?`, () => this.known()),
    ]);
  }

  back() {
    return this.talk("Welcome back.", "Who's watching?", [
      this.held.map((p) => strip(p.name, () => this.enterAs(p))),
      strip("Someone new", () => this.first()),
      linkButton("Not on the list? I've been here before", () => this.known()),
    ]);
  }

  // The name lookup: suggestions after three characters, at most three of them (the server's rule).
  known() {
    const name = field({ type: "text", maxlength: 40, placeholder: "Your name", "aria-label": "Your name" });
    const suggestions = h("div", { class: "suggest", "aria-live": "polite" });
    const status = h("p", { class: "note", role: "status" });
    let found = [];
    let timer = null;
    const lookup = async () => {
      clearTimeout(timer);
      const typed = name.value.trim();
      const res = typed.length >= 3 ? await post("/api/names", { typed }) : { ok: true, data: [] };
      if (typed !== name.value.trim()) return; // a later keystroke owns the list now
      found = res.ok ? res.data : [];
      clear(suggestions);
      if (found.length) {
        suggestions.append(
          h("span", { class: "note" }, "Did you mean"),
          ...found.map((s) => h("button", { class: "chip", type: "button", onclick: () => this.choose(s) }, s.name)),
        );
      }
    };
    name.addEventListener("input", () => {
      status.textContent = "";
      clearTimeout(timer);
      timer = setTimeout(lookup, LOOKUP_AFTER_MS);
    });
    const go = async () => {
      await lookup(); // the typed name as it is now, not the last answer that came back
      const typed = name.value.trim().toLowerCase();
      const exact = found.find((s) => s.name.toLowerCase() === typed);
      if (exact) this.choose(exact);
      else status.textContent = "No one by that name yet.";
    };
    name.addEventListener("keydown", (e) => {
      if (e.key === "Enter") go();
    });
    return this.talk("Welcome back.", "What should I call you?", [
      h("div", { class: "door-form" }, name, suggestions, status, h("button", { class: "pill solid", type: "button", onclick: go }, "Continue")),
      linkButton("Never mind, I'm new", () => this.first()),
    ]);
  }

  // A profile this device holds, or one without a PIN, opens at once; any other asks for its PIN.
  async choose(suggestion) {
    const held = this.held.find((p) => p.id === suggestion.id);
    if (held) return this.enterAs(held);
    if (suggestion.has_pin) return this.pin(suggestion);
    const res = await post(`/api/profiles/${suggestion.id}/open`, { pin: null });
    if (res.ok) return this.enterAs(res.data);
    return this.known();
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

  enterAs(profile) {
    this.enter({ viewer: { profile_id: profile.id }, name: profile.name, profileTopics: profile.topics.length > 0 });
  }

  enter({ viewer = {}, name = null, profileTopics = false }) {
    for (const b of this.booth.querySelectorAll("button, input")) b.disabled = true;
    this.onEnter({ viewer, name, profileTopics });
  }

  // The trigger picker, which is also the preferences page when `editing` names a held profile.
  async picker({ editing = null }) {
    this.picked = new Set(editing ? editing.topics : []);
    this.excluded = new Set(editing ? editing.exclusions : []);
    this.booth.classList.add("compact");
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
      editing ? null : this.remember(),
      this.status,
      h(
        "div",
        { class: "picker-actions" },
        this.saveButton(editing, this.status),
        editing
          ? linkButton("Never mind, keep my list", () => this.enterAs(editing))
          : linkButton("Never mind, show me everything", () => this.enter({})),
      ),
    ];
    clear(this.wall).append(h("div", { class: "picker" }, parts));
    await this.fillTopics(topics, editing);
  }

  remember() {
    const box = h("input", { type: "checkbox", checked: true });
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
    const who = h("div", { class: "remember-who" }, this.nameField, this.pinField);
    box.addEventListener("change", () => {
      this.status.textContent = "";
      note.textContent = box.checked ? NOTE_REMEMBER : NOTE_FORGET;
      who.hidden = !box.checked;
      this.saveLabel.textContent = box.checked ? "Save and continue" : "Continue";
    });
    this.rememberBox = box;
    return h("div", { class: "remember" }, h("label", { class: "check" }, box, "Remember me"), note, who);
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
    if (!this.rememberBox.checked) return this.enter({ viewer: { topics, exclusions } });
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
        editing
          ? strip("Never mind, keep my list", () => this.enterAs(editing))
          : strip("Nope, show me all the movies.", () => this.enter({})),
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
