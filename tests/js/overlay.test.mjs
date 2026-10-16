import { test } from "node:test";
import assert from "node:assert/strict";

import { keptWalk, noteWalk } from "../../src/matinee/web/static/js/overlay.js";

test("a film is found by the walk kept with it in the newest run that showed it, or by none", () => {
  const older = { tree: "west", answers: [], says: ["Cowboys."], rushed: true };
  const newer = { tree: null, answers: [], says: [], rushed: true };
  const runs = [{ films: [{ tmdb: 2, walk: newer }] }, { films: [{ tmdb: 1, walk: older }, { tmdb: 2, walk: older }] }];
  assert.equal(keptWalk(2, runs), newer);
  assert.equal(keptWalk(1, runs), older);
  assert.equal(keptWalk(3, runs), null);
});

test("a kept walk becomes a note with the door's words apart and no run, so the history keeps no mark", () => {
  const walk = { tree: "west", answers: [{ question: "era", option: 0 }], says: ["Cowboys.", "old."], rushed: false };
  assert.deepEqual(noteWalk(walk, 7), {
    profileId: 7,
    run: null,
    tree: "west",
    answers: [{ question: "era", option: 0 }],
    says: ["old."],
    rushed: false,
    firstSay: "Cowboys.",
  });
});
