// The films a run has shown, for the Back panel and for the profile's history. A run starts when the viewer begins at the first question and
// ends at "Start over" or the wordmark; changing an answer or the door keeps it. Each film is held once, as it was
// shown on screen: a film shown again moves to the newest place. Films the check turned away unseen are never held.

// The run with `shown` as its newest film, replacing any earlier showing of the same film. `run` is unchanged.
export function remember(run, shown) {
  return [...run.filter((s) => s.film.tmdb !== shown.film.tmdb), shown];
}

// The run's films newest first, the newest marked as the one showing now when it is on screen (`showing`).
export function newestFirst(run, showing) {
  return run.map((s, i) => ({ ...s, now: showing && i === run.length - 1 })).reverse();
}

// What the run keeps of a film shown on screen: the film, the door its rank counted among, the walk a note records,
// Matinee's line as it stood at rest (and whether DoesTheDogDie's credit stood with it), the content note the check
// gave it, and whether it is a film the check turned away that the viewer asked to see (`asked`): such a film stays
// out of the history however often it is shown.
export function kept({ film, result, door, walk, said }) {
  const asked = Boolean(result.last || result.asked);
  return { film, door, walk, said, unchecked: result.unchecked ?? null, dtdd_item: result.dtdd_item ?? null, link: result.link, asked };
}

// A kept film as a pick to show again: the reply, the line and its credit, the door and the walk, as first shown.
export function asPick(shown) {
  const { gold, reveal, credit } = shown.said;
  const result = {
    film: shown.film,
    unchecked: shown.unchecked,
    dtdd_item: shown.dtdd_item,
    link: shown.link,
    swapped: null,
    last: null,
    tired: null,
    exhausted: null,
    turned_away: [],
    asked: shown.asked,
  };
  return { result, lines: { nope: null, gold, reveal, credit, beneath: () => reveal }, door: shown.door, walk: shown.walk };
}

// A new run's key: 32 hex digits, random. The server keeps the profile's history under it. Built from
// getRandomValues, which a page served over plain http on a home network has, where randomUUID is not offered.
export function runKey() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

// What the history keeps of a film shown on screen: the film and the walk that reached it, as a note records it.
// Null for a film the check turned away, which the history never keeps.
export function shownBody(shown) {
  if (shown.asked) return null;
  const { tree, answers, rushed } = shown.walk;
  return { tmdb: shown.film.tmdb, tree, answers, rushed };
}
