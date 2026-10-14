import { test } from "node:test";
import assert from "node:assert/strict";

import { MAX_REVIEW, fitted, length, roomLeft } from "../../src/matinee/web/static/js/rate.js";

const at = (n, ch = "x") => ch.repeat(n);

test("the field counts as the store does: an emoji, joined or not, by its code points", () => {
  assert.equal(length("héllo"), 5);
  assert.equal(length("\u{1F525}"), 1);
  assert.equal(length("❤️‍\u{1F525}"), 4);
});

test("the field never takes a 141st character and says so", () => {
  assert.deepEqual(fitted(at(MAX_REVIEW), at(MAX_REVIEW - 1)), { value: at(MAX_REVIEW), tripped: false });
  assert.deepEqual(fitted(at(MAX_REVIEW + 1), at(MAX_REVIEW)), { value: at(MAX_REVIEW), tripped: true });
  assert.deepEqual(fitted(at(MAX_REVIEW - 1, "\u{1F525}") + "ab", at(MAX_REVIEW - 1, "\u{1F525}")), {
    value: at(MAX_REVIEW - 1, "\u{1F525}"),
    tripped: true,
  });
});

test("room left shows over the last twenty characters only", () => {
  assert.equal(roomLeft(at(MAX_REVIEW - 21)), "");
  assert.equal(roomLeft(at(MAX_REVIEW - 20)), "20 left");
  assert.equal(roomLeft(at(MAX_REVIEW)), "0 left");
});
