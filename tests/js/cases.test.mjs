import { test } from "node:test";
import assert from "node:assert/strict";

import { CASES, filmsCount, hiddenUntil, tiers } from "../../src/matinee/web/static/js/cases.js";

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

test("a hidden film says the day and month it comes back, or that it is hidden for good", () => {
  const today = new Date("2026-10-13T12:00:00+00:00");
  assert.equal(hiddenUntil("2027-01-10T12:00:00+00:00", today), "Back on 10 January");
  assert.equal(hiddenUntil("2027-10-13T12:00:00+00:00", today), "Back on 13 October 2027"); // a year's hide made today
  assert.equal(hiddenUntil(null), "Hidden for good");
});

test("a tier of one film says \"1 film\", any other count says \"films\"", () => {
  assert.deepEqual([0, 1, 2].map(filmsCount), ["0 films", "1 film", "2 films"]);
});
