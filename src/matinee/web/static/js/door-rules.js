// The front door's rules, apart from the page so they can be tested: what the door says over the tiles,
// which tile opens at once, and when a typed name is already a profile's.

// What the front door says over the tiles: a device holding a profile is welcomed back without a name.
export function doorLines(profiles) {
  if (!profiles.length) {
    return ["Come on in.", "Nobody has a seat yet. Introduce yourself. One profile the whole house shares works fine too."];
  }
  if (profiles.some((p) => p.held)) return ["Good to see you again.", "Who's watching?"];
  return ["Come on in.", "Pick your seat, or introduce yourself and I'll find you something to watch."];
}

// A tile opens its profile at once when this device holds it or it has no PIN; otherwise the PIN is asked.
export function opensAtOnce(profile) {
  return profile.held || !profile.has_pin;
}

// A name as the store compares it: NFKC, runs of spaces as one, and case folded. Upper-casing before
// lower-casing folds as the server's casefold does for letters such as "ß".
export function nameKey(name) {
  return name.normalize("NFKC").trim().replace(/\s+/g, " ").toUpperCase().toLowerCase();
}

// The profile already going by a typed name, or undefined.
export function findTaken(profiles, typed) {
  return profiles.find((p) => nameKey(p.name) === nameKey(typed));
}

// A message split as Matinee says a line: its first sentence in gold, the rest in cream.
export function twoParts(text) {
  const parts = String(text).match(/^(.+?[.!?])\s+(.+)$/);
  return parts ? [parts[1], parts[2]] : [String(text), ""];
}
