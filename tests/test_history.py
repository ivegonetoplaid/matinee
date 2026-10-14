"""A profile's history: the runs Matinee keeps, the films each showed, and what the viewer did with them."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from itertools import count
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from matinee import records as records_module
from matinee.records import MAX_RUNS, Records, Walk
from matinee.store import Store, StoreError
from test_profiles import door  # noqa: F401  (the web fixture)

WEST = Walk("west", (("era", 0),), ("Cowboys.", "old."), False)
RUSHED = Walk(None, (), (), True)
KEY = "run-0000aaaa"


@pytest.fixture
def two(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Records, Store, tuple[int, str], tuple[int, str]]:
    """The records, the store and two profiles with their tokens; each store write reads a later time."""
    ticks = count(1)
    monkeypatch.setattr(records_module, "now", lambda: f"2026-10-13T18:{next(ticks):02d}:00+00:00")
    store = Store(tmp_path / "matinee.sqlite")
    ada, ada_token = store.create("Ada", None, [])
    bo, bo_token = store.create("Bo", None, [])
    return Records(store), store, (ada.id, ada_token), (bo.id, bo_token)


def films(run: Any) -> list[tuple[int, str | None]]:
    return [(f.tmdb, f.mark) for f in run.films]


def test_a_run_is_kept_with_its_walk_once_its_first_film_is_shown(two: Any) -> None:
    records, _, (ada, token), _ = two
    records.show(ada, KEY, 5, WEST, [token])
    records.show(ada, KEY, 6, WEST, [token])
    [run] = records.history(ada, [token])
    assert (run.began, run.walk) == ("2026-10-13T18:01:00+00:00", WEST)
    assert films(run) == [(5, None), (6, None)]


def test_a_film_shown_again_moves_to_the_end_and_keeps_its_mark(two: Any) -> None:
    records, _, (ada, token), _ = two
    for tmdb in (5, 6, 7):
        records.show(ada, KEY, tmdb, WEST, [token])
    records.rate(ada, 5, 4, [token], run=KEY)
    records.show(ada, KEY, 5, WEST, [token])
    assert films(records.history(ada, [token])[0]) == [(6, None), (7, None), (5, "rated")]


def test_each_film_keeps_the_walk_that_reached_it_and_the_run_reads_its_latest(two: Any) -> None:
    records, _, (ada, token), _ = two
    records.show(ada, KEY, 5, WEST, [token])
    records.show(ada, KEY, 6, RUSHED, [token])
    [run] = records.history(ada, [token])
    assert [f.walk for f in run.films] == [WEST, RUSHED] and run.walk == RUSHED
    records.show(ada, KEY, 5, WEST, [token])  # brought back: now the latest
    [run] = records.history(ada, [token])
    assert films(run) == [(6, None), (5, None)] and run.walk == WEST


def test_a_rating_hide_or_note_on_the_pick_marks_the_film_in_its_run(two: Any) -> None:
    records, _, (ada, token), _ = two
    for tmdb in (5, 6, 7, 8):
        records.show(ada, KEY, tmdb, WEST, [token])
    records.rate(ada, 5, 5, [token], run=KEY)
    records.hide(ada, 6, "3m", [token], run=KEY)
    records.report(ada, KEY, 7, [token])
    assert films(records.history(ada, [token])[0]) == [(5, "rated"), (6, "hid"), (7, "reported"), (8, None)]


def test_undo_of_a_hide_clears_its_mark(two: Any) -> None:
    records, _, (ada, token), _ = two
    records.show(ada, KEY, 5, WEST, [token])
    records.hide(ada, 5, "good", [token], run=KEY)
    records.unhide(ada, 5, [token], run=KEY)
    assert films(records.history(ada, [token])[0]) == [(5, None)]


def test_undo_of_a_hide_gives_back_the_mark_it_replaced(two: Any) -> None:
    records, _, (ada, token), _ = two
    records.show(ada, KEY, 5, WEST, [token])
    records.rate(ada, 5, 1, [token], run=KEY)
    records.hide(ada, 5, "3m", [token], run=KEY)
    records.hide(ada, 5, "good", [token], run=KEY)  # a second hide keeps the first one's mark to give back
    assert films(records.history(ada, [token])[0]) == [(5, "hid")]
    records.unhide(ada, 5, [token], run=KEY)
    assert films(records.history(ada, [token])[0]) == [(5, "rated")]


def test_a_mark_never_lands_on_another_profiles_run_under_the_same_key(two: Any) -> None:
    records, _, (ada, ada_token), (bo, bo_token) = two
    records.show(bo, KEY, 5, WEST, [bo_token])
    records.show(ada, KEY, 5, WEST, [ada_token])
    records.rate(ada, 5, 5, [ada_token], run=KEY)
    assert films(records.history(ada, [ada_token])[0]) == [(5, "rated")]
    assert films(records.history(bo, [bo_token])[0]) == [(5, None)]


def test_a_rating_or_hide_made_elsewhere_marks_nothing(two: Any) -> None:
    records, _, (ada, token), _ = two
    records.show(ada, KEY, 5, WEST, [token])
    records.show(ada, "run-other-run", 6, WEST, [token])
    records.rate(ada, 5, 3, [token])  # from My profile: no run named
    records.hide(ada, 5, "3m", [token], run="run-other-run")  # a run that never showed it
    records.report(ada, None, 5, [token])
    assert [films(r) for r in records.history(ada, [token])] == [[(6, None)], [(5, None)]]


def test_a_profile_keeps_its_fifty_newest_runs(two: Any, tmp_path: Path) -> None:
    records, _, (ada, token), (bo, bo_token) = two
    assert MAX_RUNS == 50
    for n in range(MAX_RUNS + 1):
        if n == 25:
            records.show(bo, "run-of-bo-1", 9, WEST, [bo_token])  # amid hers, so a count of every profile's runs shows
        records.show(ada, f"run-of-ada-{n:03d}", 5, WEST, [token])
    kept = records.history(ada, [token])
    assert len(kept) == MAX_RUNS
    assert kept[0].began > kept[-1].began  # newest first
    assert kept[-1].began == "2026-10-13T18:02:00+00:00"  # the first of Ada's runs, at 18:01, went
    assert len(records.history(bo, [bo_token])) == 1  # another profile's runs are not counted against hers
    with sqlite3.connect(tmp_path / "matinee.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM run_films").fetchone() == (
            MAX_RUNS + 1,
        )  # the dropped run's films went


@pytest.mark.parametrize("key", ["short", "x" * 65, "has space!", "../../etc"])
def test_a_run_key_out_of_shape_is_refused(two: Any, key: str) -> None:
    records, _, (ada, token), _ = two
    with pytest.raises(StoreError) as refused:
        records.show(ada, key, 5, WEST, [token])
    assert refused.value.code == "bad_run"


def test_another_device_reads_and_writes_no_history(two: Any) -> None:
    records, _, (ada, ada_token), (bo, bo_token) = two
    records.show(ada, KEY, 5, WEST, [ada_token])
    attempts: list[Callable[[], object]] = [
        lambda: records.show(ada, KEY, 6, WEST, [bo_token]),
        lambda: records.report(ada, KEY, 5, [bo_token]),
        lambda: records.history(ada, [bo_token]),
    ]
    for attempt in attempts:
        with pytest.raises(StoreError) as refused:
            attempt()
        assert refused.value.code == "not_held"
    records.show(bo, KEY, 7, WEST, [bo_token])  # the same key under another profile is another run
    assert [films(r) for r in records.history(ada, [ada_token])] == [[(5, None)]]
    assert [films(r) for r in records.history(bo, [bo_token])] == [[(7, None)]]


def me(client: TestClient) -> int:
    return int(client.post("/api/profiles", json={"name": "Ada"}).json()["id"])


def test_the_routes_keep_a_shown_film_with_the_words_of_its_walk(door: Any) -> None:  # noqa: F811
    client, _ = door
    pid = me(client)
    walk = {"tree": "west", "answers": [{"question": "era", "option": 0}], "rushed": True}
    kept = client.post(f"/api/profiles/{pid}/runs/{KEY}/films", json={"tmdb": 5, **walk})
    assert kept.status_code == 200 and kept.json() == {"tmdb": 5, "run": KEY}
    client.put(f"/api/profiles/{pid}/ratings/5", json={"score": 4, "run": KEY})
    [run] = client.get(f"/api/profiles/{pid}/runs").json()
    walk_out = {
        "tree": "west",
        "answers": [{"question": "era", "option": 0}],
        "says": ["Cowboys.", "old."],
        "rushed": True,
    }
    assert run["walk"] == walk_out
    assert run["films"] == [
        {
            "tmdb": 5,
            "title": "Film 5",
            "year": client.get("/api/film/5").json()["year"],
            "mark": "rated",
            "walk": walk_out,
        }
    ]
    client.put(f"/api/profiles/{pid}/hidden/5", json={"length": "3m", "run": KEY})
    assert client.get(f"/api/profiles/{pid}/runs").json()[0]["films"][0]["mark"] == "hid"
    client.delete(f"/api/profiles/{pid}/hidden/5", params={"run": KEY})
    assert client.get(f"/api/profiles/{pid}/runs").json()[0]["films"][0]["mark"] == "rated"


def test_a_note_made_on_the_pick_marks_its_film_reported(door: Any) -> None:  # noqa: F811
    client, store = door
    pid = me(client)
    client.post(f"/api/profiles/{pid}/runs/{KEY}/films", json={"tmdb": 5, "tree": "west"})
    note = {"profile_id": pid, "tmdb": 5, "tree": "west", "kind": "quality", "run": KEY}
    assert client.post("/api/notes", json=note).status_code == 200
    assert [f["mark"] for f in client.get(f"/api/profiles/{pid}/runs").json()[0]["films"]] == ["reported"]
    refused = client.post("/api/notes", json={**note, "run": "bad key"})
    assert refused.status_code == 400 and refused.json()["code"] == "bad_run"
    assert len(store.notes()) == 1  # the refused note was never kept


def test_the_routes_refuse_a_walk_the_catalogue_does_not_hold(door: Any) -> None:  # noqa: F811
    client, _ = door
    pid = me(client)
    path = f"/api/profiles/{pid}/runs/{KEY}/films"
    assert client.post(path, json={"tmdb": 5, "tree": "space"}).status_code == 400
    assert client.post(path, json={"tmdb": 5, "answers": [{"question": "era", "option": 0}]}).status_code == 400
    assert (
        client.post(path, json={"tmdb": 5, "tree": "west", "answers": [{"question": "era", "option": 9}]}).status_code
        == 400
    )
    assert client.post(path, json={"tmdb": 999999, "tree": "west"}).status_code == 404
    assert client.get(f"/api/profiles/{pid}/runs").json() == []
    elsewhere = TestClient(client.app, base_url="https://testserver")
    assert elsewhere.get(f"/api/profiles/{pid}/runs").status_code == 403
    assert elsewhere.post(path, json={"tmdb": 5, "tree": "west"}).status_code == 403


def test_just_pick_one_before_any_door_is_kept_with_no_answers(door: Any) -> None:  # noqa: F811
    client, _ = door
    pid = me(client)
    client.post(f"/api/profiles/{pid}/runs/{KEY}/films", json={"tmdb": 5, "rushed": True})
    [run] = client.get(f"/api/profiles/{pid}/runs").json()
    assert run["walk"] == {"tree": None, "answers": [], "says": [], "rushed": True}


def test_a_film_no_longer_listed_leaves_its_run_and_an_emptied_run_is_not_shown(door: Any) -> None:  # noqa: F811
    client, store = door
    pid = me(client)
    tokens = list(client.cookies.values())
    client.post(f"/api/profiles/{pid}/runs/{KEY}/films", json={"tmdb": 5, "rushed": True})
    Records(store).show(pid, KEY, 999999, Walk(None, (), (), True), tokens)  # a film since gone from the film table
    Records(store).show(pid, "gone-run-1", 999999, Walk(None, (), (), True), tokens)
    assert [[f["tmdb"] for f in r["films"]] for r in client.get(f"/api/profiles/{pid}/runs").json()] == [[5]]
    assert len(Records(store).history(pid, tokens)) == 2  # both runs are kept


def test_a_door_with_no_tree_behind_it_is_refused(door: Any) -> None:  # noqa: F811
    client, _ = door
    pid = me(client)
    assert client.post(f"/api/profiles/{pid}/runs/{KEY}/films", json={"tmdb": 5, "tree": "none"}).status_code == 400
