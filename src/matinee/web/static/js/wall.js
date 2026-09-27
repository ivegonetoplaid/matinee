// The poster wall: the posters of the films still in the running, laid on a
// floor in perspective, blurred on the poster layer itself and frosted. Poster
// size follows the number of films left; each change of pool shuffles the
// floor, which slides and turns with a short motion blur and never dims.

import { isPhone, prefersLessMotion } from "./dom.js";

// Posters across the viewport width: many at the full pool, the resting size at the pick.
const ACROSS = { desktop: { most: 22, fewest: 9 }, phone: { most: 14, fewest: 6 } };
const POOL_FULL = 1200;
const POOL_NARROW = 40;
const GAP = { desktop: 10, phone: 6 };
const UNIQUE_POSTERS = { desktop: 72, phone: 40 };
const MAX_CANVAS_PX = 2400; // the layer is blurred, so a lower drawing resolution is invisible
const SETTLE_MS = 700;
// The glide to the pick: far across the floor in a random direction, within the slack the grid
// keeps beyond the plane's edge (20% of the plane each side), so no edge ever shows.
const TRAVEL_MS = 1400;
const REACH = { desktop: [760, 620], phone: [190, 480] }; // px along the floor, across and deep
const REDRAW_EVERY_MS = 150;

function across(poolSize, phone) {
  const range = phone ? ACROSS.phone : ACROSS.desktop;
  if (poolSize <= 0) return range.fewest;
  const t = Math.log(Math.max(poolSize, POOL_NARROW) / POOL_NARROW) / Math.log(POOL_FULL / POOL_NARROW);
  return Math.round(range.fewest + (range.most - range.fewest) * Math.min(1, t));
}

function sample(ids, n) {
  const copy = ids.slice();
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy.slice(0, n);
}

export class Wall {
  constructor(root) {
    this.root = root;
    this.grids = [...root.querySelectorAll(".grid")];
    this.images = new Map();
    this.ids = [];
    this.pool = [];
    this.pickedIds = [];
    this.seed = 0;
    this.redrawTimer = null;
    this.across = 0;
    window.addEventListener("resize", () => this.draw());
  }

  poster(id) {
    let img = this.images.get(id);
    if (!img) {
      img = new Image();
      img.decoding = "async";
      img.onload = () => this.scheduleRedraw();
      img.onerror = () => this.images.delete(id); // asked for again the next time the wall needs it
      img.src = `/img/poster/${id}/s`;
      this.images.set(id, img);
    }
    return img;
  }

  scheduleRedraw() {
    if (this.redrawTimer) return;
    this.redrawTimer = setTimeout(() => {
      this.redrawTimer = null;
      this.draw();
    }, REDRAW_EVERY_MS);
  }

  // Show a pool. `shuffle` slides the floor to a new place, as each answer does.
  show(pool, { shuffle = true, spotlight = false } = {}) {
    this.pool = pool;
    const phone = isPhone();
    const range = phone ? ACROSS.phone : ACROSS.desktop;
    this.across = spotlight ? range.fewest : across(pool.length, phone);
    this.pickedIds = sample(pool, phone ? UNIQUE_POSTERS.phone : UNIQUE_POSTERS.desktop);
    this.pickedIds.forEach((id) => this.poster(id));
    if (shuffle) this.move();
    this.draw();
  }

  clear() {
    this.pool = [];
    this.pickedIds = [];
    this.draw();
  }

  move() {
    for (const grid of this.grids) grid.style.removeProperty("--shuffle");
    this.seed += 1;
    const drift = (this.seed % 3) - 1;
    const phone = isPhone();
    const scale = phone ? 0.35 : 1;
    for (const grid of this.grids) {
      grid.style.setProperty("--gx", `${drift * 140 * scale}px`);
      grid.style.setProperty("--gy", `${((this.seed % 2) * 2 - 1) * 80 * scale}px`);
      grid.style.setProperty("--turn", `${drift * (phone ? 2 : 4)}deg`);
    }
    if (prefersLessMotion()) return;
    this.root.classList.add("moving");
    clearTimeout(this.settleTimer);
    this.settleTimer = setTimeout(() => this.root.classList.remove("moving"), SETTLE_MS);
  }

  // A long glide to somewhere else on the floor, as if going to fetch one poster in particular.
  // Returns how long it takes, which is nothing under reduced motion.
  travel() {
    const [across, deep] = isPhone() ? REACH.phone : REACH.desktop;
    const angle = Math.random() * 2 * Math.PI;
    const reach = 0.7 + Math.random() * 0.3;
    for (const grid of this.grids) {
      grid.style.setProperty("--shuffle", `${TRAVEL_MS}ms`);
      grid.style.setProperty("--gx", `${Math.round(Math.cos(angle) * across * reach)}px`);
      grid.style.setProperty("--gy", `${Math.round(Math.sin(angle) * deep * reach)}px`);
    }
    if (prefersLessMotion()) return 0;
    this.root.classList.add("moving");
    clearTimeout(this.settleTimer);
    this.settleTimer = setTimeout(() => this.root.classList.remove("moving"), TRAVEL_MS - 300);
    return TRAVEL_MS;
  }

  draw() {
    const [first, ...rest] = this.grids;
    if (!first) return;
    const cssW = first.clientWidth;
    const cssH = first.clientHeight;
    if (!cssW || !cssH) return;
    const res = Math.min(1, MAX_CANVAS_PX / cssW);
    const width = Math.round(cssW * res);
    const height = Math.round(cssH * res);
    if (first.width !== width || first.height !== height) {
      for (const grid of this.grids) {
        grid.width = width;
        grid.height = height;
      }
    }
    const ctx = first.getContext("2d");
    ctx.fillStyle = "#07080d";
    ctx.fillRect(0, 0, width, height);
    this.tile(ctx, res, cssW, cssH);
    for (const grid of rest) {
      const other = grid.getContext("2d");
      other.clearRect(0, 0, width, height);
      other.drawImage(first, 0, 0);
    }
  }

  tile(ctx, res, cssW, cssH) {
    if (!this.pickedIds.length) return;
    const phone = isPhone();
    const gap = phone ? GAP.phone : GAP.desktop;
    const posterW = window.innerWidth / this.across;
    const posterH = posterW * 1.5;
    const cols = Math.ceil(cssW / (posterW + gap));
    const rows = Math.ceil(cssH / (posterH + gap));
    const offset = this.seed * 17;
    const n = this.pickedIds.length;
    for (let r = 0; r < rows; r += 1) {
      for (let c = 0; c < cols; c += 1) {
        const i = r * cols + c;
        const img = this.images.get(this.pickedIds[(i * 37 + 11 + offset) % n]);
        const x = c * (posterW + gap) * res;
        const y = r * (posterH + gap) * res;
        if (img && img.complete && img.naturalWidth) {
          ctx.drawImage(img, x, y, posterW * res, posterH * res);
        } else {
          ctx.fillStyle = "#161826";
          ctx.fillRect(x, y, posterW * res, posterH * res);
        }
      }
    }
  }
}
