"""Shared ratings: what the household's other profiles receive of a profile's ratings, and that nothing else of a
profile ever reaches another device."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from matinee.records import Records, Walk
from matinee.store import Settings, Store, StoreError
from matinee.web.common import TOKENS_COOKIE
from test_profiles import door  # noqa: F401  (the web fixture)

SECRET = "BO-PRIVATE-WORDS"


@pytest.fixture
def house(tmp_path: Path) -> Any:
    store = Store(tmp_path / "matinee.sqlite")
    records = Records(store)
    seats = {
        name: store.create(name, None, [], avatar) for name, avatar in (("Ada", "popcorn"), ("Bo", None), ("Cy", "vhs"))
    }
    return store, records, {name: (p.id, token) for name, (p, token) in seats.items()}


def share(store: Store, seat: tuple[int, str], on: bool) -> None:
    store.set_settings(seat[0], Settings(sharing=on), frozenset(), [seat[1]])


def seen(records: Records, seat: tuple[int, str], tmdb: int = 5) -> list[tuple[str, int, str | None]]:
    return [(r.name, r.score, r.review) for r in records.shared(seat[0], tmdb, [seat[1]])]


def test_only_profiles_that_share_reach_the_household_and_never_ones_own(house: Any) -> None:
    store, records, seat = house
    records.rate(seat["Ada"][0], 5, 5, [seat["Ada"][1]])
    records.review(seat["Ada"][0], 5, "Lovely.", [seat["Ada"][1]])
    records.rate(seat["Bo"][0], 5, 3, [seat["Bo"][1]])
    records.review(seat["Bo"][0], 5, SECRET, [seat["Bo"][1]])
    share(store, seat["Ada"], True)
    assert seen(records, seat["Cy"]) == [("Ada", 5, "Lovely.")]  # Bo's sharing is off
    assert seen(records, seat["Ada"]) == []  # her own rating is never shown to her as a shared one
    assert seen(records, seat["Bo"]) == [("Ada", 5, "Lovely.")]  # whether or not the viewer shares


def test_turning_sharing_on_or_off_takes_effect_on_the_next_request_for_every_rating(house: Any) -> None:
    store, records, seat = house
    records.rate(seat["Bo"][0], 5, 3, [seat["Bo"][1]])
    records.rate(seat["Bo"][0], 6, 1, [seat["Bo"][1]])
    share(store, seat["Bo"], True)
    assert seen(records, seat["Cy"]) == [("Bo", 3, None)] and seen(records, seat["Cy"], 6) == [("Bo", 1, None)]
    share(store, seat["Bo"], False)
    assert seen(records, seat["Cy"]) == [] and seen(records, seat["Cy"], 6) == []


def test_shared_ratings_stand_newest_first(house: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    store, records, seat = house
    times = iter(["2026-10-01T00:00:00+00:00", "2026-10-02T00:00:00+00:00"])
    monkeypatch.setattr("matinee.records.now", lambda: next(times))
    records.rate(seat["Bo"][0], 5, 2, [seat["Bo"][1]])
    records.rate(seat["Ada"][0], 5, 4, [seat["Ada"][1]])
    share(store, seat["Ada"], True)
    share(store, seat["Bo"], True)
    assert [name for name, _, _ in seen(records, seat["Cy"])] == ["Ada", "Bo"]


def test_a_deleted_profiles_shared_ratings_vanish_at_once(house: Any) -> None:
    store, records, seat = house
    records.rate(seat["Ada"][0], 5, 5, [seat["Ada"][1]])
    share(store, seat["Ada"], True)
    store.delete(seat["Ada"][0], [seat["Ada"][1]])
    assert seen(records, seat["Cy"]) == []


def test_a_shared_rating_carries_the_avatar_or_none_for_one_not_offered(house: Any, tmp_path: Path) -> None:
    store, records, seat = house
    for name in ("Ada", "Bo"):
        records.rate(seat[name][0], 5, 4, [seat[name][1]])
        share(store, seat[name], True)
    with sqlite3.connect(tmp_path / "matinee.sqlite") as db:
        db.execute("UPDATE profiles SET avatar = 'spaceship' WHERE name = 'Bo'")
    assert sorted((r.name, r.avatar) for r in records.shared(seat["Cy"][0], 5, [seat["Cy"][1]])) == [
        ("Ada", "popcorn"),
        ("Bo", None),
    ]


def test_a_device_that_holds_no_profile_receives_no_shared_rating(house: Any) -> None:
    store, records, seat = house
    records.rate(seat["Ada"][0], 5, 5, [seat["Ada"][1]])
    share(store, seat["Ada"], True)
    attempts: list[Callable[[], object]] = [
        lambda: records.shared(seat["Cy"][0], 5, []),
        lambda: records.shared(seat["Cy"][0], 5, [seat["Bo"][1]]),
    ]
    for attempt in attempts:
        with pytest.raises(StoreError) as refused:
            attempt()
        assert refused.value.code == "not_held"


def test_the_route_answers_a_held_profile_and_refuses_any_other_device(door: Any) -> None:  # noqa: F811
    client, store = door
    ada = client.post("/api/profiles", json={"name": "Ada"}).json()["id"]
    bo, bo_token = store.create("Bo", None, [], "soda")
    Records(store).rate(bo.id, 5, 4, [bo_token])
    Records(store).review(bo.id, 5, "Fun.", [bo_token])
    share(store, (bo.id, bo_token), True)
    assert client.get(f"/api/profiles/{ada}/shared/5").json() == [
        {"name": "Bo", "avatar": "soda", "score": 4, "review": "Fun."}
    ]
    assert client.get(f"/api/profiles/{ada}/shared/6").json() == []
    elsewhere = TestClient(client.app, base_url="https://testserver")
    assert elsewhere.get(f"/api/profiles/{ada}/shared/5").status_code == 403


def test_nothing_of_a_profile_but_what_it_shares_reaches_another_device(door: Any) -> None:  # noqa: F811
    client, store = door
    ada = client.post("/api/profiles", json={"name": "Ada"}).json()["id"]
    bo, token = store.create("Bo", None, [], None)
    records = Records(store)
    records.rate(bo.id, 5, 2, [token])
    records.review(bo.id, 5, SECRET, [token])
    records.hide(bo.id, 6, "good", [token])
    records.show(bo.id, "run-of-bo", 7, Walk("west", (), (SECRET + "-WALK",), False), [token])
    store.set_settings(bo.id, Settings(languages=frozenset({"fr"}), floor="well_liked"), frozenset({"fr"}), [token])
    me = {"profile_id": ada}
    replies = [
        client.get("/api/door"),
        client.post("/api/first", json={"viewer": me}),
        client.post("/api/walk", json={"tree": "west", "viewer": me}),
        client.post("/api/pick", json={"viewer": me}),
        client.get("/api/film/5"),
        client.get("/api/languages"),
        *(client.get(f"/api/profiles/{ada}/{what}") for what in ("ratings", "hidden", "runs", "settings", "shared/5")),
    ]
    for reply in replies:
        assert reply.status_code == 200, reply.request.url
        assert SECRET not in reply.text and "well_liked" not in reply.text
    for what in ("ratings", "hidden", "runs"):
        assert client.get(f"/api/profiles/{ada}/{what}").json() == [], what
    for what in ("ratings", "hidden", "runs", "settings", "shared/5"):
        assert client.get(f"/api/profiles/{bo.id}/{what}").status_code == 403
    bo_device = TestClient(client.app, base_url="https://testserver", cookies={TOKENS_COOKIE: token})
    assert SECRET + "-WALK" in bo_device.get(f"/api/profiles/{bo.id}/runs").text  # the marker is there to find
    store.set_settings(bo.id, Settings(sharing=True), frozenset(), [token])
    assert SECRET in client.get(f"/api/profiles/{ada}/shared/5").text  # shared: now, and only there
