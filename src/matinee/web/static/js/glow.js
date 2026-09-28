// A poster's glow colour, with no page in it: the poster's strongest colour. Near-black, near-white and
// grey pixels are dropped; the rest are grouped into hue bands weighted by how vivid they are, and the
// heaviest band's average colour is raised to full brightness. A poster without vivid colour glows in
// marquee gold.

export const GOLD = [242, 179, 61];
const BANDS = 24;
const DARKEST = 0.22; // a pixel darker than this (its brightest channel, 0 to 1) is near-black
const GREYEST = 0.3; // a pixel less saturated than this is grey, or near-white
const LEAST_WEIGHT = 1; // a band lighter than this is fewer than a handful of vivid pixels

function hueOf(r, g, b, max, min) {
  if (max === r) return ((((g - b) / (max - min)) * 60) % 360 + 360) % 360;
  if (max === g) return ((b - r) / (max - min)) * 60 + 120;
  return ((r - g) / (max - min)) * 60 + 240;
}

// The glow colour, as [r, g, b], of `pixels`: RGBA bytes as a canvas reads them.
export function posterGlow(pixels) {
  const bands = Array.from({ length: BANDS }, () => ({ w: 0, r: 0, g: 0, b: 0 }));
  for (let k = 0; k < pixels.length; k += 4) {
    const r = pixels[k] / 255;
    const g = pixels[k + 1] / 255;
    const b = pixels[k + 2] / 255;
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const sat = max ? (max - min) / max : 0;
    if (max < DARKEST || sat < GREYEST) continue;
    const band = bands[Math.floor(hueOf(r, g, b, max, min) / (360 / BANDS)) % BANDS];
    const w = sat * max;
    band.w += w;
    band.r += pixels[k] * w;
    band.g += pixels[k + 1] * w;
    band.b += pixels[k + 2] * w;
  }
  const best = bands.reduce((a, c) => (c.w > a.w ? c : a));
  if (best.w < LEAST_WEIGHT) return GOLD;
  const rgb = [best.r, best.g, best.b].map((v) => v / best.w);
  const lift = 255 / Math.max(...rgb, 1);
  return rgb.map((v) => Math.round(Math.min(255, v * lift)));
}
