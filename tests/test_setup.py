"""The setup note: Matinee starts around every fault but two, and says what it sees before any pick."""

from __future__ import annotations

import urllib.error
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from matinee.engine import load_catalog
from matinee.labels import LabelsError
from matinee.progress import RebuildStatus, write_status
from matinee.store import Store
from matinee.table import FilmTable
from matinee.tmdb import KEY_REFUSED, NO_KEY, NOT_ANSWERING
from matinee.trees import TreeError
from matinee.web.app import create_app
from matinee.web.config import Config, ConfigError, from_env
from matinee.web.seerr import CHECK_EVERY, SeerrCheck
from matinee.web.setup import FAILED, FETCHING, MEANWHILE, NEVER_BUILT, SEERR_AWAY, STOPPED, rebuild_lines
from matinee.web.theatre import Theatre
from test_engine import TAGS, reference, write_data
from test_web_library import SERVER, FakeLibrary, answers, write_film_table


def status(state: str, reason: str | None = None) -> RebuildStatus:
    return RebuildStatus(state, "", "", reason=reason)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("report", "films", "said"),
    [
        (None, 0, [NEVER_BUILT]),
        (None, 5, []),
        (status("running"), 0, [FETCHING]),
        (status("running"), 5, []),
        (status("finished"), 5, []),
        (status("stopped", NO_KEY), 0, [STOPPED[NO_KEY]]),
        (status("stopped", KEY_REFUSED), 5, [STOPPED[KEY_REFUSED]]),
        (status("stopped", NOT_ANSWERING), 5, [STOPPED[NOT_ANSWERING]]),
        (status("stopped", "the rebuild failed; its log says why"), 5, [FAILED]),
    ],
)
def test_the_rebuild_report_says_why_it_stopped_and_why_there_is_no_film(
    report: RebuildStatus | None, films: int, said: list[str]
) -> None:
    assert rebuild_lines(report, films) == said


def site(tmp_path: Path, config: Config, seerr: SeerrCheck, library: Any = None, **kw: Any) -> TestClient:
    data = write_data(tmp_path / "data")
    write_film_table(tmp_path / "films.sqlite")

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data, reference())

    theatre = Theatre(library, tmp_path / "films.sqlite", catalog_of=catalog_of)
    app = create_app(config, theatre, Store(tmp_path / "s.sqlite"), None, seerr=seerr, **kw)
    return TestClient(app, base_url="https://testserver")


def test_all_is_well_says_nothing(tmp_path: Path) -> None:
    config = Config(SERVER, tmp_path, "https://seerr.invalid", None)
    client = site(tmp_path, config, SeerrCheck(config.seerr_url, opener=answers), FakeLibrary())
    write_status(tmp_path, status("finished"))
    note = client.get("/api/setup").json()
    assert note["lines"] == [] and note["go_on"] and note["films"] > 0


def test_settings_it_cannot_use_and_a_silent_seerr_are_said_and_the_library_is_set_aside(tmp_path: Path) -> None:
    env = {"DATA_DIR": str(tmp_path), "JELLYFIN_URL": "http://a", "JELLYFIN_API_KEY": "k"}
    config = from_env({**env, "PLEX_URL": "http://b", "PLEX_TOKEN": "p", "SEERR_URL": "https://seerr.invalid"})

    def silent(req: Any, timeout: float) -> Any:
        raise urllib.error.URLError("no route")

    clock = [0.0]
    seerr = SeerrCheck(config.seerr_url, clock=lambda: clock[0], opener=silent)
    client = site(tmp_path, config, seerr)
    note = client.get("/api/setup").json()
    assert note["lines"][0].startswith("You've set up both Jellyfin and Plex")
    assert note["lines"][0].endswith(MEANWHILE) and SEERR_AWAY in note["lines"]
    card = client.get("/api/door")
    assert card.status_code == 200
    seerr._opener = answers  # Seerr comes back; the note drops it at the next check, with no restart
    clock[0] += CHECK_EVERY
    assert SEERR_AWAY not in client.get("/api/setup").json()["lines"]


def test_only_a_wrong_lock_and_a_missing_data_directory_refuse_to_start(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        from_env({"DATA_DIR": str(tmp_path), "DOOR_WORD": "short"})
    with pytest.raises(ConfigError):
        from_env({"DATA_DIR": str(tmp_path), "DOOR_WORD": "a long enough word", "DOOR_MATCH": "loose"})
    with pytest.raises(ConfigError):
        from_env({"DATA_DIR": str(tmp_path / "gone")})
    open_door = from_env({"DATA_DIR": str(tmp_path), "DOOR_MATCH": "loose"})
    assert open_door.door_word is None and "DOOR_MATCH" in open_door.faults[0]


def test_lines_that_cannot_be_read_are_said_and_served_as_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from matinee.quips import QuipsError

    def broken() -> Any:
        raise QuipsError("data/quips.json lacks universal rush lines")

    monkeypatch.setattr("matinee.web.app.load_quips", broken)
    config = Config(SERVER, tmp_path, None, None)
    client = site(tmp_path, config, SeerrCheck(None), FakeLibrary())
    assert client.get("/api/quips").status_code == 503
    assert any("My lines for a pick" in line for line in client.get("/api/setup").json()["lines"])


def test_no_media_server_is_no_fault(tmp_path: Path) -> None:
    config = from_env({"DATA_DIR": str(tmp_path)})
    client = site(tmp_path, config, SeerrCheck(None))
    write_status(tmp_path, status("finished"))
    lines = client.get("/api/setup").json()["lines"]
    assert MEANWHILE not in lines and not any("reach" in line for line in lines)  # a choice, not a fault


def test_a_seerr_that_stops_answering_sends_picks_to_tmdb_until_it_answers(tmp_path: Path) -> None:
    def silent(req: Any, timeout: float) -> Any:
        raise urllib.error.URLError("no route")

    clock = [0.0]
    config = Config(SERVER, tmp_path, "https://seerr.invalid", None)
    seerr = SeerrCheck(config.seerr_url, clock=lambda: clock[0], opener=silent)
    client = site(tmp_path, config, seerr, FakeLibrary())
    assert client.get("/api/film/5").json()["link_to"] == "tmdb"
    seerr._opener = answers
    clock[0] += CHECK_EVERY
    assert client.get("/api/film/5").json()["link_to"] == "seerr"


@pytest.mark.parametrize("table", [None, b"this is not a film table"])
def test_a_missing_or_unreadable_table_starts_empty_and_says_why(tmp_path: Path, table: bytes | None) -> None:
    data = write_data(tmp_path / "data")
    path = tmp_path / "films.sqlite"
    if table is not None:
        path.write_bytes(table)
    theatre = Theatre(None, path, catalog_of=lambda t: load_catalog(t, data, reference()), tags=TAGS)
    config = Config(None, tmp_path, None, None)
    client = TestClient(create_app(config, theatre, Store(tmp_path / "s.sqlite"), None), base_url="https://testserver")
    note = client.get("/api/setup").json()
    assert note["lines"] == [NEVER_BUILT] and not note["go_on"] and note["films"] == 0


def test_a_table_whose_films_no_label_names_is_not_blamed_on_the_rebuild(tmp_path: Path) -> None:
    config = Config(None, tmp_path, None, None)  # no library: only the films the labels name are offered
    client = site(tmp_path, config, SeerrCheck(None))  # this theatre's labels name no film
    write_status(tmp_path, status("finished"))
    note = client.get("/api/setup").json()
    assert note["films"] == 0 and not note["go_on"] and NEVER_BUILT not in note["lines"]


def build_real(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **broken: Any) -> TestClient:
    from matinee.web import main

    for name in ("JELLYFIN_URL", "JELLYFIN_API_KEY", "PLEX_URL", "PLEX_TOKEN", "DTDD_API_KEY", "DOOR_WORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for name, failure in broken.items():

        def fail(*_: Any, failure: Exception = failure, **__: Any) -> Any:
            raise failure

        monkeypatch.setattr(main, name, fail)
    return TestClient(main.build(), base_url="https://testserver")


@pytest.mark.parametrize("failure", [TreeError("crime.json is not a tree"), KeyError("list_tags")])
def test_shipped_files_that_cannot_be_read_start_matinee_with_the_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    client = build_real(monkeypatch, tmp_path, tags_read=failure, load_catalog=failure)
    note = client.get("/api/setup").json()
    assert not note["go_on"] and "Matinee's own files" in note["lines"][-1]


def test_labels_that_cannot_be_read_start_matinee_with_the_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = build_real(monkeypatch, tmp_path, load_labels=LabelsError("data/labels.json is not valid JSON"))
    assert any(line.startswith("My labels file can't be read") for line in client.get("/api/setup").json()["lines"])
