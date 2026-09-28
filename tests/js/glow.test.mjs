import assert from "node:assert/strict";
import { test } from "node:test";

import { GOLD, posterGlow } from "../../src/matinee/web/static/js/glow.js";

// RGBA pixels: `n` of each [r, g, b] given.
function pixels(...runs) {
  const out = [];
  for (const [n, [r, g, b]] of runs) for (let k = 0; k < n; k += 1) out.push(r, g, b, 255);
  return Uint8ClampedArray.from(out);
}

test("the glow is the heaviest vivid hue, not the average of all pixels", () => {
  // A red title over a larger, duller blue sky: averaging gives a purple-blue; the glow is red.
  const glow = posterGlow(pixels([300, [200, 30, 20]], [200, [60, 80, 140]], [900, [10, 10, 12]]));
  assert.ok(glow[0] > 200 && glow[1] < 60 && glow[2] < 60, `glow ${glow}`);
});

test("the glow is raised to full brightness", () => {
  const glow = posterGlow(pixels([400, [20, 90, 40]]));
  assert.equal(Math.max(...glow), 255);
  assert.ok(glow[1] === 255 && glow[0] < 100 && glow[2] < 140, `glow ${glow}`);
});

test("near-black, near-white and grey pixels are ignored", () => {
  const glow = posterGlow(pixels([5000, [8, 8, 10]], [5000, [250, 250, 245]], [5000, [128, 128, 128]], [80, [30, 60, 220]]));
  assert.ok(glow[2] === 255 && glow[0] < 80, `glow ${glow}`);
});

test("a poster without vivid colour glows marquee gold", () => {
  assert.deepEqual(posterGlow(pixels([1536, [128, 128, 128]], [200, [255, 255, 255]])), GOLD);
  assert.deepEqual(posterGlow(pixels([1, [220, 20, 20]], [1535, [0, 0, 0]])), GOLD);
});
