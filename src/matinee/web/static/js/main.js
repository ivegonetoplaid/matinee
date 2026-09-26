// Matinee's page: the questions on the poster wall, then the pick.

import { post } from "./api.js";
import { correctionLink } from "./correct.js";
import { clear, h, sentenceCase } from "./dom.js";
import { showPick } from "./pick.js";
import { typeLine } from "./type.js";
import { Wall } from "./wall.js";

const stage = document.getElementById("stage");
const wall = new Wall(document.getElementById("wall"));

// Where this visit stands. The viewer is a held profile or this visit's own exclusions.
const visit = {
  viewer: {},
  tree: null,
  answers: [],
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

function frame({ count, justPick = true }) {
  const line = h("h1", { class: "line", "aria-live": "polite" });
  const answers = h("div", { class: "answers", role: "group", "aria-label": "Your answers", hidden: true });
  const pick = h(
    "button",
    {
      class: "pill gold",
      type: "button",
      onclick: () => {
        lockStage();
        pickNow();
      },
    },
    "Just pick one!",
  );
  clear(stage).append(
    h("header", { class: "topbar" }, h("div", { class: "wordmark" }, "Matinee"), h("div", { class: "count" }, count)),
    h("section", { class: "talk" }, line, answers),
    h("div", { class: "bottombar" }, justPick ? pick : h("span")),
  );
  return { line, answers };
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

async function ask({ ack, question, options, count, many = false, picture = false }) {
  const { line, answers } = frame({ count });
  const buttons = options.map((o) => answerButton(o, picture));
  answers.classList.toggle("many", many);
  answers.classList.toggle("pails", picture);
  answers.append(...buttons);
  await typeLine(line, ack, question);
  answers.hidden = false;
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

export async function start() {
  const res = await post("/api/first", { viewer: visit.viewer });
  if (!res.ok) return problem(res.data, start);
  Object.assign(visit, {
    tree: null,
    answers: [],
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
  await ask({ ack, question, options, count: countText(visit.pool.length, true), many: true });
}

function chooseTree(option) {
  Object.assign(visit, { tree: option.tree, answers: [], firstSay: option.say, seen: [], treeSay: null });
  step();
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
    h("header", { class: "topbar" }, h("div", { class: "wordmark" }, "Matinee"), h("span")),
    showing,
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

async function pickNow(opening = "") {
  stage.classList.remove("revealed");
  wall.root.classList.remove("spotlit", "revealed");
  const frame = pickFrame();
  if (opening) await typeLine(frame.line, opening, "");
  // The check runs while the checking line types, not after it.
  const request = post("/api/pick", { tree: visit.tree, answers: visit.answers, viewer: visit.viewer, seen: visit.seen });
  const stopChecking = hasTopics() ? await checking(frame) : () => {};
  const res = await request;
  stopChecking();
  if (!res.ok) return problem(res.data, start);
  // A film the check turned away is seen too, so "Not that one" never draws it again.
  for (const f of [res.data.film, res.data.swapped?.film]) if (f) visit.seen.push(f.tmdb);
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
      startOver: () => {
        lockStage();
        start();
      },
      failed: (data) => problem(data, start),
      correction: (film) => correctionLink({ visit, film, trees: visit.trees }),
    },
  });
}

start();
