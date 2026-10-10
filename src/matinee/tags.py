"""The pick's tags: a film's strongest MovieLens genome words, skipping the words `data/tag_skip.txt` lists.

`data/tags.json` ships each genome film's `WORDS_PER_FILM` strongest words, strongest first, keyed by TMDB id, as
positions in the file's own word list, so no installation downloads MovieLens. It is derived from the MovieLens tag
genome and carries that dataset's licence conditions in its `licence` field, as `data/genome.json` does.
`tools/build_genome.py` writes it from the same release as `data/genome.json`.

The skip list is read when the server starts, so an edit takes effect at the next start; a pulled image carries
its own copy, which an update replaces. The pick shows a film's
first `SHOWN` words not on it, fewer when fewer remain, and none for a film the genome does not cover. Tags describe
a film; they never place it (labels alone do).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from matinee.genome import Genome
from matinee.reference import DATA

log = logging.getLogger("matinee")

TAGS_FILE = DATA / "tags.json"
SKIP_FILE = DATA / "tag_skip.txt"
WORDS_PER_FILM = 40  # room for an operator's longer skip list: the shipped one needs at most 31 for four tags
SHOWN = 4


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
    """Write the shipped tags as JSON, one film per line; returns the number of films."""
    films = sorted(strongest(genome).items())
    lines = [f'    "{tmdb}": {json.dumps(words)}' for tmdb, words in films]
    head = json.dumps({"licence": licence, "source": genome.release, "words": list(genome.tags)}, indent=2)
    body = head[: head.rindex("}")].rstrip() + ',\n  "films": {\n' + ",\n".join(lines) + "\n  }\n}\n"
    path.write_text(body, encoding="utf-8")
    return len(films)


def read_skip(path: Path = SKIP_FILE) -> frozenset[str]:
    """The words the pick never shows: one per line, `#` lines and blank lines ignored, surrounding spaces trimmed."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TagsError(f"the tag skip list at {path} cannot be read: {exc}") from exc
    return frozenset(line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))


def _shown(words: Sequence[str], films: object, skip: frozenset[str]) -> dict[int, tuple[str, ...]]:
    if not isinstance(films, dict):
        raise TagsError("its films are not an object keyed by TMDB id")
    shown: dict[int, tuple[str, ...]] = {}
    for tmdb, positions in films.items():
        if not isinstance(positions, list) or not all(type(p) is int and 0 <= p < len(words) for p in positions):
            raise TagsError(f"the tags for film {tmdb} are not positions in the word list")
        kept = [words[p] for p in positions if words[p] not in skip]
        shown[int(tmdb)] = tuple(kept[:SHOWN])
    return shown


def load_tags(path: Path = TAGS_FILE, skip_path: Path = SKIP_FILE) -> Tags:
    """Read the shipped tags and apply the skip list; raises TagsError naming the file that cannot be used."""
    skip = read_skip(skip_path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        words = [str(w) for w in doc["words"]]
        tags = Tags(str(doc["source"]), _shown(words, doc["films"], skip))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise TagsError(f"the film tags at {path} cannot be read: {exc}") from exc
    unknown = sorted(skip - set(words))
    if unknown:
        log.warning(
            "the tag skip list at %s names words no film is tagged with, so they skip nothing: %s", skip_path, unknown
        )
    return tags
