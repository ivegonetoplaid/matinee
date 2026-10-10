import { test } from "node:test";
import assert from "node:assert/strict";

import { answerRows, forget, stepBack, wayTo } from "../../src/matinee/web/static/js/way-back.js";

const walk = {
  answers: [
    { question: "kind", option: 2 },
    { question: "gore", option: 1 },
  ],
  sourceAsk: "what are we choosing from tonight?",
  sourceSay: "anything at all. ours or not.",
  doorAsk: "What are we in the mood for?",
  firstSay: "Horror",
  asks: ["what kind of nightmare?", "how much blood?"],
  says: ["ghosts, demons, curses", "some. I'll look away"],
};

test("every answer is listed in order under its question, each going back to the question it answered", () => {
  assert.deepEqual(answerRows(walk), [
    { ask: walk.sourceAsk, say: walk.sourceSay, to: "source" },
    { ask: walk.doorAsk, say: "Horror", to: "doors" },
    { ask: "what kind of nightmare?", say: "ghosts, demons, curses", to: 0 },
    { ask: "how much blood?", say: "some. I'll look away", to: 1 },
  ]);
});

test("a walk with no source question starts at the door, and a pick before any answer lists none", () => {
  assert.deepEqual(
    answerRows({ ...walk, sourceSay: null, sourceAsk: null }).map((r) => r.to),
    ["doors", 0, 1],
  );
  assert.deepEqual(answerRows({ ...walk, sourceSay: null, firstSay: null, asks: [], says: [] }), []);
});

test("a row's way back keeps exactly the answers before it, so the question asked next is the row's own", () => {
  for (const row of answerRows(walk).filter((r) => typeof r.to === "number")) {
    const left = forget(walk, row.to);
    assert.equal(left.says.length, row.to);
    assert.deepEqual(left.answers, walk.answers.slice(0, row.to));
    assert.deepEqual(left.asks, walk.asks.slice(0, row.to));
    assert.equal(walk.asks[left.asks.length], row.ask);
    assert.equal(left.rushed, false);
  }
});

test("each row takes its own way, with its kept count unchanged", () => {
  const taken = [];
  const ways = { source: () => taken.push("source"), doors: () => taken.push("doors"), reask: (k) => taken.push(k) };
  for (const row of answerRows(walk)) wayTo(row, ways);
  assert.deepEqual(taken, ["source", "doors", 0, 1]);
});

test("a walk whose lists have drifted apart is refused, never sent to a wrong question", () => {
  assert.throws(() => forget({ ...walk, asks: [...walk.asks, "one too many?"] }, 1));
});

test("back from a pick asks again the question last answered, or the one 'Just pick one!' left", () => {
  assert.equal(stepBack({ ...walk, rushed: false }), 1); // keep one answer: ask the second question again
  assert.equal(stepBack({ ...walk, rushed: true }), 2); // keep both: ask the question it left
  assert.equal(stepBack({ ...walk, says: [], asks: [], answers: [], rushed: false }), "doors"); // a door with no questions
  assert.equal(stepBack({ ...walk, says: [], asks: [], answers: [], rushed: true }), 0); // left the door's first question
});

test("back from a pick made before any door goes to the screen it left: the doors, or the walk's first screen", () => {
  const noDoor = { ...walk, firstSay: null, says: [], asks: [], answers: [], rushed: true };
  assert.equal(stepBack(noDoor), "doors");
  assert.equal(stepBack({ ...noDoor, sourceSay: null }), "source");
});
