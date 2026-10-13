"""What a profile keeps of its own: the store's rules for ratings and short reviews, and their routes."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from itertools import count
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from matinee import records as records_module
from matinee.records import MAX_REVIEW, Records
from matinee.store import Store, StoreError
from test_profiles import door  # noqa: F401  (the web fixture)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[], str]]:
    """Each store write reads a later time: t01, t02, ..."""
    ticks = count(1)

    def tick() -> str:
        return f"t{next(ticks):02d}"

    monkeypatch.setattr(records_module, "now", tick)
    yield tick


@pytest.fixture
def two(tmp_path: Path) -> tuple[Records, Store, tuple[int, str], tuple[int, str]]:
    """The records, the store, and two profiles each with its own device token."""
    store = Store(tmp_path / "matinee.sqlite")
    ada, ada_token = store.create("Ada", None, [])
    bo, bo_token = store.create("Bo", None, [])
    return Records(store), store, (ada.id, ada_token), (bo.id, bo_token)


def test_a_rating_is_saved_changed_and_cleared(two: Any, clock: Any) -> None:
    records, _, (ada, token), _ = two
    first = records.rate(ada, 5, 4, [token])
    assert (first.tmdb, first.score, first.at, first.source, first.outside, first.review) == (
        5,
        4,
        "t01",
        "matinee",
        None,
        None,
    )
    changed = records.rate(ada, 5, 2, [token])
    assert (changed.score, changed.at) == (2, "t02")
    assert records.unrate(ada, 5, [token]) is True
    assert records.ratings(ada, [token]) == []
    assert records.unrate(ada, 5, [token]) is False


def test_the_same_answer_again_records_nothing_and_keeps_the_first_time(two: Any, clock: Any) -> None:
    records, _, (ada, token), _ = two
    records.rate(ada, 5, 3, [token])
    again = records.rate(ada, 5, 3, [token])
    assert (again.score, again.at) == (3, "t01")


def test_a_short_review_is_saved_changed_and_cleared_and_never_moves_the_time(two: Any, clock: Any) -> None:
    records, _, (ada, token), _ = two
    records.rate(ada, 5, 5, [token])
    assert records.review(ada, 5, "  A delight.  ", [token]).review == "A delight."
    assert records.rate(ada, 5, 4, [token]).review == "A delight."  # a new answer keeps the short review
    changed = records.review(ada, 5, "Still a delight.", [token])
    assert (changed.review, changed.at) == ("Still a delight.", "t02")
    assert records.review(ada, 5, "", [token]).review is None
    records.review(ada, 5, "Back again.", [token])
    assert records.review(ada, 5, None, [token]).review is None


def test_clearing_a_rating_takes_its_short_review_with_it(two: Any, clock: Any) -> None:
    records, _, (ada, token), _ = two
    records.rate(ada, 5, 5, [token])
    records.review(ada, 5, "Loved the ending.", [token])
    records.unrate(ada, 5, [token])
    assert records.rate(ada, 5, 5, [token]).review is None


def test_a_short_review_over_the_limit_or_on_two_lines_is_refused_never_cut(two: Any) -> None:
    records, _, (ada, token), _ = two
    records.rate(ada, 5, 5, [token])
    records.review(ada, 5, "x" * MAX_REVIEW, [token])
    for bad in ("y" * (MAX_REVIEW + 1), "two\nlines", "a\ttab", "a\rb", "a\x85b", "a\u2028b", "a\u2029b"):
        with pytest.raises(StoreError) as refused:
            records.review(ada, 5, bad, [token])
        assert refused.value.code == "bad_review"
    assert records.ratings(ada, [token])[0].review == "x" * MAX_REVIEW


def test_a_short_review_keeps_joined_and_new_emoji(two: Any) -> None:
    records, _, (ada, token), _ = two
    records.rate(ada, 5, 5, [token])
    for text in (
        "Loved it \u2764\ufe0f\u200d\U0001f525",
        "Chef \U0001f9d1\u200d\U0001f373 kiss",
        "new \U0001fae9",
        "café",
    ):
        assert records.review(ada, 5, text, [token]).review == text


def test_another_profiles_rating_of_the_same_film_is_never_touched_or_answered(two: Any) -> None:
    records, _, (ada, ada_token), (bo, bo_token) = two
    records.rate(ada, 5, 5, [ada_token])
    records.rate(bo, 5, 1, [bo_token])
    records.review(bo, 5, "Bo's words", [bo_token])
    reviewed = records.review(ada, 5, "Ada's words", [ada_token])
    assert (reviewed.score, reviewed.review) == (5, "Ada's words")
    changed = records.rate(ada, 5, 4, [ada_token])
    assert (changed.score, changed.review) == (4, "Ada's words")
    records.unrate(ada, 5, [ada_token])
    assert [(r.tmdb, r.score, r.review) for r in records.ratings(bo, [bo_token])] == [(5, 1, "Bo's words")]


def test_ownership_is_checked_inside_the_write_transaction(two: Any, tmp_path: Path) -> None:
    _, store, (ada, token), _ = two
    with store.writing(ada, [token]) as db:
        assert db.in_transaction
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            sqlite3.connect(tmp_path / "matinee.sqlite", timeout=0).execute("BEGIN IMMEDIATE")


def test_a_short_review_needs_a_rating(two: Any) -> None:
    records, _, (ada, token), _ = two
    with pytest.raises(StoreError) as refused:
        records.review(ada, 5, "Never saw it.", [token])
    assert refused.value.code == "not_rated"
    assert records.ratings(ada, [token]) == []


@pytest.mark.parametrize("score", [0, 6, -1])
def test_only_the_five_answers_are_kept(two: Any, score: int) -> None:
    records, _, (ada, token), _ = two
    with pytest.raises(StoreError) as refused:
        records.rate(ada, 5, score, [token])
    assert refused.value.code == "bad_score"


def test_ratings_read_back_newest_first_and_only_the_profiles_own(two: Any, clock: Any) -> None:
    records, _, (ada, ada_token), (bo, bo_token) = two
    records.rate(ada, 6, 3, [ada_token])
    records.rate(bo, 5, 1, [bo_token])
    records.rate(ada, 5, 5, [ada_token])
    assert [(r.tmdb, r.score) for r in records.ratings(ada, [ada_token])] == [(5, 5), (6, 3)]
    assert [(r.tmdb, r.score) for r in records.ratings(bo, [bo_token])] == [(5, 1)]


def test_a_device_that_does_not_hold_the_profile_reads_and_writes_nothing(two: Any) -> None:
    records, _, (ada, ada_token), (_, bo_token) = two
    records.rate(ada, 5, 4, [ada_token])
    attempts: list[Callable[[], object]] = [
        lambda: records.rate(ada, 5, 1, [bo_token]),
        lambda: records.unrate(ada, 5, [bo_token]),
        lambda: records.review(ada, 5, "not mine", [bo_token]),
        lambda: records.ratings(ada, [bo_token]),
        lambda: records.ratings(ada, []),
    ]
    for attempt in attempts:
        with pytest.raises(StoreError) as refused:
            attempt()
        assert refused.value.code == "not_held"
    [kept] = records.ratings(ada, [ada_token])
    assert (kept.score, kept.review) == (4, None)


def test_a_rating_never_lands_on_a_new_profile_that_reuses_a_deleted_ones_id(tmp_path: Path) -> None:
    store = Store(tmp_path / "matinee.sqlite")
    records = Records(store)
    gone, stale = store.create("Gone", None, [])
    store.delete(gone.id, [stale])
    newcomer, token = store.create("Newcomer", None, [])
    assert newcomer.id == gone.id
    with pytest.raises(StoreError) as refused:
        records.rate(gone.id, 5, 1, [stale])
    assert refused.value.code == "not_held"
    assert records.ratings(newcomer.id, [token]) == []


def me(client: TestClient) -> int:
    return int(client.post("/api/profiles", json={"name": "Ada"}).json()["id"])


def test_the_routes_save_read_change_and_clear_a_rating(door: Any) -> None:  # noqa: F811
    client, _ = door
    pid = me(client)
    saved = client.put(f"/api/profiles/{pid}/ratings/5", json={"score": 4})
    assert saved.status_code == 200 and saved.json()["score"] == 4 and saved.json()["review"] is None
    reviewed = client.put(f"/api/profiles/{pid}/ratings/5/review", json={"review": "Good fun."})
    assert reviewed.json()["review"] == "Good fun."
    assert [(r["tmdb"], r["score"], r["review"]) for r in client.get(f"/api/profiles/{pid}/ratings").json()] == [
        (5, 4, "Good fun.")
    ]
    assert client.delete(f"/api/profiles/{pid}/ratings/5").json() == {"tmdb": 5, "cleared": True}
    assert client.get(f"/api/profiles/{pid}/ratings").json() == []


def test_the_routes_refuse_in_words(door: Any) -> None:  # noqa: F811
    client, _ = door
    pid = me(client)
    unrated = client.put(f"/api/profiles/{pid}/ratings/5/review", json={"review": "Hmm."})
    assert unrated.status_code == 400 and unrated.json()["code"] == "not_rated"
    client.put(f"/api/profiles/{pid}/ratings/5", json={"score": 3})
    long = client.put(f"/api/profiles/{pid}/ratings/5/review", json={"review": "z" * (MAX_REVIEW + 1)})
    assert long.status_code == 400 and long.json()["message"] == "Short and sweet, please. About 20 words."
    assert client.put(f"/api/profiles/{pid}/ratings/5", json={"score": 9}).json()["code"] == "bad_score"
    assert client.put(f"/api/profiles/{pid}/ratings/999999", json={"score": 3}).status_code == 404
    assert client.put(f"/api/profiles/{pid}/ratings/5", json={"score": 3, "extra": 1}).status_code == 422


def test_another_device_is_refused_every_rating_route(door: Any) -> None:  # noqa: F811
    client, _ = door
    pid = me(client)
    client.put(f"/api/profiles/{pid}/ratings/5", json={"score": 5})
    elsewhere = TestClient(client.app, base_url="https://testserver")
    refusals = [
        elsewhere.get(f"/api/profiles/{pid}/ratings"),
        elsewhere.put(f"/api/profiles/{pid}/ratings/5", json={"score": 1}),
        elsewhere.put(f"/api/profiles/{pid}/ratings/5/review", json={"review": "mine now"}),
        elsewhere.delete(f"/api/profiles/{pid}/ratings/5"),
    ]
    assert [(r.status_code, r.json()["code"]) for r in refusals] == [(403, "not_held")] * 4
    assert [(r["score"], r["review"]) for r in client.get(f"/api/profiles/{pid}/ratings").json()] == [(5, None)]
