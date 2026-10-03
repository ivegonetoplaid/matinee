import assert from "node:assert/strict";
import { test } from "node:test";

import { avatarSrc, initials } from "../../src/matinee/web/static/js/mark.js";

test("initials are the first letter of each word, at most three, as capitals", () => {
  assert.equal(initials("Ada"), "A");
  assert.equal(initials("mary  ann lee"), "MAL");
  assert.equal(initials("The Big Lebowski Fan Club"), "TBL");
  assert.equal(initials("  zoë  "), "Z");
  assert.equal(initials("Émile"), "É");
});

test("an avatar is served at twice the size it is shown", () => {
  assert.equal(avatarSrc("popcorn", "door"), "/static/avatars/popcorn-256.webp");
  assert.equal(avatarSrc("vhs", "bar"), "/static/avatars/vhs-80.webp");
});
