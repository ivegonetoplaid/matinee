import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { CAP_HEIGHT, MARK_NAME, M_BEARING } from "../../src/matinee/web/static/js/flight.js";

const MARK_SVG = readFileSync(new URL("../../src/matinee/web/static/marquee/mark-corner.svg", import.meta.url), "utf8");

// The corner mark's lettering as the drawing places it: the name group's origin, the group's own shift, the
// glyph scale and the M's first x, read from mark-corner.svg itself.
function lettering() {
  const m = MARK_SVG.match(
    /<g transform="translate\(([\d.-]+) ([\d.-]+)\)" fill="url\(#mk-name\)"><g transform="translate\(([\d.-]+) 0\)"><path transform="translate\(0 0\) scale\(([\d.]+)\)" d="M([\d.]+)/,
  );
  assert.ok(m, "the drawing's name group was not found");
  const [x, y, dx, scale, mx] = m.slice(1).map(Number);
  return { x, y, dx, scale, mx };
}

test("the flight lands where the corner mark's drawing puts its lettering", () => {
  const { x, y, dx, scale, mx } = lettering();
  const close = (a, b) => assert.ok(Math.abs(a - b) < 0.01, `${a} is not ${b}`);
  close(MARK_NAME.left, x + dx + mx * scale); // the M's ink starts here
  close(MARK_NAME.baseline, y);
  close(MARK_NAME.cap, 120 * scale); // the outlines' capitals are 120 units tall
  close((M_BEARING * MARK_NAME.cap) / CAP_HEIGHT, mx * scale); // the bearing the copy's M leaves
});
