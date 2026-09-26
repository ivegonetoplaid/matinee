// Matinee's page: the questions on the poster wall, then the pick.

import { post } from "./api.js";
import { clear, h, sentenceCase } from "./dom.js";
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
  seen: [],
  pool: [],
};

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

async function ask({ ack, question, options, count, many = false }) {
  const { line, answers } = frame({ count });
  const buttons = options.map((o) =>
    h(
      "button",
      {
        class: "answer",
        type: "button",
        onclick: () => {
          lockStage();
          o.go();
        },
      },
      sentenceCase(o.say),
    ),
  );
  answers.classList.toggle("many", many);
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
  Object.assign(visit, { tree: null, answers: [], firstSay: null, seen: [], pool: res.data.pool });
  wall.show(visit.pool, { shuffle: false });
  const [greeting, question] = res.data.lines;
  const name = res.data.name;
  const ack = name ? greeting.replace(/\.$/, `, ${name}.`) : greeting;
  const options = res.data.options.map((o) => ({ say: o.say, go: () => chooseTree(o) }));
  await ask({ ack, question, options, count: countText(visit.pool.length, true), many: true });
}

function chooseTree(option) {
  Object.assign(visit, { tree: option.tree, answers: [], firstSay: option.say, seen: [] });
  step();
}

async function step() {
  const res = await post("/api/walk", { tree: visit.tree, answers: visit.answers, viewer: visit.viewer });
  if (!res.ok) return problem(res.data, start);
  visit.pool = res.data.pool;
  wall.show(visit.pool);
  const q = res.data.question;
  if (!q) return pickNow(res.data.line);
  const options = q.options.map((o) => ({
    say: o.say,
    go: () => {
      if (!visit.answers.length) visit.firstSay = o.say;
      visit.answers.push({ question: q.id, option: o.index });
      step();
    },
  }));
  await ask({ ack: res.data.line, question: q.ask, options, count: countText(visit.pool.length, false) });
}

async function pickNow(opening = "") {
  const res = await post("/api/pick", {
    tree: visit.tree,
    answers: visit.answers,
    viewer: visit.viewer,
    seen: visit.seen,
  });
  if (!res.ok) return problem(res.data, start);
  const { line } = frame({ count: countText(1, false), justPick: false });
  if (opening) await typeLine(line, opening, "");
  const film = res.data.film;
  if (!film) {
    await typeLine(line, res.data.exhausted, "");
    return;
  }
  visit.seen.push(film.tmdb);
  wall.show([film.tmdb], { spotlight: true });
  await typeLine(line, "Here. Watch this one.", `${film.title}${film.year ? ` (${film.year})` : ""}`);
}

start();
