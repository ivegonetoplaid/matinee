// The films a run has shown, for the Back panel. A run starts when the viewer begins at the first question and
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
// Matinee's line as it stood at rest (and whether DoesTheDogDie's credit stood with it), and the content note the
// check gave it. Nothing else of DoesTheDogDie: never the film a check turned away.
export function kept({ film, result, door, walk, said }) {
  return { film, door, walk, said, unchecked: result.unchecked ?? null, dtdd_item: result.dtdd_item ?? null, link: result.link };
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
  };
  return { result, lines: { nope: null, gold, reveal, credit, beneath: () => reveal }, door: shown.door, walk: shown.walk };
}
