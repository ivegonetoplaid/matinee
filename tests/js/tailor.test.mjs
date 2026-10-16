import { test } from "node:test";
import assert from "node:assert/strict";

import { OFFER, STEPS, WELCOME, WHATS_NEW, stepKeys } from "../../src/matinee/web/static/js/tailor.js";

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

test("a profile made before My profile is welcomed, and shown what is new, in the decided words", () => {
  assert.equal(WELCOME, "New: you can now rate films, hide films, and see what I've picked for you.");
  assert.equal(
    WHATS_NEW.join(" "),
    "Welcome back. You could already tell me what to steer around. Now you can rate films, hide the ones you don't want, look back at what I've picked, and tell me how well rated a film needs to be and which languages you watch in.",
  );
});
