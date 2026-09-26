"""Personal corrections: one override per correction, for one profile only."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from matinee.engine import load_catalog
from matinee.store import SavedCorrection, Store, StoreError
from matinee.table import FilmTable
from matinee.web.app import create_app
from matinee.web.config import Config
from matinee.web.theatre import Theatre
from test_engine import TREE, reference, write_data
from test_viewing import FakeDtdd
from test_web_library import SECRET_KEY, SECRET_URL, FakeLibrary, write_film_table


def test_a_correction_is_one_override_of_structured_rows(tmp_path: Path) -> None:
    store = Store(tmp_path / "m.sqlite")
    profile, _ = store.create("Cal", None, [], [])
    store.correct(profile.id, 603, "horror", ["thriller", "drama", "horror"])
    with sqlite3.connect(tmp_path / "m.sqlite") as db:
        rows = db.execute("SELECT override_id, profile_id, tmdb, tree, direction, at FROM corrections").fetchall()
    assert {(r[3], r[4]) for r in rows} == {("horror", "remove"), ("drama", "add"), ("thriller", "add")}
    assert len({r[0] for r in rows}) == 1 and {r[1] for r in rows} == {profile.id} and {r[2] for r in rows} == {603}
    assert len({r[5] for r in rows}) == 1 and rows[0][5].startswith("20")
    assert store.corrections(profile.id)[0] == SavedCorrection(603, "horror", "remove")
    with pytest.raises(StoreError):
        store.correct(9999, 603, "horror", [])


@pytest.fixture
def site(tmp_path: Path) -> tuple[TestClient, Store]:
    data = write_data(tmp_path / "data", dict(TREE))
    (data / "trees" / "east.json").write_text('{"pool": "horror", "opening": "boo.", "questions": []}')
    write_film_table(tmp_path / "films.sqlite")

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data, reference())

    theatre = Theatre(FakeLibrary(), tmp_path / "films.sqlite", catalog_of=catalog_of)
    store = Store(tmp_path / "matinee.sqlite")
    config = Config(SECRET_URL, SECRET_KEY, tmp_path, "https://seerr.invalid", "d" * 16)
    app = create_app(config, theatre, store, FakeDtdd(), clock=lambda: 0.0)
    return TestClient(app, base_url="https://testserver"), store


def pool(client: TestClient, tree: str, profile_id: int | None) -> list[int]:
    viewer = {} if profile_id is None else {"profile_id": profile_id}
    return list(client.post("/api/walk", json={"tree": tree, "viewer": viewer}).json()["pool"])


def test_a_correction_changes_only_that_profiles_results(site: Any) -> None:
    client, store = site
    me = client.post("/api/profiles", json={"name": "Me"}).json()["id"]
    them, _ = store.create("Them", None, [], [])
    resp = client.post("/api/corrections", json={"profile_id": me, "tmdb": 5, "remove_from": "west", "add_to": []})
    assert resp.status_code == 200 and resp.json()["line"] == "Got it. I'll remember that for you."
    assert 5 not in pool(client, "west", me)
    assert 5 in pool(client, "west", None)
    assert store.corrections(them.id) == []


def test_a_correction_adds_the_film_where_it_belongs(site: Any) -> None:
    client, _ = site
    me = client.post("/api/profiles", json={"name": "Me"}).json()["id"]
    assert 5 not in pool(client, "east", me)  # east holds the Horror-tagged films; film 5 is a comedy
    client.post("/api/corrections", json={"profile_id": me, "tmdb": 5, "remove_from": "west", "add_to": ["east"]})
    assert 5 in pool(client, "east", me) and 5 not in pool(client, "west", me)


def test_a_later_correction_wins(site: Any) -> None:
    client, _ = site
    me = client.post("/api/profiles", json={"name": "Me"}).json()["id"]
    assert 6 in pool(client, "east", me) and 6 in pool(client, "west", me)  # a Horror-tagged western
    client.post("/api/corrections", json={"profile_id": me, "tmdb": 6, "remove_from": "west", "add_to": []})
    client.post("/api/corrections", json={"profile_id": me, "tmdb": 6, "remove_from": "east", "add_to": ["west"]})
    assert 6 in pool(client, "west", me) and 6 not in pool(client, "east", me)


def test_only_a_held_profile_may_correct_and_only_known_trees_and_films(site: Any) -> None:
    client, store = site
    them, _ = store.create("Them", None, [], [])
    body = {"profile_id": them.id, "tmdb": 5, "remove_from": "west", "add_to": []}
    assert client.post("/api/corrections", json=body).status_code == 403
    assert client.post("/api/corrections", json={"tmdb": 5, "remove_from": "west"}).status_code == 422
    me = client.post("/api/profiles", json={"name": "Me"}).json()["id"]
    for bad in ({"remove_from": "nowhere"}, {"add_to": ["nowhere"]}, {"tmdb": 123456}):
        req = {"profile_id": me, "tmdb": 5, "remove_from": "west", "add_to": [], **bad}
        assert client.post("/api/corrections", json=req).status_code == 400
    assert store.corrections(me) == [] and store.corrections(them.id) == []


def test_both_halves_land_together_or_not_at_all(tmp_path: Path) -> None:
    store = Store(tmp_path / "m.sqlite")
    profile, _ = store.create("Cal", None, [], [])
    with sqlite3.connect(tmp_path / "m.sqlite") as db:
        db.execute(
            "CREATE TRIGGER no_adds BEFORE INSERT ON corrections WHEN NEW.direction = 'add'"
            " BEGIN SELECT RAISE(ABORT, 'refused'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        store.correct(profile.id, 603, "horror", ["drama"])
    assert store.corrections(profile.id) == []


def test_a_correction_cannot_add_to_a_gated_age_band_tree(tmp_path: Path) -> None:
    data = write_data(tmp_path / "data", dict(TREE))
    gated = {
        "pool": "kids",
        "opening": "hi!",
        "questions": [{"id": "age", "ask": "who?", "options": [{"say": "little.", "filter": {"kids_band": "little"}}]}],
    }
    (data / "trees" / "kids.json").write_text(json.dumps(gated))
    write_film_table(tmp_path / "films.sqlite")

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data, reference())

    theatre = Theatre(FakeLibrary(), tmp_path / "films.sqlite", catalog_of=catalog_of)
    store = Store(tmp_path / "matinee.sqlite")
    config = Config(SECRET_URL, SECRET_KEY, tmp_path, "https://seerr.invalid", "d" * 16)
    client = TestClient(
        create_app(config, theatre, store, FakeDtdd(), clock=lambda: 0.0), base_url="https://testserver"
    )
    me = client.post("/api/profiles", json={"name": "Me"}).json()["id"]
    into_kids = {"profile_id": me, "tmdb": 5, "remove_from": "west", "add_to": ["kids"]}
    assert client.post("/api/corrections", json=into_kids).status_code == 400
    out_of_kids = {"profile_id": me, "tmdb": 1, "remove_from": "kids", "add_to": ["west"]}
    assert client.post("/api/corrections", json=out_of_kids).status_code == 200
    assert store.corrections(me) == [SavedCorrection(1, "kids", "remove"), SavedCorrection(1, "west", "add")]


def feedback_rows(tmp_path: Path) -> list[tuple[Any, ...]]:
    with sqlite3.connect(tmp_path / "matinee.sqlite") as db:
        return db.execute("SELECT profile_id, tmdb, tree, kind, path, rushed, comment FROM feedback").fetchall()


def test_a_note_keeps_what_was_wrong_the_answers_and_why_and_changes_no_pool(site: Any, tmp_path: Path) -> None:
    client, _ = site
    me = client.post("/api/profiles", json={"name": "Me"}).json()["id"]
    before = pool(client, "west", me)
    body = {
        "profile_id": me,
        "tmdb": 5,
        "tree": "west",
        "kind": "kind",
        "answers": [{"question": "era", "option": 0}],
        "rushed": True,
        "comment": "  too goofy for this  ",
    }
    resp = client.post("/api/notes", json=body)
    assert resp.status_code == 200 and resp.json()["line"] == "Thanks. I've kept that for whoever tunes Matinee."
    said = TREE["questions"][0]["options"][0]["say"]
    assert feedback_rows(tmp_path) == [(me, 5, "west", "kind", json.dumps([said]), 1, "too goofy for this")]
    assert pool(client, "west", me) == before


def test_only_a_held_profile_may_note_and_only_answers_the_tree_has(site: Any, tmp_path: Path) -> None:
    client, store = site
    them, _ = store.create("Them", None, [], [])
    base = {"tmdb": 5, "tree": "west", "kind": "quality", "answers": [{"question": "era", "option": 0}]}
    assert client.post("/api/notes", json={**base, "profile_id": them.id}).status_code == 403
    me = client.post("/api/profiles", json={"name": "Me"}).json()["id"]
    for bad in ({"kind": "boring"}, {"comment": "x" * 501}):
        assert client.post("/api/notes", json={**base, "profile_id": me, **bad}).status_code == 422
    refused: list[dict[str, Any]] = [
        {"tree": "nowhere"},
        {"tmdb": 123456},
        {"answers": [{"question": "nope", "option": 0}]},
        {"answers": [{"question": "era", "option": 49}]},
    ]
    for bad in refused:
        assert client.post("/api/notes", json={**base, "profile_id": me, **bad}).status_code == 400
    assert feedback_rows(tmp_path) == []
