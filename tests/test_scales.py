"""Scales cut into bands, and the pool floors agree with the tree files' reference floors."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from matinee.reference import DATA, Cuts, ReferenceError, spec_of
from matinee.scales import band_index, membership, offered, scale_of
from matinee.table import FilmTable

SPEC = {
    "score": "gore",
    "percentiles": [40, 70, 90],
    "bands": ["spotless", "some", "messy", "rip"],
    "unscored_bands": ["some", "messy"],
    "keyword_bonus": {"each": 0.08, "max_count": 3, "keywords": ["gore", "blood", "splatter", "torture"]},
}
SCORES = {"gore": ["g1", "g2"]}
CUTS = Cuts(("g1", "g2"), (40.0, 70.0, 90.0), (0.2, 0.4, 0.6))


def table(rows: dict[int, tuple[float, float] | None], keywords: dict[int, list[str] | None]) -> FilmTable:
    """A film table with tags g1 and g2; a row of None is a film the genome does not cover."""
    ids = list(rows)
    matrix = np.array([r if r is not None else (np.nan, np.nan) for r in rows.values()], dtype=np.float32)
    films = pd.DataFrame(
        {"keywords": [None if keywords.get(t) is None else frozenset(keywords[t] or []) for t in ids]}, index=ids
    )
    return FilmTable(films, ("g1", "g2"), matrix, datetime.now(UTC), None, "test")


def scale() -> object:
    return scale_of("horror", "gore", SPEC, SCORES)


def test_band_edges_belong_to_the_band_above() -> None:
    scores = pd.Series([0.0, 0.2, 0.39, 0.4, 0.6, 1.0, np.nan])
    assert band_index(scores, CUTS).tolist() == [0, 1, 1, 2, 3, 3, -1]


def test_membership_bonus_unscored_and_pins() -> None:
    t = table(
        {1: (0.1, 0.1), 2: (0.1, 0.1), 3: (0.1, 0.1), 4: None, 5: None, 6: (0.9, 0.9)},
        {1: [], 2: ["gore"], 3: ["gore", "blood", "splatter", "torture"], 4: ["gore", "blood"], 5: None, 6: []},
    )
    m = membership(
        t, scale_of("horror", "gore", SPEC, SCORES), CUTS, {"rip": frozenset({5}), "spotless": frozenset({6})}
    )
    bands = {i: sorted(b for b in m.columns if m.loc[i, b]) for i in m.index}
    assert bands[1] == ["spotless"]  # 0.10
    assert bands[2] == ["spotless"]  # 0.10 + 0.08 = 0.18
    assert bands[3] == ["some"]  # 0.10 + three bonuses (four keywords, capped) = 0.34
    assert bands[4] == ["messy", "some"]  # no genome entry: the keywords do not count
    assert bands[5] == ["rip"]  # pinned, although unscored
    assert bands[6] == ["spotless"]  # pinned, although it scores rip


def test_offered_answers() -> None:
    t = table({1: (0.1, 0.1), 2: None, 3: (0.9, 0.9)}, {})
    m = membership(t, scale_of("horror", "gore", SPEC, SCORES), CUTS, {})
    assert offered(m, frozenset({"spotless"})).tolist() == [True, False, False]
    assert offered(m, frozenset({"spotless", "some"})).tolist() == [True, True, False]
    assert offered(m, frozenset({"some", "messy"})).tolist() == [False, True, False]
    assert offered(m, frozenset({"rip"})).tolist() == [False, False, True]
    with pytest.raises(ReferenceError):
        offered(m, frozenset({"bucket"}))


def test_scale_spec_is_checked() -> None:
    with pytest.raises(ReferenceError):
        scale_of("horror", "gore", {**SPEC, "bands": ["spotless", "some", "messy"]}, SCORES)
    with pytest.raises(ReferenceError):
        scale_of("horror", "gore", {**SPEC, "unscored_bands": ["nope"]}, SCORES)


GORE_KEYWORDS = {
    "gore",
    "splatter",
    "extreme violence",
    "torture",
    "body horror",
    "dismemberment",
    "decapitation",
    "cannibalism",
    "brutality",
    "graphic violence",
    "blood",
    "bloody",
}


def test_gore_question_offers_the_decided_pails() -> None:
    """Decision 59, read against the shipped horror tree: each answer's pails, the unscored rule and the bonus."""
    doc = json.loads((DATA / "trees" / "horror.json").read_text(encoding="utf-8"))
    gore = next(q for q in doc["questions"] if q["id"] == "gore")
    offers = [o["filter"]["bands"] for o in gore["options"]]
    assert [b["scale"] for b in offers] == ["gore"] * 4
    assert [b["in"] for b in offers] == [
        ["spotless"],
        ["spotless", "some"],
        ["some", "messy"],
        ["spotless", "some", "messy", "rip"],
    ]
    assert offers[gore["treat_as"]]["in"] == ["spotless"]
    scale = doc["scales"]["gore"]
    assert scale["percentiles"] == [40, 70, 90]
    assert scale["unscored_bands"] == ["some", "messy"]
    assert scale["keyword_bonus"]["each"] == 0.08
    assert scale["keyword_bonus"]["max_count"] == 3
    assert set(scale["keyword_bonus"]["keywords"]) == GORE_KEYWORDS
    assert doc["scores"][scale["score"]] == [
        "gore",
        "goretastic",
        "gory",
        "bloody",
        "splatter",
        "gruesome",
        "gratuitous violence",
        "torture",
    ]
    assert set(gore["skip_if_topics"]) == {188, 296, 331, 203, 250, 200, 361, 171, 258, 223, 254, 255}


def test_spec_of_accepts_engine_keys_on_a_scale_and_nothing_else() -> None:
    gore: dict[str, object] = dict(SPEC)
    doc = {
        "scores": {"gore": ["g1"]},
        "reference": {"movielens_genres": ["Horror"], "floor_any": {}},
        "scales": {"gore": gore},
    }
    spec = spec_of("horror", doc)
    assert spec is not None and spec.scales["gore"].percentiles == (40.0, 70.0, 90.0)
    gore["bandz"] = []
    with pytest.raises(ReferenceError):
        spec_of("horror", doc)
