// The poster wall's geometry, with no page in it: how large the posters are for a pool, how far apart
// they sit, and which film each cell of the endless wall shows. Along a row the films run in the
// wall's order, and each row starts a fixed number of films (the stride) on from the row above, so
// the wall repeats in both directions and no edge ever shows. The stride is chosen so that two
// cells showing the same film sit as far apart as the pool's size allows. A film's home cell is its
// cell in row 0.

// Posters across the viewport width: many at the full pool, the resting size at the pick.
export const ACROSS = { desktop: { most: 22, fewest: 10 }, phone: { most: 14, fewest: 5.2 } };
const POOL_FULL = 1200;
const POOL_NARROW = 40;
export const GAP = { desktop: 14, phone: 8 };
export const POSTER_RATIO = 1.5; // height over width
const REPEAT_ROWS = 64; // rows searched for a film's nearest repeat when choosing the stride
// Poster picture widths the server offers, smallest first.
const PICTURE_WIDTHS = [
  ["xs", 100],
  ["s", 160],
  ["m", 320],
  ["l", 640],
];

export const mod = (a, n) => ((a % n) + n) % n;

// Posters across for a pool of `poolSize` films: on a log curve from the most at POOL_FULL films or
// more to the fewest at POOL_NARROW or fewer. `resting` gives the size the posters keep through a pick.
export function posterAcross(poolSize, phone, resting = false) {
  const range = phone ? ACROSS.phone : ACROSS.desktop;
  if (resting || poolSize <= 0) return range.fewest;
  const t = Math.log(Math.max(poolSize, POOL_NARROW) / POOL_NARROW) / Math.log(POOL_FULL / POOL_NARROW);
  return range.fewest + (range.most - range.fewest) * Math.min(1, t);
}

// The wall's measurements for a viewport of `vw` by `vh` px: the poster's width and height, the
// spacing from one poster to the next along each axis, how many cells cover the screen along each
// axis, and the stride, for `films` films.
export function wallLayout(vw, vh, across, phone, films) {
  const gap = phone ? GAP.phone : GAP.desktop;
  const w = vw / across;
  const h = w * POSTER_RATIO;
  const sx = w + gap;
  const sy = h + gap;
  const screenCols = Math.ceil(vw / sx);
  const screenRows = Math.ceil(vh / sy);
  return { vw, vh, w, h, gap, sx, sy, screenCols, screenRows, films, stride: bestStride(films, sx, sy) };
}

// The shortest distance in px between two cells showing the same film, for a wall of `films` films
// whose rows start `stride` films apart, searched over REPEAT_ROWS rows.
export function repeatDistance(films, stride, sx, sy) {
  let best = films * sx;
  for (let dj = 1; dj <= REPEAT_ROWS; dj += 1) {
    let di = mod(-dj * stride, films);
    if (di > films / 2) di -= films;
    best = Math.min(best, Math.hypot(di * sx, dj * sy));
  }
  return best;
}

// The stride that puts a film's repeats farthest apart; the smallest such stride on a tie.
export function bestStride(films, sx, sy) {
  let best = { stride: 1, d: -1 };
  for (let stride = 1; stride < films; stride += 1) {
    const d = repeatDistance(films, stride, sx, sy);
    if (d > best.d) best = { stride, d };
  }
  return best.stride;
}

// Which of the wall's films (an index into its order) the cell at column `i`, row `j` shows.
export function filmIndex(layout, i, j) {
  if (!layout.films) return -1;
  return mod(i + j * layout.stride, layout.films);
}

// The cell nearest cell `near` that shows the film at `index` in the order.
export function nearestCell(layout, index, near) {
  let best = null;
  for (let j = near.j - REPEAT_ROWS; j <= near.j + REPEAT_ROWS; j += 1) {
    const base = mod(index - j * layout.stride, layout.films);
    const i = base + Math.round((near.i - base) / layout.films) * layout.films;
    const d = Math.hypot((i - near.i) * layout.sx, (j - near.j) * layout.sy);
    if (!best || d < best.d) best = { d, cell: { i, j } };
  }
  return best.cell;
}

// The smallest poster picture that covers a cell `width` px wide at `density` device pixels per px.
export function pictureSize(width, density) {
  const needed = width * density;
  const fit = PICTURE_WIDTHS.find(([, px]) => px >= needed);
  return (fit || PICTURE_WIDTHS.at(-1))[0];
}

// A pool in the page's order. `ranks` maps each film already seen to its place; films not yet seen are
// given the next places in a random order drawn with `rand`. Returns the extended ranks and the pool
// sorted by them, so a narrower pool keeps its films in the order they already had.
export function rankPool(ranks, pool, rand) {
  const next = new Map(ranks);
  const unseen = pool.filter((id) => !next.has(id));
  for (let k = unseen.length - 1; k > 0; k -= 1) {
    const j = Math.floor(rand() * (k + 1));
    [unseen[k], unseen[j]] = [unseen[j], unseen[k]];
  }
  for (const id of unseen) next.set(id, next.size);
  return { ranks: next, order: pool.slice().sort((a, b) => next.get(a) - next.get(b)) };
}

// Where cell (i, j) is on the screen, as its top-left corner in px, for a camera at `cam`.
export function cellBox(layout, cam, { i, j }) {
  return { x: i * layout.sx - cam.x + layout.vw / 2, y: j * layout.sy - cam.y + layout.vh / 2, w: layout.w, h: layout.h };
}

export function onScreen(layout, box) {
  return box.x + box.w > 0 && box.x < layout.vw && box.y + box.h > 0 && box.y < layout.vh;
}

// Every cell at least partly on the screen.
export function screenCells(layout, cam) {
  const cells = [];
  const i0 = Math.floor((cam.x - layout.vw / 2) / layout.sx);
  const j0 = Math.floor((cam.y - layout.vh / 2) / layout.sy);
  for (let j = j0; j <= j0 + layout.screenRows + 1; j += 1) {
    for (let i = i0; i <= i0 + layout.screenCols + 1; i += 1) {
      if (onScreen(layout, cellBox(layout, cam, { i, j }))) cells.push({ i, j });
    }
  }
  return cells;
}

// The cell nearest the camera's centre.
export function camCell(layout, cam) {
  const i = Math.round((cam.x - layout.w / 2) / layout.sx);
  const j = Math.round((cam.y - layout.h / 2) / layout.sy);
  return { i: i || 0, j: j || 0 }; // never -0, so a cell compares equal to itself
}

// The cell of the new layout to centre after a re-sort: the nearest new cell of the film still in the
// running whose poster stood nearest the screen's centre, so the survivors close ranks around it. Null
// when none of `before` (the posters on screen, as { id, x, y, w, h }) is still in `order`.
export function resortAnchor(before, order, next) {
  const index = new Map(order.map((id, k) => [id, k]));
  let near = null;
  for (const p of before) {
    if (!index.has(p.id)) continue;
    const d = Math.hypot(p.x + p.w / 2 - next.vw / 2, p.y + p.h / 2 - next.vh / 2);
    if (!near || d < near.d) near = { d, id: p.id };
  }
  return near ? nearestCell(next, index.get(near.id), { i: 0, j: 0 }) : null;
}

// Where a film that was off the screen enters from: just past the screen's edge, on the line from the
// screen's centre toward its old place nearest the old camera.
function edgeEntry(was, index, layout) {
  const old = cellBox(was.layout, was.cam, nearestCell(was.layout, index, camCell(was.layout, was.cam)));
  const dx = old.x + old.w / 2 - layout.vw / 2;
  const dy = old.y + old.h / 2 - layout.vh / 2;
  const k = Math.min(dx ? (layout.vw / 2 + layout.w) / Math.abs(dx) : Infinity, dy ? (layout.vh / 2 + layout.h) / Math.abs(dy) : Infinity);
  return { x: layout.vw / 2 + dx * k - layout.w / 2, y: layout.vh / 2 + dy * k - layout.h / 2, w: layout.w, h: layout.h };
}

// The re-sort, planned. `before` lists the posters on the screen under the old layout; `was` and `now`
// are { layout, cam, order } for the old wall and the new one. Each new on-screen cell arrives: from the
// nearest box in `before` showing its film (`source` is that box's index), else, for a film that was in
// the old wall, in from the screen's edge toward its old place, else (a film new to the wall) it
// appears in place (`from` null). Each box in `before` that no arrival came from departs: toward its
// film's nearest new cell when the film is still in the running, else in place (`to` null).
export function resortPlan(before, was, now) {
  const oldIndex = new Map(was.order.map((id, k) => [id, k]));
  const newIndex = new Map(now.order.map((id, k) => [id, k]));
  const used = new Set();
  const arrivals = screenCells(now.layout, now.cam).map((cell) => {
    const id = filmAt(now.layout, now.order, new Map(), cell.i, cell.j);
    const to = cellBox(now.layout, now.cam, cell);
    let source = -1;
    before.forEach((p, k) => {
      if (p.id !== id) return;
      if (source < 0 || Math.hypot(p.x - to.x, p.y - to.y) < Math.hypot(before[source].x - to.x, before[source].y - to.y)) source = k;
    });
    if (source >= 0) {
      used.add(source);
      return { cell, id, source, from: before[source] };
    }
    const from = oldIndex.has(id) && was.layout?.films ? edgeEntry(was, oldIndex.get(id), now.layout) : null;
    return { cell, id, source, from };
  });
  const departures = [];
  before.forEach((p, k) => {
    if (used.has(k)) return;
    const index = newIndex.get(p.id);
    const to = index === undefined ? null : cellBox(now.layout, now.cam, nearestCell(now.layout, index, camCell(now.layout, now.cam)));
    departures.push({ source: k, to });
  });
  return { arrivals, departures };
}

// The film cell (i, j) shows: one a hunt placed there (`placed`, keyed "i,j"), or the wall's own.
export function filmAt(layout, order, placed, i, j) {
  const hunted = placed.get(`${i},${j}`);
  if (hunted !== undefined) return hunted;
  return layout.films ? order[filmIndex(layout, i, j)] : null;
}

// Whether film `id` shows in any of the eight cells around `cell`, counting films a hunt placed.
export function besideItself(layout, order, placed, cell, id) {
  for (let di = -1; di <= 1; di += 1) {
    for (let dj = -1; dj <= 1; dj += 1) {
      if ((di || dj) && filmAt(layout, order, placed, cell.i + di, cell.j + dj) === id) return true;
    }
  }
  return false;
}
