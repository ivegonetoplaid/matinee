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
