"""An installation with no DoesTheDogDie key: no list, no check, stored topics kept and ignored, and said so."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from matinee.engine import Viewer, load_catalog, walk
from matinee.pick import DeviceCap, Picker
from matinee.store import Store
from matinee.table import FilmTable
from matinee.web.app import create_app
from matinee.web.config import Config, from_env
from matinee.web.main import warn_kept_topics
from matinee.web.theatre import Theatre
from notes import main as notes_main
from test_engine import reference, write_data
from test_web_library import SERVER, FakeLibrary, write_film_table

GORE_SKIPPED = 188  # a topic that skips the gore question


@pytest.fixture
def keyless(tmp_path: Path) -> tuple[TestClient, Store, Theatre]:
    data = write_data(tmp_path / "data")
    write_film_table(tmp_path / "films.sqlite")

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data, reference())

    theatre = Theatre(FakeLibrary(), tmp_path / "films.sqlite", catalog_of=catalog_of)
    store = Store(tmp_path / "matinee.sqlite")
    config = Config(SERVER, tmp_path, "https://seerr.invalid", None)
    app = create_app(config, theatre, store, None, clock=lambda: 0.0)
    return TestClient(app, base_url="https://testserver"), store, theatre


def test_the_key_is_optional(tmp_path: Path) -> None:
    env = {"DATA_DIR": str(tmp_path), "JELLYFIN_URL": "http://u", "JELLYFIN_API_KEY": "k"}
    env["SEERR_URL"] = "s"
    assert from_env(env).dtdd_key is None
    assert from_env({**env, "DTDD_API_KEY": " key "}).dtdd_key == "key"


def test_no_key_offers_no_list_and_says_so_at_the_door(keyless: Any) -> None:
    client, _, _ = keyless
    assert client.get("/api/door").json()["dtdd"] is False
    assert client.get("/api/topics").status_code == 404
    me = client.post("/api/profiles", json={"name": "Ada"}).json()
    assert client.put(f"/api/profiles/{me['id']}/topics", json={"topics": [GORE_SKIPPED]}).status_code in (404, 405)


def test_stored_topics_stay_in_the_store_and_change_no_walk_or_pick(keyless: Any) -> None:
    client, store, theatre = keyless
    me = client.post("/api/profiles", json={"name": "Kept", "topics": [GORE_SKIPPED]}).json()
    viewer = {"profile_id": me["id"]}
    era = [{"question": "era", "option": 1}]
    step = client.post("/api/walk", json={"tree": "west", "answers": era, "viewer": viewer}).json()
    assert step["question"]["id"] == "gore"  # the topic would skip it with a key
    cat = theatre.showing().catalog
    gated = list(walk(cat, "west", Viewer(topics=frozenset({GORE_SKIPPED})), []).pool)
    assert 0 < len(gated) < len(walk(cat, "west", Viewer(), []).pool)
    pick = client.post("/api/pick", json={"tree": "west", "viewer": viewer, "seen": gated}).json()
    assert pick["film"] is not None and pick["film"]["tmdb"] not in gated  # drawn from the films the topic cut
    assert pick["unchecked"] is None and pick["turned_away"] == []
    assert client.post("/api/first", json={"viewer": viewer}).json()["checked"] is False
    assert store.everyone()[0].topics == frozenset({GORE_SKIPPED})


def test_a_keyed_picker_cannot_serve_a_keyless_app(tmp_path: Path) -> None:
    from test_pick import ScriptedDtdd

    write_film_table(tmp_path / "films.sqlite")
    theatre = Theatre(
        FakeLibrary(),
        tmp_path / "films.sqlite",
        catalog_of=lambda t: load_catalog(t, write_data(tmp_path / "d"), reference()),
    )
    config = Config(SERVER, tmp_path, "https://seerr.invalid", None)
    with pytest.raises(ValueError, match="agree"):
        create_app(config, theatre, Store(tmp_path / "s.sqlite"), None, picker=Picker(ScriptedDtdd({}), DeviceCap()))


def test_a_key_still_checks(tmp_path: Path) -> None:
    from test_pick import ScriptedDtdd, stat

    dtdd = ScriptedDtdd({n: [stat(GORE_SKIPPED, 9, 0)] for n in range(1, 100)})
    picker = Picker(dtdd, DeviceCap())
    assert picker.pick([1, 2], frozenset({GORE_SKIPPED}), "device").film is None
    assert Picker(None, DeviceCap()).pick([1, 2], frozenset({GORE_SKIPPED}), "device").film in (1, 2)


def test_kept_topics_are_warned_of_until_cleared(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store = Store(tmp_path / "matinee.sqlite")
    store.create("Ada", None, [GORE_SKIPPED])
    store.create("Bo", None, [])
    with caplog.at_level(logging.WARNING, logger="matinee.web"):
        warn_kept_topics(store)
    [said] = [r.getMessage() for r in caplog.records]
    assert "was set before and is now missing" in said and "1 profile still hold" in said
    assert "DTDD_API_KEY" in said and "tools/notes.py clear-topics" in said
    caplog.clear()
    assert notes_main(["--state", str(tmp_path), "clear-topics"]) == 0
    assert [p.topics for p in store.everyone()] == [frozenset(), frozenset()]
    with caplog.at_level(logging.WARNING, logger="matinee.web"):
        warn_kept_topics(store)
    assert not caplog.records


def test_a_reloaded_table_runs_the_reload_hook(tmp_path: Path) -> None:
    data = write_data(tmp_path / "data")
    write_film_table(tmp_path / "films.sqlite")
    calls: list[int] = []
    theatre = Theatre(
        FakeLibrary(),
        tmp_path / "films.sqlite",
        catalog_of=lambda table: load_catalog(table, data, reference()),
        on_reload=lambda: calls.append(1),
    )
    theatre.showing()
    assert calls == []
    later = time.time() + 5
    os.utime(tmp_path / "films.sqlite", (later, later))
    theatre.showing()
    assert calls == [1]
