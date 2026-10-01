"""Reference statistics: what every score means, fixed against films in general rather than one library.

A tree file names its reference (MovieLens genres plus a score floor) and the
scales it cuts into answers. `compute` measures
those over the genome and `to_json` writes them as a shipped data file; at
runtime Matinee only reads that file and never recomputes it from a library.

Standard deviations are population deviations (ddof 0). Percentiles use linear
interpolation. Every number is rounded to six places for a readable file. The
source is named by the dataset's own generation date, never the run date, so a
rerun on the same release and tree files writes an identical file.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from matinee.genome import Genome, Mask

DATA = Path(__file__).resolve().parents[2] / "data"
REFERENCE_PATH = DATA / "reference.json"
LICENCE = (
    "Derived from the MovieLens ml-latest tag genome (F. Maxwell Harper and Joseph A. Konstan, 2015; "
    "Jesse Vig, Shilad Sen and John Riedl, 2012). Redistributed under the dataset's own licence "
    "conditions, which bind this file: research and non-commercial use only, no implied endorsement "
    "by the University of Minnesota or GroupLens, and any redistribution under these same conditions."
)
PLACES = 6


class ReferenceError(ValueError):
    """A tree file's statistics section is malformed, or the shipped reference does not cover it."""


@dataclass(frozen=True)
class Floor:
    score: str
    tags: tuple[str, ...]
    minimum: float


@dataclass(frozen=True)
class ScaleSpec:
    score: str
    tags: tuple[str, ...]
    percentiles: tuple[float, ...]


@dataclass(frozen=True)
class TreeSpec:
    """The parts of one tree file the reference is computed from."""

    tree: str
    genres: tuple[str, ...]
    floor_any: tuple[Floor, ...]
    scales: Mapping[str, ScaleSpec]


@dataclass(frozen=True)
class Cuts:
    tags: tuple[str, ...]
    percentiles: tuple[float, ...]
    cuts: tuple[float, ...]


@dataclass(frozen=True)
class TreeReference:
    genres: tuple[str, ...]
    floor_any: tuple[Floor, ...]
    films: int
    scales: Mapping[str, Cuts]


@dataclass(frozen=True)
class Reference:
    source: str
    trees: Mapping[str, TreeReference]

    def scale(self, tree: str, scale: str) -> Cuts:
        try:
            return self.trees[tree].scales[scale]
        except KeyError as exc:
            raise ReferenceError(f"the reference has no scale '{scale}' for tree '{tree}'") from exc


def _tags(scores: Mapping[str, Any], name: str, tree: str) -> tuple[str, ...]:
    if name not in scores:
        raise ReferenceError(f"tree '{tree}' refers to score '{name}' but its 'scores' do not define it")
    return tuple(scores[name])


REFERENCE_KEYS = {"movielens_genres", "floor_any"}
SCALE_KEYS = {"score", "percentiles"}
SCALE_ENGINE_KEYS = {"bands", "unscored_bands", "keyword_bonus"}


def _exact_keys(block: Mapping[str, Any], keys: set[str], what: str, optional: frozenset[str] = frozenset()) -> None:
    """Refuse a block missing a key of `keys` or carrying any other: a misspelt key must fail, never read as absent."""
    have = set(block)
    if not keys <= have or have - keys - optional:
        raise ReferenceError(
            f"{what} must have the keys {sorted(keys)} (optionally {sorted(optional)}); it has {sorted(block)}"
        )


def spec_of(tree: str, doc: Mapping[str, Any]) -> TreeSpec | None:
    """The statistics section of a parsed tree file, or None for a tree with no reference (comedy, modes).

    A tree with no floor writes `"floor_any": {}` explicitly.
    """
    ref = doc.get("reference")
    if ref is None:
        return None
    _exact_keys(ref, REFERENCE_KEYS, f"tree '{tree}' reference")
    scores = doc.get("scores", {})
    floors = tuple(Floor(name, _tags(scores, name, tree), float(v)) for name, v in ref["floor_any"].items())
    scales = {}
    for name, s in doc.get("scales", {}).items():
        _exact_keys(s, SCALE_KEYS, f"tree '{tree}' scale '{name}'", frozenset(SCALE_ENGINE_KEYS))
        scales[name] = ScaleSpec(s["score"], _tags(scores, s["score"], tree), tuple(float(p) for p in s["percentiles"]))
    return TreeSpec(tree, tuple(ref["movielens_genres"]), floors, scales)


def load_specs(trees_dir: Path) -> list[TreeSpec]:
    """Every tree file's statistics section, in file-name order."""
    specs = []
    for path in sorted(trees_dir.glob("*.json")):
        spec = spec_of(path.stem, json.loads(path.read_text(encoding="utf-8")))
        if spec is not None:
            specs.append(spec)
    return specs


def reference_films(genome: Genome, spec: TreeSpec) -> Mask:
    """Genome films carrying one of the tree's MovieLens genres and reaching any one of its floors."""
    films = genome.with_genres(spec.genres)
    if not spec.floor_any:
        return films
    passes = np.zeros(len(genome.movie_ids), dtype=bool)
    for floor in spec.floor_any:
        passes |= genome.mean_of(floor.tags) >= floor.minimum
    return films & passes


def _round(x: float | np.floating[Any]) -> float:
    return round(float(x), PLACES)


def compute_tree(genome: Genome, spec: TreeSpec) -> TreeReference:
    films = reference_films(genome, spec)
    if not films.any():
        raise ReferenceError(f"tree '{spec.tree}' has no reference films in {genome.release}")
    scales = {
        name: Cuts(
            s.tags,
            s.percentiles,
            tuple(_round(c) for c in np.percentile(genome.mean_of(s.tags)[films], s.percentiles)),
        )
        for name, s in spec.scales.items()
    }
    return TreeReference(spec.genres, spec.floor_any, int(films.sum()), scales)


def compute(genome: Genome, specs: Sequence[TreeSpec]) -> Reference:
    return Reference(genome.release, {s.tree: compute_tree(genome, s) for s in sorted(specs, key=lambda s: s.tree)})


def to_json(ref: Reference) -> str:
    """The reference as the shipped data file's text."""
    trees = {
        name: {
            "movielens_genres": list(t.genres),
            "floor_any": {f.score: {"tags": list(f.tags), "min": f.minimum} for f in t.floor_any},
            "films": t.films,
            "scales": {
                n: {"tags": list(c.tags), "percentiles": list(c.percentiles), "cuts": list(c.cuts)}
                for n, c in t.scales.items()
            },
        }
        for name, t in ref.trees.items()
    }
    return json.dumps({"licence": LICENCE, "source": ref.source, "trees": trees}, indent=2) + "\n"


def from_json(text: str) -> Reference:
    doc = json.loads(text)
    trees = {
        name: TreeReference(
            genres=tuple(t["movielens_genres"]),
            floor_any=tuple(Floor(s, tuple(f["tags"]), float(f["min"])) for s, f in t["floor_any"].items()),
            films=int(t["films"]),
            scales={
                n: Cuts(tuple(c["tags"]), tuple(float(x) for x in c["percentiles"]), tuple(float(x) for x in c["cuts"]))
                for n, c in t["scales"].items()
            },
        )
        for name, t in doc["trees"].items()
    }
    return Reference(str(doc["source"]), trees)


def load_reference(path: Path = REFERENCE_PATH) -> Reference:
    if not path.exists():
        raise ReferenceError(f"no reference statistics at {path}; run tools/build_reference.py")
    return from_json(path.read_text(encoding="utf-8"))


def _tree_problems(spec: TreeSpec, have: TreeReference) -> list[str]:
    out = []
    if spec.genres != have.genres or spec.floor_any != have.floor_any:
        out.append(f"tree '{spec.tree}': its reference genres or floor differ from the shipped reference")
    for name, scale in spec.scales.items():
        got = have.scales.get(name)
        if got is None or (got.tags, got.percentiles) != (scale.tags, scale.percentiles):
            out.append(f"tree '{spec.tree}': scale '{name}' is missing from the reference or has other tags")
    return out


def problems(ref: Reference, specs: Sequence[TreeSpec]) -> list[str]:
    """Every scale or reference definition a tree file names that the shipped statistics do not cover."""
    out: list[str] = []
    for spec in specs:
        have = ref.trees.get(spec.tree)
        if have is None:
            out.append(f"tree '{spec.tree}' has no entry in the reference statistics")
            continue
        out.extend(_tree_problems(spec, have))
    return out
