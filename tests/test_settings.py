"""A profile's tailoring settings and welcome mark, and the languages the film table holds."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from matinee.languages import held
from matinee.store import FLOORS, Settings, Store, StoreError
from matinee.web import mine
from test_profiles import door  # noqa: F401  (the web fixture)

KNOWN = frozenset({"en", "fr", "ja"})


@pytest.fixture
def ada(tmp_path: Path) -> tuple[Store, int, str]:
    store = Store(tmp_path / "matinee.sqlite")
    profile, token = store.create("Ada", None, [])
    return store, profile.id, token


def settings(p: Any) -> tuple[str, frozenset[str], int, bool, bool]:
    return p.floor, p.languages, p.rated_out, p.sharing, p.welcomed


def test_a_new_profile_has_every_default_and_has_seen_the_welcome(ada: Any) -> None:
    store, pid, token = ada
    assert settings(store.profile(pid, [token])) == ("anything", frozenset(), 1, False, True)


def test_each_setting_changes_alone_and_the_rest_stay(ada: Any) -> None:
    store, pid, token = ada
    store.set_settings(pid, Settings(floor="well_liked"), KNOWN, [token])
    store.set_settings(pid, Settings(languages=frozenset({"fr", "ja"})), KNOWN, [token])
    store.set_settings(pid, Settings(rated_out=0), KNOWN, [token])
    changed = store.set_settings(pid, Settings(sharing=True), KNOWN, [token])
    assert settings(changed) == ("well_liked", frozenset({"fr", "ja"}), 0, True, True)
    assert settings(store.profile(pid, [token])) == settings(changed)
    back = store.set_settings(pid, Settings(languages=frozenset(), sharing=False), KNOWN, [token])
    assert settings(back) == ("well_liked", frozenset(), 0, False, True)


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (Settings(floor="everything"), "bad_setting"),
        (Settings(rated_out=6), "bad_setting"),
        (Settings(rated_out=-1), "bad_setting"),
        (Settings(languages=frozenset({"de"})), "bad_language"),
        (Settings(languages=frozenset({"en", "xx"})), "bad_language"),
    ],
)
def test_a_value_outside_its_choices_is_refused_and_changes_nothing(ada: Any, change: Settings, code: str) -> None:
    store, pid, token = ada
    with pytest.raises(StoreError) as refused:
        store.set_settings(pid, change, KNOWN, [token])
    assert refused.value.code == code
    assert settings(store.profile(pid, [token])) == ("anything", frozenset(), 1, False, True)


def test_every_floor_offered_is_kept(ada: Any) -> None:
    store, pid, token = ada
    for floor in FLOORS:
        assert store.set_settings(pid, Settings(floor=floor), KNOWN, [token]).floor == floor


def test_a_ticked_language_the_table_no_longer_holds_stays_kept_and_never_refuses_a_save(ada: Any) -> None:
    store, pid, token = ada
    store.set_settings(pid, Settings(languages=frozenset({"fr", "ja"})), KNOWN, [token])
    later = frozenset({"en", "ja"})  # a rebuild dropped French
    kept = store.set_settings(pid, Settings(languages=frozenset({"fr", "ja", "en"})), later, [token])
    assert kept.languages == frozenset({"fr", "ja", "en"})
    assert store.set_settings(pid, Settings(sharing=True), later, [token]).languages == frozenset({"fr", "ja", "en"})
    assert store.set_settings(pid, Settings(languages=frozenset()), later, [token]).languages == frozenset()  # Any
    with pytest.raises(StoreError) as refused:  # once cleared, a language the table lost cannot be ticked again
        store.set_settings(pid, Settings(languages=frozenset({"fr"})), later, [token])
    assert refused.value.code == "bad_language"


def test_the_welcome_mark_is_kept(tmp_path: Path) -> None:
    store = Store(tmp_path / "matinee.sqlite")
    profile, token = store.create("Ada", None, [])
    with sqlite3.connect(tmp_path / "matinee.sqlite") as db:
        db.execute("UPDATE profiles SET welcomed = 0")  # as a profile made before this feature arrives
    assert store.profile(profile.id, [token]).welcomed is False
    assert store.welcome(profile.id, [token]).welcomed is True
    assert store.profile(profile.id, [token]).welcomed is True


def test_another_device_reads_and_changes_no_setting(ada: Any) -> None:
    store, pid, _ = ada
    _, other = store.create("Bo", None, [])
    attempts: list[Callable[[], object]] = [
        lambda: store.profile(pid, [other]),
        lambda: store.set_settings(pid, Settings(sharing=True), KNOWN, [other]),
        lambda: store.welcome(pid, [other]),
    ]
    for attempt in attempts:
        with pytest.raises(StoreError) as refused:
            attempt()
        assert refused.value.code == "not_held"


def test_the_languages_held_are_counted_most_first_and_never_the_placeholder() -> None:
    films = pd.DataFrame({"language": ["ja", "fr", "ja", None, "xx", "en", "fr", "ja", "", "de"], "audio": [None] * 10})
    assert held(films) == [("ja", 3), ("fr", 2), ("de", 1), ("en", 1)]


def me(client: TestClient) -> int:
    return int(client.post("/api/profiles", json={"name": "Ada"}).json()["id"])


def test_the_routes_read_and_change_settings_and_mark_the_welcome(door: Any) -> None:  # noqa: F811
    client, store = door
    pid = me(client)
    path = f"/api/profiles/{pid}/settings"
    assert client.get(path).json() == {
        "topics": [],
        "floor": "anything",
        "languages": [],
        "rated_out": 1,
        "sharing": False,
        "welcomed": True,
    }
    changed = client.put(path, json={"floor": "middle", "languages": ["fr"], "sharing": True}).json()
    assert (changed["floor"], changed["languages"], changed["rated_out"], changed["sharing"]) == (
        "middle",
        ["fr"],
        1,
        True,
    )
    refused = client.put(path, json={"languages": ["de"]})
    assert refused.status_code == 400 and refused.json()["code"] == "bad_language"
    assert client.put(path, json={"rated_out": 0}).json()["rated_out"] == 0
    assert client.get(path).json()["rated_out"] == 0
    assert client.put(path, json={"rated_out": 9}).json()["code"] == "bad_setting"
    assert client.put(path, json={"colour": "red"}).status_code == 422
    with sqlite3.connect(store._path) as db:
        db.execute("UPDATE profiles SET welcomed = 0")
    assert client.get(path).json()["welcomed"] is False
    assert client.post(f"/api/profiles/{pid}/welcomed").json()["welcomed"] is True


def test_another_device_is_refused_every_settings_route(door: Any) -> None:  # noqa: F811
    client, _ = door
    pid = me(client)
    elsewhere = TestClient(client.app, base_url="https://testserver")
    refusals = [
        elsewhere.get(f"/api/profiles/{pid}/settings"),
        elsewhere.put(f"/api/profiles/{pid}/settings", json={"sharing": True}),
        elsewhere.post(f"/api/profiles/{pid}/welcomed"),
    ]
    assert [(r.status_code, r.json()["code"]) for r in refusals] == [(403, "not_held")] * 3
    assert client.get(f"/api/profiles/{pid}/settings").json()["sharing"] is False


def test_the_page_learns_the_languages_the_film_table_holds(door: Any) -> None:  # noqa: F811
    client, _ = door
    assert client.get("/api/languages").json() == [
        {"code": "en", "films": 37},
        {"code": "fr", "films": 1},
    ]  # the live list


def test_the_front_door_never_carries_a_profiles_settings(door: Any) -> None:  # noqa: F811
    client, _ = door
    pid = me(client)
    client.put(f"/api/profiles/{pid}/settings", json={"sharing": True, "languages": ["fr"]})
    [tile] = client.get("/api/door").json()["profiles"]
    assert set(tile) == {"id", "name", "avatar", "has_pin", "held"}


def test_saving_a_setting_other_than_the_languages_never_reads_the_catalogue(
    door: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = door
    pid = me(client)

    def unreadable(films: Any) -> list[tuple[str, int]]:
        raise RuntimeError("the catalogue cannot be made")

    monkeypatch.setattr(mine, "held", unreadable)
    assert client.put(f"/api/profiles/{pid}/settings", json={"sharing": True}).json()["sharing"] is True
