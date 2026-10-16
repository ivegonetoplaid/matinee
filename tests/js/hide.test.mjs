import { test } from "node:test";
import assert from "node:assert/strict";

import { LENGTHS } from "../../src/matinee/web/static/js/hide.js";

test("a hide offers the four lengths the store keeps, in order, none chosen", () => {
  assert.deepEqual(
    LENGTHS.map((l) => [l.length, l.say]),
    [
      ["3m", "3 months"],
      ["6m", "6 months"],
      ["1y", "1 year"],
      ["good", "For good"],
    ],
  );
});
