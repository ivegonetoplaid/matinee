"""The pick's tags: a film's strongest MovieLens genome words, skipping the words `data/tag_skip.txt` lists.

`data/tags.json` ships each genome film's `WORDS_PER_FILM` strongest words, strongest first, keyed by TMDB id, as
positions in the file's own word list, so no installation downloads MovieLens. It is derived from the MovieLens tag
genome and carries that dataset's licence conditions in its `licence` field, as `data/genome.json` does.
`tools/build_genome.py` writes it from the same release as `data/genome.json`.

The file also lists the word pairs that say nearly the same thing (`alike`): two forms of one word, such as "spy" and
"spies", or two words whose relevance rises and falls together across every genome film, correlated at `ALIKE` or
more, such as "espionage" and "spying". The pick never shows both words of a pair.

The skip list is read when the server starts, so an edit takes effect at the next start; a pulled image carries
its own copy, which an update replaces. The pick shows a film's first `SHOWN` words not on it, passing over a word
alike to one already shown; fewer when fewer remain, and none for a film the genome does not cover. Tags describe
a film; they never place it (labels alone do).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from matinee.genome import Genome
from matinee.reference import DATA

log = logging.getLogger("matinee")

TAGS_FILE = DATA / "tags.json"
SKIP_FILE = DATA / "tag_skip.txt"
WORDS_PER_FILM = 40  # room for an operator's longer skip list: the shipped one needs at most 34 for four distinct tags
SHOWN = 4
# Two words whose relevance correlates at this or more across the genome's films say nearly the same thing on the pick.
# Measured on the 2023 release: from 0.78 the pairs merged are near-synonyms ("espionage" and "spying"); below it,
# words that only appear together ("animals" and "talking animals").
ALIKE = 0.78
# Endings that make two forms of one word ("teen", "teens", "teenager"), with what replaces them; none leaves a stem
# shorter than three letters.
ENDINGS = (("agers", ""), ("ager", ""), ("ers", ""), ("er", ""), ("ies", "y"), ("ing", ""), ("es", ""), ("s", ""))


class TagsError(ValueError):
    """The shipped tags or the skip list cannot be read; the message names the file."""


@dataclass(frozen=True)
class Tags:
    """Each covered film's tags, the skip list already applied. A film it does not hold has none."""

    release: str = ""
    shown: Mapping[int, tuple[str, ...]] = field(default_factory=dict)

    def of(self, tmdb: int) -> list[str]:
        return list(self.shown.get(tmdb, ()))


def strongest(genome: Genome, count: int = WORDS_PER_FILM) -> dict[int, list[int]]:
    """Each genome film's `count` strongest words, as positions in `genome.tags`, strongest first, keyed by TMDB id.
    Where two MovieLens films share a TMDB id, the first one wins, as in the shipped scores."""
    films: dict[int, list[int]] = {}
    order = np.argsort(-genome.relevance, axis=1, kind="stable")[:, :count]
    for row, movie in enumerate(genome.movie_ids):
        tmdb = genome.tmdb_by_movie.get(int(movie))
        if tmdb is not None and tmdb not in films:
            films[tmdb] = [int(i) for i in order[row]]
    return films


def write_tags(genome: Genome, path: Path, licence: str) -> int:
    """Write the shipped tags as JSON: the alike pairs on one line, then one film per line; returns the film count."""
    films = sorted(strongest(genome).items())
    lines = [f'    "{tmdb}": {json.dumps(words)}' for tmdb, words in films]
    head = json.dumps({"licence": licence, "source": genome.release, "words": list(genome.tags)}, indent=2)
    alike = json.dumps([list(pair) for pair in alike_pairs(genome)])
    body = (
        head[: head.rindex("}")].rstrip()
        + f',\n  "alike": {alike},\n  "films": {{\n'
        + ",\n".join(lines)
        + "\n  }\n}\n"
    )
    path.write_text(body, encoding="utf-8")
    return len(films)


def forms(word: str) -> frozenset[str]:
    """`word` as letters and digits only, and with each of its `ENDINGS` taken off: two words sharing one are forms of
    one word ("spies" and "spying" share "spy"; "super hero" and "superheroes" share "superhero")."""
    bare = re.sub(r"[^a-z0-9]", "", word.lower())
    cut = {
        bare[: -len(end)] + put for end, put in ENDINGS if bare.endswith(end) and len(bare) - len(end) + len(put) >= 3
    }
    return frozenset({bare} | cut)


def alike_pairs(genome: Genome) -> list[tuple[int, int]]:
    """Every pair of genome words, as positions in `genome.tags` with the lower first, that are forms of one word or
    whose relevance across the genome's films correlates at `ALIKE` or more."""
    correlated = np.asarray(np.corrcoef(genome.relevance.T) >= ALIKE, dtype=bool)
    shapes = [forms(t) for t in genome.tags]
    count = len(genome.tags)
    return [(a, b) for a in range(count) for b in range(a + 1, count) if correlated[a, b] or shapes[a] & shapes[b]]


def read_skip(path: Path = SKIP_FILE) -> frozenset[str]:
    """The words the pick never shows: one per line, `#` lines and blank lines ignored, surrounding spaces trimmed."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TagsError(f"the tag skip list at {path} cannot be read: {exc}") from exc
    return frozenset(line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))


def _positions(value: object, count: int) -> bool:
    return isinstance(value, list) and all(type(p) is int and 0 <= p < count for p in value)


def _alike(value: object, count: int) -> frozenset[frozenset[int]]:
    if not isinstance(value, list) or not all(_positions(pair, count) and len(pair) == 2 for pair in value):
        raise TagsError("its alike pairs are not pairs of positions in the word list")
    return frozenset(frozenset(pair) for pair in value)


def _first_distinct(positions: Sequence[int], alike: frozenset[frozenset[int]]) -> tuple[int, ...]:
    """The first `SHOWN` of `positions`, passing over one alike to a position already taken."""
    taken: list[int] = []
    for p in positions:
        if all(frozenset((p, q)) not in alike for q in taken):
            taken.append(p)
        if len(taken) == SHOWN:
            break
    return tuple(taken)


def _shown(words: Sequence[str], films: object, skip: frozenset[str], alike: object) -> dict[int, tuple[str, ...]]:
    if not isinstance(films, dict):
        raise TagsError("its films are not an object keyed by TMDB id")
    pairs = _alike(alike, len(words))
    shown: dict[int, tuple[str, ...]] = {}
    for tmdb, positions in films.items():
        if not _positions(positions, len(words)):
            raise TagsError(f"the tags for film {tmdb} are not positions in the word list")
        kept = [p for p in positions if words[p] not in skip]
        shown[int(tmdb)] = tuple(words[p] for p in _first_distinct(kept, pairs))
    return shown


def load_tags(path: Path = TAGS_FILE, skip_path: Path = SKIP_FILE) -> Tags:
    """Read the shipped tags and apply the skip list; raises TagsError naming the file that cannot be used."""
    skip = read_skip(skip_path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        words = [str(w) for w in doc["words"]]
        tags = Tags(str(doc["source"]), _shown(words, doc["films"], skip, doc["alike"]))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise TagsError(f"the film tags at {path} cannot be read: {exc}") from exc
    unknown = sorted(skip - set(words))
    if unknown:
        log.warning(
            "the tag skip list at %s names words no film is tagged with, so they skip nothing: %s", skip_path, unknown
        )
    return tags
