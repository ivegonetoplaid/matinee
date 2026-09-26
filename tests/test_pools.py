"""Pool rules on a constructed table."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from matinee.pools import SCORES, House, build_pools
from matinee.table import FilmTable

TAGS = tuple(sorted({t for tags in SCORES.values() for t in tags}))
NO_PINS = House(kids_pins={}, tree_pins={}, payoff_pins={}, scale_pins={})


def make_table(films: list[dict[str, object]], relevance: dict[int, dict[str, float]]) -> FilmTable:
    """Films with default relevance 0.1 on every tag, overridden per film; a film absent from `relevance` has none."""
    frame = pd.DataFrame(films).set_index("tmdb")
    frame["collection_id"] = frame["collection_id"].astype("Int64")
    matrix = np.full((len(frame), len(TAGS)), np.nan, dtype=np.float32)
    for i, t in enumerate(frame.index):
        if t in relevance:
            matrix[i] = 0.1
            for tag, value in relevance[t].items():
                matrix[i, TAGS.index(tag)] = value
    return FilmTable(frame, TAGS, matrix, datetime.now(UTC), None, "test")


def film(tmdb: int, genres: str, cert: str, collection: int | None) -> dict[str, object]:
    return {
        "tmdb": tmdb,
        "name": f"Film {tmdb}",
        "year": 2000,
        "genres": frozenset(genres.split("|")),
        "certificate": cert,
        "keywords": frozenset(),
        "collection_id": collection,
        "tmdb_known": True,
    }


def test_kids_franchise_respects_the_adult_ceiling_and_joins_as_rough() -> None:
    table = make_table(
        [
            film(1, "Animation|Family", "G", 7),
            film(2, "Adventure", "PG-13", 7),
            film(3, "Adventure", "PG-13", 7),
            film(4, "Adventure", "R", 7),
        ],
        {1: {}, 2: {"foul language": 0.6}, 3: {"foul language": 0.2}, 4: {}},
    )
    pools = build_pools(table, NO_PINS)
    assert pools["kids"].to_dict() == {1: True, 2: False, 3: True, 4: False}
    assert pools["kids:franchise"].to_dict() == {1: False, 2: False, 3: True, 4: False}
    assert not pools["kids:family"][3]


def test_missing_score_never_removes_a_film_from_horror() -> None:
    table = make_table(
        [film(1, "Horror|Comedy", "R", None), film(2, "Horror|Comedy", "R", None), film(3, "Horror", "R", None)],
        {1: {"scary": 0.0, "frightening": 0.0, "creepy": 0.0, "horror": 0.0}, 3: {}},
    )
    pools = build_pools(table, NO_PINS)
    assert pools["horror"].to_dict() == {1: False, 2: True, 3: True}
    assert pools["comedy"][1]
