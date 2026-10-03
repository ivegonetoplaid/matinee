import assert from "node:assert/strict";
import { test } from "node:test";

import { doorLines, findTaken, nameKey, opensAtOnce, twoParts } from "../../src/matinee/web/static/js/door-rules.js";

test("the door's line depends on whether profiles exist and whether this device holds one", () => {
  assert.deepEqual(doorLines([]), [
    "Welcome.",
    "Nobody has a seat yet. Introduce yourself. One profile the whole house shares works fine too.",
  ]);
  assert.deepEqual(doorLines([{ held: false }, { held: true }]), ["Welcome back.", "Who's watching?"]);
  assert.deepEqual(doorLines([{ held: false }]), [
    "Welcome.",
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
