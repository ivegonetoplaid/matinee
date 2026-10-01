"""Which doors and kinds each film belongs to, as labelled outside Matinee and kept in its state directory.

The labels file lives beside the film table, never in this repository, because it
lists the films one library holds. Its shape (format 2):

    {"format": 2,
     "trees": {"action": {"kinds": {"1891": ["scifi_action", "quests"]}},
               "kids":   {"kinds": {"9340": ["adventure", "silly"]}, "bands": {"9340": "family"}}}}

`kinds` maps a TMDB id to the kinds it holds at that door; every film listed under
a door is behind it. A door that asks no question (Westerns) lists its films with
no kinds. `bands` gives each For the kids film the youngest age band it suits:
`little`, `family` or `older`. A film the file does not list at all has not been
labelled yet (`matinee.pools` gives it a waiting room). A missing file means no
film is labelled; a file in any other format or shape stops the server at start-up.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

FORMAT = 2
BANDS = ("little", "family", "older")  # youngest first
log = logging.getLogger("matinee.labels")


class LabelsError(ValueError):
    """The labels file is in another format or shape."""


@dataclass(frozen=True)
class TreeLabels:
    kinds: Mapping[int, frozenset[str]] = field(default_factory=dict)
    bands: Mapping[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Labels:
    trees: Mapping[str, TreeLabels] = field(default_factory=dict)

    def of(self, tree: str) -> TreeLabels:
        return self.trees.get(tree, TreeLabels())

    def films(self) -> frozenset[int]:
        """Every film the file lists under any door."""
        return frozenset().union(*(set(t.kinds) for t in self.trees.values()))


def _bands(name: str, raw: object) -> dict[int, str]:
    if not isinstance(raw, dict) or set(raw.values()) - set(BANDS):
        raise LabelsError(f"labels for tree '{name}': 'bands' must map TMDB ids to one of {list(BANDS)}")
    return {int(t): str(b) for t, b in raw.items()}


def _tree(name: str, raw: object) -> TreeLabels:
    if not isinstance(raw, dict) or set(raw) - {"kinds", "bands"}:
        raise LabelsError(f"labels for tree '{name}' must hold only 'kinds' and 'bands'")
    kinds = raw.get("kinds", {})
    if not isinstance(kinds, dict) or not all(isinstance(v, list) for v in kinds.values()):
        raise LabelsError(f"labels for tree '{name}': 'kinds' must map TMDB ids to lists of kinds")
    try:
        return TreeLabels(
            kinds={int(t): frozenset(str(k) for k in v) for t, v in kinds.items()},
            bands=_bands(name, raw.get("bands", {})),
        )
    except (TypeError, ValueError) as exc:
        raise LabelsError(f"labels for tree '{name}' name a film by something other than a TMDB id") from exc


def load_labels(path: Path) -> Labels:
    """Read the labels file; an absent file is no labels, logged, and a malformed one raises LabelsError."""
    if not path.exists():
        log.warning("no labels file at %s; every film waits behind the doors its genres name", path)
        return Labels()
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        found = doc.get("format") if isinstance(doc, dict) else None
        raise LabelsError(
            f"the labels file at {path} is format {found}; this Matinee reads only format {FORMAT}."
            " Write it again with the labelling pass's settle step."
        )
    trees = doc.get("trees", {})
    if not isinstance(trees, dict):
        raise LabelsError(f"the labels file at {path} has no 'trees' mapping")
    return Labels({name: _tree(name, raw) for name, raw in trees.items()})
