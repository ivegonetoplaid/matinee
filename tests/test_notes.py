"""Notes on a pick: kept for whoever runs Matinee, and changing nothing any viewer is shown."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from matinee.engine import load_catalog
from matinee.store import Store
from matinee.table import FilmTable
from matinee.web.app import create_app
from matinee.web.config import Config
from matinee.web.theatre import Theatre
from test_engine import TREE, reference, write_data
from test_viewing import FakeDtdd
from test_web_library import SECRET_KEY, SECRET_URL, FakeLibrary, seat_for, write_film_table


@pytest.fixture
def site(tmp_path: Path) -> tuple[TestClient, Store]:
    data = write_data(tmp_path / "data", dict(TREE))
    (data / "trees" / "east.json").write_text('{"pool": "horror", "opening": "boo.", "questions": []}')
    kids = {
        "pool": "kids",
        "opening": "hi!",
        "questions": [{"id": "age", "ask": "who?", "options": [{"say": "little.", "filter": {"kids_band": "little"}}]}],
    }
    (data / "trees" / "kids.json").write_text(json.dumps(kids))
    write_film_table(tmp_path / "films.sqlite")

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data, reference())

    theatre = Theatre(FakeLibrary(), tmp_path / "films.sqlite", catalog_of=catalog_of)
    store = Store(tmp_path / "matinee.sqlite")
    config = Config(SECRET_URL, SECRET_KEY, tmp_path, "https://seerr.invalid", "d" * 16)
    app = create_app(config, theatre, store, FakeDtdd(), clock=lambda: 0.0)
    return TestClient(app, base_url="https://testserver"), store


def pool(client: TestClient, tree: str, profile_id: int | None) -> list[int]:
    viewer = seat_for(client) if profile_id is None else {"profile_id": profile_id}
    return list(client.post("/api/walk", json={"tree": tree, "viewer": viewer}).json()["pool"])


def note_rows(tmp_path: Path) -> list[tuple[Any, ...]]:
    with sqlite3.connect(tmp_path / "matinee.sqlite") as db:
        return db.execute("SELECT profile_id, tmdb, tree, kind, path, rushed, comment FROM notes").fetchall()


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
    assert resp.status_code == 200
    assert resp.json()["lines"] == [
        "Thanks. That's gone to whoever runs Matinee.",
        "If they agree, it moves for everyone.",
    ]
    said = TREE["questions"][0]["options"][0]["say"]
    assert note_rows(tmp_path) == [(me, 5, "west", "kind", json.dumps([said]), 1, "too goofy for this")]
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
    assert note_rows(tmp_path) == []


def test_no_note_of_any_kind_changes_any_viewers_pool(site: Any) -> None:
    client, _ = site
    me = client.post("/api/profiles", json={"name": "Me"}).json()["id"]
    other = seat_for(client)["profile_id"]
    before = {t: (pool(client, t, me), pool(client, t, other)) for t in ("west", "east")}
    assert 5 in before["west"][0]
    for kind in ("genre", "kind", "quality"):
        note = {"profile_id": me, "tmdb": 5, "tree": "west", "kind": kind}
        assert client.post("/api/notes", json=note).status_code == 200
    assert {t: (pool(client, t, me), pool(client, t, other)) for t in ("west", "east")} == before


def test_the_corrections_route_is_gone(site: Any) -> None:
    client, _ = site
    me = client.post("/api/profiles", json={"name": "Me"}).json()["id"]
    body = {"profile_id": me, "tmdb": 5, "remove_from": "west", "add_to": []}
    assert client.post("/api/corrections", json=body).status_code in (404, 405)


def test_a_genre_note_keeps_every_tree_it_names_the_kids_tree_included(site: Any, tmp_path: Path) -> None:
    client, _ = site
    me = client.post("/api/profiles", json={"name": "Me"}).json()["id"]
    note = {"profile_id": me, "tmdb": 5, "tree": "west", "kind": "genre", "belongs": ["kids", "east"]}
    assert client.post("/api/notes", json=note).status_code == 200
    with sqlite3.connect(tmp_path / "matinee.sqlite") as db:
        assert db.execute("SELECT kind, belongs FROM notes").fetchall() == [("genre", '["east", "kids"]')]


def test_where_a_film_belongs_is_only_another_known_tree_on_a_genre_note(site: Any, tmp_path: Path) -> None:
    client, _ = site
    me = client.post("/api/profiles", json={"name": "Me"}).json()["id"]
    base = {"profile_id": me, "tmdb": 5, "tree": "west", "kind": "genre"}
    for bad in ({"belongs": ["nowhere"]}, {"belongs": ["west"]}, {"kind": "kind", "belongs": ["east"]}):
        assert client.post("/api/notes", json={**base, **bad}).status_code == 400
    assert client.post("/api/notes", json={**base, "belongs": ["east"] * 13}).status_code == 422
    assert note_rows(tmp_path) == []
