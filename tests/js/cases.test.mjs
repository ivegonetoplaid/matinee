import { test } from "node:test";
import assert from "node:assert/strict";

import { CASES, tiers } from "../../src/matinee/web/static/js/cases.js";

test("ratings stand in tiers best first, newest first within a tier, and a rating with no film has no row", () => {
  const newestFirst = [
    { tmdb: 1, score: 3 },
    { tmdb: 2, score: 5 },
    { tmdb: 3, score: 3 },
    { tmdb: 4, score: 1 },
  ];
  assert.deepEqual(
    tiers(newestFirst).map((t) => [t.say, t.films.map((f) => f.tmdb)]),
    [
      ["Loved it!", [2]],
      ["It was ok, I guess", [1, 3]],
      ["Hated it", [4]],
    ],
  );
});

test("each rating has its own case, gold for Loved it! down to distressed for Hated it", () => {
  assert.deepEqual(CASES, { 5: "gold", 4: "silver", 3: "neutral", 2: "weathered", 1: "distressed" });
});
