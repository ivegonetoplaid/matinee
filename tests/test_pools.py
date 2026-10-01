"""Pool rules on a constructed table."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from matinee.labels import Labels, TreeLabels
from matinee.pools import SCORES, House, build_pools, waiting
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
    pools = build_pools(table, NO_PINS, Labels())
    assert pools["kids"].to_dict() == {1: True, 2: False, 3: True, 4: False}
    assert pools["kids:franchise"].to_dict() == {1: False, 2: False, 3: True, 4: False}
    assert not pools["kids:family"][3]


def labels(**doors: dict[int, list[str]]) -> Labels:
    return Labels(
        {door: TreeLabels(kinds={t: frozenset(k) for t, k in films.items()}) for door, films in doors.items()}
    )


def test_a_labelled_film_is_behind_exactly_the_doors_listing_it_whatever_its_genres() -> None:
    table = make_table([film(1, "Adventure|Science Fiction", "PG-13", None), film(2, "Horror|Comedy", "R", None)], {})
    pools = build_pools(table, NO_PINS, labels(scifi={1: ["space_aliens"]}, comedy={2: ["horror_comedy"]}))
    assert [door for door in ("action", "scifi", "fantasy") if pools[door][1]] == ["scifi"]
    assert pools["comedy"][2] and not pools["horror"][2]


def test_an_unlisted_film_waits_behind_the_doors_its_genres_name() -> None:
    table = make_table(
        [
            film(1, "Adventure|Mystery|Science Fiction", "PG", None),
            film(2, "Western", "R", None),
            film(3, "Music", "R", None),
            film(4, "Documentary|War", "R", None),
        ],
        {},
    )
    pools = build_pools(table, NO_PINS, labels(western={2: []}))
    doors = ("action", "comedy", "drama", "thriller", "crime", "horror", "scifi", "fantasy", "romance", "animation")
    assert {door for door in (*doors, "western", "war") if pools[door][1]} == {"action", "thriller", "scifi"}
    assert waiting(table, NO_PINS, labels(western={2: []})).to_dict() == {1: True, 2: False, 3: True, 4: False}
    assert not any(pools[door][3] for door in doors)  # a film whose genres name no door waits behind none
    assert not pools["war"][4] and pools["nonfiction"][4]  # a documentary keeps its own rule and does not wait


def test_a_house_pin_puts_a_film_behind_a_door_the_labels_do_not() -> None:
    table = make_table([film(1, "Crime", "R", None)], {})
    house = House(kids_pins={}, tree_pins={"action": frozenset({1})}, payoff_pins={}, scale_pins={})
    pools = build_pools(table, house, labels(crime={1: ["cops"]}))
    assert pools["action"][1] and pools["crime"][1] and not pools["drama"][1]


def test_a_standup_special_joins_comedy_and_stays_out_of_nonfiction() -> None:
    special = {**film(1, "Comedy|Documentary", "TV-MA", None), "keywords": frozenset({"stand-up comedy"})}
    pinned = film(2, "Documentary", "R", None)
    table = make_table([special, pinned, film(3, "Documentary", "R", None)], {})
    house = House(kids_pins={}, tree_pins={}, payoff_pins={}, scale_pins={}, specials=frozenset({2}))
    pools = build_pools(table, house, Labels())
    assert pools["comedy"].to_dict() == {1: True, 2: True, 3: False}
    assert pools["nonfiction"].to_dict() == {1: False, 2: False, 3: True}
