// Matinee's page: the box office, then the questions on the poster wall, then the pick.

import { get, post } from "./api.js";
import { correctionLink } from "./correct.js";
import { credits } from "./credits.js";
import { Door } from "./door.js";
import { closeIris, openIris } from "./iris.js";
import { clear, h, sentenceCase } from "./dom.js";
import { showPick } from "./pick.js";
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
  treeSay: null,
  seen: [],
  pool: [],
  trees: [],
};

const CHECK_SHUFFLE_MS = 900;
const CHECKING = "One moment. Let me check this one against your list.";

function countText(n, first) {
  const films = `${n.toLocaleString("en")} ${n === 1 ? "film" : "films"}`;
  return first ? `${films} in the running` : `${films} still in the running`;
}

// The first action on a screen wins: every button on it is disabled at once, so an
// answer and "Just pick one!" can never both run.
function lockStage() {
  for (const button of stage.querySelectorAll("button")) button.disabled = true;
}

// The profile's name at the top of the wall, with "Edit my list" and "Not <name>?".
function nameTag() {
  if (!visit.name) return null;
  const leave = (opts) => {
    lockStage();
    boot(opts);
  };
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

// The answers so far, first to last. Each re-asks the question it answered.
function trail() {
  if (!visit.tree) return null;
  const crumbs = [visit.firstSay, ...visit.says].map((say, i) =>
    h(
      "li",
      {},
      h(
        "button",
        {
          class: "crumb",
          type: "button",
          title: sentenceCase(say),
          onclick: () => {
            lockStage();
            backTo(i);
          },
        },
        sentenceCase(say),
      ),
    ),
  );
  return h("nav", { class: "trail", "aria-label": "Your answers so far" }, h("ol", {}, crumbs));
}

// A question screen. "Just pick one!" stands last, beneath the answers, and shows with them.
function frame({ count }) {
  const line = h("h1", { class: "line", "aria-live": "polite" });
  const answers = h("div", { class: "answers", role: "group", "aria-label": "Your answers", hidden: true });
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
    h("header", { class: "topbar" }, h("div", { class: "wordmark" }, "Matinee"), nameTag(), h("div", { class: "count" }, count)),
    h("section", { class: "talk" }, trail(), line, answers, pick),
    h("div", { class: "bottombar" }, h("span"), credits()),
  );
  return { line, answers, pick };
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

// `reveal` runs once the screen is built and before the line types (the iris opening onto the wall).
async function ask({ ack, question, options, count, many = false, picture = false, reveal = null }) {
  const { line, answers, pick } = frame({ count });
  const buttons = options.map((o) => answerButton(o, picture));
  answers.classList.toggle("many", many);
  answers.classList.toggle("pails", picture);
  answers.append(...buttons);
  if (reveal) await reveal();
  await typeLine(line, ack, question);
  answers.hidden = false;
  pick.hidden = false;
}

function problem(data, again) {
  wall.clear();
  const line = h("h1", { class: "line done" });
  line.append(h("span", { class: "ack" }, data.message || "Something went wrong."));
  clear(stage).append(
    h("header", { class: "topbar" }, h("div", { class: "wordmark" }, "Matinee")),
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
  wall.root.classList.remove("spotlit", "revealed");
  stage.classList.add("at-door");
  wall.root.classList.add("at-door");
  if (first.ok) wall.show(first.data.pool, { shuffle: false });
  await new Door({ stage, onEnter: enter }).open({ door: door.data, ...opts });
}

async function enter({ viewer, name, profileTopics }) {
  Object.assign(visit, { viewer, name, profileTopics });
  await closeIris();
  clear(stage);
  stage.classList.remove("at-door");
  wall.root.classList.remove("at-door");
  await start({ reveal: openIris });
  openIris(); // a start that ended on a problem screen still opens
}

async function start({ reveal = null } = {}) {
  const res = await post("/api/first", { viewer: visit.viewer });
  if (!res.ok) return problem(res.data, start);
  Object.assign(visit, {
    tree: null,
    answers: [],
    says: [],
    rushed: false,
    firstSay: null,
    treeSay: null,
    seen: [],
    pool: res.data.pool,
    trees: res.data.options,
  });
  stage.classList.remove("revealed");
  wall.root.classList.remove("spotlit", "revealed");
  wall.show(visit.pool, { shuffle: false });
  const [greeting, question] = res.data.lines;
  const name = res.data.name;
  const ack = name ? greeting.replace(/\.$/, `, ${name}.`) : greeting;
  const options = res.data.options.map((o) => ({ say: o.say, go: () => chooseTree(o) }));
  await ask({ ack, question, options, count: countText(visit.pool.length, true), many: true, reveal });
}

function chooseTree(option) {
  Object.assign(visit, { tree: option.tree, answers: [], says: [], rushed: false, firstSay: option.say, seen: [], treeSay: null });
  step();
}

// Crumb 0 is the first question; crumb i re-asks the question answers[i - 1] answered.
function backTo(i) {
  if (i === 0) return start();
  visit.answers = visit.answers.slice(0, i - 1);
  visit.says = visit.says.slice(0, i - 1);
  visit.rushed = false;
  if (!visit.answers.length) visit.treeSay = null;
  return step();
}

async function step() {
  const res = await post("/api/walk", { tree: visit.tree, answers: visit.answers, viewer: visit.viewer });
  if (!res.ok) return problem(res.data, start);
  visit.pool = res.data.pool;
  wall.show(visit.pool);
  const q = res.data.question;
  if (!q) return pickNow(res.data.line);
  const picture = q.presentation === "pails" && q.options.every((o) => o.image);
  const options = q.options.map((o) => ({
    say: o.say,
    image: o.image,
    go: () => {
      if (!visit.answers.length) visit.treeSay = o.say;
      visit.answers.push({ question: q.id, option: o.index });
      visit.says.push(o.say);
      step();
    },
  }));
  await ask({ ack: res.data.line, question: q.ask, options, count: countText(visit.pool.length, false), picture });
}

function pickFrame() {
  const line = h("h1", { class: "line pick-line", "aria-live": "polite" });
  const aside = h("div", { class: "aside" }, line);
  const showing = h("section", { class: "showing" }, aside);
  clear(stage).append(
    h("header", { class: "topbar" }, h("div", { class: "wordmark" }, "Matinee"), nameTag() || h("span")),
    showing,
    h("footer", { class: "bottombar" }, h("span"), credits()),
  );
  return { line, aside, showing };
}

function hasTopics() {
  return Boolean(visit.viewer.profile_id ? visit.profileTopics : visit.viewer.topics?.length);
}

async function checking(frame) {
  wall.root.classList.remove("spotlit", "revealed");
  await typeLine(frame.line, CHECKING, "");
  const timer = setInterval(() => wall.move(), CHECK_SHUFFLE_MS);
  return () => clearInterval(timer);
}

const SEEN_MAX = 200; // PickIn.seen's max_length on the server

// `risk` is "Just pick one" after three films tripped the list: nothing is checked or turned away.
async function pickNow(opening = "", risk = false) {
  stage.classList.remove("revealed");
  wall.root.classList.remove("spotlit", "revealed");
  const frame = pickFrame();
  if (opening) await typeLine(frame.line, opening, "");
  // The check runs while the checking line types, not after it.
  const seen = visit.seen.slice(-SEEN_MAX); // the server takes at most SEEN_MAX; the oldest may come round again
  const body = { tree: visit.tree, answers: visit.answers, viewer: visit.viewer, seen, risk };
  const request = post("/api/pick", body);
  const stopChecking = hasTopics() && !risk ? await checking(frame) : () => {};
  const res = await request;
  stopChecking();
  if (!res.ok) return problem(res.data, start);
  // Every film the check turned away is seen too, so "Not that one" never draws it again.
  if (res.data.film) visit.seen.push(res.data.film.tmdb);
  visit.seen.push(...res.data.turned_away);
  await showPick({
    stage,
    wall,
    pool: visit.pool,
    reminder: visit.treeSay || visit.firstSay,
    result: res.data,
    frame,
    actions: {
      notThatOne: () => {
        lockStage();
        pickNow();
      },
      justPick: () => {
        lockStage();
        pickNow("", true);
      },
      startOver: () => {
        lockStage();
        start();
      },
      failed: (data) => problem(data, start),
      correction: (film) => correctionLink({ visit, film, trees: visit.trees }),
    },
  });
}

boot();
