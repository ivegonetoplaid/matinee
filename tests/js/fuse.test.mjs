import assert from "node:assert/strict";
import { test } from "node:test";

import { TICK_MS, fuseTimeline } from "../../src/matinee/web/static/js/fuse.js";

test("the fuse counts down from its seconds to one, a number per tick, then burns a tick later", () => {
  assert.deepEqual(fuseTimeline(5), [
    { at: 0, show: 5 },
    { at: 1000, show: 4 },
    { at: 2000, show: 3 },
    { at: 3000, show: 2 },
    { at: 4000, show: 1 },
    { at: 5000, burn: true },
  ]);
});

test("the fuse keeps real seconds and ends on the burn whatever its length", () => {
  assert.equal(TICK_MS, 1000);
  const one = fuseTimeline(1);
  assert.deepEqual(one, [{ at: 0, show: 1 }, { at: 1000, burn: true }]);
  assert.equal(fuseTimeline(9).filter((s) => s.burn).length, 1);
});
