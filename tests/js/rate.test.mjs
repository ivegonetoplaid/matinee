import { mock, test } from "node:test";
import assert from "node:assert/strict";

import { MAX_REVIEW, autosaver, fitted, length, oneLine, roomLeft } from "../../src/matinee/web/static/js/rate.js";

const at = (n, ch = "x") => ch.repeat(n);

test("the field counts as the store does: an emoji, joined or not, by its code points", () => {
  assert.equal(length("héllo"), 5);
  assert.equal(length("\u{1F525}"), 1);
  assert.equal(length("❤️‍\u{1F525}"), 4);
});

test("the field never takes a character past the limit and says so", () => {
  assert.deepEqual(fitted(at(MAX_REVIEW), at(MAX_REVIEW - 1)), { value: at(MAX_REVIEW), tripped: false });
  assert.deepEqual(fitted(at(MAX_REVIEW + 1), at(MAX_REVIEW)), { value: at(MAX_REVIEW), tripped: true });
  assert.deepEqual(fitted(at(MAX_REVIEW - 1, "\u{1F525}") + "ab", at(MAX_REVIEW - 1, "\u{1F525}")), {
    value: at(MAX_REVIEW - 1, "\u{1F525}"),
    tripped: true,
  });
});

test("room left always shows, from the whole limit down to none", () => {
  assert.equal(roomLeft(""), `${MAX_REVIEW} left`);
  assert.equal(roomLeft(at(MAX_REVIEW)), "0 left");
});

test("a line break typed or pasted into the box becomes one space", () => {
  assert.equal(oneLine("Gets worse.\n\n  Still good\r\nhere"), "Gets worse. Still good here");
  assert.equal(oneLine("one line"), "one line");
});

test("the short review saves once typing pauses, at once on leaving, and never twice for one text", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  const sent = [];
  const heard = [];
  const saver = autosaver(
    async (text) => (sent.push(text), { ok: true, data: { review: text } }),
    (res, text) => heard.push(text),
    "old",
  );
  saver.soon("g");
  saver.soon("go");
  mock.timers.tick(999);
  assert.deepEqual(sent, []); // still typing
  mock.timers.tick(1);
  await saver.now("go"); // the pause's save, then leaving the field with nothing new
  assert.deepEqual(sent, ["go"]);
  saver.soon("gone");
  await saver.now("gone"); // leaving the field cancels the pending pause's save
  await saver.now("old");
  mock.timers.tick(5000); // so no stale "gone" lands over the newer text
  await saver.now("old");
  assert.deepEqual(sent, ["go", "gone", "old"]);
  assert.deepEqual(heard, ["go", "gone", "old"]);
  mock.timers.reset();
});
