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


def test_a_kids_only_film_stays_out_of_western_and_nonfiction() -> None:
    table = make_table(
        [film(1, "Animation|Family|Western", "G", None), film(2, "Animation|Family|Documentary", "G", None)],
        {},
    )
    pools = build_pools(table, NO_PINS)
    assert pools["kids"][1] and pools["kids"][2]
    assert not pools["western"][1] and not pools["nonfiction"][2]


def test_a_standup_special_joins_comedy_and_stays_out_of_nonfiction() -> None:
    special = {**film(1, "Comedy|Documentary", "TV-MA", None), "keywords": frozenset({"stand-up comedy"})}
    pinned = film(2, "Documentary", "R", None)
    table = make_table([special, pinned, film(3, "Documentary", "R", None)], {})
    house = House(kids_pins={}, tree_pins={}, payoff_pins={}, scale_pins={}, specials=frozenset({2}))
    pools = build_pools(table, house)
    assert pools["comedy"].to_dict() == {1: True, 2: True, 3: False}
    assert pools["nonfiction"].to_dict() == {1: False, 2: False, 3: True}


def test_the_crime_pool_takes_every_crime_film_and_claims_no_stray() -> None:
    exciting = {"action": 0.9, "action packed": 0.9, "good action": 0.9}
    table = make_table(
        [film(1, "Crime", "R", None), film(2, "Crime", "R", None), film(3, "Drama", "R", None)],
        {1: {"action": 0.1}, 2: exciting, 3: {}},
    )
    pools = build_pools(table, NO_PINS)
    assert pools["crime"].to_dict() == {1: True, 2: True, 3: False}
    assert pools["drama"][1]  # a Crime film no other tree claims stays a drama stray beside the crime pool
    assert pools["action"][2]  # a Crime film exciting enough stays in action beside the crime pool
    assert not pools["action"][1]


def test_the_crime_pool_leaves_out_a_film_for_the_whole_family() -> None:
    table = make_table(
        [film(1, "Animation|Crime|Family", "PG", None), film(2, "Animation|Crime", "PG-13", None)], {1: {}, 2: {}}
    )
    pools = build_pools(table, NO_PINS)
    assert pools["kids:young"][1] and not pools["crime"][1]
    assert pools["crime"][2]  # an older kids' film may still be crime
