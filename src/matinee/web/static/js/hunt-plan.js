// The hunt's plan, with no page in it. Before a pick's hunt starts, every hop is planned: which axis,
// which way, how many posters, how long it takes and how long it pauses. The wall is moved by a camera;
// a cell is a poster's place on the endless wall, counted in columns (i) and rows (j), and the camera
// stops on a cell when that cell's centre is at the screen's centre.

// Hop lengths as shares of the screen's half-span along the hop's axis (`halfSpan`), shortest move times and
// pauses in seconds, by the number of hops. Each hop's longest share is shorter than the hop before it can draw. Shares rather than posters, because a wall of 4,000 films shows about
// three times as many posters across as a wall of 40: a length in posters fitted to one is lost on the other.
// The hunt runs like a prize wheel: the first hop is the longest and fastest, each later one shorter and slower,
// and the last coasts to a stop.
export const HOP_TABLE = {
  1: { lengths: [[1.4, 2.3]], move: [2], pause: [0.3] },
  2: { lengths: [[1.3, 2.2], [0.4, 1.1]], move: [1.2, 1.4], pause: [0.12, 0.34] },
  3: { lengths: [[1.2, 2], [0.5, 1.1], [0.1, 0.4]], move: [1, 0.9, 1.25], pause: [0.1, 0.12, 0.34] },
};
const PLAN_TRIES = 20; // plans drawn for one whose landing cell starts off screen, before the first hop is stretched
const HOP_COUNTS = [1, 2, 2, 3, 3, 3]; // one, two or three hops, weighted 1, 2 and 3 in 6
const FIRST_AXIS_ACROSS = 0.6; // the first hop runs across more often than down
export const TICK_PX = 12; // the most a hop passes its stop by before settling back
const TICK_SHARE = 0.06; // ... and never more than this share of the hop
const TICK_SPLIT = 0.8; // the share of a hop's time spent reaching the far point of the tick
const SLOWDOWN = 0.7; // each hop's fastest frame is at most this share of the hop before it's
export const FRAME_S = 1 / 60; // the frame the speed limit is counted in
export const SETTLE_S = 0.4; // the wall easing forward to the next whole row as the drift stops

// A CSS cubic-bezier easing as a function of progress, solved by Newton's method, then bisection.
export function bezier(x1, y1, x2, y2) {
  const cx = 3 * x1;
  const bx = 3 * (x2 - x1) - cx;
  const ax = 1 - cx - bx;
  const cy = 3 * y1;
  const by = 3 * (y2 - y1) - cy;
  const ay = 1 - cy - by;
  const sx = (t) => ((ax * t + bx) * t + cx) * t;
  const sy = (t) => ((ay * t + by) * t + cy) * t;
  const dx = (t) => (3 * ax * t + 2 * bx) * t + cx;
  return (x) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let t = x;
    for (let k = 0; k < 6; k += 1) {
      const e = sx(t) - x;
      const d = dx(t);
      if (Math.abs(e) < 1e-6 || Math.abs(d) < 1e-6) break;
      t -= e / d;
    }
    let lo = 0;
    let hi = 1;
    for (let k = 0; k < 30 && Math.abs(sx(t) - x) > 1e-6; k += 1) {
      if (sx(t) < x) lo = t;
      else hi = t;
      t = (lo + hi) / 2;
    }
    return sy(t);
  };
}

export const HOP_EASE = bezier(0.35, 0, 0.12, 1); // gathers speed briefly, then a long slow-down
export const SETTLE_EASE = (t) => 1 - (1 - t) * (1 - t);

// How far along its axis a hop of `dist` px has gone at share `t` of its time: past the stop by the
// tick, then back onto it.
export function hopOffset(t, dist) {
  const over = Math.min(TICK_PX, dist * TICK_SHARE);
  if (t < TICK_SPLIT) return (dist + over) * HOP_EASE(t / TICK_SPLIT);
  return dist + over * (1 - SETTLE_EASE((t - TICK_SPLIT) / (1 - TICK_SPLIT)));
}

// The most a hop of `dist` px lasting `seconds` moves the wall in any one frame's time.
export function peakStep(dist, seconds) {
  const frame = FRAME_S / seconds;
  const samples = 2000;
  let peak = 0;
  for (let k = 0; k <= samples; k += 1) {
    const t = k / samples;
    peak = Math.max(peak, Math.abs(hopOffset(Math.min(1, t + frame), dist) - hopOffset(t, dist)));
  }
  return peak;
}

// A hop's time, lengthened where needed so it never moves the wall more than `most` px in one frame's
// time. Its length never changes.
export function limitedTime(dist, seconds, most) {
  let time = seconds;
  for (let k = 0; k < 20; k += 1) {
    const peak = peakStep(dist, time);
    if (peak <= most) return time;
    time *= (peak / most) * 1.01;
  }
  return time;
}

export function hopCount(rand) {
  return HOP_COUNTS[Math.floor(rand() * HOP_COUNTS.length)];
}

// Where the camera comes to rest as the drift stops: the next whole row in the drift's direction
// (down the wall, as the wall drifts up), on the same column. `cam` is in px on the wall.
export function settledCamera(cam, layout) {
  const row = Math.ceil((cam.y - layout.h / 2) / layout.sy - 1e-9);
  return { x: cam.x, y: row * layout.sy + layout.h / 2 };
}

// Where the camera stands to centre `cell`, in px on the wall.
export function centreOf(cell, layout) {
  return { x: cell.i * layout.sx + layout.w / 2, y: cell.j * layout.sy + layout.h / 2 };
}

function hopAxes(n, rand) {
  const first = rand() < FIRST_AXIS_ACROSS ? "x" : "y";
  const other = first === "x" ? "y" : "x";
  if (n === 1) return [first];
  if (n === 2) return [first, other];
  return [first, other, rand() < 0.5 ? "x" : "y"];
}

// How many posters from the screen's centre along `axis` the first one wholly off screen stands.
export function halfSpan(layout, axis) {
  if (axis === "x") return Math.floor((layout.vw + layout.w) / (2 * layout.sx)) + 1;
  return Math.floor((layout.vh + layout.h) / (2 * layout.sy)) + 1;
}

function offScreen(landing, from, layout) {
  return Math.abs(landing.i - from.i) >= halfSpan(layout, "x") || Math.abs(landing.j - from.j) >= halfSpan(layout, "y");
}

// One draw of the hops from `from`, each hop's share of its half-span drawn from the table, then cut to
// fall short of the hop before it in px (the screen's two half-spans differ). `reach` stretches the first hop to its
// half-span, which puts the landing cell off screen whatever the later hops draw, since none reverses.
// Each hop is timed to stay under the speed limit (half the poster spacing a frame) and under SLOWDOWN of
// the hop before it's fastest frame.
function drawPlan(n, rand, layout, from, reach) {
  const table = HOP_TABLE[n];
  const signs = { x: 0, y: 1 };
  const spacing = { x: layout.sx, y: layout.sy };
  let cell = { ...from };
  let before = { dist: Infinity, peak: Infinity };
  const hops = hopAxes(n, rand).map((axis, k) => {
    const [lo, hi] = table.lengths[k];
    const share = lo + rand() * (hi - lo);
    const half = halfSpan(layout, axis);
    let cells = Math.max(1, Math.round(share * half));
    if (k === 0 && reach) cells = Math.max(cells, half);
    cells = Math.max(1, Math.min(cells, Math.ceil(before.dist / spacing[axis]) - 1));
    if (!signs[axis]) signs[axis] = rand() < 0.5 ? -1 : 1;
    const sign = signs[axis];
    const dist = cells * spacing[axis];
    const seconds = limitedTime(dist, table.move[k], Math.min(spacing[axis] / 2, before.peak * SLOWDOWN));
    before = { dist, peak: peakStep(dist, seconds) };
    cell = axis === "x" ? { i: cell.i + sign * cells, j: cell.j } : { i: cell.i, j: cell.j + sign * cells };
    return { axis, sign, cells, dist, seconds, pause: table.pause[k], to: cell };
  });
  return { hops, landing: cell };
}

// The hunt from `from`, a cell the camera has settled on. The landing cell always starts off screen, so
// the wall is seen to search: up to PLAN_TRIES draws are made for one that lands there, and failing that
// the first hop is stretched until it does. No hop moves back along an axis the settle or an earlier hop
// travelled: the settle travelled down the wall, so every vertical hop goes down it too.
export function planHunt({ n, rand, layout, from }) {
  for (let k = 0; k < PLAN_TRIES; k += 1) {
    const plan = drawPlan(n, rand, layout, from, false);
    if (offScreen(plan.landing, from, layout)) return plan;
  }
  return drawPlan(n, rand, layout, from, true);
}

// Where the camera aims, as a fractional cell, at share `t` of `hop` from cell `start`.
export function hopCell(start, hop, t) {
  const cells = (hopOffset(t, hop.dist) / (hop.dist / hop.cells)) * hop.sign;
  return hop.axis === "x" ? { i: start.i + cells, j: start.j } : { i: start.i, j: start.j + cells };
}

// The films a hunt places for film `id`: the plan's landing cell, keyed "i,j".
export function placeLanding(plan, id) {
  return new Map([[`${plan.landing.i},${plan.landing.j}`, id]]);
}
