"""The pick's rank: a film's place among its door's films by TMDB's vote average, in the decided words."""

from __future__ import annotations

import json
from collections.abc import Sequence
from types import SimpleNamespace
from typing import cast

import numpy as np
import pandas as pd
import pytest

from matinee.engine import VOTE_FLOOR, Catalog, FirstOption
from matinee.ranks import DOOR_WORDS, Rank, rank, rank_among
from matinee.reference import DATA


def films(scores: Sequence[float | None], votes: list[int] | None = None) -> pd.DataFrame:
    """Films 1..n with these TMDB scores and vote counts (every film over the floor unless given)."""
    n = len(scores)
    return pd.DataFrame(
        {
            "tmdb_rating": [np.nan if s is None else s for s in scores],
            "vote_count": pd.array(votes or [VOTE_FLOOR] * n, dtype="Int64"),
            "rating": [10.0] * n,  # the media server's rating: never read
        },
        index=pd.Index(range(1, n + 1), name="tmdb"),
    )


HUNDRED = films([float(100 - i) for i in range(100)])  # film k is k-th best: its place is k / 100
EVERY = np.ones(100, dtype=bool)


@pytest.mark.parametrize(
    ("position", "words", "standing"),
    [
        (1, "A crowd favourite in horror", "Top 5%"),
        (5, "A crowd favourite in horror", "Top 5%"),  # on the 5% edge: the higher band
        (6, "Very well received in horror", "Top 10%"),
        (10, "Very well received in horror", "Top 10%"),
        (11, "Well liked in horror", "Top 25%"),
        (25, "Well liked in horror", "Top 25%"),
        (26, "Above the middle in horror", "Top 40%"),
        (40, "Above the middle in horror", "Top 40%"),
        (41, "Middle of the pack in horror", "Middle 20%"),
        (60, "Middle of the pack in horror", "Middle 20%"),
        (61, "A tougher sell in horror", "Bottom 40%"),
        (90, "A tougher sell in horror", "Bottom 40%"),  # on the bottom-10% edge: the higher band
        (91, "Bringing up the rear in horror", "Bottom 10%"),
        (100, "Bringing up the rear in horror", "Bottom 10%"),
    ],
)
def test_a_film_reads_the_band_its_place_falls_in_and_an_edge_reads_as_the_higher(
    position: int, words: str, standing: str
) -> None:
    assert rank_among(HUNDRED, EVERY, position, "horror") == Rank(words, f"{standing} by TMDB audience rating")


def said(found: Rank | None) -> str | None:
    """The rank's words, or None for no rank."""
    return found.words if found else None


def test_films_with_the_same_score_share_the_better_place() -> None:
    scores = [float(100 - i) for i in range(100)]
    scores[3:6] = [96.5] * 3  # films 4, 5 and 6 tie: they share place 4, inside the top 5%
    tied = films(scores)
    assert {said(rank_among(tied, EVERY, t, "drama")) for t in (4, 5, 6)} == {"A crowd favourite in drama"}
    # Each tied film counts ahead of film 7.
    assert said(rank_among(tied, EVERY, 7, "drama")) == "Very well received in drama"


def test_a_film_under_the_vote_floor_or_without_a_score_has_no_rank_and_is_not_counted() -> None:
    scores: list[float | None] = [float(100 - i) for i in range(100)]
    votes = [VOTE_FLOOR] * 100
    scores[:5] = [200.0, 199.0, 198.0, 197.0, None]  # five films ahead of the rest, none of them counted
    votes[:4] = [VOTE_FLOOR - 1] * 4
    table = films(scores, votes)
    assert [rank_among(table, EVERY, t, "horror") for t in (1, 5)] == [None, None]
    assert said(rank_among(table, EVERY, 6, "horror")) == "A crowd favourite in horror"  # first of 95 counted


def test_the_rank_counts_only_the_doors_films_plus_the_film_itself() -> None:
    door = np.zeros(100, dtype=bool)
    door[[0, *range(2, 40)]] = True  # 39 films; film 2, second best of all, stands outside the door
    assert said(rank_among(HUNDRED, door, 3, "war")) == "Very well received in war films"  # 2nd of the door's 39
    assert said(rank_among(HUNDRED, door, 2, "war")) == "A crowd favourite in war films"  # 2nd of 39 and itself: 2/40
    assert said(rank_among(HUNDRED, door, 100, "war")) == "Bringing up the rear in war films"


def test_before_any_door_the_line_says_overall_and_the_media_servers_rating_is_never_read() -> None:
    assert said(rank_among(HUNDRED, EVERY, 30, None)) == "Above the middle overall"
    library = HUNDRED.assign(rating=np.linspace(0, 10, 100))
    assert said(rank_among(library, EVERY, 30, None)) == "Above the middle overall"


def test_every_door_the_first_question_offers_has_its_rank_word() -> None:
    doors = {o["tree"] for o in json.loads((DATA / "first_question.json").read_text(encoding="utf-8"))["options"]}
    assert doors == set(DOOR_WORDS)


def test_a_door_ranks_among_its_own_pool_and_before_a_door_among_every_doors_pool() -> None:
    horror, war = np.zeros(100, dtype=bool), np.zeros(100, dtype=bool)
    horror[:10], war[90:] = True, True
    cat = cast(
        Catalog,
        SimpleNamespace(
            table=SimpleNamespace(films=HUNDRED),
            trees={"horror": SimpleNamespace(pool="horror"), "war": SimpleNamespace(pool="war")},
            pools={"horror": horror, "war": war},
            first_options=(FirstOption("Horror", "horror", "Horror"), FirstOption("War", "war", "War")),
        ),
    )
    assert said(rank(cat, 95, "war")) == "Middle of the pack in war films"  # 5th of the door's 10
    assert said(rank(cat, 95, "horror")) == "Bringing up the rear in horror"  # behind all ten of horror's
    assert said(rank(cat, 95, None)) == "A tougher sell overall"  # 15th of the 20 behind either door
    assert rank(cat, 95, "west") is None  # a door with no word has no rank
