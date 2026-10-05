"""The genome scores Matinee ships, `data/genome.json`, so no installation downloads MovieLens.

The file holds, for every film the ml-latest genome covers that has a TMDB id,
the relevance of every genome tag a reader names (`tags_read`): the fall-asleep
mode's scores, every tree's and mode's `scores`, and the answer key's list tags.
It is derived from the MovieLens tag genome and carries that dataset's licence
conditions in its `licence` field, as `data/reference.json` does. Values are
written to five decimal places, which is the precision the genome publishes, so
each reads back as exactly the float32 the full genome holds.

`tools/build_genome.py` writes it from an ml-latest directory; the rebuild reads it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

import numpy as np

from matinee.genome import GenomeError, Scores
from matinee.pools import SCORES
from matinee.reference import DATA
from matinee.trees import load_trees

GENOME_FILE = DATA / "genome.json"
PLACES = 5


def tags_read(data: Path = DATA) -> tuple[str, ...]:
    """Every genome tag a reader names, sorted: the fall-asleep scores, each tree's scores, and the list tags."""
    named: set[str] = {tag for tags in SCORES.values() for tag in tags}
    for tree in load_trees((data / "trees", data / "modes")).values():
        named.update(tag for tags in tree.scores.values() for tag in tags)
    key = json.loads((data / "answer_key.json").read_text(encoding="utf-8"))
    named.update(key["list_tags"]["tags"])
    return tuple(sorted(named))


def _row(values: Iterable[float]) -> str:
    return "[" + ", ".join(f"{round(float(v), PLACES):g}" for v in values) + "]"


def write_scores(scores: Scores, path: Path, licence: str) -> None:
    """Write `scores` as JSON, one film per line so a change reads as a change to that film."""
    films = sorted(scores.rows.items())
    lines = [f'    "{tmdb}": {_row(scores.relevance[row])}' for tmdb, row in films]
    head = json.dumps({"licence": licence, "source": scores.release, "tags": list(scores.tags)}, indent=2)
    body = head[: head.rindex("}")].rstrip() + ',\n  "films": {\n' + ",\n".join(lines) + "\n  }\n}\n"
    path.write_text(body, encoding="utf-8")


def _matrix(films: Mapping[str, object], width: int) -> tuple[dict[int, int], np.ndarray]:
    rows: dict[int, int] = {}
    values: list[list[float]] = []
    for tmdb, row in films.items():
        if not isinstance(row, list) or len(row) != width or not all(isinstance(v, int | float) for v in row):
            raise GenomeError(f"genome scores for film {tmdb} are not {width} numbers")
        rows[int(tmdb)] = len(values)
        values.append([float(v) for v in row])
    return rows, np.array(values, dtype=np.float32).reshape(len(values), width)


def load_scores(path: Path = GENOME_FILE) -> Scores:
    """Read the shipped scores; raises GenomeError naming the path when the file is absent or malformed."""
    if not path.exists():
        raise GenomeError(f"no genome scores at {path}; they ship with Matinee, so the checkout is incomplete")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        tags = tuple(str(t) for t in doc["tags"])
        rows, relevance = _matrix(doc["films"], len(tags))
        return Scores(str(doc["source"]), tags, rows, relevance)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise GenomeError(f"the genome scores at {path} are malformed: {exc}") from exc
