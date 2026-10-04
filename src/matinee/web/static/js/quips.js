// Matinee's lines for a pick, with no page in it: which set a pick draws from, a per-visit deck for
// each set, and the rule that keeps a nope line and a reveal line together under the combined cap.

export const UNIVERSAL = "universal";

// The set of `kind` ("reveal", "nope" or "rush") that a pick after `category` (the tree or mode the first
// answer led to, or null before one) draws from: the category's own lines, or, when it has none of
// this kind, universal's. Returns { key, lines }.
export function setFor(quips, category, kind) {
  const lines = category ? quips.categories[category]?.[kind] : null;
  if (lines?.length) return { key: `${category}:${kind}`, lines };
  return { key: `${UNIVERSAL}:${kind}`, lines: quips.categories[UNIVERSAL]?.[kind] || [] };
}

const shortest = (lines) => lines.reduce((a, b) => (b.length < a.length ? b : a));

// One deck per set for the visit: each set deals like a shuffled deck and is reshuffled only once
// every line in it has been dealt. `rand` is Math.random or a stand-in.
export class Deck {
  constructor(rand = Math.random) {
    this.rand = rand;
    this.left = new Map(); // set key -> the lines not yet dealt, in dealing order
  }

  remaining(set) {
    let left = this.left.get(set.key);
    if (!left?.length) {
      left = set.lines.slice();
      for (let k = left.length - 1; k > 0; k -= 1) {
        const j = Math.floor(this.rand() * (k + 1));
        [left[k], left[j]] = [left[j], left[k]];
      }
      this.left.set(set.key, left);
    }
    return left;
  }

  // The next line of `set` no longer than `room` characters. When no line left in the deck fits, the
  // set's shortest line: the one repeat a visit allows.
  deal(set, room = Infinity) {
    const left = this.remaining(set);
    const k = left.findIndex((line) => line.length <= room);
    if (k >= 0) return left.splice(k, 1)[0];
    return shortest(set.lines);
  }
}

// A nope line and a reveal line shown together, within `cap` characters. When the first pair dealt
// is over the cap, the longer of the two goes back unshown and its set deals the next line that fits
// beside the other; if the pair is still over, the other is redealt the same way.
export function dealPair(deck, nopeSet, revealSet, cap) {
  let nope = deck.deal(nopeSet);
  let reveal = deck.deal(revealSet);
  if (nope.length + reveal.length <= cap) return { nope, reveal };
  const redealNope = nope.length >= reveal.length;
  for (const which of redealNope ? ["nope", "reveal"] : ["reveal", "nope"]) {
    if (which === "nope") {
      deck.remaining(nopeSet).push(nope);
      nope = deck.deal(nopeSet, cap - reveal.length);
    } else {
      deck.remaining(revealSet).push(reveal);
      reveal = deck.deal(revealSet, cap - nope.length);
    }
    if (nope.length + reveal.length <= cap) break;
  }
  return { nope, reveal };
}

// A reveal line to show beneath `fixed` (a nope line, or the check's explanation), within `cap`
// characters together: only the reveal line is redealt.
export function dealBeneath(deck, fixed, revealSet, cap) {
  return deck.deal(revealSet, cap - fixed.length);
}
