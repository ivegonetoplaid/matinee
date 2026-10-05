// What this installation offers, as the front door's reply says, read once per visit. Without a
// DoesTheDogDie key the page offers no list of topics and shows no DoesTheDogDie credit anywhere.

export const offers = { dtdd: true, postersFromTmdb: false };

export function learnOffers(door) {
  offers.dtdd = Boolean(door.dtdd);
  offers.postersFromTmdb = door.posters_from === "tmdb";
}
