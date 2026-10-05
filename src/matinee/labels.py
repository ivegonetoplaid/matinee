"""Which doors and kinds each film belongs to, as labelled outside Matinee and shipped in `data/labels.json`.

The labels file is Matinee's own judgement, keyed by TMDB id: every film of TMDB's
most-voted ten thousand, and every film of the first library it sorted. Its shape
(format 2):

    {"format": 2,
     "trees": {"action": {"kinds": {"1891": ["scifi_action", "quests"]}},
               "kids":   {"kinds": {"9340": ["adventure", "silly"]}, "bands": {"9340": "family"}}}}

`kinds` maps a TMDB id to the kinds it holds at that door; every film listed under
a door is behind it. A door that asks no question (Westerns) lists its films with
no kinds. `bands` gives each For the kids film the youngest age band it suits:
`little`, `family` or `older`. A film the file does not list at all has not been
labelled yet (`matinee.pools` gives it a waiting room). A missing file, or one in
any other format or shape, stops the server at start-up with a LabelsError naming
the problem.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from matinee.reference import DATA

FORMAT = 2
LABELS = DATA / "labels.json"
OVERRIDES = "overrides.json"  # the household's own placements, in the data directory; Matinee never writes it
BANDS = ("little", "family", "older")  # youngest first


class LabelsError(ValueError):
    """The labels file is in another format or shape."""


@dataclass(frozen=True)
class TreeLabels:
    kinds: Mapping[int, frozenset[str]] = field(default_factory=dict)
    bands: Mapping[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Labels:
    trees: Mapping[str, TreeLabels] = field(default_factory=dict)
    overridden: frozenset[int] = frozenset()  # films whose whole placement comes from the household file

    def of(self, tree: str) -> TreeLabels:
        return self.trees.get(tree, TreeLabels())

    def films(self) -> frozenset[int]:
        """Every film the file lists under any door."""
        return frozenset().union(*(set(t.kinds) for t in self.trees.values()))

    def named(self) -> frozenset[int]:
        """Every film the file names anywhere: under a door's kinds or in the kids bands."""
        return self.films() | frozenset().union(*(set(t.bands) for t in self.trees.values()))


def with_overrides(shipped: Labels, household: Labels) -> Labels:
    """The shipped labels with the household's laid over them: a film the household file names anywhere takes its
    whole placement from that file, every door and band of it, and keeps none of the shipped ones."""
    taken = household.named()
    trees: dict[str, TreeLabels] = {}
    for name in set(shipped.trees) | set(household.trees):
        ours, theirs = shipped.of(name), household.of(name)
        kinds = {t: k for t, k in ours.kinds.items() if t not in taken} | dict(theirs.kinds)
        bands = {t: b for t, b in ours.bands.items() if t not in taken} | dict(theirs.bands)
        trees[name] = TreeLabels(kinds, bands)
    return Labels(trees, taken)


def load_overrides(data_dir: Path) -> Labels | None:
    """The household override file, `overrides.json` in the data directory, or None when there is none.

    It has the labels file's shape. Raises LabelsError naming the path when it cannot be used.
    """
    path = data_dir / OVERRIDES
    return load_labels(path) if path.exists() else None


def _bands(name: str, raw: object) -> dict[int, str]:
    if not isinstance(raw, dict) or not all(isinstance(b, str) for b in raw.values()) or set(raw.values()) - set(BANDS):
        raise LabelsError(f"labels for tree '{name}': 'bands' must map TMDB ids to one of {list(BANDS)}")
    try:
        return {int(t): b for t, b in raw.items()}
    except (TypeError, ValueError) as exc:
        raise LabelsError(f"labels for tree '{name}' name a film by something other than a TMDB id") from exc


def _tree(name: str, raw: object) -> TreeLabels:
    if not isinstance(raw, dict) or set(raw) - {"kinds", "bands"}:
        raise LabelsError(f"labels for tree '{name}' must hold only 'kinds' and 'bands'")
    kinds = raw.get("kinds", {})
    if not isinstance(kinds, dict) or not all(isinstance(v, list) for v in kinds.values()):
        raise LabelsError(f"labels for tree '{name}': 'kinds' must map TMDB ids to lists of kinds")
    bands = _bands(name, raw.get("bands", {}))
    try:
        parsed_kinds = {int(t): frozenset(str(k) for k in v) for t, v in kinds.items()}
    except (TypeError, ValueError) as exc:
        raise LabelsError(f"labels for tree '{name}' name a film by something other than a TMDB id") from exc
    return TreeLabels(kinds=parsed_kinds, bands=bands)


def load_labels(path: Path = LABELS) -> Labels:
    """Read the labels file; raises LabelsError naming the path when it is absent or malformed."""
    if not path.exists():
        raise LabelsError(f"no labels file at {path}; it ships with Matinee, so the checkout is incomplete")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LabelsError(f"the labels file at {path} is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        found = doc.get("format") if isinstance(doc, dict) else None
        raise LabelsError(
            f"the labels file at {path} is format {found!r}; this Matinee reads only format {FORMAT}."
            " Write it again with the labelling pass's settle step."
        )
    trees = doc.get("trees", {})
    if not isinstance(trees, dict):
        raise LabelsError(f"the labels file at {path} has no 'trees' mapping")
    return Labels({name: _tree(name, raw) for name, raw in trees.items()})
