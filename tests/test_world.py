"""Films the library does not hold: how the table keeps them, and how the server offers them beside the library's."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from matinee.engine import Viewer, load_catalog, walk
from matinee.genome import Scores
from matinee.labels import Labels, TreeLabels
from matinee.library import LibraryFilm
from matinee.pools import load_house
from matinee.table import build_table, library_films, load_table, with_live, write_table
from matinee.tmdb import TmdbFilm
from test_engine import TAGS, reference, write_data

NOW = datetime(2026, 10, 4, tzinfo=UTC)
SCORES = Scores("test", TAGS, {1: 0, 2: 1}, np.zeros((2, len(TAGS)), dtype=np.float32))
SCORES.relevance[1, TAGS.index("gore_a")] = 0.9


def record(t: int, title: str, cert: str = "PG", genres: tuple[str, ...] = ("Western",), age: int = 10) -> TmdbFilm:
    fetched = (NOW - timedelta(days=age)).isoformat()
    return TmdbFilm(
        t, fetched, None, None, [], "en", f"/p{t}.jpg", "", title=title, year=1990 + t, runtime_min=100.0,
        rating=7.0, genres=list(genres), synopsis=f"About {title}.", vote_count=1000 * t, certification=cert,
    )  # fmt: skip


def lib(
    t: int, name: str | None = None, cert: str = "PG", genres: frozenset[str] = frozenset({"Drama"})
) -> LibraryFilm:
    return LibraryFilm(f"{t:032x}", t, f"Held {t}" if name is None else name, 2000, genres, cert, 90.0, 6.0, None)


CACHE = {
    1: record(1, "Held one"),
    2: record(2, "World two", cert="", genres=("Western", "Family")),
    3: record(3, "World three", cert="G"),
    4: record(4, "Too old", age=200),
}


def test_the_table_holds_the_library_and_every_labelled_film_with_a_usable_record() -> None:
    table, report = build_table([lib(1)], SCORES, CACHE, NOW, listed=[1, 2, 3, 4, 5])
    films = table.films
    assert list(films.index) == [1, 2, 3]  # 4's record is too old and 5 has none
    assert report.not_held == 2 and report.listed_without_record == 2
    held, world = films.loc[1], films.loc[2]
    assert (held.item_id, held["name"], held.certificate, held.tmdb_title) == (f"{1:032x}", "Held 1", "PG", "Held one")
    assert held.genres == frozenset({"Western"})  # TMDB's genres, the names the rules read
    assert pd_none(world.item_id) and (world["name"], world.year, world.certificate) == ("World two", 1992, "")
    assert world.genres == frozenset({"Western", "Family"}) and world.synopsis == "About World two."
    assert table.genome[list(films.index).index(2)][TAGS.index("gore_a")] == np.float32(0.9)


def test_a_library_film_takes_tmdb_facts_only_where_its_own_cannot_serve() -> None:
    table, _ = build_table(
        [lib(1, name=""), lib(3, cert="gb/U", genres=frozenset({"Kids & Family"}))], SCORES, CACHE, NOW
    )
    assert table.films.loc[1, "name"] == "Held one"  # an empty title is TMDB's
    assert table.films.loc[3, "certificate"] == "G"  # another country's rating is TMDB's US one
    plain, _ = build_table([lib(3, cert="NR")], SCORES, {}, NOW)
    assert plain.films.loc[3, "certificate"] == "NR" and plain.films.loc[3, "genres"] == frozenset({"Drama"})


def test_the_server_reads_which_films_are_held_from_the_live_list() -> None:
    table, _ = build_table([lib(1)], SCORES, CACHE, NOW, listed=[1, 2, 3])
    both, _ = with_live(table, [lib(1), lib(2, name="Bought since")], listed=[1, 2, 3])
    films = both.films
    assert films.held.to_dict() == {1: True, 2: True, 3: False}
    assert films.loc[2, "name"] == "Bought since" and films.loc[2, "item_id"] == f"{2:032x}"
    gone, _ = with_live(table, [lib(2)], listed=[2, 3])
    assert list(gone.films.index) == [2, 3]  # 1 left the library and no label names it: never offered
    sold, _ = with_live(table, [], listed=[1, 2, 3])
    assert sold.films.held.to_dict() == {1: False, 2: False, 3: False}
    assert sold.films.loc[1, "name"] == "Held one" and pd_none(sold.films.loc[1, "item_id"])
    down, _ = with_live(table, None, listed=[1, 2, 3])
    assert not down.films.held.any() and len(down.films) == 3


def test_a_film_with_no_us_rating_never_enters_the_kids_pool(tmp_path: Path) -> None:
    table, _ = build_table([], SCORES, CACHE, NOW, listed=[2, 3])
    served, _ = with_live(table, [], listed=[2, 3])
    kids = Labels(
        {"kids": TreeLabels({2: frozenset({"adventure"}), 3: frozenset({"adventure"})}, {2: "little", 3: "little"})}
    )
    from matinee.pools import build_pools

    pools = build_pools(served, load_house(write_data(tmp_path) / "house_overrides.json"), kids)
    assert dict(zip(served.films.index, pools["kids"], strict=True)) == {2: False, 3: True}
    assert not served.films.held.any()


def test_a_film_the_library_does_not_hold_can_be_drawn_into_a_pool(tmp_path: Path) -> None:
    table, _ = build_table([lib(1)], SCORES, CACHE, NOW, listed=[1, 2, 3])
    served, _ = with_live(table, [lib(1)], listed=[1, 2, 3])
    west = Labels({"west": TreeLabels({1: frozenset(), 2: frozenset(), 3: frozenset()})})
    cat = load_catalog(served, write_data(tmp_path), reference(), west)
    assert set(walk(cat, "west", Viewer(), []).pool) >= {2, 3}
    assert served.films.held.tolist() == [True, False, False]


def test_the_table_round_trips_and_names_its_library(tmp_path: Path) -> None:
    table, _ = build_table([lib(1)], SCORES, CACHE, NOW, listed=[1, 2, 3])
    write_table(table, tmp_path / "films.sqlite")
    back = load_table(tmp_path / "films.sqlite")
    assert list(back.films.index) == [1, 2, 3]
    assert (
        back.films.loc[2, "tmdb_genres"] == frozenset({"Western", "Family"}) and back.films.loc[2, "vote_count"] == 2000
    )
    assert [f.tmdb for f in library_films(back)] == [1]
    assert np.array_equal(back.genome, table.genome, equal_nan=True)


def pd_none(value: object) -> bool:
    return value is None or value != value  # None, NaN or pandas' NA


def test_a_kids_pin_never_carries_an_unrated_film_the_library_does_not_hold(tmp_path: Path) -> None:
    from matinee.pools import kids_bands

    cache = {**CACHE, 5: record(5, "Rated", cert="PG-13")}
    table, _ = build_table([lib(3, cert="NR")], SCORES, cache, NOW, listed=[2, 3, 5])
    served, _ = with_live(table, [lib(3, cert="NR")], listed=[2, 3, 5])
    pins = {2: "family", 3: "family", 5: "little"}
    bands = kids_bands(served, TreeLabels(), pins)
    assert dict(zip(served.films.index, bands["older"], strict=True)) == {2: False, 3: True, 5: True}
    assert bool(bands["little"][5]) and not bool(bands["little"][3]) and bool(bands["family"][3])


def test_a_record_kept_before_titles_names_no_film_and_the_table_still_writes(tmp_path: Path) -> None:
    from dataclasses import replace

    untitled = {2: replace(CACHE[2], title=None)}
    table, report = build_table([], SCORES, untitled, NOW, listed=[2])
    assert list(table.films.index) == [] and report.listed_without_record == 1
    write_table(table, tmp_path / "films.sqlite")


def test_the_insert_names_one_placeholder_per_column() -> None:
    from matinee.table import COLUMNS, INSERT_FILM

    assert INSERT_FILM.count("?") == len(COLUMNS) + 1


def test_a_film_whose_record_names_no_title_is_never_offered_from_a_loaded_table(tmp_path: Path) -> None:
    from dataclasses import replace

    untitled = {**CACHE, 1: replace(CACHE[1], title=None)}
    table, _ = build_table([lib(1)], SCORES, untitled, NOW, listed=[1, 2])
    write_table(table, tmp_path / "films.sqlite")
    back = load_table(tmp_path / "films.sqlite")
    unusable, _ = with_live(back, None, listed=[1, 2])
    assert list(unusable.films.index) == [2]  # 1 is the library's, and with no title it cannot be named alone
    assert all(isinstance(n, str) and n for n in unusable.films["name"])
