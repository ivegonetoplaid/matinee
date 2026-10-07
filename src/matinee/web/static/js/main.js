// Matinee's page: the box office, then the questions on the poster wall, then the pick.

import { del, get, post, put } from "./api.js";
import { noteLink } from "./note.js";
import { aboutLink, credits } from "./credits.js";
import { Door, buildMarquee, showCount } from "./door.js";
import { LockedDoor, WALL_FADE_MS } from "./locked.js";
import { clear, h, isPhone, prefersLessMotion, sentenceCase, wait } from "./dom.js";
import { showPick } from "./pick.js";
import { posterPaths } from "./pictures.js";
import { Deck, dealBeneath, dealPair, setFor } from "./quips.js";
import { lightFuse } from "./fuse.js";
import { typeLine } from "./type.js";
import { Wall } from "./wall.js";
import { viewerTag } from "./viewer.js";
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
  rushed: false, // "Just pick one!" ended the questions early
  firstSay: null,
  source: null, // the source question's answer, asked at the start of every walk; "all" when it is not asked
  sourceSay: null,
  sourceReply: "", // Matinee's gold line on the doors within the source
  seen: [],
  pool: [],
  trees: [],
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

// Leaving a pick by a way back out (a trail answer, the name tag, "Start over") ends it at the tap:
// the hunt stops where it is, and the pick changes nothing further while the next screen loads.
function leaveTo(next) {
  lockStage();
  wall.endPick();
  next();
}

// The wordmark is a link that does what "Start over" does: back to the first question, as the same viewer.
// Without a viewer (a problem before going in) it goes back to the door.
function wordmark() {
  const go = (e) => {
    e.preventDefault();
    leaveTo(visit.viewer.profile_id ? start : boot);
  };
  return h("a", { class: "wordmark", href: "/", onclick: go }, "Matinee");
}

// The theatre's top bar, the wordmark at its left. A name that flew in from the door gives way to it, and
// the door, faded since going in, is no longer the stage's.
function topbar(...rest) {
  const bar = h("header", { class: "topbar" }, wordmark(), ...rest);
  landing?.settle();
  landing = null;
  stage.classList.remove("at-door", "leaving");
  return bar;
}

// The viewer at the right of the top bar: their mark and name, which open the profile menu.
function nameTag() {
  if (!visit.name) return null;
  const leave = (opts) => leaveTo(() => boot(opts));
  const id = visit.viewer.profile_id;
  return viewerTag({ name: visit.name, avatar: visit.avatar }, avatarsOffered, {
    editList: offers.dtdd ? () => leave({ screen: "list", profileId: id }) : null,
    switchProfiles: () => leave({}),
    deleteProfile: async () => {
      const res = await del(`/api/profiles/${id}`);
      if (res.ok) leave({ said: [`${res.data.name}'s seat is empty.`, "Who's watching?"] });
      return res;
    },
    saveAvatar: async (avatar) => {
      const res = await put(`/api/profiles/${id}/avatar`, { avatar });
      if (res.ok) visit.avatar = res.data.avatar;
      return res;
    },
  });
}

// The way here: "Start", the source answer when the source question was asked, the door, then each answer.
function crumbs() {
  return ["Start", visit.sourceSay, visit.firstSay, ...visit.says].filter((say) => say !== null);
}

// The way here, at the foot of the screen. A crumb takes the viewer to the screen it led to; the crumb for
// the screen they are on, `here`, is plain text. "Start" and the door keep their full words where the trail
// must fit one line; the source answer and the answers shorten first.
function trail(here) {
  if (!visit.tree && !visit.sourceSay) return null;
  const door = visit.sourceSay === null ? 1 : 2;
  const items = crumbs().map((say, i) => {
    const words = sentenceCase(say);
    const crumb =
      i === here
        ? h("span", { class: "crumb here", "aria-current": "page", title: words }, words)
        : h("button", { class: "crumb", type: "button", title: words, onclick: () => leaveTo(() => goTo(i)) }, words);
    return h("li", i === 0 || i === door ? { class: "keep" } : {}, crumb);
  });
  return h("nav", { class: "trail", "aria-label": "The way here" }, h("ol", {}, items));
}

// Where "Back" leads, as a crumb: the screen before the one showing, whose crumb is `here` (null on a pick
// "Just pick one!" ended early, which leads back to the question it left). None where that is the walk's
// first screen, which "Start over" reaches.
function backTo(here) {
  const target = here === null ? crumbs().length - 1 : here - 1;
  return target > 0 ? target : null;
}

// A phone's way back from a question screen, in the trail's place: "Back", where there is a screen before
// this one other than the first, and "Start over". None on the walk's first screen.
function wayBack(here) {
  if (!visit.tree && !visit.sourceSay) return null;
  const target = backTo(here);
  const back =
    target === null
      ? null
      : h("button", { class: "action cream", type: "button", onclick: () => leaveTo(() => goTo(target)) }, "Back");
  const again = h("button", { class: "action cream", type: "button", onclick: () => leaveTo(start) }, "Start over");
  return h("nav", { class: "way-back", "aria-label": "Way back" }, back, again);
}

// The trail's last crumb, which led to the screen showing now; on a pick "Just pick one!" ended early,
// the last crumb led to a question, so none.
function lastCrumb(onPick) {
  return onPick && visit.rushed ? null : crumbs().length - 1;
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
    h("div", { class: "bottombar" }, trail(lastCrumb(false)), wayBack(lastCrumb(false)), h("span"), credits()),
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
  if (!keep) wall.clear();
  const line = h("h1", { class: "line done" });
  line.append(h("span", { class: "ack" }, data.message || "Something went wrong."));
  clear(stage).append(
    topbar(),
    h(
      "section",
      { class: "talk" },
      line,
      h("button", { class: "action cream", type: "button", onclick: again }, "Try again"),
    ),
    h("footer", { class: "bottombar" }, aboutLink(), credits()),
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
  clear(stage).append(topbar(), h("section", { class: "talk setup" }, line, said, action), h("footer", { class: "bottombar" }, aboutLink(), credits()));
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

// The strip during a walk: the stale-data warning, then the walk's own notice when the library stopped
// answering and its source answer can no longer be kept. A response with no notice takes it down again.
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

// The box office. `opts.screen` opens it on a new profile ("new") or the viewer's list ("list").
// When a door word is set and this device has not given it, the locked door stands in its place, and
// nothing about the films is asked for until the word is right.
async function boot(opts = {}) {
  const gate = await get("/api/admission");
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
  Object.assign(visit, { viewer, name, avatar, profileTopics });
  const request = post("/api/first", { viewer });
  landing = door;
  await door.leave([nameTag()].filter(Boolean));
  await start({ request, keep: true });
}

// A walk's first screen: the source question while it is asked, else the doors. No answer carries over from
// the last walk. `request` is the start already asked for, if any; `keep` keeps the wall's posters behind a
// problem screen (a start after going in, and its retries).
async function start({ request = null, keep = false } = {}) {
  const res = await (request ?? post("/api/first", { viewer: visit.viewer }));
  if (!res.ok) return problem(res.data, () => start({ keep }), keep);
  Object.assign(visit, {
    tree: null,
    answers: [],
    says: [],
    rushed: false,
    firstSay: null,
    source: res.data.source ? null : "all",
    sourceSay: null,
    sourceReply: "",
    seen: [],
    profileTopics: res.data.checked, // the server's word on whether picks are checked, read afresh every start
  });
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
  Object.assign(visit, { tree: null, answers: [], says: [], rushed: false, firstSay: null, seen: [] });
  const got = res ?? (await post("/api/first", { viewer: visit.viewer, source: visit.source }));
  if (!got.ok) return problem(got.data, start);
  showFirst(got);
  const options = got.data.options.map((o) => ({ say: o.say, go: () => chooseTree(o) }));
  await ask({ ack, question: got.data.lines[1], options, count: countText(visit.pool.length), many: true });
}

function chooseTree(option) {
  Object.assign(visit, { tree: option.tree, answers: [], says: [], rushed: false, firstSay: option.say, seen: [] });
  step();
}

// Crumb 0 ("Start") is the walk's first screen; the source answer's crumb, when there is one, is the doors;
// the door's crumb is its first question; each crumb above that is the screen its answer led to.
function goTo(i) {
  if (i === 0) return start();
  const off = visit.sourceSay === null ? 0 : 1;
  if (i === off) return doors();
  visit.answers = visit.answers.slice(0, i - 1 - off);
  visit.says = visit.says.slice(0, i - 1 - off);
  visit.rushed = false;
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
  const foot = h("footer", { class: "bottombar" }, trail(lastCrumb(true)), h("span"), credits({ dtdd: offers.dtdd }));
  clear(stage).append(topbar(nameTag() || h("span")), showing, ...(phone ? [aside] : []), foot);
  return { line, aside, left, showing, credit: foot.querySelector(".dtdd-credit") };
}

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

// The lines for a pick, from the set of the category the first answer led to. After "Not that one" a
// nope line and a reveal line are dealt together under the combined cap; otherwise a reveal line alone.
// `beneath(fixed)` redeals only the reveal line to fit beneath `fixed`, the check's explanation.
// The pick's lines. `gold` is the line that stays through the hunt, with the reveal line dealt to fit
// beneath it: the nope line after "Not that one", else `held`, the reply to the last answer.
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

// What the screen gives up as a pick begins: a question's words fade out, or, on "Not that one", the
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

// Opens the pick screen and types a line in gold: after "Not that one" the nope line, which stays
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

// Every film the pick showed or the check turned away is seen, so "Not that one" never draws it again.
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

// Whether the check's line types: on a pick that is not "Not that one", with no fuse lit.
function checksAloud(posterBack, fuse) {
  return hasTopics() && !posterBack && !fuse;
}

// `again` is "Not that one" or "Roll again": a nope line types in gold. `posterBack` is "Not that one":
// the resting poster goes back to the wall while the next film is fetched, and the check's line does not type.
// `destruct` (seconds) lights a fuse on the reply: it counts down and burns away on its own clock, and the
// check's line does not type over it.
async function pickNow(opening = "", again = false, destruct = null, posterBack = again) {
  const round = wall.round;
  // The pick is asked for first, so the check and the fetch run while the words fade and the line types.
  const request = requestPick();
  // A reply that self-destructs owns the line; any other reply stays through the hunt.
  const lines = pickLines(again, destruct ? "" : opening);
  await clearForPick(posterBack);
  const { frame, readUntil } = await openPick(opening, lines.nope);
  const fuse = fuseOn(frame, opening, destruct, round);
  // The check's line types only on a checked pick that is not "Not that one", and never over a fuse.
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
  });
}

// A phone pick's "Back", to the question the last answer was given on; null where that is the walk's first
// screen.
function backAction() {
  const target = backTo(lastCrumb(true));
  return target === null ? null : () => leaveTo(() => goTo(target));
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
    startOver: () => leaveTo(start),
    back: backAction(),
    failed: (data) => problem(data, start),
    noteLink: (film) => noteLink({ visit, film, trees: visit.trees }),
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
  return showPick({ stage, wall, result, frame, readUntil, lines, fuse: null, actions: pickActions() });
}

boot();
