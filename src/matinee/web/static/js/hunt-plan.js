// The hunt's plan, with no page in it. Before a pick's hunt starts, every hop is planned: which axis,
// which way, how many posters, how long it takes and how long it pauses. The wall is moved by a camera;
// a cell is a poster's place on the endless wall, counted in columns (i) and rows (j), and the camera
// stops on a cell when that cell's centre is at the screen's centre.

// Hop lengths in posters, move times and pauses in seconds, by the number of hops.
export const HOP_TABLE = {
  1: { lengths: [[6, 9]], move: [1.5], pause: [0.3] },
  2: { lengths: [[5, 7], [1, 1]], move: [1.05, 0.55], pause: [0.18, 0.34] },
  3: { lengths: [[5, 8], [2, 3], [1, 1]], move: [0.95, 0.7, 0.5], pause: [0.14, 0.22, 0.34] },
};
const HOP_COUNTS = [1, 2, 2, 3, 3, 3]; // one, two or three hops, weighted 1, 2 and 3 in 6
const FIRST_AXIS_ACROSS = 0.6; // the first hop runs across more often than down
const VERTICAL_SCALE = 0.7; // rows are taller than columns are wide
export const TICK_PX = 12; // the most a hop passes its stop by before settling back
const TICK_SHARE = 0.06; // ... and never more than this share of the hop
const TICK_SPLIT = 0.8; // the share of a hop's time spent reaching the far point of the tick
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

// A hop's time, lengthened where needed so it never moves the wall more than half the spacing
// between posters along its axis in one frame's time. Its length never changes.
export function limitedTime(dist, seconds, spacing) {
  let time = seconds;
  for (let k = 0; k < 20; k += 1) {
    const peak = peakStep(dist, time);
    if (peak <= spacing / 2) return time;
    time *= (peak / (spacing / 2)) * 1.01;
  }
  return time;
}

const pickInt = (rand, [lo, hi]) => lo + Math.floor(rand() * (hi - lo + 1));

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

// The hunt from `from`, a cell the camera has settled on. The first hop always runs at least one
// poster further than the screen shows along its axis, so the landing cell starts off screen and
// the wall is seen to search. No hop moves back along an axis the settle or an earlier hop
// travelled: the settle travelled down the wall, so every vertical hop goes down it too.
export function planHunt({ n, rand, layout, from }) {
  const table = HOP_TABLE[n];
  const signs = { x: 0, y: 1 };
  const reach = { x: layout.screenCols + 1, y: layout.screenRows + 1 };
  const spacing = { x: layout.sx, y: layout.sy };
  let cell = { ...from };
  const hops = hopAxes(n, rand).map((axis, k) => {
    const drawn = pickInt(rand, table.lengths[k]);
    let cells = axis === "y" && drawn > 1 ? Math.max(1, Math.round(drawn * VERTICAL_SCALE)) : drawn;
    if (k === 0) cells = Math.max(cells, reach[axis]);
    if (!signs[axis]) signs[axis] = rand() < 0.5 ? -1 : 1;
    const sign = signs[axis];
    const dist = cells * spacing[axis];
    cell = axis === "x" ? { i: cell.i + sign * cells, j: cell.j } : { i: cell.i, j: cell.j + sign * cells };
    return { axis, sign, cells, dist, seconds: limitedTime(dist, table.move[k], spacing[axis]), pause: table.pause[k], to: cell };
  });
  return { hops, landing: cell };
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
