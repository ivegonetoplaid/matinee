import assert from "node:assert/strict";
import { test } from "node:test";

import {
  cellBox,
  filmAt,
  onScreen,
  rankPool,
  resortAnchor,
  resortPlan,
  screenCells,
  wallLayout,
} from "../../src/matinee/web/static/js/wall-grid.js";

function seeded(seed) {
  let s = seed;
  return () => {
    s = (s * 1103515245 + 12345) % 2147483648;
    return s / 2147483648;
  };
}

const range = (n, from = 0) => Array.from({ length: n }, (_, k) => from + k);
const centred = (layout, i, j) => ({ x: i * layout.sx + layout.w / 2, y: j * layout.sy + layout.h / 2 });

// The posters on screen for a wall, as the page lists them before a re-sort.
function shown(wall) {
  return screenCells(wall.layout, wall.cam).map((cell) => ({
    id: filmAt(wall.layout, wall.order, new Map(), cell.i, cell.j),
    ...cellBox(wall.layout, wall.cam, cell),
  }));
}

function walls(oldFilms, newOrder) {
  const was = { order: range(oldFilms, 100) };
  was.layout = wallLayout(1280, 800, 16, false, was.order.length);
  was.cam = centred(was.layout, 0, 0);
  const now = { order: newOrder };
  now.layout = wallLayout(1280, 800, 12, false, newOrder.length);
  now.cam = centred(now.layout, 0, 0);
  return { was, now };
}

test("screenCells lists exactly the cells at least partly on the screen", () => {
  const layout = wallLayout(1280, 800, 10, false, 50);
  const cam = { x: 333.3, y: -271.9 };
  const listed = new Set(screenCells(layout, cam).map(({ i, j }) => `${i},${j}`));
  for (let j = -20; j <= 20; j += 1) {
    for (let i = -20; i <= 20; i += 1) {
      assert.equal(listed.has(`${i},${j}`), onScreen(layout, cellBox(layout, cam, { i, j })), `cell ${i},${j}`);
    }
  }
});

test("a narrower pool keeps its films in the order they already had", () => {
  const first = rankPool(new Map(), range(40, 1), seeded(3));
  const narrower = rankPool(first.ranks, range(20, 1).reverse(), seeded(9));
  assert.deepEqual(
    narrower.order,
    first.order.filter((id) => id <= 20),
  );
  const again = rankPool(narrower.ranks, range(40, 1), seeded(11));
  assert.deepEqual(again.order, first.order);
});

test("films the wall has not seen join after those it has, and the order is drawn at random", () => {
  const first = rankPool(new Map(), range(30, 1), seeded(5));
  assert.notDeepEqual(first.order, range(30, 1));
  const wider = rankPool(first.ranks, range(40, 1), seeded(7));
  assert.deepEqual(wider.order.slice(0, 30), first.order);
  assert.deepEqual(new Set(wider.order.slice(30)), new Set(range(10, 31)));
});

test("every cell on the new screen arrives once, and every old poster is used or departs once", () => {
  const { was, now } = walls(120, range(60, 100).filter((id) => id % 2 === 0));
  const before = shown(was);
  const plan = resortPlan(before, was, now);
  assert.equal(plan.arrivals.length, screenCells(now.layout, now.cam).length);
  const sources = plan.arrivals.filter((a) => a.source >= 0).map((a) => a.source);
  const departed = plan.departures.map((d) => d.source);
  assert.equal(new Set([...sources, ...departed]).size, before.length);
  assert.equal(new Set(departed).size, departed.length);
  for (const k of departed) assert.ok(!sources.includes(k));
});

test("a film still in the running that was on screen slides from the nearest place it stood", () => {
  const { was, now } = walls(120, range(60, 100).filter((id) => id % 2 === 0));
  const before = shown(was);
  const plan = resortPlan(before, was, now);
  let slid = 0;
  for (const arrival of plan.arrivals) {
    const copies = before.filter((p) => p.id === arrival.id);
    if (!copies.length) continue;
    slid += 1;
    const to = cellBox(now.layout, now.cam, arrival.cell);
    const nearest = Math.min(...copies.map((p) => Math.hypot(p.x - to.x, p.y - to.y)));
    assert.equal(before[arrival.source].id, arrival.id);
    assert.equal(Math.hypot(arrival.from.x - to.x, arrival.from.y - to.y), nearest);
  }
  assert.ok(slid > 0);
});

test("a dropped film's poster departs where it stands; a survivor's moves toward its new place", () => {
  const { was, now } = walls(120, range(60, 100).filter((id) => id % 2 === 0));
  const before = shown(was);
  const plan = resortPlan(before, was, now);
  const kept = new Set(now.order);
  let dropped = 0;
  for (const d of plan.departures) {
    const film = before[d.source].id;
    if (kept.has(film)) {
      assert.ok(d.to);
      const target = now.layout;
      assert.equal(filmAt(target, now.order, new Map(), Math.round((d.to.x + now.cam.x - target.vw / 2) / target.sx), Math.round((d.to.y + now.cam.y - target.vh / 2) / target.sy)), film);
    } else {
      assert.equal(d.to, null);
      dropped += 1;
    }
  }
  assert.ok(dropped > 0);
});

test("a film that was off screen enters from the edge on the side of its old place", () => {
  const was = { order: range(400, 100) };
  was.layout = wallLayout(1280, 800, 10, false, 400);
  was.cam = centred(was.layout, 0, 0);
  // The film one column past the right edge of the old screen.
  const right = Math.max(...screenCells(was.layout, was.cam).map((c) => c.i)) + 1;
  const film = filmAt(was.layout, was.order, new Map(), right, 0);
  const now = { order: [film, ...range(30, 1000)] };
  now.layout = wallLayout(1280, 800, 10, false, now.order.length);
  now.cam = centred(now.layout, 0, 0);
  const plan = resortPlan(shown(was), was, now);
  const arrivals = plan.arrivals.filter((a) => a.id === film);
  assert.ok(arrivals.length > 0);
  for (const arrival of arrivals) {
    assert.equal(arrival.source, -1);
    assert.ok(arrival.from.x >= now.layout.vw, `enters at x ${arrival.from.x}`);
  }
});

test("a film new to the wall appears in place", () => {
  const { was, now } = walls(80, [...range(10, 100), ...range(10, 5000)]);
  const plan = resortPlan(shown(was), was, now);
  const fresh = plan.arrivals.filter((a) => a.id >= 5000);
  assert.ok(fresh.length > 0);
  for (const arrival of fresh) assert.equal(arrival.from, null);
});

test("the re-sort centres the new place of the survivor nearest the screen's centre", () => {
  const { was, now } = walls(120, range(60, 100).filter((id) => id % 3 === 0));
  const before = shown(was);
  const anchor = resortAnchor(before, now.order, now.layout);
  const kept = before.filter((p) => now.order.includes(p.id));
  const nearest = kept.reduce((a, b) =>
    Math.hypot(a.x + a.w / 2 - 640, a.y + a.h / 2 - 400) <= Math.hypot(b.x + b.w / 2 - 640, b.y + b.h / 2 - 400) ? a : b,
  );
  assert.equal(filmAt(now.layout, now.order, new Map(), anchor.i, anchor.j), nearest.id);
  assert.equal(resortAnchor(before, range(5, 9000), now.layout), null);
});
