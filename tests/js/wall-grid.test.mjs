import assert from "node:assert/strict";
import { test } from "node:test";

import { besideItself, filmAt, filmIndex, nearestCell, pictureSize, posterAcross, wallLayout } from "../../src/matinee/web/static/js/wall-grid.js";

test("every film shows at its home cell, in the wall's order along row 0", () => {
  const layout = wallLayout(1280, 800, posterAcross(3900, false), false, 3900);
  for (let k = 0; k < layout.films; k += 1) assert.equal(filmIndex(layout, k, 0), k);
});

test("along any row the films run in the wall's order and start again after the last", () => {
  const layout = wallLayout(412, 915, posterAcross(7, true), true, 7);
  for (const j of [-3, 0, 5]) {
    for (let i = -10; i < 10; i += 1) assert.equal(filmIndex(layout, i + 1, j), (filmIndex(layout, i, j) + 1) % 7);
  }
});

// The nearest pair of cells showing the same film, found by looking.
function nearestRepeat(layout) {
  let best = Infinity;
  const here = filmIndex(layout, 0, 0);
  for (let dj = 0; dj <= 40; dj += 1) {
    for (let di = -layout.films; di <= layout.films; di += 1) {
      if ((dj > 0 || di > 0) && filmIndex(layout, di, dj) === here) best = Math.min(best, Math.hypot(di * layout.sx, dj * layout.sy));
    }
  }
  return best;
}

test("a film's repeats sit at least 0.8 of the ideal spacing apart, for any pool", () => {
  for (const [vw, vh, phone] of [
    [1280, 800, false],
    [412, 915, true],
  ]) {
    for (const films of [2, 3, 5, 14, 40, 69, 70, 71, 128, 300, 999]) {
      const layout = wallLayout(vw, vh, posterAcross(films, phone), phone, films);
      const ideal = Math.sqrt(films * layout.sx * layout.sy);
      assert.ok(nearestRepeat(layout) >= 0.8 * ideal, `${vw}x${vh}, ${films} films: repeats too close`);
    }
  }
});

test("a large pool never repeats a film within two screens", () => {
  for (const [vw, vh, phone] of [
    [1280, 800, false],
    [412, 915, true],
    [1920, 1080, false],
  ]) {
    const layout = wallLayout(vw, vh, posterAcross(3921, phone), phone, 3921);
    assert.ok(nearestRepeat(layout) > 2 * Math.hypot(vw, vh));
  }
});

test("the nearest cell showing a film does show it, and no cell nearer does", () => {
  const layout = wallLayout(412, 915, posterAcross(69, true), true, 69);
  const near = { i: 5, j: -3 };
  for (const index of [0, 13, 68]) {
    const cell = nearestCell(layout, index, near);
    assert.equal(filmIndex(layout, cell.i, cell.j), index);
    const d = Math.hypot((cell.i - near.i) * layout.sx, (cell.j - near.j) * layout.sy);
    for (let j = near.j - 8; j <= near.j + 8; j += 1) {
      for (let i = near.i - 80; i <= near.i + 80; i += 1) {
        if (filmIndex(layout, i, j) === index) assert.ok(Math.hypot((i - near.i) * layout.sx, (j - near.j) * layout.sy) >= d - 1e-9);
      }
    }
  }
});

test("posters grow as the pool narrows and rest at the resting size", () => {
  assert.equal(posterAcross(5000, false), 22);
  assert.equal(posterAcross(5000, true), 14);
  assert.ok(posterAcross(300, false) < posterAcross(900, false));
  assert.equal(posterAcross(40, false), 10);
  assert.equal(posterAcross(5000, false, true), 10);
  assert.equal(posterAcross(5000, true, true), 5.2);
});

test("the wall picture is the smallest that covers the cell", () => {
  assert.equal(pictureSize(28, 3), "xs");
  assert.equal(pictureSize(128, 1), "s");
  assert.equal(pictureSize(160, 1), "s");
  assert.equal(pictureSize(192, 1), "m");
  assert.equal(pictureSize(79, 2.6), "m");
  assert.equal(pictureSize(400, 2), "l");
});

test("a film is beside itself when a neighbouring cell shows it, placed or in the wall's order", () => {
  const layout = wallLayout(1280, 800, posterAcross(40, false, true), false, 40);
  const order = Array.from({ length: 40 }, (_, k) => k);
  const none = new Map();
  const home = filmAt(layout, order, none, 3, 3);
  assert.equal(besideItself(layout, order, none, { i: 2, j: 3 }, home), true);
  assert.equal(besideItself(layout, order, none, { i: 3, j: 3 }, home), false);
  const placed = new Map([["10,10", 999]]);
  assert.equal(besideItself(layout, order, placed, { i: 11, j: 11 }, 999), true);
  assert.equal(besideItself(layout, order, placed, { i: 12, j: 12 }, 999), false);
});
