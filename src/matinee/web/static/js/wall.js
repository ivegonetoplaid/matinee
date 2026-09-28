// The poster wall: a flat grid of the posters of the films still in the running, each its own image,
// sharp and upright, held at 35 per cent strength. The grid repeats in both directions, so no edge
// ever shows, and it drifts upward while the viewer answers. The posters ignore taps and clicks; a
// poster whose picture has not loaded is a dark cell.

import { isPhone } from "./dom.js";
import { filmIndex, mod, pictureSize, posterAcross, wallLayout } from "./wall-grid.js";

const DRIFT_PX_S = 10; // upward, timed by the clock, never by frames
const MAX_STEP_S = 0.25; // a frame after a long pause (a hidden tab) moves the wall no further than this

const BLANK = "/static/blank.svg"; // a tile with no picture shows this, so it is a dark cell, never a broken image
const SIZES = ["l", "m", "s"];

const lessMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

function shuffled(ids) {
  const copy = ids.slice();
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

export class Wall {
  constructor(root) {
    this.root = root;
    this.layer = document.createElement("div");
    this.layer.className = "wall-tiles";
    root.append(this.layer);
    this.tiles = [];
    this.pictures = new Map(); // picture url -> { ready, failed }
    this.rank = new Map(); // film id -> its place in this page's order, drawn at random once
    this.order = [];
    this.resting = false;
    this.layout = null;
    this.cam = { x: 0, y: 0 }; // the point of the wall at the screen's centre, in px
    this.corner = null; // the top-left cell the tiles are laid from, as "i,j"
    this.dirty = false; // a picture arrived: tiles showing a dark cell look again
    this.last = performance.now();
    window.addEventListener("resize", () => this.relayout());
    requestAnimationFrame((t) => this.frame(t));
  }

  // Show a pool. `resting` sets the posters to the size they keep through the pick, whatever the
  // pool's size.
  show(pool, { resting = false } = {}) {
    this.order = this.ordered(pool);
    this.resting = resting;
    this.relayout();
  }

  clear() {
    this.order = [];
    this.relayout();
  }

  // The pool in this page's order. A film is given its place the first time the wall sees it, at
  // random, so every visit's wall is dealt differently while a narrower pool keeps its films in
  // the order they already had.
  ordered(pool) {
    for (const id of shuffled(pool.filter((id) => !this.rank.has(id)))) this.rank.set(id, this.rank.size);
    return pool.slice().sort((a, b) => this.rank.get(a) - this.rank.get(b));
  }

  relayout() {
    const phone = isPhone();
    const across = posterAcross(this.order.length, phone, this.resting);
    const next = wallLayout(window.innerWidth, window.innerHeight, across, phone, this.order.length);
    const prev = this.layout;
    // The camera keeps its place in cells, on a column's centre.
    const col = prev ? Math.round((this.cam.x - prev.w / 2) / prev.sx) : 0;
    const row = prev ? (this.cam.y - prev.h / 2) / prev.sy : 0;
    this.cam.x = col * next.sx + next.w / 2;
    this.cam.y = row * next.sy + next.h / 2;
    this.layout = next;
    this.size = pictureSize(next.w, window.devicePixelRatio || 1);
    this.buildTiles();
    this.layer.hidden = !next.films;
    this.corner = null;
    this.place();
  }

  buildTiles() {
    const L = this.layout;
    const across = L.screenCols + 2;
    const down = L.screenRows + 2;
    while (this.tiles.length < across * down) {
      const img = document.createElement("img");
      img.className = "tile";
      img.alt = "";
      img.src = BLANK;
      img.decoding = "async";
      img.draggable = false;
      this.layer.append(img);
      this.tiles.push({ img });
    }
    while (this.tiles.length > across * down) this.tiles.pop().img.remove();
    this.tiles.forEach((tile, n) => {
      Object.assign(tile, { a: n % across, b: Math.floor(n / across), i: null, j: null, id: null });
      tile.img.style.width = `${L.w}px`;
      tile.img.style.height = `${L.h}px`;
    });
    this.across = across;
    this.down = down;
  }

  frame(now) {
    const dt = Math.min(MAX_STEP_S, (now - this.last) / 1000);
    this.last = now;
    if (!lessMotion.matches) this.cam.y += DRIFT_PX_S * dt;
    this.place();
    requestAnimationFrame((t) => this.frame(t));
  }

  // Moves the layer under the camera and lays each tile on the cell it now covers. Tiles are laid
  // again only when the camera crosses into a new row or column, or a picture has arrived.
  place() {
    const L = this.layout;
    if (!L) return;
    this.layer.style.transform = `translate3d(${L.vw / 2 - this.cam.x}px, ${L.vh / 2 - this.cam.y}px, 0)`;
    const i0 = Math.floor((this.cam.x - L.vw / 2) / L.sx);
    const j0 = Math.floor((this.cam.y - L.vh / 2) / L.sy);
    const corner = `${i0},${j0}`;
    if (corner === this.corner && !this.dirty) return;
    this.corner = corner;
    this.dirty = false;
    for (const tile of this.tiles) this.lay(tile, i0 + mod(tile.a - i0, this.across), j0 + mod(tile.b - j0, this.down));
  }

  lay(tile, i, j) {
    const L = this.layout;
    if (tile.i !== i || tile.j !== j) {
      tile.i = i;
      tile.j = j;
      tile.img.style.transform = `translate(${i * L.sx}px, ${j * L.sy}px)`;
    }
    tile.id = L.films ? this.order[filmIndex(L, i, j)] : null;
    const src = (tile.id === null ? null : this.picture(tile.id)) || BLANK;
    if (tile.img.getAttribute("src") !== src) tile.img.src = src;
  }

  // The url of a film's wall picture once it has loaded. While it loads, a picture of the film
  // already loaded at another size stands in; with none, or after it failed, null, and the tile
  // stays a dark cell.
  picture(id) {
    const url = `/img/poster/${id}/${this.size}`;
    if (this.request(url)) return url;
    return SIZES.map((size) => `/img/poster/${id}/${size}`).find((other) => this.pictures.get(other)?.ready) || null;
  }

  // Whether the picture at `url` has loaded; asks for it the first time.
  request(url) {
    const known = this.pictures.get(url);
    if (known) return known.ready;
    const entry = { ready: false };
    this.pictures.set(url, entry);
    const img = new Image();
    img.onload = () => {
      entry.ready = true;
      this.dirty = true;
    };
    img.src = url;
    return false;
  }
}
