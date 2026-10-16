import { test } from "node:test";
import assert from "node:assert/strict";

import { byDay, dayCount, didWith, runCaption, runGroups } from "../../src/matinee/web/static/js/shelves.js";

test("a run is captioned with what its door and answers said, or Just pick one! when it asked nothing", () => {
  assert.equal(runCaption({ says: ["Cowboys.", "old."], rushed: false }), "Cowboys › Old");
  assert.equal(runCaption({ says: ["Cowboys."], rushed: true }), "Cowboys › Just pick one!"); // rushed after the door
  assert.equal(runCaption({ says: [], rushed: true }), "Just pick one!");
});

test("each film reads what the viewer did with it, the run's last film reading as landed on", () => {
  const scoreOf = (tmdb) => ({ 1: 4 })[tmdb] ?? null;
  assert.equal(didWith({ tmdb: 1, mark: "rated" }, false, scoreOf), "You rated it: Really liked it");
  assert.equal(didWith({ tmdb: 2, mark: "rated" }, true, scoreOf), "You landed on this one"); // its rating was cleared
  assert.equal(didWith({ tmdb: 3, mark: "hid" }, true, scoreOf), "You hid it");
  assert.equal(didWith({ tmdb: 3, mark: "reported" }, false, scoreOf), "You reported it");
  assert.equal(didWith({ tmdb: 3, mark: null }, false, scoreOf), "You rolled past it");
  assert.equal(didWith({ tmdb: 1, mark: null }, true, scoreOf), "You landed on this one"); // rated later, elsewhere
});

test("runs gather on the viewer's own day, newest first, whatever the machine's zone", () => {
  const run = (began, n) => ({ began, films: Array.from({ length: n }, (_, i) => ({ tmdb: i, walk: { tree: null, answers: [], says: [], rushed: true } })) });
  const runs = [run("2026-10-13T16:30:00Z", 2), run("2026-10-13T14:00:00Z", 3), run("2026-10-11T21:00:00Z", 1)];
  assert.deepEqual(byDay(runs, "Asia/Tokyo").map((d) => d.runs.length), [1, 1, 1]); // 01:30 on the 14th, 23:00 on the 13th
  const days = byDay(runs, "Europe/London");
  assert.deepEqual(days.map((d) => d.runs.length), [2, 1]);
  assert.equal(dayCount(days[0]), "You asked 2 times, 5 films");
  assert.equal(dayCount(days[1]), "You asked once, 1 film");
});

test("a run whose viewer changed the door mid-run shows each walk's films under its own words", () => {
  const space = { tree: "space", answers: [{ question: "era", option: 1 }], says: ["Space.", "new."], rushed: false };
  const west = { tree: "west", answers: [{ question: "era", option: 0 }], says: ["Cowboys.", "old."], rushed: false };
  const films = [[1, null, space], [2, null, { ...space }], [3, "rated", west], [4, null, west]];
  const run = { films: films.map(([tmdb, mark, walk]) => ({ tmdb, mark, walk })) };
  const groups = runGroups(run, (tmdb) => (tmdb === 3 ? 5 : null));
  assert.deepEqual(
    groups.map((g) => [g.caption, g.films.map((f) => [f.film.tmdb, f.did, f.score])]),
    [
      ["Space › New", [[1, "You rolled past it", null], [2, "You rolled past it", null]]],
      ["Cowboys › Old", [[3, "You rated it: Loved it!", 5], [4, "You landed on this one", null]]],
    ],
  );
  assert.equal(dayCount({ runs: [run] }), "You asked 2 times, 4 films");
});
