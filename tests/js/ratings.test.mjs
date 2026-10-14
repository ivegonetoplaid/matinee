import { test } from "node:test";
import assert from "node:assert/strict";

import { ANSWERS, answerOf, said } from "../../src/matinee/web/static/js/ratings.js";

test("the five answers stand best first, each kept as its number", () => {
  assert.deepEqual(
    ANSWERS.map((a) => [a.score, a.say]),
    [
      [5, "Loved it!"],
      [4, "Really liked it"],
      [3, "It was ok, I guess"],
      [2, "Didn't like it"],
      [1, "Hated it"],
    ],
  );
  assert.equal(answerOf(3), "It was ok, I guess");
  assert.equal(answerOf(9), "");
});

test("a shared rating reads as a sentence after the name, never a number", () => {
  assert.deepEqual([5, 4, 3, 2, 1].map(said), ["loved it", "really liked it", "thought it was ok", "didn't like it", "hated it"]);
  assert.equal(said(0), "");
});
