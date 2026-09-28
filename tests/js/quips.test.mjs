import assert from "node:assert/strict";
import { test } from "node:test";

import { Deck, dealBeneath, dealPair, setFor } from "../../src/matinee/web/static/js/quips.js";

function seeded(seed) {
  let s = seed;
  return () => {
    s = (s * 1103515245 + 12345) % 2147483648;
    return s / 2147483648;
  };
}

const QUIPS = {
  borrow: { standup: "comedy" },
  categories: {
    universal: { reveal: ["U reveal one.", "U reveal two."], nope: ["U nope."] },
    horror: { reveal: ["H reveal."], nope: ["H nope."] },
    comedy: { reveal: ["C reveal."] },
  },
};

test("a category draws only its own lines, a borrower draws its lender's, and each set falls back on its own", () => {
  assert.deepEqual(setFor(QUIPS, "horror", "reveal").lines, ["H reveal."]);
  assert.deepEqual(setFor(QUIPS, "horror", "nope").lines, ["H nope."]);
  assert.deepEqual(setFor(QUIPS, "standup", "reveal").lines, ["C reveal."]);
  // comedy has reveal lines but no nope lines: its nope lines come from universal
  assert.deepEqual(setFor(QUIPS, "comedy", "nope").lines, ["U nope."]);
  assert.deepEqual(setFor(QUIPS, "drama", "reveal").lines, ["U reveal one.", "U reveal two."]);
  // "Just pick one!" before any category
  assert.deepEqual(setFor(QUIPS, null, "reveal").lines, ["U reveal one.", "U reveal two."]);
});

test("no line repeats until its set has run out, then the set is reshuffled", () => {
  const set = { key: "t", lines: ["a", "b", "c", "d", "e"] };
  const deck = new Deck(seeded(3));
  const first = Array.from({ length: 5 }, () => deck.deal(set));
  assert.deepEqual([...first].sort(), set.lines);
  const second = Array.from({ length: 5 }, () => deck.deal(set));
  assert.deepEqual([...second].sort(), set.lines);
  // decks of different sets are kept apart
  const other = { key: "u", lines: ["x"] };
  assert.equal(deck.deal(other), "x");
});

test("a pair over the cap drops the longer line and redeals from its set until the pair fits", () => {
  const nopes = { key: "n", lines: ["a much longer nope line", "short no"] };
  const reveals = { key: "r", lines: ["reveal ok"] };
  for (let seed = 1; seed < 30; seed += 1) {
    const deck = new Deck(seeded(seed));
    const { nope, reveal } = dealPair(deck, nopes, reveals, 20);
    assert.equal(reveal, "reveal ok");
    assert.equal(nope, "short no");
    assert.ok(nope.length + reveal.length <= 20);
    // the dropped line went back unshown: it is dealt later
    assert.equal(deck.deal(nopes), "a much longer nope line");
  }
});

test("when no line left in a set fits, that set's shortest line stands in", () => {
  const nopes = { key: "n", lines: ["twelve chars", "eleven char"] };
  const reveals = { key: "r", lines: ["a reveal of twenty ch"] };
  const deck = new Deck(seeded(5));
  const { nope, reveal } = dealPair(deck, nopes, reveals, 25);
  assert.equal(nope, "eleven char");
  assert.equal(reveal, "a reveal of twenty ch");
});

test("beneath an explanation only the reveal line is redealt to fit", () => {
  const reveals = { key: "r", lines: ["a long reveal line here", "short"] };
  for (let seed = 1; seed < 20; seed += 1) {
    assert.equal(dealBeneath(new Deck(seeded(seed)), "an explanation of 30 characters", reveals, 40), "short");
  }
});

test("with the real lines and caps, no pair ever exceeds the cap", async () => {
  const { readFileSync } = await import("node:fs");
  const real = JSON.parse(readFileSync(new URL("../../data/quips.json", import.meta.url), "utf8"));
  for (const category of [null, "horror", "comedy", "standup", "drama"]) {
    const deck = new Deck(seeded(9));
    for (let k = 0; k < 200; k += 1) {
      const { nope, reveal } = dealPair(deck, setFor(real, category, "nope"), setFor(real, category, "reveal"), real.caps.pair);
      assert.ok(nope.length + reveal.length <= real.caps.pair, `${category}: ${nope} / ${reveal}`);
    }
  }
});
