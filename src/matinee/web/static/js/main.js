// Matinee's page: the box office, then the questions on the poster wall, then the pick.

import { del, get, post, put } from "./api.js";
import { noteLink, walkOf } from "./note.js";
import { aboutLink, dtddFoot, dtddSetting } from "./credits.js";
import { Door, buildMarquee, marqueeReady, showCount } from "./door.js";
import { LockedDoor, WALL_FADE_MS } from "./locked.js";
import { clear, h, isPhone, prefersLessMotion, sentenceCase, wait } from "./dom.js";
import { cornerMark } from "./flight.js";
import { pickPanel } from "./panel.js";
import { asPick, newestFirst, remember, runKey, shownBody } from "./run.js";
import { undoLink } from "./hide.js";
import { answerRows, forget, stepBack, wayTo } from "./way-back.js";
import { showPick } from "./pick.js";
import { posterPaths } from "./pictures.js";
import { Deck, dealBeneath, dealPair, setFor } from "./quips.js";
import { lightFuse } from "./fuse.js";
import { typeLine } from "./type.js";
import { Wall } from "./wall.js";
import { viewerTag } from "./viewer.js";
import { isOpen as profileOpen, openProfile, profileLayer, refreshFilms } from "./profile.js";
import { keptWalk, openOverlay } from "./overlay.js";
import { answerOf } from "./ratings.js";
import { settingsPart } from "./settings.js";
import { ALL_SET, WELCOME, WHATS_NEW, tailorSteps } from "./tailor.js";
import { hiddenPart, hiddenUntil, ratedPart } from "./cases.js";
import { shownPart } from "./shelves.js";
import { learnOffers, offers } from "./offers.js";

const stage = document.getElementById("stage");
const wall = new Wall(document.getElementById("wall"));

// Where this visit stands. The viewer is always a profile this device holds.
const visit = {
  viewer: {},
  name: null,
  avatar: null,
  profileTopics: false,
  tree: null,
  answers: [],
  says: [], // what the viewer answered, one per entry in answers
  asks: [], // the question each of those answered
  rushed: false, // "Just pick one!" ended the questions early
  firstSay: null,
  source: null, // the source question's answer, asked at the start of every walk; "all" when it is not asked
  sourceSay: null,
  sourceAsk: null, // the source question, while it is asked
  sourceReply: "", // Matinee's gold line on the doors within the source
  doorAsk: null, // the doors' question
  seen: [],
  pool: [],
  trees: [],
  run: [], // the films this run has shown on screen, oldest first (run.js)
  runKey: null, // the key the server keeps this run's history under, new at every run's start
};

const CHECKING = "Let me check this one against your list.";

// The films still in the running, beside "Just pick one!", with thousands separators.
function countText(n) {
  return `${n.toLocaleString("en")} ${n === 1 ? "film" : "films"} to choose from`;
}

// The pick's lines, fetched once per page, once the device is admitted; null until they arrive, or when they
// could not be read.
let quips = null;
let quipsAsked = false;
const deck = new Deck(); // one per visit: no line repeats until its set has run out
function loadQuips() {
  if (quipsAsked) return;
  quipsAsked = true;
  get("/api/quips").then((res) => {
    if (res.ok) quips = res.data;
    else console.warn("the pick's lines could not be read; picks show no line", res.data);
  });
}

// The avatars the server offers, as the door's reply names them.
let avatarsOffered = [];

// The door whose name flew in on going in; its name stands at the wordmark's place until the theatre's own
// wordmark takes over.
let landing = null;

const TALK_FADE_MS = 350; // the question's words fade out as a pick begins
const READ_MS = 1000; // Matinee's reply to the last answer is read this long before the hunt starts

// The first action on a screen wins: every button on it is disabled at once, so an
// answer and "Just pick one!" can never both run.
function lockStage() {
  for (const button of stage.querySelectorAll("button")) button.disabled = true;
}

// Leaving a pick by a way back out (an answer in the Back panel, the name tag, "Start over") ends it at the tap:
// the hunt stops where it is, and the pick changes nothing further while the next screen loads.
function leaveTo(next) {
  dropPickEntry();
  lockStage();
  wall.endPick();
  next();
}

// The wordmark is the corner mark, a link that does what "Start over" does: back to the first question, as
// the same viewer. Without a viewer (a problem before going in) it goes back to the door.
function wordmark() {
  const go = (e) => {
    e.preventDefault();
    leaveTo(visit.viewer.profile_id ? startOver : boot);
  };
  return h("a", { class: "wordmark", href: "/", onclick: go }, cornerMark("Matinee"));
}

// The theatre's top bar, the wordmark at its left. A name that flew in from the door gives way to it, and
// the door, faded since going in, is no longer the stage's.
function topbar(...rest) {
  const mark = wordmark();
  const bar = h("header", { class: "topbar" }, mark, ...rest);
  if (landing) mark.classList.add("arriving");
  landing?.settle({ handover: true });
  landing = null;
  stage.classList.remove("at-door", "leaving");
  return bar;
}

// The viewer at the right of the top bar: their mark and name, which open the profile menu.
function nameTag() {
  if (!visit.name) return null;
  return viewerTag(
    { name: visit.name, avatar: visit.avatar },
    { myProfile: (opener) => myProfile(opener), switchProfiles: () => leaveTo(() => boot({})) },
  );
}

async function saveAvatar(id, avatar) {
  const res = await put(`/api/profiles/${id}/avatar`, { avatar });
  if (res.ok) visit.avatar = res.data.avatar;
  return res;
}

// The top bar's viewer, drawn again with the name and avatar the viewer now has.
function redrawTag() {
  const old = stage.querySelector(".topbar .viewer");
  if (old) old.replaceWith(nameTag());
}

// My profile, over the theatre as it stands; `at` opens it at one of its parts, and `then` runs as it closes.
function myProfile(opener = null, at = null, then = null) {
  const id = visit.viewer.profile_id;
  const viewer = { id, name: visit.name, avatar: visit.avatar };
  const openFilm = (from, film, did, walk) =>
    openOverlay({ layer: profileLayer(), film, did, walk, opener: from, viewer, poster: (tmdb, size) => wall.posterUrl(tmdb, size), trees: () => visit.trees, changed: refreshFilms });
  return openProfile({
    viewer,
    avatars: avatarsOffered,
    opener,
    at,
    then,
    parts: {
      tailor: (body) => settingsPart(body, { id, dtdd: offers.dtdd, credit: dtddSetting }),
      rated: (body, mine) =>
        ratedPart(body, mine.ratings, {
          poster: (tmdb) => wall.posterUrl(tmdb, "m"),
          phone: isPhone(),
          onOpen: (r, opener) => openFilm(opener, r, `You rated it: ${answerOf(r.score)}`, keptWalk(r.tmdb, mine.runs)),
        }),
      shown: (body, mine) =>
        shownPart(body, mine.runs, mine.ratings, {
          poster: (tmdb, size) => wall.posterUrl(tmdb, size),
          phone: isPhone(),
          onOpen: (f, did, opener) => openFilm(opener, f, did, f.walk),
        }),
      hidden: (body, mine, { recount }) =>
        hiddenPart(body, mine.hidden, {
          id,
          poster: (tmdb) => wall.posterUrl(tmdb, "m"),
          recount,
          onOpen: (f, opener) => openFilm(opener, f, hiddenUntil(f.until), keptWalk(f.tmdb, mine.runs)),
        }),
    },
    actions: {
      saveAvatar: async (avatar) => {
        const res = await saveAvatar(id, avatar);
        if (res.ok) redrawTag();
        return res;
      },
      renamed: (seat) => {
        visit.name = seat.name;
        redrawTag();
      },
      switchProfiles: () => leaveTo(() => boot({})),
      deleteProfile: async ({ leaving }) => {
        const res = await del(`/api/profiles/${id}`);
        if (res.ok) leaving(() => leaveTo(() => boot({ said: [`${res.data.name}'s seat is empty.`, "Who's watching?"] })));
        return res;
      },
    },
  });
}

// The walk's steps so far: "Start", the source answer when the source question was asked, the door, then each
// answer. A question screen's "Back" goes to the screen before the step showing now.
function walkSteps() {
  return ["Start", visit.sourceSay, visit.firstSay, ...visit.says].filter((say) => say !== null);
}

// Where a question screen's "‹ Back" leads, as a step: the screen before the one showing, whose step is `here`.
// None where that is the walk's first screen: one step back there is the same as starting over.
function backTo(here) {
  const target = here - 1;
  return target > 0 ? target : null;
}

// A question screen's way back: one action at the foot's left at every width, where the pick's "‹ Back" stands.
// "‹ Back" where there is a screen before this one other than the first; "Start over" where one step back would
// reach the walk's first screen. None on the walk's first screen.
function wayBack(here) {
  if (!visit.tree && !visit.sourceSay) return null;
  const target = backTo(here);
  const action =
    target === null
      ? h("button", { class: "action cream", type: "button", onclick: () => leaveTo(startOver) }, "Start over")
      : h("button", { class: "action cream", type: "button", onclick: () => leaveTo(() => goTo(target)) }, "‹ Back");
  return h("nav", { class: "way-back", "aria-label": "Way back" }, action);
}

// The last step, which led to the screen showing now.
function lastStep() {
  return walkSteps().length - 1;
}

// A question screen. "Just pick one!" stands last, beneath the answers and any footnote, with the count of
// films still in the running beside it, and shows with them.
function frame({ count, footnote }) {
  const line = h("h1", { class: "line", "aria-live": "polite" });
  const answers = h("div", { class: "answers", role: "group", "aria-label": "Your answers", hidden: true });
  const note = footnote ? h("p", { class: "footnote", hidden: true }, footnote) : null;
  const pick = h(
    "button",
    {
      class: "action gold just-pick",
      type: "button",
      onclick: () => {
        lockStage();
        visit.rushed = true;
        pickNow(rushLine());
      },
    },
    "Just pick one!",
  );
  const row = h("div", { class: "just-pick-row", hidden: true }, pick, h("span", { class: "count" }, count));
  clear(stage).append(
    topbar(nameTag()),
    h("section", { class: "talk" }, line, answers, note, row),
    h("div", { class: "bottombar" }, wayBack(lastStep())),
  );
  return { line, answers, note, pick: row };
}

// A picture question (the gore pails) shows each answer as its image, with the answer's words beneath it.
function answerButton(o, picture) {
  const onclick = () => {
    lockStage();
    o.go();
  };
  if (!picture) return h("button", { class: "letterbox", type: "button", onclick }, sentenceCase(o.say));
  return h(
    "button",
    { class: "pail", type: "button", onclick },
    h("img", { src: o.image, alt: "", width: 512, height: 512, decoding: "async" }),
    h("span", { class: "pail-say" }, sentenceCase(o.say)),
  );
}

async function ask({ ack, question, options, count, many = false, picture = false, footnote = null }) {
  const { line, answers, note, pick } = frame({ count, footnote });
  const buttons = options.map((o) => answerButton(o, picture));
  answers.classList.toggle("many", many);
  answers.classList.toggle("pails", picture);
  answers.append(...buttons);
  await typeLine(line, ack, question);
  answers.hidden = false;
  if (note) note.hidden = false;
  pick.hidden = false;
}

// A problem screen: the message and "Try again". The wall is emptied, so no stale film list shows, except
// when `keep` is set: a start that fails after going in keeps the door's posters behind it.
function problem(data, again, keep = false) {
  dropPickEntry();
  if (!keep) wall.clear();
  const line = h("h1", { class: "line" });
  line.append(h("span", { class: "ack" }, data.message || "Something went wrong."));
  clear(stage).append(
    topbar(),
    h(
      "section",
      { class: "talk" },
      line,
      h("button", { class: "action cream", type: "button", onclick: again }, "Try again"),
    ),
    h("footer", { class: "bottombar" }, aboutLink()),
  );
}

// The setup note: what Matinee sees wrong with its setup, said once per visit before any pick. "Show me the
// films" goes on to the door; with no film to offer there is no way in, only "Try again", which asks afresh.
let setupSeen = false;
async function setupNote(note, onGo) {
  setupSeen = true;
  wall.clear();
  const line = h("h1", { class: "line", "aria-live": "polite" });
  const said = h("div", { class: "setup-lines", hidden: true }, note.lines.map((text) => h("p", { class: "note" }, text)));
  const go = () => {
    lockStage();
    onGo();
  };
  const action = note.go_on
    ? h("button", { class: "action gold", type: "button", onclick: go }, "Show me the films")
    : h("button", { class: "action cream", type: "button", onclick: go }, "Try again");
  action.hidden = true;
  clear(stage).append(topbar(), h("section", { class: "talk setup" }, line, said, action), h("footer", { class: "bottombar" }, aboutLink()));
  // What it says, and the way on, appear once the heading has typed; the way on takes the focus, which scrolls
  // it clear of the foot's band when the note runs long.
  await typeLine(line, note.heading, "");
  said.hidden = false;
  action.hidden = false;
  action.focus();
}

// The warning the server gives while the film data breaks TMDB's terms: a strip across the top of every
// screen, the stage starting beneath it. None given, the strip goes.
let staleWarning = null;
function showWarning(text) {
  let strip = document.getElementById("warning");
  if (!text) {
    strip?.remove();
    document.documentElement.style.removeProperty("--warning-h");
    return;
  }
  if (!strip) {
    strip = h("p", { id: "warning", class: "warning-strip", role: "alert" });
    document.body.prepend(strip);
    new ResizeObserver(() => document.documentElement.style.setProperty("--warning-h", `${strip.offsetHeight}px`)).observe(strip);
  }
  strip.textContent = text;
}

// The strip during a walk: the stale-data warning, then the walk's own notice: the library stopped answering
// and its source answer can no longer be kept, or Seerr does not answer. A response with no notice takes it down.
function showFallback(fallback) {
  showWarning([staleWarning, fallback].filter(Boolean).join(" "));
}

// The setup note, when there is something to say and it has not been said this visit; a note with no way in
// is said every time, since there is nowhere else to go. Resolves to true when the note took the screen.
async function saidSetup(again) {
  const res = await get("/api/setup");
  if (!res.ok) {
    console.warn("the setup note could not be read; going on without it", res.data);
    return false;
  }
  staleWarning = res.data.warning;
  showWarning(staleWarning);
  if (!res.data.lines.length || (setupSeen && res.data.go_on)) return false;
  await setupNote(res.data, again);
  return true;
}

// The wall's picture source, asked for beside the door and the first pool, so the first wall is laid from
// it. It is asked for once per visit; a failed answer leaves every picture on Matinee's own image route
// and is asked again at the next boot.
let picturesKnown = false;
async function askPictures() {
  if (picturesKnown) return;
  const res = await get("/api/pictures");
  if (!res.ok) {
    console.warn("the image source could not be read; every picture comes from Matinee's server", res.data);
    return;
  }
  wall.usePictures(posterPaths(res.data), res.data.source === "tmdb");
  picturesKnown = true;
}

// The box office. `opts.screen` "new" opens it on a new profile.
// When a door word is set and this device has not given it, the locked door stands in its place, and
// nothing about the films is asked for until the word is right.
async function boot(opts = {}) {
  const [gate] = await Promise.all([get("/api/admission"), marqueeReady]);
  if (!gate.ok) return problem(gate.data, () => boot(opts));
  if (!gate.data.admitted) return lockedDoor(gate.data.greeting);
  if (await saidSetup(() => boot(opts))) return undefined;
  loadQuips();
  const [door, first] = await Promise.all([get("/api/door"), post("/api/first", { viewer: {} }), askPictures()]);
  if (first.ok) wall.show(first.data.pool);
  return frontDoor(door, opts);
}

// The front door, its wall already shown. `opts.marquee` is the locked door's, kept in place.
async function frontDoor(door, opts) {
  if (!door.ok) return problem(door.data, () => boot(opts));
  avatarsOffered = door.data.avatars;
  learnOffers(door.data);
  stage.classList.remove("revealed");
  stage.classList.add("at-door");
  return new Door({ stage, onEnter: enter }).open({ door: door.data, ...opts });
}

function lockedDoor(greeting) {
  wall.clear();
  stage.classList.remove("revealed");
  stage.classList.add("at-door", "at-locked");
  const marquee = buildMarquee(null);
  clear(stage).append(h("h1", { class: "sr-only" }, "Matinee: a private screening"), marquee);
  // The right word: the front door's films are asked for at once and the poster wall is laid behind the
  // locked door while it swings, so the wipe opens onto a drawn wall.
  const onAdmitted = async (locked) => {
    loadQuips();
    const ready = Promise.all([get("/api/door"), post("/api/first", { viewer: {} }), askPictures()]).then(async ([door, first]) => {
      if (first.ok) {
        wall.show(first.data.pool);
        await wall.whenStill();
        if (!prefersLessMotion()) await wait(WALL_FADE_MS);
      }
      return door;
    });
    const door = await locked.open(ready, (res) => res.ok && showCount(marquee, res.data.now_showing));
    stage.classList.remove("at-locked");
    if (await saidSetup(() => boot())) return undefined;
    return frontDoor(door, { marquee });
  };
  return new LockedDoor({ stage, marquee, greeting, onAdmitted }).show();
}

// Going in: the start is asked for at once, while the door's name flies to the wordmark's place, and the
// first question types once it has landed.
async function enter({ viewer, name, avatar, profileTopics, door }) {
  Object.assign(visit, { viewer, name, avatar, profileTopics, run: [], runKey: runKey() });
  const request = post("/api/first", { viewer });
  landing = door;
  await door.leave([nameTag()].filter(Boolean));
  await start({ request, keep: true });
  await welcomeIfNew();
}

// Where a walk stands before any answer, from the start the server gave.
function freshWalk(first) {
  return {
    tree: null,
    answers: [],
    says: [],
    asks: [],
    rushed: false,
    firstSay: null,
    source: first.source ? null : "all",
    sourceSay: null,
    sourceAsk: first.source ? first.source.ask : null,
    doorAsk: null,
    sourceReply: "",
    seen: [],
    profileTopics: first.checked, // the server's word on whether picks are checked, read afresh every start
  };
}

// "Start over" and the wordmark: a new run, which forgets the films shown, from the walk's first screen.
function startOver() {
  Object.assign(visit, { run: [], runKey: runKey() });
  return start();
}

// A walk's first screen: the source question while it is asked, else the doors. No answer carries over from
// the last walk. `request` is the start already asked for, if any; `keep` keeps the wall's posters behind a
// problem screen (a start after going in, and its retries).
async function start({ request = null, keep = false } = {}) {
  const res = await (request ?? post("/api/first", { viewer: visit.viewer }));
  if (!res.ok) return problem(res.data, () => start({ keep }), keep);
  Object.assign(visit, freshWalk(res.data));
  const [greeting] = res.data.lines;
  const name = res.data.name;
  const ack = name ? greeting.replace(/\.$/, `, ${name}.`) : greeting;
  if (!res.data.source) return doors(res, ack);
  showFirst(res);
  const options = res.data.source.options.map((o) => ({ say: o.say, go: () => chooseSource(o) }));
  await ask({ ack, question: res.data.source.ask, options, count: countText(visit.pool.length) });
}

// The wall and the doors' films behind a walk's first screens.
function showFirst(res) {
  showFallback(res.data.fallback);
  Object.assign(visit, { pool: res.data.pool, trees: res.data.options });
  stage.classList.remove("revealed");
  wall.show(visit.pool);
}

function chooseSource(option) {
  Object.assign(visit, { source: option.source, sourceSay: option.say, sourceReply: option.reply });
  doors();
}

// The doors, within the source answer and with its reply. `res` is the first screen already fetched, when the
// source question was not asked; `ack` its greeting.
async function doors(res = null, ack = visit.sourceReply) {
  Object.assign(visit, { tree: null, answers: [], says: [], asks: [], rushed: false, firstSay: null, seen: [] });
  const got = res ?? (await post("/api/first", { viewer: visit.viewer, source: visit.source }));
  if (!got.ok) return problem(got.data, start);
  showFirst(got);
  if (got.data.unsettled) return nothingLeft(got.data.unsettled);
  visit.doorAsk = got.data.lines[1];
  const options = got.data.options.map((o) => ({ say: o.say, go: () => chooseTree(o) }));
  await ask({ ack, question: got.data.lines[1], options, count: countText(visit.pool.length), many: true });
}

// A tailoring step in the theatre: the line, its explanation, the answers, then the actions; a step's credit stands in
// the foot band beside "About Matinee". A `plain` screen, with no answers, keeps the theatre's own centred column.
async function tailorScreen({ ack, ask, detail, answers, actions, credit = null, plain = false }) {
  const line = h("h1", { class: "line", "aria-live": "polite" });
  const later = [
    detail ? h("p", { class: "note tailor-detail", hidden: true }, detail) : null,
    h("div", { class: "tailor-answers", hidden: true }, answers),
    h("div", { class: "door-actions tailor-actions", hidden: true }, actions),
  ].filter(Boolean);
  const talk = h("section", { class: plain ? "talk tailor-talk plain" : "talk tailor-talk" }, line, later);
  clear(stage).append(topbar(nameTag()), talk, h("footer", { class: "bottombar" }, aboutLink(), credit ? h("p", { class: "credits" }, credit) : null));
  await typeLine(line, ack, ask);
  for (const node of later) node.hidden = false;
  stage.querySelector(".tailor-talk :is(input, button)")?.focus({ preventScroll: true });
}

// After the welcome's last step: "You're all set up.", then My profile, with the theatre at its first screen beneath,
// or the theatre's first screen.
function allSet() {
  const profile = h("button", { class: "action cream", type: "button" }, ALL_SET.profile);
  const watch = h("button", { class: "action gold", type: "button", onclick: () => start() }, ALL_SET.watch);
  profile.addEventListener("click", async () => {
    await start();
    myProfile(null, "tailor");
  });
  return tailorScreen({ ack: ALL_SET.ack, ask: ALL_SET.ask, answers: [], actions: [watch, profile], plain: true });
}

// "Show me": what is new, in Matinee's own voice on a wider screen (a phone takes it as a quieter paragraph), then the
// tailoring steps from the profile's settings as they stand, then "You're all set up."
function whatsNew() {
  const id = visit.viewer.profile_id;
  const steps = () => tailorSteps({ id, dtdd: offers.dtdd, credit: dtddSetting, show: tailorScreen, done: allSet });
  const go = h("button", { class: "action gold", type: "button", onclick: steps }, "Let's go");
  const [ack, said] = WHATS_NEW;
  const spoken = isPhone() ? { ask: "", detail: said } : { ask: said };
  return tailorScreen({ ack, ...spoken, answers: [], actions: [go], plain: true });
}

// The first time a profile made before My profile enters the theatre: the page dims but for the profile button, and
// a line beside it names what is new, with "Show me" and "Not now". Either marks the profile, so it shows once.
// Found once the profile's settings have arrived, on the page as it then stands; not over My profile or an open
// menu, and not after the viewer has gone on, so the welcome waits for the next visit.
async function welcomeIfNew() {
  const id = visit.viewer.profile_id;
  if (!id) return;
  const res = await get(`/api/profiles/${id}/settings`);
  if (!res.ok || res.data.welcomed || visit.viewer.profile_id !== id) return;
  const button = stage.querySelector(".topbar .viewer-button");
  const busy = profileOpen() || stage.querySelector(".viewer-menu:not([hidden])") || !stage.querySelector(".answers");
  if (!button || busy) return;
  const scrim = h("div", { class: "welcome-scrim" });
  const show = h("button", { class: "action gold", type: "button" }, "Show me");
  const later = h("button", { class: "action cream", type: "button" }, "Not now");
  const box = h("div", { class: "welcome", role: "dialog", "aria-modal": "true", "aria-labelledby": "welcome-line" }, h("p", { class: "welcome-line", id: "welcome-line" }, WELCOME), h("div", { class: "welcome-actions" }, show, later));
  // Everything but the line's box is out of reach while it stands; the top bar stands above the dimming, all but the
  // viewer's button faded, and the box hangs from the button.
  const lit = button.closest(".viewer");
  const bar = button.closest(".topbar");
  const away = [...[...stage.children].filter((n) => n !== bar), ...[...bar.children].filter((n) => n !== lit), button];
  for (const node of away) node.inert = true;
  bar.classList.add("lit");
  stage.append(scrim);
  lit.append(box);
  show.focus({ preventScroll: true });
  const finish = (then) => {
    for (const b of [show, later]) b.disabled = true;
    post(`/api/profiles/${id}/welcomed`).then((marked) => {
      if (!marked.ok) console.warn("the welcome could not be marked as seen; it may show again", marked.data);
    });
    scrim.remove();
    box.remove();
    bar.classList.remove("lit");
    for (const node of away) node.inert = false;
    then();
  };
  show.addEventListener("click", () => finish(whatsNew));
  later.addEventListener("click", () => finish(() => button.focus({ preventScroll: true })));
  box.addEventListener("keydown", (e) => {
    if (e.key === "Escape") later.click(); // Escape is "Not now"
  });
}

// The viewer's settings and hidden films leave no door: say how many films there would have been without them,
// and open My profile at the settings. Closing it asks for the doors afresh.
function nothingLeft(n) {
  const line = h("h1", { class: "line", "aria-live": "polite" });
  line.append(h("span", { class: "ack" }, `Your settings leave me nothing to pick. Without them, I'd have had ${n.toLocaleString("en")} ${n === 1 ? "film" : "films"} to choose from.`));
  const change = h("button", { class: "action gold", type: "button" }, "Change my settings");
  change.addEventListener("click", () => myProfile(change, "tailor", () => start()));
  clear(stage).append(topbar(nameTag()), h("section", { class: "talk" }, line, change), h("footer", { class: "bottombar" }, aboutLink()));
  change.focus({ preventScroll: true });
}

function chooseTree(option) {
  Object.assign(visit, { tree: option.tree, answers: [], says: [], asks: [], rushed: false, firstSay: option.say, seen: [] });
  step();
}

// Step 0 ("Start") is the walk's first screen; the source answer's step, when there is one, is the doors;
// the door's step is its first question; each step above that is the screen its answer led to.
function goTo(i) {
  if (i === 0) return start();
  const off = visit.sourceSay === null ? 0 : 1;
  if (i === off) return doors();
  return reask(i - 1 - off);
}

// Asks again the question that followed the first `kept` answers, forgetting that answer and every later one.
function reask(kept) {
  Object.assign(visit, forget(visit, kept));
  return step();
}

async function step() {
  const body = { tree: visit.tree, answers: visit.answers, viewer: visit.viewer, source: visit.source };
  const res = await post("/api/walk", body);
  if (!res.ok) return problem(res.data, start);
  showFallback(res.data.fallback);
  visit.pool = res.data.pool;
  const q = res.data.question;
  // The last answer brings the posters to the size they keep through the pick.
  wall.show(visit.pool, { resting: !q });
  if (!q) return pickNow(res.data.line, false, res.data.self_destruct);
  const picture = q.presentation === "pails" && q.options.every((o) => o.image);
  const options = q.options.map((o) => ({
    say: o.say,
    image: o.image,
    go: () => {
      visit.answers.push({ question: q.id, option: o.index });
      visit.says.push(o.say);
      visit.asks.push(q.ask);
      step();
    },
  }));
  const count = countText(visit.pool.length);
  await ask({ ack: res.data.line, question: q.ask, options, count, picture, footnote: q.footnote });
}

// The pick screen. The aside hangs from the top of the left column, so nothing re-centres as the film
// arrives; the poster settles beneath it, in the column's foot.
// On a phone the aside stands outside the showing, which scrolls on its own above it, so Matinee's words
// keep the foot while the poster and the details scroll.
function pickFrame() {
  const line = h("h1", { class: "line pick-line", "aria-live": "polite" });
  const aside = h("div", { class: "aside" }, line);
  const phone = isPhone();
  const left = h("div", { class: "pick-left" }, phone ? null : aside);
  const showing = h("section", { class: "showing" }, left);
  // DoesTheDogDie's credit, hidden until a line names one of its topics: at the foot bar's right end on a desktop,
  // centred in the foot band on a phone.
  const credit = dtddFoot();
  // The foot bar's row is kept from the start on a desktop, so nothing moves when its actions arrive.
  const bar = h("div", { class: "foot-bar" }, h("div"), h("div"), h("div", { class: "bar-right" }, phone ? null : credit));
  // The pick's foot holds its bar: "Start over" is in the Back panel, and the acknowledgements are on About.
  const foot = h("footer", { class: "bottombar" }, phone ? credit : bar);
  clear(stage).append(topbar(nameTag() || h("span")), showing, ...(phone ? [aside] : []), foot);
  const frame = { line, aside, left, showing, bar, credit };
  frame.panel = pickPanel(stage, frame, panelHistory);
  pickShowing = frame;
  holdPickEntry();
  return frame;
}

// The browser's back, and a phone's back gesture, on a pick. While a pick is on screen the page holds one history
// entry at its own address, as About does, and an open panel holds one more above it, pushed by the tap that opens
// it. Back from the panel's entry closes the panel alone; back from the pick's steps back one answer (way-back.js
// `stepBack`). Leaving a pick, or closing its panel, any other way takes its entries back off, so a later back never
// lands on a pick or panel that has gone. Back with About open over a pick closes About alone. A reload starts with
// none of them.
// NOTE: the page's own back is a task the browser runs later; a pick opened within that moment holds no entry.
const PICK_ENTRY = { matinee: "pick" };
const PANEL_ENTRY = { matinee: "panel" };
let pickShowing = null; // the frame of the last pick screen drawn
let ownBacks = 0; // backs the page takes itself, to drop its own entries

// A new pick screen holds the pick's entry: pushed after an answer, kept through "Show me another", and stepped down to
// from a panel's entry when a film is brought back from the panel. A panel closed by the tap that drew this pick has
// already asked for that step, which the browser has yet to take, so it is not asked for twice.
function holdPickEntry() {
  if (history.state?.matinee === PANEL_ENTRY.matinee) {
    if (ownBacks > 0) return;
    ownBacks++;
    history.back();
  } else if (history.state?.matinee !== PICK_ENTRY.matinee) {
    history.pushState(PICK_ENTRY, "");
  }
}

function dropPickEntry() {
  const depth = { [PICK_ENTRY.matinee]: 1, [PANEL_ENTRY.matinee]: 2 }[history.state?.matinee];
  if (!depth) return;
  ownBacks++;
  history.go(-depth);
}

const panelHistory = {
  opened: () => history.pushState(PANEL_ENTRY, ""),
  closed: () => {
    if (history.state?.matinee !== PANEL_ENTRY.matinee) return;
    ownBacks++;
    history.back();
  },
};

function onBack(e) {
  if (ownBacks > 0) {
    ownBacks--;
    return;
  }
  const onPick = pickShowing?.showing.isConnected;
  if (e.state?.matinee === PICK_ENTRY.matinee) {
    // Back from the panel's entry closes the panel; back from About's leaves About to close itself; arriving on a
    // pick's entry with no pick on screen (a pick that failed under About) steps off it.
    if (!onPick) dropPickEntry();
    else pickShowing.panel.closedByBack();
    return;
  }
  if (!onPick) return;
  leaveTo(() => wayTo({ to: stepBack(visit) }, { source: start, doors: () => doors(), reask }));
}

window.addEventListener("popstate", onBack);
dropPickEntry(); // a reload, or arriving back at a page that held a pick

function hasTopics() {
  return visit.profileTopics;
}

// While the check runs the line says so, beneath the reply to the last answer when there is one, and the
// wall keeps drifting; nothing else on it moves.
function checking(frame, held) {
  if (!held) return typeLine(frame.line, CHECKING, "");
  return typeLine(frame.line, held, CHECKING, { shown: held.length });
}

const SEEN_MAX = 200; // PickIn.seen's max_length on the server

// The pick's answer, with the check said aloud while it runs when `aloud`. Once the answer is back the
// reply stands alone again, unless the check's reason is about to take its place.
async function checkedPick(request, frame, lines, aloud) {
  if (aloud) await checking(frame, lines.gold);
  const res = await request;
  if (aloud && res.ok && lines.gold && !res.data.swapped && frame.showing.isConnected) {
    await typeLine(frame.line, lines.gold, "", { shown: lines.gold.length });
  }
  return res;
}

// The question's words fade out as a pick begins from a question screen.
async function fadeTalk() {
  const talk = stage.querySelector(".talk");
  if (!talk || prefersLessMotion()) return;
  talk.classList.add("hushed");
  await wait(TALK_FADE_MS);
}

// The lines for a pick, from the set of the category the first answer led to. After "Show me another" a
// nope line and a reveal line are dealt together under the combined cap; otherwise a reveal line alone.
// `beneath(fixed)` redeals only the reveal line to fit beneath `fixed`, the check's explanation.
// The pick's lines. `gold` is the line that stays through the hunt, with the reveal line dealt to fit
// beneath it: the nope line after "Show me another", else `held`, the reply to the last answer.
function pickLines(again, held = "") {
  if (!quips) return { nope: null, gold: held || null, reveal: "", beneath: () => "" };
  const revealSet = setFor(quips, visit.tree, "reveal");
  const cap = quips.caps.pair;
  const first = { nope: null, reveal: held ? dealBeneath(deck, held, revealSet, cap) : deck.deal(revealSet) };
  const pair = again ? dealPair(deck, setFor(quips, visit.tree, "nope"), revealSet, cap) : first;
  const beneath = (fixed) => {
    deck.remaining(revealSet).push(pair.reveal);
    return dealBeneath(deck, fixed, revealSet, cap);
  };
  return { ...pair, gold: pair.nope || held || null, beneath };
}

// The gold line for "Just pick one!": a rush line from the set of the category the first answer led to,
// standing where a reply would; "" when the lines could not be read.
function rushLine() {
  return quips ? deck.deal(setFor(quips, visit.tree, "rush")) : "";
}

// What the screen gives up as a pick begins: a question's words fade out, or, on "Show me another", the
// resting poster goes back to its cell on the wall.
async function clearForPick(posterBack) {
  if (posterBack) wall.putBack(stage.querySelector(".slot-poster"));
  else await fadeTalk();
}

// Asks the server for a pick from the answers so far, leaving out films already seen.
function requestPick() {
  const seen = visit.seen.slice(-SEEN_MAX); // the server takes at most SEEN_MAX; the oldest may come round again
  return post("/api/pick", { tree: visit.tree, answers: visit.answers, viewer: visit.viewer, seen, source: visit.source });
}

// Opens the pick screen and types a line in gold: after "Show me another" the nope line, which stays
// through the wait and the hunt, or else `opening`, the reply to the last answer. Resolves to the frame
// and the time until which a reply should stay whole before the hunt fades it (0 when none fades).
async function openPick(opening, nope) {
  stage.classList.remove("revealed");
  const frame = pickFrame();
  const gold = nope || opening;
  if (!gold) return { frame, readUntil: 0 };
  await typeLine(frame.line, gold, "");
  return { frame, readUntil: nope ? 0 : performance.now() + READ_MS };
}

// Every film the pick showed or the check turned away is seen, so "Show me another" never draws it again.
function markSeen(data) {
  if (data.film) visit.seen.push(data.film.tmdb);
  visit.seen.push(...data.turned_away);
}

// A fuse on the reply typed in `frame`, when the last answer self-destructs after `destruct` seconds; it
// goes out once the viewer leaves the pick. Otherwise null.
function fuseOn(frame, reply, destruct, round) {
  if (!destruct || !reply) return null;
  return lightFuse(frame.line, destruct, () => frame.showing.isConnected && wall.round === round);
}

// Whether the check's line types: on a pick that is not "Show me another", with no fuse lit.
function checksAloud(posterBack, fuse) {
  return hasTopics() && !posterBack && !fuse;
}

// `again` is "Show me another" or "Roll again": a nope line types in gold. `posterBack` is "Show me another":
// the resting poster goes back to the wall while the next film is fetched, and the check's line does not type.
// `destruct` (seconds) lights a fuse on the reply: it counts down and burns away on its own clock, and the
// check's line does not type over it.
async function pickNow(opening = "", again = false, destruct = null, posterBack = again, undo = null) {
  const round = wall.round;
  // The pick is asked for first, so the check and the fetch run while the words fade and the line types.
  const request = requestPick();
  // A reply that self-destructs owns the line; any other reply stays through the hunt.
  const lines = pickLines(again, destruct ? "" : opening);
  await clearForPick(posterBack);
  const { frame, readUntil } = await openPick(opening, lines.nope);
  standUndo(frame, undo);
  const fuse = fuseOn(frame, opening, destruct, round);
  // The check's line types only on a checked pick that is not "Show me another", and never over a fuse.
  const res = await checkedPick(request, frame, lines, checksAloud(posterBack, fuse));
  // The viewer took a way back out while the pick was fetched.
  if (!frame.showing.isConnected || wall.round !== round) return undefined;
  if (!res.ok) return problem(res.data, start);
  showFallback(res.data.fallback);
  markSeen(res.data);
  return showPick({
    stage,
    wall,
    result: res.data,
    frame,
    readUntil,
    lines,
    fuse,
    actions: pickActions(),
    door: visit.tree,
    walk: walkOf(visit),
  });
}

// One answer in the Back panel: its question, the answer beneath in quiet text. A tap asks that question again.
function answerRow(row) {
  const go = () => wayTo(row, { source: start, doors: () => doors(), reask });
  return h(
    "button",
    { class: "panel-row answer-row", type: "button", onclick: () => leaveTo(go) },
    h("span", { class: "row-ask" }, sentenceCase(row.ask)),
    h("span", { class: "row-say" }, sentenceCase(row.say)),
  );
}

// One film the run has shown, in the Back panel: its small poster, title and year. A tap brings it back as the pick;
// the film showing now is marked as such and does nothing.
function filmRow(shown) {
  const { film } = shown;
  // Fetched as the wall fetches its posters (crossorigin before src), so the two never share a cached copy that one
  // of them refuses.
  const thumb = h("img", { class: "thumb", crossorigin: "anonymous", src: wall.posterUrl(film.tmdb, "xs"), alt: "", loading: "lazy", decoding: "async" });
  thumb.addEventListener("error", () => thumb.setAttribute("src", "/static/blank.svg"), { once: true }); // a plain card
  const words = [h("span", { class: "row-title" }, film.title), film.year ? h("span", { class: "row-year" }, ` ${film.year}`) : null];
  if (shown.now) {
    return h("div", { class: "panel-row film-row now", "aria-current": "true" }, thumb, h("span", {}, words, h("span", { class: "row-now" }, "Showing now")));
  }
  return h("button", { class: "panel-row film-row", type: "button", onclick: () => bringBack(shown) }, thumb, h("span", {}, words));
}

// What the Back panel holds: the viewer's answers, each a way back to its question, then, under a rule, every film
// this run has shown, newest first, three at a time and scrolling past them, then "Start over" at its foot.
function backPanel() {
  const rows = answerRows(visit).map(answerRow);
  const films = newestFirst(visit.run, stage.classList.contains("revealed")); // a film rests on screen
  const shown = films.length
    ? [h("p", { class: rows.length ? "panel-section apart" : "panel-section" }, `Shown this run · ${films.length} ${films.length === 1 ? "film" : "films"}`), h("div", { class: "films" }, films.map(filmRow))]
    : [];
  const again = h("button", { class: "action cream", type: "button", onclick: () => leaveTo(startOver) }, "Start over");
  return [rows.length ? h("p", { class: "panel-section" }, "Change an answer") : null, rows, shown, h("div", { class: "panel-foot" }, again)];
}

// Keeps a film shown on screen in the profile's history, under the run its walk names. A failure costs only the
// history line, so it is logged and the pick goes on.
function keepShown(shown) {
  const run = shown.walk.run;
  const body = shownBody(shown);
  if (!run || !body) return;
  post(`/api/profiles/${shown.walk.profileId}/runs/${run}/films`, body).then((res) => {
    if (!res.ok) console.warn("a film shown could not be kept in the history", res.data);
  });
}

// The household's shared ratings of a film, the viewer's own rating of it, and the viewer, for the pick's line and
// reading panel. A failure costs only the line: none is shown.
async function household(tmdb) {
  const id = visit.viewer.profile_id;
  const [shared, mine] = await Promise.all([get(`/api/profiles/${id}/shared/${tmdb}`), get(`/api/profiles/${id}/ratings`)]);
  if (!shared.ok || !mine.ok) console.warn("the household's ratings could not be read; the pick shows none", shared.data, mine.data);
  return {
    shared: shared.ok ? shared.data : [],
    mine: mine.ok ? (mine.data.find((r) => r.tmdb === tmdb) ?? null) : null,
    viewer: { name: visit.name, avatar: visit.avatar },
  };
}

// A hide's "Undo", in the foot while the next pick hunts: in the foot bar's left on a desktop, in the foot on a phone.
// None when no hide asked for it.
function standUndo(frame, undo) {
  if (!undo) return;
  frame.undo = undoLink(undo);
  const home = isPhone() ? stage.querySelector(".bottombar") : frame.bar.firstElementChild;
  home.append(frame.undo.node);
  frame.undo.node.focus({ preventScroll: true }); // the length chosen has gone with its panel; the way back takes the focus
}

// "Hide film": hides the film from this profile's picks for `length`, marks it in its run, and rolls again as "Not
// that one" does, with "Undo" in the foot while the next pick hunts. Resolves to the server's answer, which the
// panel shows when it is a refusal.
async function hideAndRoll(film, length) {
  const id = visit.viewer.profile_id;
  const shown = visit.run.find((s) => s.film.tmdb === film.tmdb);
  const run = shown?.walk.run ?? visit.runKey;
  const res = await put(`/api/profiles/${id}/hidden/${film.tmdb}`, { length, run });
  if (!res.ok) return res;
  pickShowing?.panel.closedByBack(); // the pick's own entry takes the panel's place, so no step of history is taken
  lockStage();
  pickNow("", true, null, true, () => undoHide(film, shown, run));
  return res;
}

// "Undo" of a hide: the film comes back to this profile's picks, gets back the mark its run held before, and shows
// again as the pick, as it was first shown.
async function undoHide(film, shown, run) {
  const res = await del(`/api/profiles/${visit.viewer.profile_id}/hidden/${film.tmdb}?run=${encodeURIComponent(run)}`);
  if (!res.ok) {
    console.warn("the hide could not be undone; the film stays hidden until brought back from My profile", res.data);
    return;
  }
  if (!shown) return;
  wall.endPick(); // the roll stops where it is; the film comes back on the pick's own history entry
  bringBack(shown);
}

// What the pick screen's controls do.
function pickActions() {
  return {
    notThatOne: () => {
      lockStage();
      pickNow("", true);
    },
    rollAgain: () => {
      lockStage();
      pickNow("", true, null, false);
    },
    showPicked: (held) => {
      lockStage();
      showPicked(held);
    },
    startOver: () => leaveTo(startOver),
    backPanel,
    remember: (shown) => {
      visit.run = remember(visit.run, shown);
      keepShown(shown);
    },
    failed: (data) => problem(data, start),
    household,
    hide: hideAndRoll,
    noteLink: (film, panel, walk) => noteLink({ walk, film, trees: visit.trees, panel }),
  };
}

// "Just show me what you picked", after three films in a row tripped the list: the last of them, from the
// reply already held, shown as a pick with its trip named. No new pick is asked for and nothing of
// DoesTheDogDie; the film's details and pictures load as on any pick. "Here's what I picked." types at the tap and stays through the hunt; the trip types beneath
// it as the poster grows.
async function showPicked(held) {
  const round = wall.round;
  const [gold, trip] = held.last.lines;
  const lines = { nope: null, gold, reveal: trip, beneath: () => trip };
  const { frame, readUntil } = await openPick(gold, null);
  if (!frame.showing.isConnected || wall.round !== round) return undefined;
  const result = { ...held, film: held.last.film, swapped: null, tired: null, turned_away: [] };
  return showPick({ stage, wall, result, frame, readUntil, lines, fuse: null, actions: pickActions(), door: visit.tree, walk: walkOf(visit) });
}

// A film this run has shown, brought back from the Back panel as the pick: no new pick is asked for and no hunt runs,
// the wall cutting straight to its poster. It shows as it was first shown, with its line, its content note and the door and walk it was drawn under; its details, rank,
// tags and pictures load as on any pick, and nothing of DoesTheDogDie is asked for.
async function bringBack(shown) {
  lockStage();
  await clearForPick(Boolean(stage.querySelector(".slot-poster")));
  const round = wall.round;
  const { result, lines, door, walk } = asPick(shown);
  const { frame } = await openPick(lines.gold, null);
  if (!frame.showing.isConnected || wall.round !== round) return undefined;
  return showPick({ stage, wall, result, frame, lines, fuse: null, actions: pickActions(), door, walk, quick: true });
}

boot();
