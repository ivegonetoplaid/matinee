import { test } from "node:test";
import assert from "node:assert/strict";

import { OFFER, STEPS, stepKeys } from "../../src/matinee/web/static/js/tailor.js";

test("making a profile offers tailoring in the decided words", () => {
  assert.deepEqual(OFFER, {
    ack: "Want me to tailor picks to you?",
    ask: "It's a few quick questions.",
    yes: "Yes, let's do it",
    no: "No, just show me movies",
  });
});

test("after the topics, the steps run in My profile's order, sharing last", () => {
  assert.deepEqual(STEPS, ["floor", "languages", "rated", "sharing"]);
});

test("the topics come first only where the installation offers them, and the languages only where films hold any", () => {
  const held = [{ code: "en", films: 3 }];
  assert.deepEqual(stepKeys({ dtdd: true, held }), ["topics", "floor", "languages", "rated", "sharing"]);
  assert.deepEqual(stepKeys({ dtdd: false, held }), ["floor", "languages", "rated", "sharing"]);
  assert.deepEqual(stepKeys({ dtdd: false, held: [] }), ["floor", "rated", "sharing"]);
});
