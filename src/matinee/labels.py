"""Which kinds each film belongs to within a tree, as labelled outside Matinee and kept in its state directory.

The labels file lives beside the film table, never in this repository, because it
lists the films one library holds. Its shape:

    {"format": 1,
     "trees": {"horror": {"kinds": {"238": ["supernatural", "slowburn"], "431": []},
                          "out": [617505]}}}

`kinds` maps a TMDB id to the kinds it clearly fits; an empty list means the film
was labelled and fits no kind. Every film in `kinds` belongs to the tree and
joins its pool. `out` lists films that carry the tree's genre but belong
elsewhere; they leave the tree's pool when another tree holds them. A film
absent from `kinds` has not been labelled yet and sits under no kind. A missing
file means no film is labelled; a file in any other shape stops the server at
start-up.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

FORMAT = 1
log = logging.getLogger("matinee.labels")


class LabelsError(ValueError):
    """The labels file is in another format or shape."""


@dataclass(frozen=True)
class TreeLabels:
    kinds: Mapping[int, frozenset[str]] = field(default_factory=dict)
    out: frozenset[int] = frozenset()


@dataclass(frozen=True)
class Labels:
    trees: Mapping[str, TreeLabels] = field(default_factory=dict)

    def of(self, tree: str) -> TreeLabels:
        return self.trees.get(tree, TreeLabels())


def _tree(name: str, raw: object) -> TreeLabels:
    if not isinstance(raw, dict) or set(raw) - {"kinds", "out"}:
        raise LabelsError(f"labels for tree '{name}' must hold only 'kinds' and 'out'")
    kinds = raw.get("kinds", {})
    if not isinstance(kinds, dict) or not all(isinstance(v, list) for v in kinds.values()):
        raise LabelsError(f"labels for tree '{name}': 'kinds' must map TMDB ids to lists of kinds")
    try:
        return TreeLabels(
            kinds={int(t): frozenset(str(k) for k in v) for t, v in kinds.items()},
            out=frozenset(int(t) for t in raw.get("out", [])),
        )
    except (TypeError, ValueError) as exc:
        raise LabelsError(f"labels for tree '{name}' name a film by something other than a TMDB id") from exc


def load_labels(path: Path) -> Labels:
    """Read the labels file; an absent file is no labels, logged, and a malformed one raises LabelsError."""
    if not path.exists():
        log.warning("no labels file at %s; every labelled kind is empty", path)
        return Labels()
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise LabelsError(f"the labels file at {path} is not format {FORMAT}")
    trees = doc.get("trees", {})
    if not isinstance(trees, dict):
        raise LabelsError(f"the labels file at {path} has no 'trees' mapping")
    return Labels({name: _tree(name, raw) for name, raw in trees.items()})
