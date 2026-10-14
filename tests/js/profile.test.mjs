import { test } from "node:test";
import assert from "node:assert/strict";

import { DELETE_LINE, PARTS } from "../../src/matinee/web/static/js/profile.js";

test("My profile holds its four parts in order, each with the words the decisions set", () => {
  assert.deepEqual(
    PARTS.map((p) => [p.id, p.title, p.empty]),
    [
      ["tailor", "How I pick films for you", null],
      ["rated", "Films you've rated", "Nothing rated yet. After a film, tap Rate it and it lands here."],
      ["hidden", "Films you've hidden", "Nothing hidden. Hide a film from its pick and it waits here until it comes back."],
      ["shown", "Films I've picked for you", "No picks yet. Once I pick something for you, it shows up here."],
    ],
  );
  assert.equal(DELETE_LINE, "Your ratings, hidden films, history and settings go with it. Any notes you sent stay with whoever runs Matinee.");
});

test("the rated films' heading carries the sync line, and a phone gets the board's short side line", () => {
  const rated = PARTS.find((p) => p.id === "rated");
  assert.equal(rated.note, "Your ratings stay in Matinee for now. We\u2019re exploring syncing them with services like Trakt in the near future.");
  assert.equal(rated.phoneMeta, "Best first");
  assert.deepEqual(PARTS.filter((p) => p.note).map((p) => p.id), ["rated"]); // no other part carries it
});

test("each part with records counts them for its jump", () => {
  const mine = { ratings: [1, 2, 3], hidden: [1], runs: [1, 2] };
  assert.deepEqual(
    PARTS.map((p) => p.count?.(mine) ?? null),
    [null, 3, 1, 2],
  );
});
