"""The offline film table, the Jellyfin film parser and the TMDB cache."""

from __future__ import annotations

import json
import sqlite3
import urllib.error
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
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
    MAX_WORKERS,
    NOT_ANSWERING,
    Pacer,
    Refreshed,
    TmdbFilm,
    TmdbRefused,
    fetch_film,
    load_cache,
    needs_fetch,
    refresh,
)

NOW = datetime(2026, 9, 25, tzinfo=UTC)
FAST = Pacer(1e9)  # no wait between requests


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
    back = load_table(path)
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


def test_load_refuses_absent_and_reads_a_stale_table_flagged(tmp_path: Path) -> None:
    from matinee.table import is_stale

    with pytest.raises(TableError):
        load_table(tmp_path / "nope.sqlite")
    table, _ = build_table(LIBRARY, genome(), CACHE, NOW)
    write_table(table, tmp_path / "films.sqlite")
    back = load_table(tmp_path / "films.sqlite")
    oldest = CACHE[33].fetched
    assert not is_stale(back, oldest + timedelta(days=183) - timedelta(seconds=1))
    assert is_stale(back, oldest + timedelta(days=183))


def test_load_refuses_another_format(tmp_path: Path) -> None:
    table, _ = build_table(LIBRARY, genome(), CACHE, NOW)
    path = tmp_path / "films.sqlite"
    write_table(table, path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE meta SET value = '1' WHERE key = 'format'")  # the table before films outside the library
    db.close()
    with pytest.raises(TableError, match="format"):
        load_table(path)


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
    assert list(load_table(path).films.index) == [11, 22, 33]


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

    assert refresh([1, 2], cache, "tok", fetch=ok, rate=1) == Refreshed(2, 0)
    assert calls == [1, 2]
    assert load_cache(cache)[1].original_language == "en"

    def down(t: int, _: str) -> TmdbFilm:
        calls.append(t)
        raise urllib.error.URLError("down")

    calls.clear()
    assert refresh(range(10, 20), cache, "tok", fetch=down, rate=1) == Refreshed(0, 5, NOT_ANSWERING)
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
    refresh([1], cache, "tok", fetch=lambda t, _: None, rate=1)
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
        refresh([2], cache, "tok", fetch=crash, rate=1)
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

    assert refresh(range(10, 17), cache, "tok", fetch=missing_then_ok, rate=1) == Refreshed(1, 6)
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

    refresh([20, 21, 22, 23, 24, 25, 26], cache, "tok", fetch=flaky, rate=1)
    assert seen == [20, 21, 22, 23, 24, 25, 26]


def test_fetch_film_maps_404_to_none_and_reads_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token, pacer: None)
    assert fetch_film(5, "tok", FAST) is None
    body = {
        "belongs_to_collection": {"id": 7, "name": "Saga"},
        "keywords": {"keywords": [{"name": "gore"}]},
        "original_language": "ja",
    }
    monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token, pacer: body)
    got = fetch_film(5, "tok", FAST)
    assert got is not None
    assert (got.collection_id, got.keywords, got.original_language) == (7, ["gore"], "ja")
    monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token, pacer: {"keywords": {"keywords": []}})
    bare = fetch_film(6, "tok", FAST)
    assert bare is not None and bare.original_language == ""
    assert (bare.poster_path, bare.backdrop_path) == ("", "")
    assert not needs_fetch(bare, datetime.now(UTC))


def test_fetch_film_keeps_picture_paths_shaped_like_tmdb_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    body: dict[str, object] = {
        "keywords": {"keywords": []},
        "poster_path": "/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg",
        "backdrop_path": None,
    }
    monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token, pacer: body)
    got = fetch_film(5, "tok", FAST)
    assert got is not None and (got.poster_path, got.backdrop_path) == ("/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg", "")
    for odd in ("//evil.example/x.jpg", "/a/../b.jpg", "/x.svg", 7, "https://image.tmdb.org/t/p/w92/x.jpg", "/x.jpg\n"):
        monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token, pacer, odd=odd: {**body, "poster_path": odd})
        got = fetch_film(5, "tok", FAST)
        assert got is not None and got.poster_path == ""


def test_picture_paths_follow_the_six_month_rule_through_the_table(tmp_path: Path) -> None:
    table, _ = build_table(LIBRARY, genome(), CACHE, NOW)
    assert table.films.loc[11, "poster_path"] == "/p11.jpg" and table.films.loc[11, "backdrop_path"] == "/b11.jpg"
    assert pd.isna(table.films.loc[22, "poster_path"])  # its record is too old to serve
    assert pd.isna(table.films.loc[33, "poster_path"])  # TMDB has no picture for it
    write_table(table, tmp_path / "films.sqlite")
    back = load_table(tmp_path / "films.sqlite")
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
        load_table(path)


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
    again = load_table(tmp_path / "a.sqlite")
    write_table(again, tmp_path / "b.sqlite")
    back = load_table(tmp_path / "b.sqlite")
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

    def answer(url: str, token: str, pacer: Pacer) -> dict[str, object]:
        seen.append(url)
        return body

    monkeypatch.setattr("matinee.tmdb.get_json", answer)
    got = fetch_film(578, "tok", FAST)
    assert got is not None and "append_to_response=keywords,release_dates" in seen[0]
    assert (got.title, got.year, got.runtime_min, got.rating, got.vote_count) == ("Jaws", 1975, 124.0, 7.7, 10_500)
    assert got.genres == ["Horror", "Thriller"] and got.synopsis == "A shark." and got.certification == "PG"
    assert not needs_fetch(got, datetime.now(UTC))
    us_only_tv = {
        **body,
        "release_dates": {"results": [{"iso_3166_1": "US", "release_dates": [{"certification": "TV-14", "type": 6}]}]},
    }
    monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token, pacer: us_only_tv)
    assert (got2 := fetch_film(578, "tok", FAST)) is not None and got2.certification == "TV-14"
    bare = {"title": "Unknown", "release_date": "", "runtime": 0, "vote_average": 0, "genres": []}
    monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token, pacer: bare)
    unrated = fetch_film(9, "tok", FAST)
    assert unrated is not None and unrated.certification == "" and unrated.year is None
    assert (unrated.runtime_min, unrated.rating, unrated.vote_count, unrated.synopsis) == (None, None, 0, "")


def test_a_refused_key_stops_the_refresh_at_once(tmp_path: Path) -> None:
    calls: list[int] = []

    def refused(t: int, _: str) -> TmdbFilm:
        calls.append(t)
        raise TmdbRefused(KEY_REFUSED)

    assert refresh([1, 2, 3], tmp_path / "t.jsonl", "bad", fetch=refused, rate=1) == Refreshed(0, 0, KEY_REFUSED)
    assert calls == [1]


def test_a_401_is_a_refused_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def answer_401(req: object, timeout: float) -> object:
        raise urllib.error.HTTPError("https://api.themoviedb.org/3/movie/1", 401, "Unauthorized", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr("matinee.tmdb.urllib.request.urlopen", answer_401)
    monkeypatch.setattr("matinee.tmdb.time.sleep", lambda s: None)
    with pytest.raises(TmdbRefused):
        fetch_film(1, "bad", FAST)


def test_a_dropped_connection_is_a_network_failure_not_a_crash(tmp_path: Path) -> None:
    import http.client

    def dropped(t: int, _: str) -> TmdbFilm:
        raise http.client.RemoteDisconnected("gone")

    assert refresh(range(10), tmp_path / "t.jsonl", "tok", fetch=dropped, rate=1) == Refreshed(0, 5, NOT_ANSWERING)


def test_an_empty_theatrical_rating_never_wins_over_a_real_one(monkeypatch: pytest.MonkeyPatch) -> None:
    us = {"iso_3166_1": "US", "release_dates": [{"certification": "", "type": 3}, {"certification": "PG", "type": 4}]}
    monkeypatch.setattr(
        "matinee.tmdb.get_json", lambda url, token, pacer: {"title": "X", "release_dates": {"results": [us]}}
    )
    got = fetch_film(1, "tok", FAST)
    assert got is not None and got.certification == "PG"


def test_the_pacer_spaces_every_thread_at_the_rate_and_a_429_holds_them_all() -> None:
    time_ = FakeTime()
    pacer = Pacer(4.0, clock=time_.clock, sleep=time_.sleep)
    for _ in range(3):
        pacer.wait()
    assert time_.slept == [0.25, 0.25]  # the first goes at once, then a quarter second apart
    pacer.hold(10)
    pacer.wait()
    assert time_.slept[-1] == 10.0
    with pytest.raises(ValueError):
        Pacer(0)


def test_several_requests_are_in_flight_at_once(tmp_path: Path) -> None:
    import threading

    active, peak = [0], [0]
    guard = threading.Lock()

    def slow(t: int, _: str) -> TmdbFilm:
        with guard:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        threading.Event().wait(0.02)
        with guard:
            active[0] -= 1
        return TmdbFilm(t, NOW.isoformat(), None, None, [], "en", "", "", "T")

    assert refresh(range(40), tmp_path / "t.jsonl", "tok", fetch=slow, rate=30).fetched == 40
    assert peak[0] > 1
    peak[0] = 0
    assert refresh(range(100), tmp_path / "u.jsonl", "tok", fetch=slow, rate=1e6).fetched == 100
    assert 1 < peak[0] <= MAX_WORKERS  # threads are capped however high the rate


@pytest.mark.parametrize(
    ("text", "rate"), [("", 30.0), ("45", 45.0), ("0.5", 0.5), ("0", 30.0), ("-3", 30.0), ("fast", 30.0), ("inf", 30.0)]
)
def test_tmdb_rate_takes_any_positive_number(text: str, rate: float) -> None:
    from rebuild_table import tmdb_rate

    assert tmdb_rate(text) == rate


class FakeTime:
    """A clock that sleeping moves forward."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []
        self.during: list[Callable[[], None]] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        for act in self.during:
            act()
        self.during.clear()
        self.now += seconds


def test_a_hold_that_lands_while_a_request_waits_sends_it_after_the_hold() -> None:
    time_ = FakeTime()
    pacer = Pacer(4.0, clock=time_.clock, sleep=time_.sleep)
    pacer.wait()  # turn at 0
    time_.during.append(lambda: pacer.hold(10))  # a 429 arrives while the next request sleeps to 0.25
    pacer.wait()
    assert time_.now >= 10
    short = FakeTime()
    quick = Pacer(4.0, clock=short.clock, sleep=short.sleep)
    quick.wait()
    short.during.append(lambda: quick.hold(0.1))  # ends before the reserved turn: no second sleep
    quick.wait()
    assert short.slept == [0.25]


def test_a_429_through_get_json_waits_out_its_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    time_ = FakeTime()
    pacer = Pacer(1e6, clock=time_.clock, sleep=time_.sleep)
    answers: list[object] = [
        urllib.error.HTTPError("u", 429, "Too Many", {"Retry-After": "7"}, None),  # type: ignore[arg-type]
        io.BytesIO(b'{"title": "Jaws"}'),
    ]

    def urlopen(req: object, timeout: float) -> object:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr("matinee.tmdb.urllib.request.urlopen", urlopen)
    got = fetch_film(578, "tok", pacer)
    assert got is not None and got.title == "Jaws" and time_.now >= 7


def test_refresh_paces_every_thread_with_one_pacer_at_the_rate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Pacer] = []

    def recorded(tmdb: int, token: str, pacer: Pacer) -> TmdbFilm:
        seen.append(pacer)
        return TmdbFilm(tmdb, NOW.isoformat(), None, None, [], "en", "", "", "T")

    monkeypatch.setattr("matinee.tmdb.fetch_film", recorded)
    refresh(range(20), tmp_path / "t.jsonl", "tok", rate=45)
    assert len(seen) == 20 and len({id(p) for p in seen}) == 1 and seen[0]._gap == pytest.approx(1 / 45)


@pytest.mark.parametrize("rate", [30, 1e6])
def test_an_outage_and_a_refused_key_stop_with_the_same_counts_at_many_workers(tmp_path: Path, rate: float) -> None:
    def down(t: int, _: str) -> TmdbFilm:
        raise urllib.error.URLError("down")

    def refused(t: int, _: str) -> TmdbFilm:
        raise TmdbRefused(KEY_REFUSED)

    for _ in range(10):
        assert refresh(range(200), tmp_path / "a.jsonl", "tok", fetch=down, rate=rate) == Refreshed(0, 5, NOT_ANSWERING)
        assert refresh(range(200), tmp_path / "b.jsonl", "tok", fetch=refused, rate=rate) == Refreshed(
            0, 0, KEY_REFUSED
        )


def voted_record(t: int, votes: int) -> TmdbFilm:
    return TmdbFilm(t, NOW.isoformat(), None, None, [], "en", "", "", title=f"Film {t}", vote_count=votes)


def test_a_first_start_fetches_in_tmdbs_order_by_votes_and_films_outside_it_last(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from matinee.tmdb import fetch_order

    assert fetch_order([5, 1, 2, 9], {}, lambda: [2, 7, 1, 2]) == [2, 1, 5, 9]
    with caplog.at_level("WARNING", logger="matinee.tmdb"):
        assert fetch_order([5, 1, 9], {}, lambda: []) == [1, 5, 9]
    assert "could not be read" in caplog.text

    def never() -> list[int]:
        raise AssertionError("a later rebuild orders by the records it holds")

    held = {1: voted_record(1, 10), 2: voted_record(2, 50), 4: voted_record(4, 0)}
    assert fetch_order([3, 1, 2, 4], held, never) == [2, 1, 4, 3]
    assert fetch_order([], {}, never) == []
    old = {1: voted_record(1, 0), 2: replace(voted_record(2, 0), vote_count=None)}  # kept before vote counts
    assert fetch_order([1, 2, 3], old, lambda: [3, 2]) == [3, 2, 1]  # an upgrade reads TMDB's order too


def test_the_vote_list_reads_its_pages_in_order_and_keeps_those_before_one_that_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from matinee.tmdb import most_voted

    urls: list[str] = []

    def answer(url: str, token: str, pacer: Pacer) -> dict[str, object] | None:
        urls.append(url)
        n = int(url.rsplit("=", 1)[1])
        if n == 4:
            raise urllib.error.URLError("down")
        return {"results": [{"id": n * 10}, {"id": n * 10 + 1}, {"title": "no id"}]}

    monkeypatch.setattr("matinee.tmdb.get_json", answer)
    pages: list[int] = []
    assert most_voted("tok", FAST, 4, pages=6, on_page=lambda: pages.append(1)) == [10, 11, 20, 21, 30, 31]
    assert len(pages) == 3  # progress after each page read
    assert all("/discover/movie?sort_by=vote_count.desc&page=" in u for u in urls)
    monkeypatch.setattr("matinee.tmdb.get_json", lambda url, token, pacer: {"results": [{"id": 1}]})
    assert most_voted("tok", FAST, 4, pages=3) == [1, 1, 1]

    def refused(url: str, token: str, pacer: Pacer) -> None:
        raise TmdbRefused(KEY_REFUSED)

    monkeypatch.setattr("matinee.tmdb.get_json", refused)
    assert most_voted("tok", FAST, 4) == []


def test_refresh_reports_its_progress_with_every_record_it_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "t.jsonl"
    cache.write_text(json.dumps(asdict(voted_record(99, 5))) + "\n")
    monkeypatch.setattr("matinee.tmdb.TICK_EVERY", 0.0)
    seen: list[tuple[Refreshed, int, set[int]]] = []

    def tick(so_far: Refreshed, total: int, records: Mapping[int, TmdbFilm]) -> None:
        seen.append((so_far, total, set(records)))

    refresh(range(1, 5), cache, "tok", fetch=lambda t, _: voted_record(t, t), rate=1, tick=tick)
    assert [f for f in dict.fromkeys(s.fetched for s, _, _ in seen) if f] == [1, 2, 3, 4]
    assert {total for _, total, _ in seen} == {4}
    assert seen[-1][2] == {99, 1, 2, 3, 4}  # the records held before, and each new one as it comes


def test_progress_is_reported_while_a_request_waits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    monkeypatch.setattr("matinee.tmdb.TICK_EVERY", 0.02)
    ticks: list[int] = []

    def slow(t: int, _: str) -> TmdbFilm:
        threading.Event().wait(0.3)  # a 429's hold, or a slow answer
        return voted_record(t, 1)

    refresh([1], tmp_path / "t.jsonl", "tok", fetch=slow, rate=1, tick=lambda s, n, r: ticks.append(s.fetched))
    assert ticks.count(0) >= 3


def test_refresh_paces_with_the_pacer_it_is_given(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    given = Pacer(7.0)
    seen: list[Pacer] = []

    def recorded(tmdb: int, token: str, pacer: Pacer) -> TmdbFilm:
        seen.append(pacer)
        return voted_record(tmdb, 1)

    monkeypatch.setattr("matinee.tmdb.fetch_film", recorded)
    refresh(range(5), tmp_path / "t.jsonl", "tok", rate=30, pacer=given)
    assert len(seen) == 5 and all(p is given for p in seen)
