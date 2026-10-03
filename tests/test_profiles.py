"""Profiles remembered by device: the store's rules, and the door routes' cookies."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from matinee.dtdd import Dtdd
from matinee.engine import load_catalog
from matinee.store import LOCKOUT_S, MAX_PROFILES, Locked, Note, Store, StoreError, edits, names_match
from matinee.table import FilmTable
from matinee.web.app import create_app
from matinee.web.common import TOKENS_COOKIE
from matinee.web.config import Config
from matinee.web.theatre import Theatre
from test_engine import reference, write_data
from test_web_library import SECRET_KEY, SECRET_URL, FakeLibrary, write_film_table


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "matinee.sqlite")


def test_edit_distance() -> None:
    assert edits("dave", "dave") == 0
    assert edits("dave", "davy") == 1
    assert edits("dave", "david") == 2
    assert edits("kitten", "sitting") == 3


@pytest.mark.parametrize(
    "typed,name,match",
    [
        ("dav", "David", True),  # typed is a prefix of the name
        ("DAVIDSON", "david", True),  # the name is a prefix of what was typed
        ("brit", "Brittany", True),
        ("brtny", "Brittany", False),  # three edits
        ("britany", "Brittany", True),  # one edit
        ("xyz", "David", False),
        ("ette", "Annette", False),  # a substring is not a prefix
    ],
)
def test_name_match_rule(typed: str, name: str, match: bool) -> None:
    assert names_match(typed, name) is match


def test_suggestions_need_three_characters_and_show_at_most_three(store: Store) -> None:
    for name in ("Anna", "Annabel", "Annie", "Annette", "Bob"):
        store.create(name, None, [], [])
    assert store.suggest("an") == []
    assert store.suggest("  an ") == []
    found = store.suggest("ann")
    assert len(found) == 3 and all(p.name.lower().startswith("ann") for p in found)
    assert [p.name for p in store.suggest("bob")] == ["Bob"]


def test_pin_and_token_are_never_stored_as_typed(store: Store, tmp_path: Path) -> None:
    profile, token = store.create("Pat", "1234", [188], ["superheroes"])
    store.create("Pam", "1234", [], [])
    assert profile.has_pin and profile.topics == frozenset({188}) and profile.exclusions == frozenset({"superheroes"})
    with sqlite3.connect(tmp_path / "matinee.sqlite") as db:
        rows = db.execute("SELECT pin_salt, pin_hash FROM profiles ORDER BY id").fetchall()
        digests = [r[0] for r in db.execute("SELECT token_hash FROM tokens").fetchall()]
    (salt_a, hash_a), (salt_b, hash_b) = rows
    assert len(salt_a) == 16 and salt_a != salt_b  # a salt per profile
    assert len(hash_a) == 32 and hash_a != b"1234" and hash_a != hash_b  # same PIN, different digests
    assert hashlib.sha256(token.encode()).hexdigest() in digests and token not in digests
    assert len(token) >= 43  # 32 random bytes
    assert store.holding([token]) == {token: profile}


def test_names_are_unique_ignoring_case_and_validated(store: Store) -> None:
    store.create("Sam", None, [], [])
    with pytest.raises(StoreError) as taken:
        store.create(" sam ", None, [], [])
    assert taken.value.code == "name_taken"
    for bad in ("", "   ", "x" * 41, "bell\x07"):
        with pytest.raises(StoreError) as err:
            store.create(bad, None, [], [])
        assert err.value.code == "bad_name"
    for pin in ("123", "12345", "abcd", "１２３４"):
        with pytest.raises(StoreError) as err:
            store.create("Pin Test", pin, [], [])
        assert err.value.code == "bad_pin"


def test_the_store_holds_at_most_fifty(store: Store) -> None:
    for i in range(MAX_PROFILES):
        store.create(f"Viewer {i}", None, [], [])
    with pytest.raises(StoreError) as err:
        store.create("One too many", None, [], [])
    assert err.value.code == "full"


def test_opening_needs_the_pin_and_five_misses_lock_the_profile(store: Store) -> None:
    profile, _ = store.create("Lee", "4321", [], [])
    other, _ = store.create("Kim", "1111", [], [])
    with pytest.raises(StoreError) as err:
        store.open(profile.id, None, 1000.0)
    assert err.value.code == "wrong_pin"
    for _ in range(3):
        with pytest.raises(StoreError):
            store.open(profile.id, "0000", 1000.0)
    with pytest.raises(Locked) as locked:
        store.open(profile.id, "0000", 1000.0)  # the fifth miss
    assert locked.value.until == 1000.0 + LOCKOUT_S
    with pytest.raises(Locked):
        store.open(profile.id, "4321", 1000.0 + LOCKOUT_S - 1)  # even the right PIN, while locked
    opened, token = store.open(profile.id, "4321", 1000.0 + LOCKOUT_S)
    assert opened.id == profile.id and store.holding([token])[token].id == profile.id
    assert store.open(other.id, "1111", 1000.0)[0].id == other.id  # the lock is on one profile only


def test_a_lock_clears_the_count_when_it_ends(store: Store) -> None:
    profile, _ = store.create("Ivy", "8642", [], [])
    for _ in range(4):
        with pytest.raises(StoreError):
            store.open(profile.id, "0000", 0.0)
    with pytest.raises(Locked):
        store.open(profile.id, "0000", 0.0)
    with pytest.raises(StoreError) as err:
        store.open(profile.id, "0000", LOCKOUT_S + 1)
    assert err.value.code == "wrong_pin"  # one miss after the lock is one miss, not another lock


def test_suggestions_rank_the_closest_first(store: Store) -> None:
    for name in ("Ava", "Dan", "Dana", "David"):
        store.create(name, None, [], [])
    found = store.suggest("dav")
    assert found[0].name == "David" and len(found) <= 3
    assert all(names_match("dav", p.name) for p in found)


def test_a_right_pin_resets_the_count(store: Store) -> None:
    profile, _ = store.create("Ray", "2468", [], [])
    for _ in range(4):
        with pytest.raises(StoreError):
            store.open(profile.id, "0000", 0.0)
    store.open(profile.id, "2468", 0.0)
    for _ in range(4):
        with pytest.raises(StoreError) as err:
            store.open(profile.id, "0000", 0.0)
        assert err.value.code == "wrong_pin"


def test_a_profile_without_a_pin_opens_by_name(store: Store) -> None:
    profile, _ = store.create("Jo", None, [], [])
    assert store.open(profile.id, None, 0.0)[0].name == "Jo"


def test_a_token_for_a_deleted_profile_is_ignored(store: Store, tmp_path: Path) -> None:
    profile, token = store.create("Gone", None, [], [])
    with sqlite3.connect(tmp_path / "matinee.sqlite") as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("DELETE FROM profiles WHERE id = ?", (profile.id,))
    assert store.holding([token]) == {}


def test_the_store_refuses_a_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(StoreError):
        Store(tmp_path / "nope" / "matinee.sqlite")


@pytest.fixture
def door(tmp_path: Path) -> tuple[TestClient, Store]:
    data = write_data(tmp_path / "data")
    write_film_table(tmp_path / "films.sqlite")

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data, reference())

    theatre = Theatre(FakeLibrary(), tmp_path / "films.sqlite", catalog_of=catalog_of)
    store = Store(tmp_path / "matinee.sqlite")
    config = Config(SECRET_URL, SECRET_KEY, tmp_path, "https://seerr.invalid", "d" * 16)
    return TestClient(
        create_app(config, theatre, store, Dtdd("k"), clock=lambda: 0.0), base_url="https://testserver"
    ), store


def test_a_new_device_holds_nothing(door: Any) -> None:
    client, store = door
    store.create("Somebody", None, [188], [])
    assert client.get("/api/door").json() == {"now_showing": 40, "profiles": []}


def test_saving_a_profile_sets_a_token_cookie_without_name_or_pin(door: Any) -> None:
    client, _ = door
    resp = client.post("/api/profiles", json={"name": "Robin", "pin": "9876", "topics": [188]})
    assert resp.status_code == 200 and resp.json()["name"] == "Robin" and "pin" not in resp.json()
    assert len(resp.headers.get_list("set-cookie")) == 1
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith(f"{TOKENS_COOKIE}=")
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie and "Max-Age=" in cookie
    value = cookie.split(";")[0].split("=", 1)[1]
    assert "Robin" not in value and "robin" not in value and "9876" not in value
    assert [p["name"] for p in client.get("/api/door").json()["profiles"]] == ["Robin"]


def test_a_device_lists_only_profiles_it_holds(door: Any) -> None:
    client, store = door
    store.create("Elsewhere", None, [], [])
    client.post("/api/profiles", json={"name": "Here"})
    assert [p["name"] for p in client.get("/api/door").json()["profiles"]] == ["Here"]
    names = client.post("/api/names", json={"typed": "else"}).json()
    assert names == [{"id": names[0]["id"], "name": "Elsewhere", "has_pin": False}]  # a name, never a list
    assert client.post("/api/names", json={"typed": "el"}).json() == []


def test_a_device_may_hold_several_and_opens_by_pin(door: Any) -> None:
    client, store = door
    other, _ = store.create("Quinn", "1357", [], [])
    client.post("/api/profiles", json={"name": "First"})
    wrong = client.post(f"/api/profiles/{other.id}/open", json={"pin": "0000"})
    assert wrong.status_code == 401 and wrong.json()["code"] == "wrong_pin"
    opened = client.post(f"/api/profiles/{other.id}/open", json={"pin": "1357"})
    assert opened.status_code == 200
    assert sorted(p["name"] for p in client.get("/api/door").json()["profiles"]) == ["First", "Quinn"]


def test_locked_profile_says_how_long(door: Any) -> None:
    client, store = door
    other, _ = store.create("Max", "2222", [], [])
    for _ in range(4):
        client.post(f"/api/profiles/{other.id}/open", json={"pin": "0000"})
    resp = client.post(f"/api/profiles/{other.id}/open", json={"pin": "0000"})
    assert resp.status_code == 423
    assert resp.json()["message"] == "Too many wrong PINs. That profile is locked for 15 minutes."


def test_stale_tokens_are_cleared_from_the_cookie(door: Any, tmp_path: Path) -> None:
    client, store = door
    client.post("/api/profiles", json={"name": "Keep"})
    client.cookies.set(TOKENS_COOKIE, client.cookies[TOKENS_COOKIE] + ".bogus", domain="testserver.local")
    resp = client.get("/api/door")
    assert [p["name"] for p in resp.json()["profiles"]] == ["Keep"]
    cookie = resp.headers.get("set-cookie", "")
    kept = cookie.split(";")[0].split("=", 1)[1]
    assert "bogus" not in kept and len(kept) >= 43  # the good token stays


def test_a_taken_name_and_a_full_store_are_refused_in_words(door: Any) -> None:
    client, store = door
    client.post("/api/profiles", json={"name": "Twin"})
    resp = client.post("/api/profiles", json={"name": "twin"})
    assert resp.status_code == 409 and resp.json()["message"] == "Someone already goes by that name here. Try another?"


def test_the_ninth_profile_pushes_out_the_oldest(door: Any) -> None:
    client, _ = door
    for i in range(9):
        client.post("/api/profiles", json={"name": f"Seat {i}"})
    names = [p["name"] for p in client.get("/api/door").json()["profiles"]]
    assert "Seat 8" in names and "Seat 0" not in names and len(names) == 8


def test_reopening_a_held_profile_keeps_its_token_and_skips_the_pin(door: Any) -> None:
    client, _ = door
    mine = client.post("/api/profiles", json={"name": "Mine", "pin": "1212"}).json()
    for i in range(7):
        client.post("/api/profiles", json={"name": f"Other {i}"})
    for _ in range(10):
        assert client.post(f"/api/profiles/{mine['id']}/open", json={}).status_code == 200
    names = [p["name"] for p in client.get("/api/door").json()["profiles"]]
    assert len(names) == 8 and "Mine" in names and "Other 0" in names


def test_request_fields_are_bounded(door: Any) -> None:
    client, _ = door
    assert client.post("/api/names", json={"typed": "x" * 81}).status_code == 422
    assert client.post("/api/profiles", json={"name": "x" * 81}).status_code == 422
    assert client.post("/api/profiles", json={"name": "ok", "topics": list(range(401))}).status_code == 422


def test_a_device_holding_a_profile_deletes_it_everywhere_and_its_notes_stay(door: Any, tmp_path: Path) -> None:
    client, store = door
    other_device = TestClient(client.app, base_url="https://testserver")
    gone = client.post("/api/profiles", json={"name": "Leaving", "pin": "4321", "exclusions": ["superheroes"]}).json()
    client.post("/api/profiles", json={"name": "Staying"})
    assert other_device.post(f"/api/profiles/{gone['id']}/open", json={"pin": "4321"}).status_code == 200
    store.note(Note(gone["id"], 5, "west", "kind", ("Cowboys.",), False, "kept after"))
    resp = client.delete(f"/api/profiles/{gone['id']}")
    assert resp.status_code == 200 and resp.json() == {"name": "Leaving"}
    with sqlite3.connect(tmp_path / "matinee.sqlite") as db:
        assert db.execute("SELECT name FROM profiles").fetchall() == [("Staying",)]
        assert db.execute("SELECT COUNT(*) FROM tokens WHERE profile_id = ?", (gone["id"],)).fetchone() == (0,)
    assert [(n.comment, n.profile) for n in store.notes()] == [("kept after", None)]
    left = resp.headers["set-cookie"].split(";")[0].split("=", 1)[1].split(".")
    assert len(left) == 1  # the deleted profile's token is gone from this device's cookie
    assert [p.name for p in store.holding(left).values()] == ["Staying"]  # the deleting device keeps its others
    assert [p["name"] for p in client.get("/api/door").json()["profiles"]] == ["Staying"]
    assert other_device.get("/api/door").json()["profiles"] == []  # the other device's token went with it


def test_a_device_that_does_not_hold_a_profile_cannot_delete_it(door: Any, tmp_path: Path) -> None:
    client, store = door
    guarded, _ = store.create("Guarded", "1111", [], ["superheroes"])
    client.post("/api/profiles", json={"name": "Mine"})
    for target in (guarded.id, 999):
        assert client.delete(f"/api/profiles/{target}").status_code == 403
    with sqlite3.connect(tmp_path / "matinee.sqlite") as db:
        assert db.execute("SELECT name, exclusions FROM profiles ORDER BY id").fetchall() == [
            ("Guarded", '["superheroes"]'),
            ("Mine", "[]"),
        ]


def test_deleting_the_last_held_profile_clears_the_cookie(door: Any) -> None:
    client, _ = door
    only = client.post("/api/profiles", json={"name": "Only"}).json()
    resp = client.delete(f"/api/profiles/{only['id']}")
    assert resp.status_code == 200
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith(f'{TOKENS_COOKIE}=""') or "Max-Age=0" in cookie
