import assert from "node:assert/strict";
import { test } from "node:test";

import { WIPE_MS, bandsAt } from "../../src/matinee/web/static/js/locked.js";

// Each band's [left, right] edges, in per cent of the width.
function bands(path) {
  const numbers = [...path.matchAll(/(-?[\d.]+)% (?:0|100)%/g)].map((m) => Number(m[1]));
  const out = [];
  for (let i = 0; i < numbers.length; i += 4) out.push([numbers[i], numbers[i + 2]]);
  return out;
}

test("ten bands cover the door before the wipe and nothing after it", () => {
  const before = bands(bandsAt(0));
  assert.equal(before.length, 10);
  before.forEach(([left, right], i) => {
    assert.ok(Math.abs(left - i * 10) < 1e-9 && Math.abs(right - (i + 1) * 10) < 1e-9);
  });
  for (const [left, right] of bands(bandsAt(WIPE_MS))) assert.ok(Math.abs(right - left) < 1e-9);
  assert.equal(WIPE_MS, 800);
});

test("the centre bands close first and the outermost start 0.42 s later, each over 0.38 s", () => {
  const width = (path, i) => {
    const [left, right] = bands(path)[i];
    return right - left;
  };
  const mid = bandsAt(200);
  assert.ok(width(mid, 4) < 10 && width(mid, 5) < 10); // the centre ones are closing
  assert.equal(width(mid, 0), 10); // the outermost have not begun
  assert.ok(width(bandsAt(380), 4) < 1e-9); // a centre band is gone after 0.38 s
  assert.equal(width(bandsAt(420), 9), 10); // the outermost begin at 0.42 s
  assert.ok(width(bandsAt(610), 9) > 0 && width(bandsAt(610), 9) < 10);
  const bandCentres = bands(bandsAt(300)).map(([l, r]) => (l + r) / 2);
  bandCentres.forEach((centre, i) => assert.ok(Math.abs(centre - (i + 0.5) * 10) < 1e-9)); // each about its own centre
});
