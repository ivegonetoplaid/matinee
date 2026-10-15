import { test } from "node:test";
import assert from "node:assert/strict";

import { asPick, kept, newestFirst, remember, runKey, shownBody } from "../../src/matinee/web/static/js/run.js";

const shown = (tmdb) => ({ film: { tmdb, title: `Film ${tmdb}`, year: 2000 } });

test("every film shown is held once, newest first, a film shown again moving to the top", () => {
  let run = [];
  for (const tmdb of [1, 2, 3, 2]) run = remember(run, shown(tmdb));
  assert.deepEqual(
    newestFirst(run, true).map((s) => [s.film.tmdb, s.now]),
    [
      [2, true],
      [3, false],
      [1, false],
    ],
  );
});

test("holding a film leaves the run it was given unchanged, and nothing is showing off the pick", () => {
  const run = [shown(1)];
  remember(run, shown(2));
  assert.equal(run.length, 1);
  assert.deepEqual(
    newestFirst([shown(1), shown(2)], false).map((s) => s.now),
    [false, false],
  );
});

test("a run of twenty films keeps all twenty", () => {
  let run = [];
  for (let tmdb = 1; tmdb <= 20; tmdb++) run = remember(run, shown(tmdb));
  assert.equal(newestFirst(run, true).length, 20);
});

test("a kept film comes back exactly as first shown: its line and credit, language line, note, door and walk", () => {
  const first = {
    film: { tmdb: 7, title: "Film 7", year: 1999 },
    result: { unchecked: "Nobody has voted on this one.", dtdd_item: 42, link: "https://dtdd.invalid", swapped: { film: { tmdb: 8 } }, heard: { original: "th", audio: ["en"] } },
    door: "horror",
    walk: { tree: "horror", answers: [{ question: "kind", option: 1 }], says: ["ghosts"], rushed: false },
    said: { gold: "I passed on one where a dog dies.", reveal: "Try this.", credit: true },
  };
  const again = asPick(kept(first));
  assert.deepEqual(again.result.film, first.film);
  assert.equal(again.result.unchecked, first.result.unchecked);
  assert.equal(again.result.dtdd_item, 42);
  assert.equal(again.result.link, first.result.link);
  assert.deepEqual(again.result.heard, first.result.heard);
  assert.equal(again.door, "horror");
  assert.deepEqual(again.walk, first.walk);
  assert.deepEqual([again.lines.gold, again.lines.reveal, again.lines.credit], [first.said.gold, "Try this.", true]);
  assert.equal(again.lines.beneath("anything"), "Try this.");
  // The film the check turned away is never carried into the run.
  assert.deepEqual([again.result.swapped, again.result.last, again.result.turned_away], [null, null, []]);
  // Brought back, shown again and kept again, it still comes back with its credit.
  const twice = asPick(kept({ film: first.film, result: again.result, door: again.door, walk: again.walk, said: { ...first.said } }));
  assert.equal(twice.lines.credit, true);
});

test("each run's key is 32 hex digits and new every time", () => {
  const keys = new Set(Array.from({ length: 50 }, () => runKey()));
  assert.equal(keys.size, 50);
  for (const key of keys) assert.match(key, /^[0-9a-f]{32}$/);
});

test("the history keeps a shown film with its walk, never its words or its line", () => {
  const walk = { profileId: 3, run: "k", tree: "west", answers: [{ question: "era", option: 0 }], says: ["old."], rushed: true, firstSay: "Cowboys." };
  assert.deepEqual(shownBody({ film: { tmdb: 5, title: "Five" }, walk, said: { gold: "x" } }), {
    tmdb: 5,
    tree: "west",
    answers: [{ question: "era", option: 0 }],
    rushed: true,
  });
});

const ordinary = { film: { tmdb: 7, title: "Seven" }, result: { link: "l" }, door: "west", walk: { tree: "west", answers: [], rushed: false }, said: {} };

test("a film the check turned away, shown on asking, stays out of the history even when brought back", () => {
  const asked = kept({ ...ordinary, result: { link: "l", last: { film: { tmdb: 7 } } } });
  assert.equal(shownBody(asked), null);
  const again = kept({ ...ordinary, result: asPick(asked).result });
  assert.equal(shownBody(again), null);
});

test("an ordinary film brought back from the Back panel is kept again", () => {
  const first = kept(ordinary);
  assert.deepEqual(shownBody(first), { tmdb: 7, tree: "west", answers: [], rushed: false });
  assert.deepEqual(shownBody(kept({ ...ordinary, result: asPick(first).result })), shownBody(first));
});
