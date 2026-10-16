// The five answers a viewer can give a film, best first, and how each reads as a sentence about a profile that
// shared it. A rating is kept as 1 ("Hated it") to 5 ("Loved it!"); the viewer only ever sees the words.

// The answers as the viewer gives them, best first, each with the number it is kept as.
export const ANSWERS = [
  { score: 5, say: "Loved it!" },
  { score: 4, say: "Really liked it" },
  { score: 3, say: "It was ok, I guess" },
  { score: 2, say: "Didn't like it" },
  { score: 1, say: "Hated it" },
];

const SAID = { 5: "loved it", 4: "really liked it", 3: "thought it was ok", 2: "didn't like it", 1: "hated it" };

// What a profile's rating says after its name: "loved it", "thought it was ok".
export function said(score) {
  return SAID[score] ?? "";
}

// The answer's own words for a rating: "Loved it!".
export function answerOf(score) {
  return ANSWERS.find((a) => a.score === score)?.say ?? "";
}
