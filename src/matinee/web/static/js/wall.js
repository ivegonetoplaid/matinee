// The poster wall: a flat grid of the posters of the films still in the running, each its own image,
// sharp and upright, held at 35 per cent strength. The grid repeats in both directions, so no edge
// ever shows, and it drifts upward while the viewer answers. Each answer re-sorts it in place, and a
// pick hunts across it to the picked film's poster. The posters ignore taps and clicks; a poster
// whose picture has not loaded is a dark cell.

import { isPhone } from "./dom.js";
import { GOLD, posterGlow } from "./glow.js";
import { corsImage, fromTmdb, posterUrl } from "./pictures.js";
import { SETTLE_EASE, SETTLE_S, bezier, centreOf, hopCell, hopCount, placeLanding, planHunt, settledCamera } from "./hunt-plan.js";
import {
  ACROSS,
  besideItself,
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
const RESORT_MS = 1400; // each answer's re-sort
const RESORT_EASE = "cubic-bezier(0.45, 0, 0.25, 1)"; // eases out of place, glides, and settles; never a dash then a crawl
const LANDING_TRIES = 20; // hunt plans tried for a landing cell clear of the picked film's own copies
const PRELOAD_MS = 600; // the re-sort waits this long at most for the posters it brings on screen
const FIRST_MS = 2500; // a wall laid fresh waits this long at most for its pictures before it fades in
const DROPPED_SCALE = 0.5; // a dropped film's poster shrinks to this and fades where it stands
const BLANK = "/static/blank.svg"; // a tile with no picture shows this, so it is a dark cell, never a broken image
const SIZES = ["l", "m", "s", "xs"];
const GROW = 2.4; // the landed poster grows to this many times a poster at the resting size
const GROW_MS = 750;
const GROW_EASE = bezier(0.2, 0.8, 0.2, 1);
const WALL_STRENGTH = 0.35; // the wall's posters, as the stylesheet's --tile holds them
const AWAY_STRENGTH = 0.12; // the rest of the wall once the pick has landed, and behind the resting page
const GLOW_BLUR = 0.25; // the glow's blur, as a share of the poster's width once grown
const GLOW_SPREAD = 0.033; // the glow's spread, likewise
const GLOW_ALPHA = 0.35; // the glow's strength once grown
const GLOW_SAMPLE = [32, 48]; // the poster is read at this size for its colour
const STEP_BACK_MS = 350; // the wall dimming for a resting page that has no poster to bring forward
const RETURN_MS = 450; // "Not that one" carries the resting poster back to its cell
const LANDED_DRAW_MS = 1000; // under reduced motion, the jump waits at most this long for the landed picture
const NONE_PLACED = new Map();

const lessMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

// The glow colour of the picture `img` draws. A picture whose pixels cannot be read glows gold, and
// the failure is logged.
function glowOf(img) {
  if (!img?.naturalWidth || img.naturalWidth <= 1) return GOLD;
  try {
    const canvas = document.createElement("canvas");
    [canvas.width, canvas.height] = GLOW_SAMPLE;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    context.drawImage(img, 0, 0, canvas.width, canvas.height);
    return posterGlow(context.getImageData(0, 0, canvas.width, canvas.height).data);
  } catch (err) {
    console.warn("the poster's glow colour could not be read; it glows gold", err);
    return GOLD;
  }
}

// The box, in layer px, of cell (i, j) grown `scale` times about its centre.
function grownBox(i, j, layout, scale) {
  return {
    x: i * layout.sx - (layout.w * (scale - 1)) / 2,
    y: j * layout.sy - (layout.h * (scale - 1)) / 2,
    w: layout.w * scale,
    h: layout.h * scale,
  };
}

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
    this.paths = new Map(); // film id -> its TMDB poster path, when TMDB is the image source
    this.fromTmdb = false; // TMDB is the image source
    this.ranks = new Map(); // film id -> its place in this page's order, drawn at random once
    this.order = [];
    this.resting = false;
    this.layout = null;
    this.cam = { x: 0, y: 0 }; // the point of the wall at the screen's centre, in px
    this.liftRows = 0; // during a pick, how many rows below its aim the camera stands, so the aim sits higher
    this.corner = null; // the top-left cell the tiles are laid from, as "i,j"
    this.dirty = false; // a picture arrived: tiles showing a dark cell look again
    this.showing = null; // the latest pool shown; an earlier one still preparing gives way
    this.still = Promise.resolve(); // resolves once the latest re-sort, or a poster's return, has ended
    this.tweens = []; // the hunt's motions, run by the frame clock
    this.round = 0; // each ending of a pick (endPick) ends every motion of the round before
    this.drifting = true;
    this.placed = new Map(); // "i,j" -> the film a hunt placed in that cell
    this.landed = null; // the cell a hunt landed on
    this.lifted = null; // the landed cell while its poster has left the wall, as "i,j"
    this.look = null; // how the landed poster is shown: { lit, scale }, strength and size
    // The landed poster's sharper picture, on its own element over the landed cell, shown only once it
    // has decoded; until then the tile beneath keeps drawing the wall's picture.
    this.front = corsImage(document.createElement("img"));
    this.front.className = "tile front";
    this.front.alt = "";
    this.front.hidden = true;
    this.frontCell = null; // the landed cell the front element's picture belongs to, once it has decoded
    this.glow = GOLD; // the landed poster's glow colour, [r, g, b]
    this.last = performance.now();
    window.addEventListener("resize", () => this.relayout(null, null));
    requestAnimationFrame((t) => this.frame(t));
  }

  // Takes the image source and the TMDB poster paths the wall's pictures load from, before the first pool
  // is shown.
  usePictures(paths, tmdb) {
    this.paths = paths;
    this.fromTmdb = tmdb;
  }

  // The address of film `id`'s poster at `size`.
  posterUrl(id, size) {
    return posterUrl(this.paths, id, size);
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
      this.still = this.fadeIn();
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

  // A wall laid fresh stays unseen until its tiles' pictures can be drawn, or for FIRST_MS, then fades
  // in whole (the stylesheet's .waiting), so it never fills in a cell at a time.
  async fadeIn() {
    if (!this.layout.films) return;
    this.layer.classList.add("waiting");
    const urls = this.tiles.filter((tile) => tile.id !== null).map((tile) => this.posterUrl(tile.id, this.size));
    await within(FIRST_MS, urls.map((url) => this.pictures.get(url)?.settled));
    this.layer.classList.remove("waiting");
  }

  clear() {
    this.endPick();
    this.showing = {};
    this.setPool([], this.resting);
    this.relayout(this.measure(0, this.resting), null);
    this.still = Promise.resolve();
  }

  // Resolves once the wall has finished moving: to the latest pool it was shown, and any poster's return.
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
    this.look = null;
    this.liftRows = 0;
    this.glow = GOLD;
    this.frontCell = null;
    this.front.hidden = true;
    this.layer.style.removeProperty("--tile");
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
    this.cam = centreOf({ i, j: j + this.liftRows }, this.layout);
  }

  // The hunt for film `id`. It waits for any re-sort to end and until `notBefore` (a
  // performance.now() time), then stops the drift, calls `onStop`, and eases forward to the next
  // whole row; it plans every hop, places the film in the cell the last hop lands on (a cell off the
  // screen until the hunt brings it in), and plays the hops. Resolves to the pause the plan gives
  // after the last hop, in seconds, or null when the pick was ended (`endPick`, a new pool or a
  // cleared wall) at any point. Under reduced motion the camera jumps straight to the landing cell.
  // The camera is steered in cells, so a window resized mid-hunt only rescales it.
  async hunt(id, { rand = Math.random, notBefore = 0, onStop = () => {}, lift = 0 } = {}) {
    const round = this.round;
    if (!(await this.readyToHunt(round, notBefore))) return null;
    this.lift(false);
    this.drifting = false;
    onStop();
    const from = await this.settle(lift);
    if (!from || round !== this.round) return null;
    const plan = this.planClearOf(id, from, rand);
    this.placed = new Map([...this.placed, ...placeLanding(plan, id)]);
    this.dirty = true;
    this.request(this.posterUrl(id, this.size));
    if (lessMotion.matches) return this.jump(plan, round);
    return this.hop(plan, from);
  }

  // A hunt plan whose landing cell has no copy of film `id` in the eight cells around it, so the picked
  // film never lands beside itself. Tries up to LANDING_TRIES plans; a pool too small to allow it takes
  // the last.
  planClearOf(id, from, rand) {
    let plan = null;
    for (let k = 0; k < LANDING_TRIES; k += 1) {
      plan = planHunt({ n: hopCount(rand), rand, layout: this.layout, from });
      if (!besideItself(this.layout, this.order, this.placed, plan.landing, id)) return plan;
    }
    return plan;
  }

  // Under reduced motion: the camera moves to the landing cell at once, and the jump ends once the
  // landed tile can draw the picked film's picture (or after LANDED_DRAW_MS), so it never shows the
  // film the cell held before. Resolves to 0, the pause, or null when the pick was ended meanwhile.
  async jump(plan, round) {
    this.aim(plan.landing.i, plan.landing.j);
    this.landed = plan.landing;
    this.place();
    const img = this.landedTile()?.img;
    if (img) await within(LANDED_DRAW_MS, [img.decode()]);
    return round === this.round ? 0 : null;
  }

  // Whether the pick of `round` may start its hunt: once any re-sort has ended and `notBefore` has
  // passed, and only while the pick has not been ended and the wall has films.
  async readyToHunt(round, notBefore) {
    await this.whenStill();
    if (round !== this.round || !this.layout?.films) return false;
    return this.tween(Math.max(0, notBefore - performance.now()), () => {});
  }

  // Eases the camera forward to the next whole row in the drift's direction and resolves to that
  // cell, or to null when the pick was ended meanwhile. Over the same ease the aim rises `lift` px above
  // the screen's centre, where the hunt then lands. Under reduced motion it moves at once.
  async settle(lift = 0) {
    const L = this.layout;
    const was = this.liftRows;
    const to = lift / L.sy;
    const base = { x: this.cam.x, y: this.cam.y - was * L.sy }; // the camera's aim, without its lift
    const row = (base.y - L.h / 2) / L.sy;
    const from = camCell(L, settledCamera(base, L));
    if (!lessMotion.matches) {
      const eased = await this.tween(
        SETTLE_S * 1000,
        (t) => {
          this.liftRows = was + (to - was) * t;
          this.aim(from.i, row + (from.j - row) * t);
        },
        SETTLE_EASE,
      );
      if (!eased) return null;
    }
    this.liftRows = to;
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

  // Holds the rest of the wall at `strength` (0 to 1).
  dim(strength) {
    this.layer.style.setProperty("--tile", String(strength));
  }

  // Dims the wall to the strength it keeps behind the resting page, over STEP_BACK_MS (at once under
  // reduced motion).
  stepBack() {
    if (lessMotion.matches) return this.dim(AWAY_STRENGTH);
    return this.tween(STEP_BACK_MS, (t) => this.dim(WALL_STRENGTH + (AWAY_STRENGTH - WALL_STRENGTH) * t));
  }

  // How many times its wall size the landed poster grows: to GROW times a resting-size poster, whatever
  // the size of the wall's posters when the pick began.
  grownScale() {
    const resting = window.innerWidth / (isPhone() ? ACROSS.phone.fewest : ACROSS.desktop.fewest);
    return (GROW * resting) / this.layout.w;
  }

  // Whether the landed poster can draw a picture of its film fit to grow: its sharper picture has decoded,
  // or its tile has drawn the wall's picture at the wall's size. A smaller picture standing in, or the
  // blank of a dark cell, does not count.
  landedHasPicture() {
    if (this.frontCell) return true;
    const tile = this.landedTile();
    const img = tile?.img;
    const own = tile && this.posterUrl(tile.id, this.size);
    return Boolean(img && img.getAttribute("src") === own && img.complete && img.naturalWidth > 1);
  }

  // Puts `url`, the landed poster's sharper picture, on the front element and shows it over the landed
  // cell, in the same box, once it has decoded there. Resolves once it shows, or when it cannot.
  async useSharp(url) {
    const cell = this.landed && `${this.landed.i},${this.landed.j}`;
    if (!cell) return;
    this.front.src = url;
    try {
      await this.front.decode();
    } catch {
      return; // the picture failed; the wall's own picture stays, and request() or picture() has logged why
    }
    if (!this.landed || `${this.landed.i},${this.landed.j}` !== cell) return;
    this.frontCell = cell;
    this.glow = glowOf(this.front);
    this.dirty = true;
  }

  // Brings the landed poster forward: over `pause` seconds it brightens to full strength while the rest
  // of the wall dims halfway to AWAY_STRENGTH; then over GROW_MS it grows in place to its grown size
  // while the wall dims the rest of the way. Under reduced motion it is shown grown at once. Resolves
  // true when it ends, or false when the pick was ended first.
  async bringForward(pause) {
    const grown = this.grownScale();
    this.grown = grown;
    if (!this.frontCell) this.glow = glowOf(this.landedTile()?.img);
    const half = WALL_STRENGTH + (AWAY_STRENGTH - WALL_STRENGTH) / 2;
    const show = (lit, scale, away) => {
      this.look = { lit, scale };
      this.dim(away);
      this.dirty = true;
    };
    if (lessMotion.matches) {
      show(1, grown, AWAY_STRENGTH);
      return true;
    }
    const lit = await this.tween(pause * 1000, (t) => show(WALL_STRENGTH + (1 - WALL_STRENGTH) * t, 1, WALL_STRENGTH + (half - WALL_STRENGTH) * t));
    if (!lit) return false;
    return this.tween(GROW_MS, (t) => show(1, 1 + (grown - 1) * t, half + (AWAY_STRENGTH - half) * t), GROW_EASE);
  }

  // Dresses the landed poster as `look` says, or returns a poster that was dressed to the wall's own.
  // It grows about its centre, above its neighbours, by its laid-out size rather than a scale, so its
  // picture stays sharp. The front element, once its picture has decoded, is dressed over it the same.
  dress(tile, i, j, layout) {
    const cell = `${i},${j}`;
    const landed = Boolean(this.landed && this.look && `${this.landed.i},${this.landed.j}` === cell);
    if (!landed && !tile.dressed) return;
    tile.dressed = landed;
    if (!landed) {
      tile.img.style.boxShadow = "";
      return this.fit(tile.img, grownBox(i, j, layout, 1), null, "");
    }
    const box = grownBox(i, j, layout, this.look.scale);
    this.fit(tile.img, box, this.look.lit, "1");
    tile.img.style.boxShadow = this.glowShadow(box);
    const front = this.frontCell === cell;
    this.front.hidden = !front || this.lifted === cell;
    if (front) this.fit(this.front, box, this.look.lit, "2");
    return undefined;
  }

  // The landed poster's glow for a poster in `box`: its colour, sized from the poster's width and grown
  // in with it, so a phone's glow stays around the poster.
  glowShadow(box) {
    const g = this.grown > 1 ? Math.min(1, Math.max(0, (this.look.scale - 1) / (this.grown - 1))) : 1;
    return this.glowAt(box.w, g);
  }

  // The landed poster's glow for a poster `w` px wide, at `g` (0 to 1) of its full strength. The poster
  // at rest keeps it at full strength.
  glowAt(w, g = 1) {
    const [r, gr, b] = this.glow;
    const blur = Math.round(w * GLOW_BLUR * g);
    const spread = Math.round(w * GLOW_SPREAD * g);
    return `0 0 ${blur}px ${spread}px rgba(${r}, ${gr}, ${b}, ${(GLOW_ALPHA * g).toFixed(3)})`;
  }

  // Lays `img` in `box` (layer px) at strength `lit` (null: the wall's own), stacked at `z`.
  fit(img, box, lit, z) {
    img.style.transform = `translate(${box.x}px, ${box.y}px)`;
    img.style.width = `${box.w}px`;
    img.style.height = `${box.h}px`;
    img.style.opacity = lit === null ? "" : String(lit);
    img.style.zIndex = z;
  }

  // "Not that one": carries `img`, the poster resting on the page, from where it rests back to its cell
  // on the wall over RETURN_MS, at the wall's size and strength, while the wall's dimming lifts; then
  // the cell shows its poster again and the wall drifts. The element itself moves onto the wall, so
  // its picture never has to be drawn again. The next hunt waits for it. Resolves when it has ended.
  putBack(img) {
    const done = this.returnPoster(img, this.landed);
    this.still = Promise.all([this.still, done]);
    return done;
  }

  async returnPoster(img, cell) {
    const from = img?.getBoundingClientRect();
    this.look = null;
    this.frontCell = null;
    this.front.hidden = true;
    this.dirty = true;
    if (!cell || !from?.width || lessMotion.matches) {
      img?.remove();
      return this.liftDim(cell);
    }
    img.getAnimations().forEach((motion) => motion.cancel());
    img.removeAttribute("style");
    img.className = "tile";
    const screen = { x: from.left, y: from.top, w: from.width, h: from.height };
    this.fit(img, { ...this.toLayer(screen), w: screen.w, h: screen.h }, 1, "3");
    this.layer.append(img);
    const between = (a, b, t) => a + (b - a) * t;
    // Both ends are worked out each frame, so a window resized mid-return still lands in the cell.
    const moved = await this.tween(
      RETURN_MS,
      (t) => {
        const start = { ...this.toLayer(screen), w: screen.w, h: screen.h };
        const end = grownBox(cell.i, cell.j, this.layout, 1);
        const box = { x: between(start.x, end.x, t), y: between(start.y, end.y, t), w: between(start.w, end.w, t), h: between(start.h, end.h, t) };
        this.fit(img, box, between(1, WALL_STRENGTH, t), "3");
        this.dim(between(AWAY_STRENGTH, WALL_STRENGTH, t));
      },
      GROW_EASE,
    );
    img.remove();
    if (moved) this.settleBack();
    return undefined;
  }

  // With no poster to carry back (none rested, or reduced motion), the dimming lifts over RETURN_MS
  // (at once under reduced motion) before the wall drifts again.
  async liftDim(cell) {
    if (cell && !lessMotion.matches) {
      const lifted = await this.tween(RETURN_MS, (t) => this.dim(AWAY_STRENGTH + (WALL_STRENGTH - AWAY_STRENGTH) * t));
      if (!lifted) return;
    }
    this.settleBack();
  }

  // The returned poster is back in its cell, the dimming lifted and the wall drifting. The wall is laid
  // at once, so the cell shows its poster in the same frame the returning one leaves.
  settleBack() {
    this.lift(false);
    this.landed = null;
    this.drifting = true;
    this.layer.style.removeProperty("--tile");
    this.place();
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
    this.layer.append(this.front);
    this.layer.hidden = !L.films;
    this.corner = null;
    this.place();
  }

  // Enough tiles to cover the screen with a cell to spare on every side, not yet on the page.
  makeTiles(layout) {
    const across = layout.screenCols + 2;
    const down = layout.screenRows + 2;
    return Array.from({ length: across * down }, (_, n) => {
      const img = corsImage(document.createElement("img"));
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
    const urls = onScreenTiles.map((tile) => this.posterUrl(tile.id, view.size));
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
    const view = { layout: L, order: this.order, size: this.size, placed: this.placed, lifted: this.lifted };
    this.layTiles(this.tiles, this.cam, view);
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
    if (view.placed) this.dress(tile, i, j, view.layout);
  }

  // The url of a film's wall picture at `size` once it has loaded. While it loads, a picture of the
  // film already loaded at another size stands in; with none, or after it failed, null, and the tile
  // stays a dark cell.
  picture(id, size) {
    const url = this.posterUrl(id, size);
    if (this.request(url)) return url;
    return SIZES.map((other) => this.posterUrl(id, other)).find((other) => this.pictures.get(other)?.ready) || null;
  }

  // Whether the picture at `url` has loaded; asks for it the first time. The entry's `settled`
  // resolves once the picture has loaded or failed.
  request(url) {
    const known = this.pictures.get(url);
    if (known) return known.ready;
    const entry = { ready: false };
    const img = corsImage();
    entry.settled = new Promise((done) => {
      img.onload = () => {
        entry.ready = true;
        this.dirty = true;
        done();
      };
      // The cell stays dark. The server logs an image route failure; a TMDB one is logged here.
      img.onerror = () => {
        if (fromTmdb(url)) console.warn("a poster from TMDB's image server failed to load", url);
        done();
      };
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
