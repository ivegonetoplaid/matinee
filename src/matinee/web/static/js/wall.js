// The poster wall: a flat grid of the posters of the films still in the running, each its own image,
// sharp and upright, held at 35 per cent strength. The grid repeats in both directions, so no edge
// ever shows, and it drifts upward while the viewer answers. Each answer re-sorts it in place, and a
// pick hunts across it to the picked film's poster. The posters ignore taps and clicks; a poster
// whose picture has not loaded is a dark cell.

import { isPhone } from "./dom.js";
import { SETTLE_EASE, SETTLE_S, centreOf, hopCell, hopCount, placeLanding, planHunt, settledCamera } from "./hunt-plan.js";
import {
  camCell,
  cellBox,
  filmAt,
  mod,
  onScreen,
  pictureSize,
  posterAcross,
  rankPool,
  resortAnchor,
  resortPlan,
  screenCells,
  wallLayout,
} from "./wall-grid.js";

const DRIFT_PX_S = 10; // upward, timed by the clock, never by frames
const MAX_STEP_S = 0.25; // a frame after a long pause (a hidden tab) moves the wall no further than this
const RESORT_MS = 800; // each answer's re-sort
const RESORT_EASE = "cubic-bezier(0.2, 0.8, 0.2, 1)";
const PRELOAD_MS = 600; // the re-sort waits this long at most for the posters it brings on screen
const DROPPED_SCALE = 0.5; // a dropped film's poster shrinks to this and fades where it stands
const BLANK = "/static/blank.svg"; // a tile with no picture shows this, so it is a dark cell, never a broken image
const SIZES = ["l", "m", "s"];
const NONE_PLACED = new Map();

const lessMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

// Resolves once every promise has settled or `ms` has passed, whichever comes first.
function within(ms, promises) {
  return Promise.race([Promise.allSettled(promises), new Promise((done) => setTimeout(done, ms))]);
}

export class Wall {
  constructor(root) {
    this.root = root;
    this.layer = document.createElement("div");
    this.layer.className = "wall-tiles";
    root.append(this.layer);
    this.tiles = [];
    this.pictures = new Map(); // picture url -> { ready, settled }
    this.ranks = new Map(); // film id -> its place in this page's order, drawn at random once
    this.order = [];
    this.resting = false;
    this.layout = null;
    this.cam = { x: 0, y: 0 }; // the point of the wall at the screen's centre, in px
    this.corner = null; // the top-left cell the tiles are laid from, as "i,j"
    this.dirty = false; // a picture arrived: tiles showing a dark cell look again
    this.showing = null; // the latest pool shown; an earlier one still preparing gives way
    this.still = Promise.resolve(); // resolves once the latest re-sort has ended
    this.tweens = []; // the hunt's motions, run by the frame clock
    this.round = 0; // each ending of a pick (endPick) ends every motion of the round before
    this.drifting = true;
    this.placed = new Map(); // "i,j" -> the film a hunt placed in that cell
    this.landed = null; // the cell a hunt landed on
    this.lifted = null; // the landed cell while its poster has left the wall, as "i,j"
    this.last = performance.now();
    window.addEventListener("resize", () => this.relayout(null, null));
    requestAnimationFrame((t) => this.frame(t));
  }

  // Show a pool. `resting` sets the posters to the size they keep through the pick, whatever the
  // pool's size. A wall already showing films re-sorts in place: it prepares the posters the new
  // layout puts on screen and waits, briefly, until their pictures can be drawn; then the films still
  // in the running slide into their new places and the dropped ones shrink and fade where they stand.
  // Under reduced motion it changes without sliding. `whenStill()` resolves once that has ended.
  show(pool, { resting = false } = {}) {
    this.endPick();
    const { ranks, order } = rankPool(this.ranks, pool, Math.random);
    this.ranks = ranks;
    const token = {};
    this.showing = token;
    const next = this.measure(order.length, resting);
    if (!this.layout?.films || !order.length) {
      this.setPool(order, resting);
      this.relayout(next, null);
      this.still = Promise.resolve();
      return;
    }
    const cam = this.camFor(next, resortAnchor(this.onScreen(), order, next));
    const tiles = this.makeTiles(next);
    this.still = this.prepare(tiles, next, order, cam).then(() => {
      if (this.showing !== token) return undefined;
      const before = this.onScreen();
      const was = { layout: this.layout, cam: { ...this.cam }, order: this.order };
      const old = this.tiles;
      this.setPool(order, resting);
      this.relayout(next, cam, tiles);
      if (!lessMotion.matches) return this.resort(before, was, old);
      for (const tile of old) tile.img.remove();
      return undefined;
    });
  }

  clear() {
    this.endPick();
    this.showing = {};
    this.setPool([], this.resting);
    this.relayout(this.measure(0, this.resting), null);
    this.still = Promise.resolve();
  }

  // Resolves once the wall has finished moving to the latest pool it was shown.
  whenStill() {
    return this.still;
  }

  // Ends a hunt and everything a pick left on the wall: its motions stop where they are, the landed
  // cell is forgotten and the wall drifts again. A film a hunt placed stays in its cell until a new
  // pool's tiles take over, so no poster on screen changes film when the viewer leaves.
  endPick() {
    this.round += 1;
    this.drifting = true;
    this.landed = null;
    this.lifted = null;
    this.dirty = true;
  }

  // Runs `apply(ease(t))` each frame for `ms`, t from 0 to 1. Resolves true when it ends, or false when
  // a new pool or a cleared wall ended it first.
  tween(ms, apply, ease = (t) => t) {
    return new Promise((done) => this.tweens.push({ start: performance.now(), ms, apply, ease, done, round: this.round }));
  }

  runTweens(now) {
    this.tweens = this.tweens.filter((tw) => {
      if (tw.round !== this.round) {
        tw.done(false);
        return false;
      }
      const t = tw.ms > 0 ? Math.min(1, Math.max(0, (now - tw.start) / tw.ms)) : 1;
      tw.apply(tw.ease(t));
      if (t < 1) return true;
      tw.done(true);
      return false;
    });
  }

  // Centres the camera on column `i`, row `j`, which may be fractional.
  aim(i, j) {
    this.cam = centreOf({ i, j }, this.layout);
  }

  // The hunt for film `id`. It waits for any re-sort to end and until `notBefore` (a
  // performance.now() time), then stops the drift, calls `onStop`, and eases forward to the next
  // whole row; it plans every hop, places the film in the cell the last hop lands on (a cell off the
  // screen until the hunt brings it in), and plays the hops. Resolves to the pause the plan gives
  // after the last hop, in seconds, or null when the pick was ended (`endPick`, a new pool or a
  // cleared wall) at any point. Under reduced motion the camera jumps straight to the landing cell.
  // The camera is steered in cells, so a window resized mid-hunt only rescales it.
  async hunt(id, { rand = Math.random, notBefore = 0, onStop = () => {} } = {}) {
    const round = this.round;
    if (!(await this.readyToHunt(round, notBefore))) return null;
    this.lift(false);
    this.drifting = false;
    onStop();
    const from = await this.settle();
    if (!from || round !== this.round) return null;
    const plan = planHunt({ n: hopCount(rand), rand, layout: this.layout, from });
    this.placed = new Map([...this.placed, ...placeLanding(plan, id)]);
    this.dirty = true;
    this.request(`/img/poster/${id}/${this.size}`);
    if (lessMotion.matches) {
      this.aim(plan.landing.i, plan.landing.j);
      this.landed = plan.landing;
      return 0;
    }
    return this.hop(plan, from);
  }

  // Whether the pick of `round` may start its hunt: once any re-sort has ended and `notBefore` has
  // passed, and only while the pick has not been ended and the wall has films.
  async readyToHunt(round, notBefore) {
    await this.whenStill();
    if (round !== this.round || !this.layout?.films) return false;
    return this.tween(Math.max(0, notBefore - performance.now()), () => {});
  }

  // Eases the camera forward to the next whole row in the drift's direction and resolves to that
  // cell, or to null when the pick was ended meanwhile. Under reduced motion it moves at once.
  async settle() {
    const L = this.layout;
    const row = (this.cam.y - L.h / 2) / L.sy;
    const from = camCell(L, settledCamera(this.cam, L));
    if (!lessMotion.matches) {
      const eased = await this.tween(SETTLE_S * 1000, (t) => this.aim(from.i, row + (from.j - row) * t), SETTLE_EASE);
      if (!eased) return null;
    }
    this.aim(from.i, from.j);
    return from;
  }

  async hop(plan, from) {
    let at = from;
    for (const [k, hop] of plan.hops.entries()) {
      const start = at;
      const moved = await this.tween(hop.seconds * 1000, (t) => {
        const cell = hopCell(start, hop, t);
        this.aim(cell.i, cell.j);
      });
      if (!moved) return null;
      at = hop.to;
      this.aim(at.i, at.j);
      const last = k === plan.hops.length - 1;
      if (!last && !(await this.tween(hop.pause * 1000, () => {}))) return null;
    }
    this.landed = plan.landing;
    return plan.hops.at(-1).pause;
  }

  // The landed poster's element, or null when no hunt has landed.
  landedTile() {
    if (!this.landed) return null;
    return this.tiles.find((tile) => tile.i === this.landed.i && tile.j === this.landed.j) || null;
  }

  // Takes the landed poster off the wall while it rests on the page, or, with `away` false, puts it back.
  lift(away) {
    this.lifted = away && this.landed ? `${this.landed.i},${this.landed.j}` : null;
    this.dirty = true;
  }

  // A new pool's tiles take over: the films a hunt placed belong to the tiles they leave.
  setPool(order, resting) {
    this.order = order;
    this.resting = resting;
    this.placed = new Map();
  }

  measure(films, resting) {
    const phone = isPhone();
    return wallLayout(window.innerWidth, window.innerHeight, posterAcross(films, phone, resting), phone, films);
  }

  // The camera for layout `next`: on `anchor`'s centre when one is given, else on the cell the camera
  // stands on now; either way on a column's centre, keeping the part-row it has now.
  camFor(next, anchor) {
    const prev = this.layout;
    const col = prev ? Math.round((this.cam.x - prev.w / 2) / prev.sx) : 0;
    const row = prev ? (this.cam.y - prev.h / 2) / prev.sy : 0;
    const part = row - Math.floor(row);
    return {
      x: (anchor ? anchor.i : col) * next.sx + next.w / 2,
      y: (anchor ? anchor.j + part : row) * next.sy + next.h / 2,
    };
  }

  // Lays the wall out as `next` (or as the pool and window now ask) with the camera at `cam` (or where
  // `camFor` puts it), on `tiles` when given, else on tiles made fresh. The wall's other tiles leave
  // the page, except those a re-sort is about to play as ghosts, which it removes itself.
  relayout(next, cam, tiles = null) {
    const L = next || this.measure(this.order.length, this.resting);
    this.cam = cam || this.camFor(L, null);
    if (!tiles) for (const tile of this.tiles) tile.img.remove();
    this.layout = L;
    this.size = pictureSize(L.w, window.devicePixelRatio || 1);
    this.tiles = tiles || this.makeTiles(L);
    for (const tile of this.tiles) this.layer.append(tile.img);
    this.layer.hidden = !L.films;
    this.corner = null;
    this.place();
  }

  // Enough tiles to cover the screen with a cell to spare on every side, not yet on the page.
  makeTiles(layout) {
    const across = layout.screenCols + 2;
    const down = layout.screenRows + 2;
    return Array.from({ length: across * down }, (_, n) => {
      const img = document.createElement("img");
      img.className = "tile";
      img.alt = "";
      img.src = BLANK;
      img.decoding = "async";
      img.draggable = false;
      img.style.width = `${layout.w}px`;
      img.style.height = `${layout.h}px`;
      return { img, a: n % across, b: Math.floor(n / across), across, down, i: null, j: null, id: null };
    });
  }

  // Lays `tiles` as layout `next` will show them with the camera at `cam`, asks for their pictures,
  // and resolves once every on-screen tile's picture can be drawn, or after PRELOAD_MS.
  async prepare(tiles, next, order, cam) {
    const view = { layout: next, order, size: pictureSize(next.w, window.devicePixelRatio || 1) };
    const shown = new Set(screenCells(next, cam).map(({ i, j }) => `${i},${j}`));
    const start = performance.now();
    this.layTiles(tiles, cam, view);
    const onScreenTiles = tiles.filter((tile) => shown.has(`${tile.i},${tile.j}`));
    const urls = onScreenTiles.map((tile) => `/img/poster/${tile.id}/${view.size}`);
    urls.forEach((url) => this.request(url));
    await within(PRELOAD_MS, urls.map((url) => this.pictures.get(url).settled));
    this.layTiles(tiles, cam, view);
    await within(Math.max(0, PRELOAD_MS - (performance.now() - start)), onScreenTiles.map((tile) => tile.img.decode()));
  }

  layTiles(tiles, cam, view) {
    const L = view.layout;
    const i0 = Math.floor((cam.x - L.vw / 2) / L.sx);
    const j0 = Math.floor((cam.y - L.vh / 2) / L.sy);
    for (const tile of tiles) this.lay(tile, i0 + mod(tile.a - i0, tile.across), j0 + mod(tile.b - j0, tile.down), view);
  }

  frame(now) {
    const dt = Math.min(MAX_STEP_S, (now - this.last) / 1000);
    this.last = now;
    if (this.drifting && !lessMotion.matches) this.cam.y += DRIFT_PX_S * dt;
    if (this.tweens.length) this.runTweens(now);
    this.place();
    requestAnimationFrame((t) => this.frame(t));
  }

  // Moves the layer under the camera and lays each tile on the cell it now covers. Tiles are laid
  // again only when the camera crosses into a new row or column, or a picture has arrived.
  place() {
    const L = this.layout;
    if (!L) return;
    this.layer.style.transform = `translate3d(${L.vw / 2 - this.cam.x}px, ${L.vh / 2 - this.cam.y}px, 0)`;
    const corner = `${Math.floor((this.cam.x - L.vw / 2) / L.sx)},${Math.floor((this.cam.y - L.vh / 2) / L.sy)}`;
    if (corner === this.corner && !this.dirty) return;
    this.corner = corner;
    this.dirty = false;
    this.layTiles(this.tiles, this.cam, { layout: L, order: this.order, size: this.size, placed: this.placed, lifted: this.lifted });
  }

  // Puts `tile` on cell (i, j) of `view.layout` and gives it that cell's picture.
  lay(tile, i, j, view) {
    if (tile.i !== i || tile.j !== j) {
      for (const motion of tile.img.getAnimations()) motion.cancel();
      tile.i = i;
      tile.j = j;
      tile.img.style.transform = `translate(${i * view.layout.sx}px, ${j * view.layout.sy}px)`;
    }
    tile.id = filmAt(view.layout, view.order, view.placed || NONE_PLACED, i, j);
    const src = (tile.id === null ? null : this.picture(tile.id, view.size)) || BLANK;
    if (tile.img.getAttribute("src") !== src) tile.img.src = src;
    tile.img.style.visibility = view.lifted === `${i},${j}` ? "hidden" : "";
  }

  // The url of a film's wall picture at `size` once it has loaded. While it loads, a picture of the
  // film already loaded at another size stands in; with none, or after it failed, null, and the tile
  // stays a dark cell.
  picture(id, size) {
    const url = `/img/poster/${id}/${size}`;
    if (this.request(url)) return url;
    return SIZES.map((other) => `/img/poster/${id}/${other}`).find((other) => this.pictures.get(other)?.ready) || null;
  }

  // Whether the picture at `url` has loaded; asks for it the first time. The entry's `settled`
  // resolves once the picture has loaded or failed.
  request(url) {
    const known = this.pictures.get(url);
    if (known) return known.ready;
    const entry = { ready: false };
    const img = new Image();
    entry.settled = new Promise((done) => {
      img.onload = () => {
        entry.ready = true;
        this.dirty = true;
        done();
      };
      img.onerror = () => done(); // the cell stays dark; the server has logged why
    });
    this.pictures.set(url, entry);
    img.src = url;
    return false;
  }

  // The posters on the screen now, each with its element: film, screen box and img. A re-sort still
  // running ends here, so every poster is where its cell puts it.
  onScreen() {
    const L = this.layout;
    if (!L?.films) return [];
    this.layer.querySelectorAll(".ghost").forEach((ghost) => ghost.remove());
    const shown = [];
    for (const tile of this.tiles) {
      for (const motion of tile.img.getAnimations()) motion.cancel();
      const box = cellBox(L, this.cam, tile);
      if (onScreen(L, box)) shown.push({ id: tile.id, img: tile.img, ...box });
    }
    return shown;
  }

  // Screen px to the layer's own px, which the drift carries.
  toLayer({ x, y }) {
    return { x: x + this.cam.x - this.layout.vw / 2, y: y + this.cam.y - this.layout.vh / 2 };
  }

  // Plays the re-sort from `before` (the posters that were on screen, with their elements) under
  // `was`, onto the tiles now laid; `old` are the tiles the wall had. An old element a new tile arrives
  // from leaves the page at once, as the new tile takes its place; the rest stay behind as ghosts,
  // beneath the new tiles, and leave. Resolves when every motion has ended.
  resort(before, was, old) {
    const plan = resortPlan(before, was, { layout: this.layout, cam: this.cam, order: this.order });
    const leaving = new Set(plan.departures.map((d) => before[d.source].img));
    for (const tile of old) if (!leaving.has(tile.img)) tile.img.remove();
    const byCell = new Map(this.tiles.map((tile) => [`${tile.i},${tile.j}`, tile]));
    const motions = [];
    for (const arrival of plan.arrivals) {
      const tile = byCell.get(`${arrival.cell.i},${arrival.cell.j}`);
      if (tile) motions.push(this.slide(tile.img, arrival.from, cellBox(this.layout, this.cam, arrival.cell)));
    }
    for (const departure of plan.departures) motions.push(this.depart(before[departure.source], departure.to));
    return Promise.all(motions.map((m) => m.finished.catch(() => undefined))).then(() => undefined);
  }

  slide(img, from, to) {
    const b = this.toLayer(to);
    let start;
    if (from) {
      const a = this.toLayer(from);
      start = { transform: `translate(${a.x}px, ${a.y}px) scale(${from.w / to.w}, ${from.h / to.h})` };
    } else {
      const inset = (1 - DROPPED_SCALE) / 2;
      start = { transform: `translate(${b.x + to.w * inset}px, ${b.y + to.h * inset}px) scale(${DROPPED_SCALE})`, opacity: 0 };
    }
    return img.animate([start, { transform: `translate(${b.x}px, ${b.y}px)` }], { duration: RESORT_MS, easing: RESORT_EASE });
  }

  // An old poster leaving the screen on its own element, beneath the new tiles: it slides to `to`,
  // or, with no `to`, shrinks and fades where it stands. Removed when its motion ends.
  depart(shown, to) {
    const { img } = shown;
    img.classList.add("ghost");
    this.layer.prepend(img);
    const a = this.toLayer(shown);
    let end;
    if (to) {
      const b = this.toLayer(to);
      end = { transform: `translate(${b.x}px, ${b.y}px) scale(${to.w / shown.w}, ${to.h / shown.h})` };
    } else {
      const inset = (1 - DROPPED_SCALE) / 2;
      end = { transform: `translate(${a.x + shown.w * inset}px, ${a.y + shown.h * inset}px) scale(${DROPPED_SCALE})`, opacity: 0 };
    }
    img.style.transform = `translate(${a.x}px, ${a.y}px)`;
    const motion = img.animate([{ transform: img.style.transform }, end], { duration: RESORT_MS, easing: RESORT_EASE, fill: "forwards" });
    const leave = () => img.remove();
    motion.finished.then(leave, leave);
    return motion;
  }
}
