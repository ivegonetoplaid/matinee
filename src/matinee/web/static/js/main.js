// Matinee's page: the box office, then the questions on the poster wall, then the pick.

import { get, post } from "./api.js";
import { correctionLink } from "./correct.js";
import { credits } from "./credits.js";
import { Door } from "./door.js";
import { clear, h, isPhone, prefersLessMotion, sentenceCase, wait } from "./dom.js";
import { showPick } from "./pick.js";
import { Deck, dealBeneath, dealPair, setFor } from "./quips.js";
import { lightFuse } from "./fuse.js";
import { typeLine } from "./type.js";
import { Wall } from "./wall.js";

const stage = document.getElementById("stage");
const wall = new Wall(document.getElementById("wall"));

// Where this visit stands. The viewer is a held profile or this visit's own exclusions.
const visit = {
  viewer: {},
  name: null,
  profileTopics: false,
  tree: null,
  answers: [],
  says: [], // what the viewer answered, one per entry in answers
  rushed: false, // "Just pick one!" ended the questions early
  firstSay: null,
  seen: [],
  pool: [],
  trees: [],
};

const CHECKING = "One moment. Let me check this one against your list.";

function countText(n, first) {
  const films = `${n.toLocaleString("en")} ${n === 1 ? "film" : "films"}`;
  return first ? `${films} in the running` : `${films} still in the running`;
}

// The pick's lines, fetched once per page; null until they arrive, or when they could not be read.
let quips = null;
const deck = new Deck(); // one per visit: no line repeats until its set has run out
get("/api/quips").then((res) => {
  if (res.ok) quips = res.data;
  else console.warn("the pick's lines could not be read; picks show no line", res.data);
});

// The door whose name flew in on going in; its name stands at the wordmark's place until the theatre's own
// wordmark takes over.
let landing = null;

const TALK_FADE_MS = 350; // the question's words fade out as a pick begins
const READ_MS = 1000; // Matinee's reply to the last answer stays whole this long before the hunt fades it

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

// The theatre's top bar, the wordmark at its left. A name that flew in from the door gives way to it, and
// the door, faded since going in, is no longer the stage's.
function topbar(...rest) {
  const bar = h("header", { class: "topbar" }, h("div", { class: "wordmark" }, "Matinee"), ...rest);
  landing?.settle();
  landing = null;
  stage.classList.remove("at-door", "leaving");
  return bar;
}

// The profile's name at the top of the wall, with "Edit my list" and "Not <name>?".
function nameTag() {
  if (!visit.name) return null;
  const leave = (opts) => leaveTo(() => boot(opts));
  return h(
    "div",
    { class: "nametag" },
    h("span", { class: "nametag-name" }, visit.name),
    h("button", { class: "link-button", type: "button", onclick: () => leave({ screen: "list", profileId: visit.viewer.profile_id }) }, "Edit my list"),
    h(
      "button",
      {
        class: "link-button",
        type: "button",
        onclick: () => leave({ screen: "known" }),
      },
      `Not ${visit.name}?`,
    ),
  );
}

// The way here, at the foot of the screen: "Start", the door, then each answer so far. A crumb takes the
// viewer to the screen it led to; the crumb for the screen they are on, `here`, is plain text.
function trail(here) {
  if (!visit.tree) return null;
  const crumbs = ["Start", visit.firstSay, ...visit.says].map((say, i) => {
    const words = sentenceCase(say);
    const crumb =
      i === here
        ? h("span", { class: "crumb here", "aria-current": "page", title: words }, words)
        : h("button", { class: "crumb", type: "button", title: words, onclick: () => leaveTo(() => goTo(i)) }, words);
    return h("li", {}, crumb);
  });
  return h("nav", { class: "trail", "aria-label": "The way here" }, h("ol", {}, crumbs));
}

// The trail's last crumb, which led to the screen showing now; on a pick "Just pick one!" ended early,
// the last crumb led to a question, so none.
function lastCrumb(onPick) {
  return onPick && visit.rushed ? null : visit.says.length + 1;
}

// A question screen. "Just pick one!" stands last, beneath the answers and any footnote, and shows with them.
function frame({ count, footnote }) {
  const line = h("h1", { class: "line", "aria-live": "polite" });
  const answers = h("div", { class: "answers", role: "group", "aria-label": "Your answers", hidden: true });
  const note = footnote ? h("p", { class: "footnote", hidden: true }, footnote) : null;
  const pick = h(
    "button",
    {
      class: "pill gold just-pick",
      type: "button",
      hidden: true,
      onclick: () => {
        lockStage();
        visit.rushed = true;
        pickNow();
      },
    },
    "Just pick one!",
  );
  clear(stage).append(
    topbar(nameTag(), h("div", { class: "count" }, count)),
    h("section", { class: "talk" }, line, answers, note, pick),
    h("div", { class: "bottombar" }, trail(lastCrumb(false)), h("span"), credits()),
  );
  return { line, answers, note, pick };
}

// A picture question (the gore pails) shows each answer as its image, with the answer's words beneath it.
function answerButton(o, picture) {
  const onclick = () => {
    lockStage();
    o.go();
  };
  if (!picture) return h("button", { class: "answer", type: "button", onclick }, sentenceCase(o.say));
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
      h("div", { class: "answers" }, h("button", { class: "answer", type: "button", onclick: again }, "Try again")),
    ),
  );
}

// The box office. `opts.screen` opens it on the name lookup ("known") or the viewer's list ("list").
async function boot(opts = {}) {
  const [door, first] = await Promise.all([get("/api/door"), post("/api/first", { viewer: {} })]);
  if (!door.ok) return problem(door.data, () => boot(opts));
  stage.classList.remove("revealed");
  stage.classList.add("at-door");
  if (first.ok) wall.show(first.data.pool);
  await new Door({ stage, onEnter: enter }).open({ door: door.data, ...opts });
}

// Going in: the start is asked for at once, while the door's name flies to the wordmark's place, and the
// first question types once it has landed.
async function enter({ viewer, name, profileTopics, door }) {
  Object.assign(visit, { viewer, name, profileTopics });
  const request = post("/api/first", { viewer });
  landing = door;
  await door.leave([nameTag()].filter(Boolean));
  await start({ request, keep: true });
}

// The first question. `request` is the start already asked for, if any; `keep` keeps the wall's posters
// behind a problem screen (a start after going in, and its retries).
async function start({ request = null, keep = false } = {}) {
  const res = await (request ?? post("/api/first", { viewer: visit.viewer }));
  if (!res.ok) return problem(res.data, () => start({ keep }), keep);
  Object.assign(visit, {
    tree: null,
    answers: [],
    says: [],
    rushed: false,
    firstSay: null,
    seen: [],
    pool: res.data.pool,
    trees: res.data.options,
  });
  stage.classList.remove("revealed");
  wall.show(visit.pool);
  const [greeting, question] = res.data.lines;
  const name = res.data.name;
  const ack = name ? greeting.replace(/\.$/, `, ${name}.`) : greeting;
  const options = res.data.options.map((o) => ({ say: o.say, go: () => chooseTree(o) }));
  await ask({ ack, question, options, count: countText(visit.pool.length, true), many: true });
}

function chooseTree(option) {
  Object.assign(visit, { tree: option.tree, answers: [], says: [], rushed: false, firstSay: option.say, seen: [] });
  step();
}

// Crumb 0 ("Start") is the first question; crumb 1, the door, is its first question; crumb i above that
// is the screen answers[i - 2] led to.
function goTo(i) {
  if (i === 0) return start();
  visit.answers = visit.answers.slice(0, i - 1);
  visit.says = visit.says.slice(0, i - 1);
  visit.rushed = false;
  return step();
}

async function step() {
  const res = await post("/api/walk", { tree: visit.tree, answers: visit.answers, viewer: visit.viewer });
  if (!res.ok) return problem(res.data, start);
  visit.pool = res.data.pool;
  const q = res.data.question;
  // The last answer brings the posters to the size they keep through the pick.
  wall.show(visit.pool, { resting: !q });
  if (!q) return pickNow(res.data.line, false, false, res.data.self_destruct);
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
  const count = countText(visit.pool.length, false);
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
  const foot = h("footer", { class: "bottombar" }, trail(lastCrumb(true)), h("span"), credits());
  clear(stage).append(topbar(nameTag() || h("span")), showing, ...(phone ? [aside] : []), foot);
  return { line, aside, left, showing };
}

function hasTopics() {
  return Boolean(visit.viewer.profile_id ? visit.profileTopics : visit.viewer.topics?.length);
}

// While the check runs the line says so and the wall keeps drifting; nothing else on it moves.
function checking(frame) {
  return typeLine(frame.line, CHECKING, "");
}

const SEEN_MAX = 200; // PickIn.seen's max_length on the server

// `risk` is "Just pick one" after three films tripped the list: nothing is checked or turned away.
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
function pickLines(again) {
  if (!quips) return { nope: null, reveal: "", beneath: () => "" };
  const revealSet = setFor(quips, visit.tree, "reveal");
  const cap = quips.caps.pair;
  const pair = again ? dealPair(deck, setFor(quips, visit.tree, "nope"), revealSet, cap) : { nope: null, reveal: deck.deal(revealSet) };
  const beneath = (fixed) => {
    deck.remaining(revealSet).push(pair.reveal);
    return dealBeneath(deck, fixed, revealSet, cap);
  };
  return { ...pair, beneath };
}

// What the screen gives up as a pick begins: a question's words fade out, or, on "Not that one", the
// resting poster goes back to its cell on the wall.
async function clearForPick(again) {
  if (again) wall.putBack(stage.querySelector(".slot-poster"));
  else await fadeTalk();
}

// Asks the server for a pick from the answers so far, leaving out films already seen.
function requestPick(risk) {
  const seen = visit.seen.slice(-SEEN_MAX); // the server takes at most SEEN_MAX; the oldest may come round again
  return post("/api/pick", { tree: visit.tree, answers: visit.answers, viewer: visit.viewer, seen, risk });
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

// Whether the check's line types: on a checked pick that is not "Not that one" or rushed, with no fuse lit.
function checksAloud(risk, again, fuse) {
  return hasTopics() && !risk && !again && !fuse;
}

// `again` is "Not that one": the resting poster goes back to the wall while the next film is fetched,
// and the check's line does not type. `destruct` (seconds) lights a fuse on the reply: it counts down and
// burns away on its own clock, and the check's line does not type over it.
async function pickNow(opening = "", risk = false, again = false, destruct = null) {
  const round = wall.round;
  // The pick is asked for first, so the check and the fetch run while the words fade and the line types.
  const request = requestPick(risk);
  const lines = pickLines(again);
  await clearForPick(again);
  const { frame, readUntil } = await openPick(opening, lines.nope);
  const fuse = fuseOn(frame, opening, destruct, round);
  // The check's line types only on a checked pick that is not "Not that one", and never over a fuse.
  if (checksAloud(risk, again, fuse)) await checking(frame);
  const res = await request;
  // The viewer took a way back out while the pick was fetched.
  if (!frame.showing.isConnected || wall.round !== round) return undefined;
  if (!res.ok) return problem(res.data, start);
  markSeen(res.data);
  return showPick({
    stage,
    wall,
    result: res.data,
    frame,
    readUntil,
    lines,
    fuse,
    actions: {
      notThatOne: () => {
        lockStage();
        pickNow("", false, true);
      },
      rollAgain: () => {
        lockStage();
        pickNow();
      },
      justPick: () => {
        lockStage();
        pickNow("", true);
      },
      startOver: () => leaveTo(start),
      failed: (data) => problem(data, start),
      correction: (film) => correctionLink({ visit, film, trees: visit.trees }),
    },
  });
}

boot();
