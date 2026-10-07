import assert from "node:assert/strict";
import { test } from "node:test";

import {
  boardText,
  doorLines,
  findTaken,
  nameKey,
  opensAtOnce,
  stripLap,
  twoParts,
} from "../../src/matinee/web/static/js/door-rules.js";

test("the door's line depends on whether profiles exist and whether this device holds one", () => {
  assert.deepEqual(doorLines([]), [
    "Come on in.",
    "Nobody has a seat yet. Introduce yourself. One profile the whole house shares works fine too.",
  ]);
  assert.deepEqual(doorLines([{ held: false }, { held: true }]), ["Good to see you again.", "Who's watching?"]);
  assert.deepEqual(doorLines([{ held: false }]), [
    "Come on in.",
    "Pick your seat, or introduce yourself and I'll find you something to watch.",
  ]);
});

test("a tile opens at once when held or without a PIN, and asks the PIN otherwise", () => {
  assert.equal(opensAtOnce({ held: true, has_pin: true }), true);
  assert.equal(opensAtOnce({ held: false, has_pin: false }), true);
  assert.equal(opensAtOnce({ held: false, has_pin: true }), false);
});

test("a typed name is taken as the store compares names", () => {
  const profiles = [{ name: "Mary Ann" }, { name: "STRASSE" }, { name: "Bo" }];
  assert.equal(findTaken(profiles, "  mary   ann ")?.name, "Mary Ann");
  assert.equal(findTaken(profiles, "Straße")?.name, "STRASSE");
  assert.equal(findTaken(profiles, "bob"), undefined);
  assert.equal(nameKey("ＡＤＡ"), "ada"); // NFKC folds full-width letters
});

test("a message splits into its first sentence and the rest", () => {
  assert.deepEqual(twoParts("I can't find that one any more."), ["I can't find that one any more.", ""]);
  assert.deepEqual(twoParts("The theatre's full up on regulars. Ask whoever runs this place to make room."), [
    "The theatre's full up on regulars.",
    "Ask whoever runs this place to make room.",
  ]);
});

test("the letter board reads the film count, or Private screening before admission", () => {
  assert.equal(boardText(null), "Private screening");
  assert.equal(boardText(1), "1 film");
  assert.equal(boardText(10272), "10,272 films");
});

test("the lit strip's bulbs take every place in the lap once, clockwise", () => {
  const top = Array.from({ length: 24 }, (_, k) => stripLap("top", k, 24));
  const bottom = Array.from({ length: 24 }, (_, k) => stripLap("bottom", k, 24));
  const all = [...top, ...bottom];
  assert.equal(new Set(all).size, 48);
  assert.ok(all.every((lap) => lap >= 0 && lap < 1));
  assert.ok(top.every((lap, k) => k === 0 || lap > top[k - 1])); // left to right along the top
  assert.ok(bottom.every((lap, k) => k === 0 || lap < bottom[k - 1])); // right to left along the bottom
  assert.ok(Math.min(...bottom) > Math.max(...top)); // the bottom row follows the top
});
