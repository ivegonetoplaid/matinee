"""The offline film table, the Jellyfin film parser and the TMDB cache."""

from __future__ import annotations

import json
import sqlite3
import urllib.error
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from matinee.genome import Genome, Scores
from matinee.library import LibraryError, LibraryFilm
from matinee.library.jellyfin import parse_film
from matinee.table import TableError, build_table, load_table, write_table
from matinee.tmdb import (
    KEY_REFUSED,
    NOT_ANSWERING,
    Refreshed,
    TmdbFilm,
    TmdbRefused,
    fetch_film,
    load_cache,
    needs_fetch,
    refresh,
)

NOW = datetime(2026, 9, 25, tzinfo=UTC)


def film(item: str, tmdb: int | None, name: str, path_tmdb: int | None = None, genres: str = "Horror") -> LibraryFilm:
    return LibraryFilm(item, tmdb, name, 2000, frozenset(genres.split("|")), "R", 95.0, 6.5, path_tmdb)


def genome() -> Scores:
    """Two genome films: movie 1 is TMDB 11, movie 2 is TMDB 22. Movie 3 shares TMDB 11 and is ignored."""
    full = Genome(
        release="test release",
        movie_ids=np.array([1, 2, 3]),
        tags=("gore", "scary"),
        relevance=np.array([[0.0, 0.25], [0.5, 1.0], [0.9, 0.9]], dtype=np.float32),
        tmdb_by_movie={1: 11, 2: 22, 3: 11},
        genres_by_movie={},
    )
    return full.scores(full.tags)


def tmdb(
    tmdb_id: int, age_days: int, keywords: list[str], language: str | None = "en", poster: str | None = ""
) -> TmdbFilm:
    fetched = (NOW - timedelta(days=age_days)).isoformat()
    backdrop = poster and poster.replace("/p", "/b")
    collection = 900 if tmdb_id == 11 else None
    return TmdbFilm(tmdb_id, fetched, collection, None, keywords, language, poster, backdrop, title=f"Film {tmdb_id}")


LIBRARY = [
    film("a", 11, "Genome film", path_tmdb=11),
    film("a2", 11, "Genome film, second copy", path_tmdb=12),
    film("b", 22, "Other genome film", path_tmdb=99),
    film("c", 33, "Unscored film"),
    film("d", None, "No id film"),
]
CACHE = {
    11: tmdb(11, 10, ["gore"], poster="/p11.jpg"),
    22: tmdb(22, 200, ["blood"], poster="/p22.jpg"),
    33: tmdb(33, 20, [], language=""),
}


def test_build_keeps_missing_scores_missing_and_reports() -> None:
    table, report = build_table(LIBRARY, genome(), CACHE, NOW)
    assert list(table.films.index) == [11, 22, 33]
    assert table.films.loc[11, "item_id"] == "a"
    gore = table.tag("gore")
    assert gore[11] == 0.0 and gore[22] == 0.5 and np.isnan(gore[33])
    assert table.has_genome().tolist() == [True, True, False]
    assert report.no_tmdb_id == ["No id film (2000)"]
    assert report.path_mismatches == [
        "Genome film, second copy (2000): folder says 12, server says 11",
        "Other genome film (2000): folder says 99, server says 22",
    ]
    assert report.tmdb_too_old == ["Other genome film (2000)"]
    assert not table.films.loc[22, "tmdb_known"]
    assert table.films.loc[22, "keywords"] is None
    assert table.films.loc[11, "keywords"] == frozenset({"gore"})
    assert table.films.loc[11, "language"] == "en"
    assert pd.isna(table.films.loc[33, "language"])
    assert table.oldest_tmdb == CACHE[33].fetched


def test_write_then_load_round_trips(tmp_path: Path) -> None:
    table, _ = build_table(LIBRARY, genome(), CACHE, NOW)
    path = tmp_path / "films.sqlite"
    write_table(table, path)
    back = load_table(path, NOW)
    assert list(back.films.index) == [11, 22, 33]
    assert back.films.loc[11, "genres"] == frozenset({"Horror"})
    assert back.films.loc[11, "collection_id"] == 900
    assert pd.isna(back.films.loc[33, "collection_id"])
    assert back.tag("scary")[22] == 1.0
    assert np.isnan(back.tag("scary")[33])
    assert back.release == "test release"
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM genome").fetchone() == (2,)
    assert not (tmp_path / "films.sqlite.partial").exists()


def test_load_refuses_absent_and_stale(tmp_path: Path) -> None:
    with pytest.raises(TableError):
        load_table(tmp_path / "nope.sqlite", NOW)
    table, _ = build_table(LIBRARY, genome(), CACHE, NOW)
    write_table(table, tmp_path / "films.sqlite")
    oldest = CACHE[33].fetched
    load_table(tmp_path / "films.sqlite", oldest + timedelta(days=183) - timedelta(seconds=1))
    with pytest.raises(TableError, match="six months"):
        load_table(tmp_path / "films.sqlite", oldest + timedelta(days=183))


def test_load_refuses_another_format(tmp_path: Path) -> None:
    table, _ = build_table(LIBRARY, genome(), CACHE, NOW)
    path = tmp_path / "films.sqlite"
    write_table(table, path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE meta SET value = '1' WHERE key = 'format'")  # the table before films outside the library
    db.close()
    with pytest.raises(TableError, match="format"):
        load_table(path, NOW)


def test_failed_write_leaves_the_previous_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    table, _ = build_table(LIBRARY, genome(), CACHE, NOW)
    path = tmp_path / "films.sqlite"
    write_table(table, path)
    before = path.read_bytes()

    def boom(*_: object) -> object:
        raise OSError("disk full")

    monkeypatch.setattr("matinee.table.json.dumps", boom)
    with pytest.raises(OSError):
        write_table(table, path)
    assert path.read_bytes() == before
    assert list(load_table(path, NOW).films.index) == [11, 22, 33]


def test_record_exactly_six_months_old_is_not_used() -> None:
    edge = {11: TmdbFilm(11, (NOW - timedelta(days=183)).isoformat(), None, None, ["gore"], "en")}
    table, report = build_table(LIBRARY[:1], genome(), edge, NOW)
    assert report.tmdb_too_old == ["Genome film (2000)"]
    assert not table.films.loc[11, "tmdb_known"]


def test_unknown_tag_is_refused() -> None:
    table, _ = build_table(LIBRARY, genome(), CACHE, NOW)
    with pytest.raises(TableError):
        table.mean_of(["no such tag"])


def test_parse_film_reads_ids_runtime_and_path_tag() -> None:
    item = {
        "Id": "abc",
        "Name": "Film",
        "ProviderIds": {"Tmdb": "123", "Imdb": "tt1"},
        "ProductionYear": 1999,
        "Genres": ["Horror", "Comedy"],
        "OfficialRating": "R",
        "RunTimeTicks": 54_000_000_000,
        "CommunityRating": 6.1,
        "Path": "/media/Movies/Film (1999) {tmdb-124}/Film (1999) {tmdb-123}.mkv",
    }
    f = parse_film(item)
    assert (f.tmdb, f.year, f.runtime_min, f.rating, f.path_tmdb) == (123, 1999, 90.0, 6.1, 123)
    moved = parse_film({**item, "Path": "/m/Film (1999) {tmdb-777}/Film.mkv"})
    assert (moved.tmdb, moved.path_tmdb) == (123, 777)
    assert f.genres == frozenset({"Horror", "Comedy"})
    bare = parse_film({"Id": "x", "Name": "Y", "ProviderIds": {"Tmdb": ""}})
    assert (bare.tmdb, bare.runtime_min, bare.path_tmdb, bare.certificate) == (None, None, None, "")
    with pytest.raises(LibraryError):
        parse_film({"Name": "no id"})


def test_needs_fetch() -> None:
    assert needs_fetch(None, NOW)
    assert not needs_fetch(tmdb(1, 10, []), NOW)
    assert needs_fetch(tmdb(1, 151, []), NOW)
    assert needs_fetch(tmdb(1, 150, []), NOW)
    assert not needs_fetch(
        TmdbFilm(1, (NOW - timedelta(days=150) + timedelta(seconds=1)).isoformat(), None, None, [], "en", "", "", "T"),
        NOW,
    )
    assert needs_fetch(tmdb(1, 10, [], language=None), NOW)
    assert not needs_fetch(tmdb(1, 10, [], language=""), NOW)
    assert needs_fetch(tmdb(1, 10, [], poster=None), NOW)  # written before picture paths were kept
    assert not needs_fetch(tmdb(1, 10, [], poster="/p1.jpg"), NOW)
    assert needs_fetch(replace(tmdb(1, 10, []), title=None), NOW)  # written before the title and shown facts were kept


def test_refresh_appends_newest_and_stops_on_an_outage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("matinee.tmdb.datetime", _Frozen)
    cache = tmp_path / "t.jsonl"
    cache.write_text(json.dumps({"tmdb": 1, "fetched_at": NOW.isoformat(), "collection_id": None, "keywords": []}))
    cache.write_text(cache.read_text() + "\n")
    calls: list[int] = []

    def ok(t: int, _: str) -> TmdbFilm:
        calls.append(t)
        return TmdbFilm(t, NOW.isoformat(), None, None, ["k"], "en", "", "")

    assert refresh([1, 2], cache, "tok", fetch=ok) == Refreshed(2, 0)
    assert calls == [1, 2]
    assert load_cache(cache)[1].original_language == "en"

    def down(t: int, _: str) -> TmdbFilm:
        calls.append(t)
        raise urllib.error.URLError("down")

    calls.clear()
    assert refresh(range(10, 20), cache, "tok", fetch=down) == Refreshed(0, 5, NOT_ANSWERING)
    assert calls == [10, 11, 12, 13, 14]


class _Frozen(datetime):
    @classmethod
    def now(cls, tz: object = None) -> _Frozen:
        return cls.fromtimestamp(NOW.timestamp(), tz=UTC)


def _rec(t: int, age_days: int) -> str:
    fetched = (NOW - timedelta(days=age_days)).isoformat()
    return json.dumps(
        {"tmdb": t, "fetched_at": fetched, "collection_id": None, "keywords": [], "original_language": "en"}
    )


def test_refresh_compacts_to_newest_and_drops_expired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("matinee.tmdb.datetime", _Frozen)
    cache = tmp_path / "t.jsonl"
    cache.write_text("\n".join([_rec(1, 20), _rec(1, 5), _rec(2, 200)]) + "\n")
    refresh([1], cache, "tok", fetch=lambda t, _: None)
    lines = cache.read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["tmdb"] == 1
    assert load_cache(cache)[1].fetched == NOW - timedelta(days=5)


def test_refresh_interrupted_keeps_the_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("matinee.tmdb.datetime", _Frozen)
    cache = tmp_path / "t.jsonl"
    cache.write_text(_rec(1, 5) + "\n")

    def crash(t: int, _: str) -> TmdbFilm:
        raise RuntimeError("killed")

    with pytest.raises(RuntimeError):
        refresh([2], cache, "tok", fetch=crash)
    assert list(load_cache(cache)) == [1]


def test_damaged_lines_are_skipped(tmp_path: Path) -> None:
    cache = tmp_path / "t.jsonl"
    good, other = _rec(1, 5), _rec(2, 5)
    cache.write_text(good + "\n" + other + _rec(3, 5) + "\n" + '{"tmdb": 4}\n' + other[:-40] + "\n")
    assert list(load_cache(cache)) == [1]


def test_unknown_to_tmdb_is_not_cached_and_not_an_outage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("matinee.tmdb.datetime", _Frozen)
    cache = tmp_path / "t.jsonl"
    seen: list[int] = []

    def missing_then_ok(t: int, _: str) -> TmdbFilm | None:
        seen.append(t)
        return None if t < 16 else TmdbFilm(t, NOW.isoformat(), None, None, [], "en")

    assert refresh(range(10, 17), cache, "tok", fetch=missing_then_ok) == Refreshed(1, 6)
    assert seen == list(range(10, 17))
    assert list(load_cache(cache)) == [16]


def test_outage_streak_resets_after_a_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("matinee.tmdb.datetime", _Frozen)
    cache = tmp_path / "t.jsonl"
    seen: list[int] = []

    def flaky(t: int, _: str) -> TmdbFilm:
        seen.append(t)
        if t == 21:
            return TmdbFilm(t, NOW.isoformat(), None, None, [], "en")
        raise urllib.error.URLError("down")

    refresh([20, 21, 22, 23, 24, 25, 26], cache, "tok", fetch=flaky)
    assert seen == [20, 21, 22, 23, 24, 25, 26]


def test_fetch_film_maps_404_to_none_and_reads_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token: None)
    assert fetch_film(5, "tok") is None
    body = {
        "belongs_to_collection": {"id": 7, "name": "Saga"},
        "keywords": {"keywords": [{"name": "gore"}]},
        "original_language": "ja",
    }
    monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token: body)
    got = fetch_film(5, "tok")
    assert got is not None
    assert (got.collection_id, got.keywords, got.original_language) == (7, ["gore"], "ja")
    monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token: {"keywords": {"keywords": []}})
    bare = fetch_film(6, "tok")
    assert bare is not None and bare.original_language == ""
    assert (bare.poster_path, bare.backdrop_path) == ("", "")
    assert not needs_fetch(bare, datetime.now(UTC))


def test_fetch_film_keeps_picture_paths_shaped_like_tmdb_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    body: dict[str, object] = {
        "keywords": {"keywords": []},
        "poster_path": "/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg",
        "backdrop_path": None,
    }
    monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token: body)
    got = fetch_film(5, "tok")
    assert got is not None and (got.poster_path, got.backdrop_path) == ("/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg", "")
    for odd in ("//evil.example/x.jpg", "/a/../b.jpg", "/x.svg", 7, "https://image.tmdb.org/t/p/w92/x.jpg", "/x.jpg\n"):
        monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token, odd=odd: {**body, "poster_path": odd})
        got = fetch_film(5, "tok")
        assert got is not None and got.poster_path == ""


def test_picture_paths_follow_the_six_month_rule_through_the_table(tmp_path: Path) -> None:
    table, _ = build_table(LIBRARY, genome(), CACHE, NOW)
    assert table.films.loc[11, "poster_path"] == "/p11.jpg" and table.films.loc[11, "backdrop_path"] == "/b11.jpg"
    assert pd.isna(table.films.loc[22, "poster_path"])  # its record is too old to serve
    assert pd.isna(table.films.loc[33, "poster_path"])  # TMDB has no picture for it
    write_table(table, tmp_path / "films.sqlite")
    back = load_table(tmp_path / "films.sqlite", NOW)
    assert back.films.loc[11, "poster_path"] == "/p11.jpg" and back.films.loc[11, "backdrop_path"] == "/b11.jpg"
    assert pd.isna(back.films.loc[22, "poster_path"]) and pd.isna(back.films.loc[33, "backdrop_path"])


def test_a_table_missing_a_column_is_refused(tmp_path: Path) -> None:
    table, _ = build_table(LIBRARY, genome(), CACHE, NOW)
    path = tmp_path / "films.sqlite"
    write_table(table, path)
    with sqlite3.connect(path) as db:
        db.execute("ALTER TABLE films DROP COLUMN language")
    db.close()
    with pytest.raises(TableError, match="no language column"):
        load_table(path, NOW)


def test_daily_time_is_checked() -> None:
    import argparse

    from rebuild_table import daily_time

    assert daily_time("04:30") == (4, 30)
    for bad in ("3am", "03:00:00", "24:00"):
        with pytest.raises(argparse.ArgumentTypeError):
            daily_time(bad)


def test_empty_tag_list_is_refused() -> None:
    table, _ = build_table(LIBRARY, genome(), CACHE, NOW)
    with pytest.raises(TableError):
        table.mean_of([])


def test_a_loaded_table_can_be_written_again(tmp_path: Path) -> None:
    table, _ = build_table(LIBRARY, genome(), CACHE, NOW)
    write_table(table, tmp_path / "a.sqlite")
    again = load_table(tmp_path / "a.sqlite", NOW)
    write_table(again, tmp_path / "b.sqlite")
    back = load_table(tmp_path / "b.sqlite", NOW)
    assert pd.isna(back.films.loc[33, "collection_id"]) and back.films.loc[11, "collection_id"] == 900
    assert back.films.loc[22, "keywords"] is None


def test_fetch_film_keeps_the_shown_facts_and_the_us_age_rating(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    body = {
        "title": "Jaws",
        "release_date": "1975-06-20",
        "runtime": 124,
        "vote_average": 7.7,
        "vote_count": 10_500,
        "genres": [{"id": 27, "name": "Horror"}, {"id": 53, "name": "Thriller"}],
        "overview": " A shark. ",
        "release_dates": {
            "results": [
                {"iso_3166_1": "GB", "release_dates": [{"certification": "12A", "type": 3}]},
                {
                    "iso_3166_1": "US",
                    "release_dates": [
                        {"certification": "", "type": 1},
                        {"certification": "TV-14", "type": 6},
                        {"certification": "PG", "type": 3},
                    ],
                },
            ]
        },
    }

    def answer(url: str, token: str) -> dict[str, object]:
        seen.append(url)
        return body

    monkeypatch.setattr("matinee.tmdb.get_json", answer)
    got = fetch_film(578, "tok")
    assert got is not None and "append_to_response=keywords,release_dates" in seen[0]
    assert (got.title, got.year, got.runtime_min, got.rating, got.vote_count) == ("Jaws", 1975, 124.0, 7.7, 10_500)
    assert got.genres == ["Horror", "Thriller"] and got.synopsis == "A shark." and got.certification == "PG"
    assert not needs_fetch(got, datetime.now(UTC))
    us_only_tv = {
        **body,
        "release_dates": {"results": [{"iso_3166_1": "US", "release_dates": [{"certification": "TV-14", "type": 6}]}]},
    }
    monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token: us_only_tv)
    assert (got2 := fetch_film(578, "tok")) is not None and got2.certification == "TV-14"
    bare = {"title": "Unknown", "release_date": "", "runtime": 0, "vote_average": 0, "genres": []}
    monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token: bare)
    unrated = fetch_film(9, "tok")
    assert unrated is not None and unrated.certification == "" and unrated.year is None
    assert (unrated.runtime_min, unrated.rating, unrated.vote_count, unrated.synopsis) == (None, None, 0, "")


def test_a_refused_key_stops_the_refresh_at_once(tmp_path: Path) -> None:
    calls: list[int] = []

    def refused(t: int, _: str) -> TmdbFilm:
        calls.append(t)
        raise TmdbRefused(KEY_REFUSED)

    assert refresh([1, 2, 3], tmp_path / "t.jsonl", "bad", fetch=refused) == Refreshed(0, 0, KEY_REFUSED)
    assert calls == [1]


def test_a_401_is_a_refused_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def answer_401(req: object, timeout: float) -> object:
        raise urllib.error.HTTPError("https://api.themoviedb.org/3/movie/1", 401, "Unauthorized", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr("matinee.tmdb.urllib.request.urlopen", answer_401)
    monkeypatch.setattr("matinee.tmdb.time.sleep", lambda s: None)
    with pytest.raises(TmdbRefused):
        fetch_film(1, "bad")


def test_a_dropped_connection_is_a_network_failure_not_a_crash(tmp_path: Path) -> None:
    import http.client

    def dropped(t: int, _: str) -> TmdbFilm:
        raise http.client.RemoteDisconnected("gone")

    assert refresh(range(10), tmp_path / "t.jsonl", "tok", fetch=dropped) == Refreshed(0, 5, NOT_ANSWERING)


def test_an_empty_theatrical_rating_never_wins_over_a_real_one(monkeypatch: pytest.MonkeyPatch) -> None:
    us = {"iso_3166_1": "US", "release_dates": [{"certification": "", "type": 3}, {"certification": "PG", "type": 4}]}
    monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token: {"title": "X", "release_dates": {"results": [us]}})
    got = fetch_film(1, "tok")
    assert got is not None and got.certification == "PG"
