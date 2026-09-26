"""Scales a tree cuts into answers, such as horror's gore pails.

A scale's score is the mean genome relevance of its tags, plus an optional
keyword bonus that applies only to films with a genome entry. Its bands are cut
at the fixed scores the reference statistics ship: a film belongs to band i when
its score is at or above cut i-1 and below cut i. A film with no genome entry has
no score and belongs to the scale's `unscored_bands`. A house pin places a film
in one band whatever its score.

An answer offers a set of bands, and a film is offered when any band it belongs
to is in that set.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from matinee.reference import Cuts, ReferenceError
from matinee.table import FilmTable


@dataclass(frozen=True)
class KeywordBonus:
    each: float
    max_count: int
    keywords: frozenset[str]


@dataclass(frozen=True)
class Scale:
    tree: str
    name: str
    tags: tuple[str, ...]
    bands: tuple[str, ...]
    unscored_bands: frozenset[str]
    bonus: KeywordBonus | None


def scale_of(tree: str, name: str, spec: Mapping[str, Any], scores: Mapping[str, Any]) -> Scale:
    """A scale from its tree-file entry; raises ReferenceError when its bands do not fit its percentiles."""
    bands = tuple(spec.get("bands", ()))
    if len(bands) != len(spec["percentiles"]) + 1:
        raise ReferenceError(f"tree '{tree}' scale '{name}' needs one more band than it has cut points")
    unscored = frozenset(spec.get("unscored_bands", bands))
    if not unscored <= set(bands):
        raise ReferenceError(f"tree '{tree}' scale '{name}' names unscored bands it does not have")
    bonus = spec.get("keyword_bonus")
    return Scale(
        tree=tree,
        name=name,
        tags=tuple(scores[spec["score"]]),
        bands=bands,
        unscored_bands=unscored,
        bonus=None
        if bonus is None
        else KeywordBonus(float(bonus["each"]), int(bonus["max_count"]), frozenset(bonus["keywords"])),
    )


def film_scores(table: FilmTable, scale: Scale) -> pd.Series:
    """The scale's score per film: NaN where the genome does not cover the film, bonus only where it does."""
    base = table.mean_of(scale.tags)
    if scale.bonus is None:
        return base
    bonus = scale.bonus
    hits = table.films.keywords.map(lambda k: min(len(bonus.keywords & (k or frozenset())), bonus.max_count))
    return base + bonus.each * hits.astype(float)


def band_index(scores: pd.Series, cuts: Cuts) -> pd.Series:
    """Band number per film (0 below the first cut); -1 where the film has no score."""
    idx = np.searchsorted(np.asarray(cuts.cuts), scores.to_numpy(), side="right")
    return pd.Series(np.where(scores.isna(), -1, idx), index=scores.index)


def membership(table: FilmTable, scale: Scale, cuts: Cuts, pins: Mapping[str, frozenset[int]]) -> pd.DataFrame:
    """One boolean column per band: whether each film belongs to it."""
    idx = band_index(film_scores(table, scale), cuts)
    ids = table.films.index
    pinned = pd.Series(False, index=ids)
    for band_pins in pins.values():
        pinned |= ids.isin(list(band_pins))
    out = {}
    for i, band in enumerate(scale.bands):
        scored = idx.eq(i) | (idx.eq(-1) & (band in scale.unscored_bands))
        out[band] = (scored & ~pinned) | pd.Series(ids.isin(list(pins.get(band, frozenset()))), index=ids)
    return pd.DataFrame(out)


def offered(members: pd.DataFrame, bands: frozenset[str]) -> pd.Series:
    """Films an answer offering `bands` shows."""
    unknown = bands - set(members.columns)
    if unknown:
        raise ReferenceError(f"an answer names bands the scale does not have: {sorted(unknown)}")
    return members[sorted(bands)].any(axis=1)
