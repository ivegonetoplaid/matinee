"""The rebuild: which server and films it reads, what it refuses, and the report it leaves for the server."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import rebuild_table
from matinee.labels import load_labels
from matinee.library import LibraryFilm
from matinee.library.choice import MediaServer
from matinee.progress import RebuildStatus, read_status
from matinee.tmdb import KEY_REFUSED, NO_KEY, Refreshed, load_cache

SETTINGS = ("DATA_DIR", "JELLYFIN_URL", "JELLYFIN_API_KEY", "PLEX_URL", "PLEX_TOKEN", "TMDB_TOKEN")


def run(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> list[Any]:
    for name in SETTINGS:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    calls: list[Any] = []

    def rebuild(*args: Any) -> RebuildStatus:
        calls.append(args)
        return RebuildStatus("finished", "", "")

    monkeypatch.setattr(rebuild_table, "rebuild", rebuild)
    monkeypatch.setattr("sys.argv", ["rebuild_table.py"])
    assert rebuild_table.main() == 0
    return calls


def test_the_rebuild_reads_whichever_server_is_set_or_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = {"DATA_DIR": str(tmp_path), "TMDB_TOKEN": "t"}
    [jf] = run(monkeypatch, {**base, "JELLYFIN_URL": "http://jf.invalid", "JELLYFIN_API_KEY": "k"})
    assert jf == (MediaServer("jellyfin", "http://jf.invalid", "k"), tmp_path, "t")
    [plex] = run(monkeypatch, {**base, "PLEX_URL": "http://plex.invalid", "PLEX_TOKEN": "p"})
    assert plex[0] == MediaServer("plex", "http://plex.invalid", "p")
    [none] = run(monkeypatch, {**base, "MATINEE_JELLYFIN_URL": "http://old.invalid", "JELLYFIN_API_KEY": ""})
    assert none[0] is None  # no library; an old setting name is never read


@pytest.mark.parametrize(
    "env",
    [
        {"JELLYFIN_URL": "http://a", "JELLYFIN_API_KEY": "k", "PLEX_URL": "http://b", "PLEX_TOKEN": "p"},
        {"JELLYFIN_URL": "http://a"},
    ],
)
def test_server_settings_it_cannot_use_leave_the_rebuild_reading_the_labels_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: dict[str, str]
) -> None:
    [call] = run(monkeypatch, {"DATA_DIR": str(tmp_path), "TMDB_TOKEN": "t", **env})
    assert call[0] is None


def test_without_a_key_it_fetches_nothing_writes_no_table_and_says_why(tmp_path: Path) -> None:
    status = rebuild_table.rebuild(None, tmp_path, "")
    assert (status.state, status.reason) == ("stopped", NO_KEY)
    assert read_status(tmp_path) == status
    assert not (tmp_path / "films.sqlite").exists()


def test_without_a_library_it_fetches_every_film_the_labels_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[list[int]] = []

    def refresh(ids: Any, cache: Path, token: str) -> Refreshed:
        asked.append(list(ids))
        assert read_status(tmp_path) is not None and read_status(tmp_path).state == "running"  # type: ignore[union-attr]
        return Refreshed(5, 0)

    monkeypatch.setattr(rebuild_table, "refresh", refresh)
    status = rebuild_table.rebuild(None, tmp_path, "t")
    assert set(asked[0]) == set(load_labels().films())
    assert (status.state, status.done, status.total) == ("finished", len(asked[0]), len(asked[0]))
    assert (tmp_path / "films.sqlite").exists()

    monkeypatch.setattr(rebuild_table, "refresh", lambda ids, cache, token: Refreshed(1, 0, KEY_REFUSED))
    stopped = rebuild_table.rebuild(None, tmp_path, "bad")
    assert (stopped.state, stopped.reason, stopped.done) == ("stopped", KEY_REFUSED, 1)
    assert read_status(tmp_path) == stopped


def test_a_report_that_cannot_be_read_counts_as_absent(tmp_path: Path) -> None:
    assert read_status(tmp_path) is None
    (tmp_path / "rebuild.json").write_text("{half")
    assert read_status(tmp_path) is None
    (tmp_path / "rebuild.json").write_text('{"state": "dancing", "started_at": "", "updated_at": ""}')
    assert read_status(tmp_path) is None


def test_an_unexpected_failure_still_ends_the_report_and_is_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rebuild_table, "refresh", lambda ids, cache, token: Refreshed(0, 0))

    def broken(*args: Any) -> Any:
        raise ValueError("a code fault")

    monkeypatch.setattr(rebuild_table, "build_table", broken)
    with pytest.raises(ValueError):
        rebuild_table.rebuild(None, tmp_path, "t")
    assert (read_status(tmp_path).state, read_status(tmp_path).reason) == ("stopped", rebuild_table.FAILED)  # type: ignore[union-attr]


def test_without_a_key_records_past_six_months_are_still_dropped(tmp_path: Path) -> None:
    cache = tmp_path / "tmdb" / "films.jsonl"
    cache.parent.mkdir()
    now = datetime.now(UTC)
    old = {"tmdb": 1, "fetched_at": (now - timedelta(days=200)).isoformat(), "collection_id": None, "keywords": []}
    fresh = {**old, "tmdb": 2, "fetched_at": (now - timedelta(days=10)).isoformat()}
    cache.write_text(json.dumps(old) + "\n" + json.dumps(fresh) + "\n")
    rebuild_table.rebuild(None, tmp_path, "")
    assert set(load_cache(cache)) == {2}
    empty = tmp_path / "other"
    empty.mkdir()
    rebuild_table.rebuild(None, empty, "")
    assert not (empty / "tmdb").exists()


def test_the_rebuild_fetches_the_labels_and_the_library_once_each(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    labelled = next(iter(load_labels().films()))
    outside = 999_999_999
    assert outside not in load_labels().films()

    class Reader:
        def films(self) -> list[LibraryFilm]:
            return [
                LibraryFilm("a" * 32, outside, "Home film", 2001, frozenset(), "", None, None, None),
                LibraryFilm("b" * 32, labelled, "Labelled", 2002, frozenset(), "", None, None, None),
            ]

    asked: list[list[int]] = []
    monkeypatch.setattr(rebuild_table, "open_reader", lambda server: Reader())

    def refresh(ids: Any, cache: Path, token: str) -> Refreshed:
        asked.append(list(ids))
        return Refreshed(0, 0)

    monkeypatch.setattr(rebuild_table, "refresh", refresh)
    rebuild_table.rebuild(MediaServer("jellyfin", "http://jf.invalid", "k"), tmp_path, "t")
    assert sorted(asked[0]) == sorted(load_labels().films() | {outside})


def test_a_one_shot_rebuild_that_stopped_exits_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SETTINGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(rebuild_table, "rebuild", lambda *a: RebuildStatus("stopped", "", "", reason=KEY_REFUSED))
    monkeypatch.setattr("sys.argv", ["rebuild_table.py"])
    assert rebuild_table.main() == 1


def test_the_rebuild_writes_labelled_films_the_library_lacks_beside_the_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from matinee.table import load_table
    from matinee.tmdb import TmdbFilm

    world, owned = sorted(load_labels().films())[:2]
    fetched = datetime.now(UTC).isoformat()
    cache = {
        t: TmdbFilm(t, fetched, None, None, [], "en", "", "", title=f"Film {t}", certification="PG", genres=["Drama"])
        for t in (world, owned)
    }

    class Reader:
        def films(self) -> list[LibraryFilm]:
            return [LibraryFilm("c" * 32, owned, "Owned", 2003, frozenset({"Drama"}), "PG", 90.0, 7.0, None)]

    monkeypatch.setattr(rebuild_table, "open_reader", lambda server: Reader())
    monkeypatch.setattr(rebuild_table, "refresh", lambda ids, cache_path, token: Refreshed(0, 0))
    monkeypatch.setattr(rebuild_table, "load_cache", lambda path: cache)
    rebuild_table.rebuild(MediaServer("jellyfin", "http://jf.invalid", "k"), tmp_path, "t")
    films = load_table(tmp_path / "films.sqlite").films
    assert films.loc[owned, "item_id"] == "c" * 32 and films.loc[owned, "name"] == "Owned"
    assert films.loc[world, "item_id"] != films.loc[world, "item_id"]  # NaN: no media-server item
    assert films.loc[world, "name"] == f"Film {world}"
