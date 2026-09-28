import assert from "node:assert/strict";
import { test } from "node:test";

import {
  HOP_TABLE,
  centreOf,
  hopCell,
  hopCount,
  hopOffset,
  limitedTime,
  peakStep,
  placeLanding,
  planHunt,
  settledCamera,
} from "../../src/matinee/web/static/js/hunt-plan.js";
import { camCell, filmAt, posterAcross, wallLayout } from "../../src/matinee/web/static/js/wall-grid.js";

// A repeatable stand-in for Math.random.
function seeded(seed) {
  let s = seed;
  return () => {
    s = (s * 1103515245 + 12345) % 2147483648;
    return s / 2147483648;
  };
}

const SCREENS = [
  [1280, 800, false],
  [412, 915, true],
];

function layouts() {
  const out = [];
  for (const [vw, vh, phone] of SCREENS) {
    for (const pool of [4000, 300, 40]) out.push(wallLayout(vw, vh, posterAcross(pool, phone), phone, pool));
    out.push(wallLayout(vw, vh, posterAcross(40, phone, true), phone, 40));
  }
  return out;
}

// Plays a plan's camera from `start` hop by hop through `hopCell`, as the page does, returning the
// cell centred after each hop, the camera there, and the axes each hop changed.
function play(plan, start, layout) {
  let cell = { ...start };
  return plan.hops.map((hop) => {
    const end = hopCell(cell, hop, 1);
    const moved = ["i", "j"].filter((a) => Math.abs(end[a] - cell[a]) > 1e-9);
    cell = end;
    const cam = centreOf(cell, layout);
    return { cell: camCell(layout, cam), cam, moved };
  });
}

test("the poster centred after the last hop is the picked film", () => {
  for (const layout of layouts()) {
    const order = Array.from({ length: layout.films }, (_, k) => 1000 + k);
    for (let seed = 1; seed < 200; seed += 1) {
      const rand = seeded(seed);
      const from = { i: 3, j: -7 };
      const plan = planHunt({ n: hopCount(rand), rand, layout, from });
      const picked = order[seed % order.length];
      const placed = placeLanding(plan, picked);
      const steps = play(plan, from, layout);
      const { i, j } = steps.at(-1).cell;
      assert.equal(filmAt(layout, order, placed, i, j), picked);
      assert.deepEqual(steps.at(-1).cell, plan.landing);
      const end = steps.at(-1).cam;
      const centre = centreOf(plan.landing, layout);
      assert.ok(Math.abs(end.x - centre.x) < 1e-6 && Math.abs(end.y - centre.y) < 1e-6);
    }
  }
});

test("from a part-row, the settle and every hop each move along one axis", () => {
  for (const layout of layouts()) {
    for (let seed = 1; seed < 100; seed += 1) {
      const rand = seeded(seed);
      const drifting = { x: centreOf({ i: 2, j: 0 }, layout).x, y: 5 * layout.sy + layout.h / 2 + layout.sy * rand() };
      const settled = settledCamera(drifting, layout);
      assert.equal(settled.x, drifting.x);
      assert.ok(settled.y >= drifting.y);
      assert.ok(settled.y - drifting.y < layout.sy);
      const from = camCell(layout, settled);
      assert.deepEqual(centreOf(from, layout), settled);
      const plan = planHunt({ n: hopCount(rand), rand, layout, from });
      for (const step of play(plan, from, layout)) assert.equal(step.moved.length, 1);
    }
  }
});

test("no hop moves back along a travelled axis, and vertical hops go the drift's way", () => {
  for (const layout of layouts()) {
    for (let seed = 1; seed < 300; seed += 1) {
      const rand = seeded(seed);
      const plan = planHunt({ n: hopCount(rand), rand, layout, from: { i: 0, j: 0 } });
      const signs = { y: 1 };
      for (const hop of plan.hops) {
        if (signs[hop.axis]) assert.equal(hop.sign, signs[hop.axis]);
        signs[hop.axis] = hop.sign;
      }
    }
  }
});

test("the landing cell starts off screen", () => {
  for (const layout of layouts()) {
    for (let seed = 1; seed < 300; seed += 1) {
      const rand = seeded(seed);
      const plan = planHunt({ n: hopCount(rand), rand, layout, from: { i: 0, j: 0 } });
      const dx = Math.abs(plan.landing.i) * layout.sx - layout.w / 2;
      const dy = Math.abs(plan.landing.j) * layout.sy - layout.h / 2;
      assert.ok(dx > layout.vw / 2 || dy > layout.vh / 2, `landing ${JSON.stringify(plan.landing)} is on screen`);
    }
  }
});

test("hop counts come one, two or three, weighted 1, 2 and 3", () => {
  const rand = seeded(7);
  const counts = { 1: 0, 2: 0, 3: 0 };
  for (let k = 0; k < 6000; k += 1) counts[hopCount(rand)] += 1;
  assert.ok(Math.abs(counts[1] - 1000) < 150 && Math.abs(counts[2] - 2000) < 150 && Math.abs(counts[3] - 3000) < 150);
});

test("hop lengths follow the table, and the first hop crosses the screen", () => {
  for (const layout of layouts()) {
    for (let seed = 1; seed < 200; seed += 1) {
      const rand = seeded(seed);
      const n = hopCount(rand);
      const plan = planHunt({ n, rand, layout, from: { i: 0, j: 0 } });
      plan.hops.forEach((hop, k) => {
        const [lo, hi] = HOP_TABLE[n].lengths[k];
        const scaled = hop.axis === "y" && hi > 1 ? [Math.round(lo * 0.7), Math.round(hi * 0.7)] : [lo, hi];
        const reach = hop.axis === "x" ? layout.screenCols + 1 : layout.screenRows + 1;
        if (k === 0) assert.ok(hop.cells >= reach && hop.cells >= scaled[0] && hop.cells <= Math.max(scaled[1], reach));
        else assert.ok(hop.cells >= scaled[0] && hop.cells <= scaled[1]);
        assert.ok(hop.seconds >= HOP_TABLE[n].move[k] - 1e-9);
        assert.equal(hop.pause, HOP_TABLE[n].pause[k]);
      });
    }
  }
});

// The most the page's camera moves along a hop's axis in any 1/60 s, in px, measured on its own: the
// hop is played through `hopCell` at 20,000 steps, each compared with the point 1/60 s later.
function fastestFrame(hop, spacing) {
  const window = 1 / 60 / hop.seconds;
  const start = { i: 0, j: 0 };
  const at = (t) => {
    const cell = hopCell(start, hop, Math.min(1, t));
    return (hop.axis === "x" ? cell.i : cell.j) * spacing;
  };
  let fastest = 0;
  for (let k = 0; k <= 20000; k += 1) fastest = Math.max(fastest, Math.abs(at(k / 20000 + window) - at(k / 20000)));
  return fastest;
}

test("no hop at 1280x800 or 412x915 moves more than half a spacing in 1/60 s", () => {
  for (const layout of layouts()) {
    for (let seed = 1; seed < 60; seed += 1) {
      const rand = seeded(seed);
      const plan = planHunt({ n: hopCount(rand), rand, layout, from: { i: 0, j: 0 } });
      for (const hop of plan.hops) {
        const spacing = hop.axis === "x" ? layout.sx : layout.sy;
        assert.ok(fastestFrame(hop, spacing) <= spacing / 2 + 1e-6, `${hop.axis} ${hop.cells} cells in ${hop.seconds} s`);
      }
    }
  }
});

test("each hop passes its stop by at most 12 px, eases back, and ends exactly on it", () => {
  for (const layout of layouts()) {
    for (let seed = 1; seed < 60; seed += 1) {
      const rand = seeded(seed);
      const plan = planHunt({ n: hopCount(rand), rand, layout, from: { i: 0, j: 0 } });
      for (const hop of plan.hops) {
        let far = 0;
        for (let k = 0; k <= 4000; k += 1) far = Math.max(far, hopOffset(k / 4000, hop.dist) - hop.dist);
        assert.ok(far > 0 && far <= Math.min(12, 0.06 * hop.dist) + 1e-9, `tick ${far} px on a ${hop.dist} px hop`);
        assert.equal(hopOffset(1, hop.dist), hop.dist);
        assert.ok(Math.abs(hopOffset(1, hop.dist) - hopOffset(1 - 1 / 60 / hop.seconds, hop.dist)) < 1);
      }
    }
  }
});

test("a hop within the limit keeps its time; one over it takes longer, never shorter", () => {
  assert.equal(limitedTime(100, 1, 100), 1);
  const long = limitedTime(3000, 0.5, 60);
  assert.ok(long > 0.5);
  assert.ok(peakStep(3000, long) <= 30);
});
