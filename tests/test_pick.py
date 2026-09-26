"""The pick and its DoesTheDogDie check."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from matinee.dtdd import Dtdd, DtddCeiling, DtddError, DtddGone
from matinee.engine import load_catalog
from matinee.pick import (
    ID_KEEP_S,
    LOOKUPS_PER_HOUR,
    DeviceCap,
    Hit,
    ItemIds,
    Picker,
    Unreadable,
    candidates,
    failing,
    look_up,
)
from matinee.store import Store
from matinee.table import FilmTable
from matinee.web.app import create_app
from matinee.web.config import Config
from matinee.web.theatre import Theatre
from test_engine import gore_cut_tree, reference, write_data
from test_web_library import SECRET_KEY, SECRET_URL, FakeLibrary, write_film_table


def stat(topic: int, yes: object, no: object) -> dict[str, Any]:
    return {"topicId": topic, "topicName": f"topic {topic}", "yesSum": yes, "noSum": no}


def test_a_topic_fails_on_five_votes_and_more_yes_than_no() -> None:
    stats = [stat(1, 3, 1), stat(2, 3, 2), stat(3, 5, 0), stat(4, 4, 4), stat(5, 9, 0), stat(6, None, 3)]
    assert failing(stats, frozenset({1, 2, 3, 4})) == (
        Hit(2, "topic 2"),
        Hit(3, "topic 3"),
    )  # 1: four votes; 4: a tie; 5: not asked


@pytest.mark.parametrize(
    "row",
    [stat(153, None, 3), stat(153, "9", "0"), {"topic": {"id": 153}, "yesSum": 9, "noSum": 0}, ["not", "an", "object"]],
)
def test_an_unreadable_vote_row_is_never_a_pass(row: Any) -> None:
    with pytest.raises(Unreadable):
        failing([stat(1, 0, 9), row], frozenset({153}))
    verdict = look_up(ScriptedDtdd({7: [row]}), 7, frozenset({153}), ItemIds())
    assert verdict.unchecked == "no_record" and verdict.hits == ()


def test_a_search_matching_twice_takes_the_movie_or_goes_unchecked() -> None:
    class Twice(ScriptedDtdd):
        def __init__(self, search: list[dict[str, Any]], films: dict[int, Any]) -> None:
            super().__init__(films)
            self.search = search

        def get(self, path: str, timeout: float, wait: float) -> Any:
            if path.startswith("/items?tmdb="):
                self.paths.append(path)
                return self.search
            return super().get(path, timeout, wait)

    show = {"id": 1008, "tmdbId": 8, "itemTypeName": "TV Show"}
    movie = {"id": 1009, "tmdbId": 8, "itemTypeName": "Movie"}
    dtdd = Twice([show, movie], {9: [stat(153, 9, 0)]})
    assert look_up(dtdd, 8, frozenset({153}), ItemIds()).hits == (Hit(153, "topic 153"),)  # the Movie's votes
    both_shows = Twice([show, {**show, "id": 1010}], {})
    assert look_up(both_shows, 8, frozenset({153}), ItemIds()).unchecked == "no_record"


class ScriptedDtdd(Dtdd):
    """Answers lookups from a table of films: tmdb -> stats, None for no record, or an exception."""

    def __init__(self, films: dict[int, Any]) -> None:
        super().__init__("k")
        self.films = films
        self.paths: list[str] = []

    def get(self, path: str, timeout: float, wait: float) -> Any:
        self.paths.append(path)
        assert timeout <= 3.0 and wait <= 3.0
        if path.startswith("/items?tmdb="):
            tmdb = int(path.split("=")[1])
            answer = self.films.get(tmdb)
            if isinstance(answer, Exception):
                raise answer
            return [] if answer is None else [{"id": 1000 + tmdb, "tmdbId": tmdb}]
        return {"topicItemStats": self.films[int(path.rsplit("/", 1)[1]) - 1000]}

    def looked_up(self) -> list[int]:
        return [int(p.split("=")[1]) for p in self.paths if p.startswith("/items?tmdb=")]


def test_look_up_reads_the_votes_or_says_why_not() -> None:
    dtdd = ScriptedDtdd({1: [stat(153, 40, 2)], 2: None, 3: DtddError("slow")})
    assert look_up(dtdd, 1, frozenset({153}), ItemIds()).hits == (Hit(153, "topic 153"),)
    assert look_up(dtdd, 1, frozenset({188}), ItemIds()).hits == ()
    assert look_up(dtdd, 2, frozenset({153}), ItemIds()).unchecked == "no_record"
    assert look_up(dtdd, 3, frozenset({153}), ItemIds()).unchecked == "slow"
    assert dtdd.paths[:2] == ["/items?tmdb=1", "/items/1001"]


def test_the_device_cap_is_sixty_an_hour() -> None:
    assert LOOKUPS_PER_HOUR == 60
    now = [0.0]
    cap = DeviceCap(clock=lambda: now[0])
    assert all(cap.take("a") for _ in range(LOOKUPS_PER_HOUR))
    assert not cap.take("a") and cap.take("b")
    now[0] = 3600.0
    assert cap.take("a")


def test_candidates_skip_what_was_seen_and_take_the_better_half() -> None:
    ratings = {1: 5.0, 2: 9.0, 3: 7.0, 4: 8.0, 5: 6.0}
    assert candidates([1, 2, 3, 4, 5], [2, 4], ratings, None) == [1, 3, 5]
    assert candidates([1, 2], [1, 2], ratings, None) == [1, 2]  # all seen: start the pool again
    assert candidates([1, 2, 3, 4, 5], [], ratings, "rating") == [2, 4, 3]


def test_no_topics_means_no_lookup() -> None:
    dtdd = ScriptedDtdd({})
    result = Picker(dtdd, DeviceCap(), random.Random(1)).pick([1, 2, 3], frozenset(), "dev")
    assert result.film in {1, 2, 3} and dtdd.paths == []


def test_a_failing_film_is_replaced_and_never_looked_up_twice() -> None:
    films = {t: [stat(153, 9, 0)] for t in range(1, 6)} | {6: [stat(153, 0, 9)]}
    dtdd = ScriptedDtdd(films)
    result = Picker(dtdd, DeviceCap(), random.Random(3)).pick(list(range(1, 7)), frozenset({153}), "dev")
    assert result.film == 6 and result.swapped in range(1, 6)
    assert result.swapped_hits == (Hit(153, "topic 153"),)
    assert len(dtdd.looked_up()) == len(set(dtdd.looked_up()))


def test_every_film_failing_says_so() -> None:
    dtdd = ScriptedDtdd({t: [stat(153, 9, 0)] for t in range(1, 4)})
    result = Picker(dtdd, DeviceCap(), random.Random(0)).pick([1, 2, 3], frozenset({153}), "dev")
    assert result.film is None and result.exhausted and sorted(dtdd.looked_up()) == [1, 2, 3]


@pytest.mark.parametrize("answer,reason", [(None, "no_record"), (DtddError("slow"), "slow")])
def test_an_unchecked_film_is_shown_with_the_reason(answer: Any, reason: str) -> None:
    result = Picker(ScriptedDtdd({1: answer}), DeviceCap(), random.Random(0)).pick([1], frozenset({153}), "dev")
    assert result.film == 1 and result.unchecked == reason


def test_past_the_cap_the_film_is_shown_unchecked() -> None:
    dtdd = ScriptedDtdd({1: [stat(153, 0, 9)]})
    cap = DeviceCap()
    for _ in range(LOOKUPS_PER_HOUR):
        cap.take("dev")
    result = Picker(dtdd, cap, random.Random(0)).pick([1], frozenset({153}), "dev")
    assert result.film == 1 and result.unchecked == "cap" and dtdd.paths == []


@pytest.fixture
def site(tmp_path: Path) -> tuple[TestClient, ScriptedDtdd]:
    data = write_data(tmp_path / "data")
    write_film_table(tmp_path / "films.sqlite")

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data, reference())

    theatre = Theatre(FakeLibrary(held=[1, 2, 3]), tmp_path / "films.sqlite", catalog_of=catalog_of)
    dtdd = ScriptedDtdd({1: [stat(153, 30, 1)], 2: [stat(153, 30, 1)], 3: [stat(153, 30, 1)]})
    config = Config(SECRET_URL, SECRET_KEY, tmp_path, "https://seerr.invalid", "d" * 16)
    app = create_app(config, theatre, Store(tmp_path / "s.sqlite"), dtdd, clock=lambda: 0.0)
    return TestClient(app, base_url="https://testserver"), dtdd


def test_a_viewer_without_topics_causes_no_lookup_and_no_device_cookie(site: Any) -> None:
    client, dtdd = site
    resp = client.post("/api/pick", json={"tree": "west"})
    body = resp.json()
    assert body["film"]["tmdb"] in {1, 2, 3} and body["swapped"] is None and body["unchecked"] is None
    assert dtdd.paths == [] and "matinee_device" not in resp.headers.get("set-cookie", "")


def test_seen_films_are_not_drawn_again(site: Any) -> None:
    client, _ = site
    assert client.post("/api/pick", json={"tree": "west", "seen": [1, 2]}).json()["film"]["tmdb"] == 3


def test_an_exhausted_pool_says_so_in_words(site: Any) -> None:
    client, dtdd = site
    resp = client.post("/api/pick", json={"tree": "west", "viewer": {"topics": [153]}})
    body = resp.json()
    assert body["film"] is None
    assert body["exhausted"] == "Every film left here trips something on your list. Want to start over?"
    assert body["swapped"]["line"] == "Oh, I almost recommended a film where topic 153. Let's find you an alternative."
    assert body["swapped"]["reveal"] == "What were you going to show me?"
    assert body["credit"] == "Powered by DoesTheDogDie.com"
    assert "matinee_device" in resp.headers["set-cookie"] and "HttpOnly" in resp.headers["set-cookie"]


def test_idle_devices_are_forgotten() -> None:
    now = [0.0]
    cap = DeviceCap(clock=lambda: now[0])
    for i in range(1000):
        cap.take(f"device {i}")
    now[0] = 3600.0 + 61
    cap.take("fresh")
    assert list(cap.spent) == ["fresh"]


def site_with(tmp_path: Path, picker: Picker | None, dtdd: ScriptedDtdd) -> TestClient:
    data = write_data(tmp_path / "data")
    write_film_table(tmp_path / "films.sqlite")

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data, reference())

    theatre = Theatre(FakeLibrary(held=[1, 2, 3]), tmp_path / "films.sqlite", catalog_of=catalog_of)
    config = Config(SECRET_URL, SECRET_KEY, tmp_path, "https://seerr.invalid", "d" * 16)
    app = create_app(config, theatre, Store(tmp_path / "s.sqlite"), dtdd, clock=lambda: 0.0, picker=picker)
    return TestClient(app, base_url="https://testserver")


def test_the_route_names_an_unchecked_film(tmp_path: Path) -> None:
    dtdd = ScriptedDtdd({1: None, 2: None, 3: None})
    client = site_with(tmp_path, Picker(dtdd, DeviceCap(), random.Random(0)), dtdd)
    body = client.post("/api/pick", json={"tree": "west", "viewer": {"topics": [153]}}).json()
    assert body["film"] is not None
    assert body["unchecked"] == "I couldn't check this one against your list, so have a look before you press play."


def test_the_route_caps_each_device_on_its_own(tmp_path: Path) -> None:
    dtdd = ScriptedDtdd({t: [stat(153, 0, 9)] for t in (1, 2, 3)})
    cap = DeviceCap()
    client = site_with(tmp_path, Picker(dtdd, cap, random.Random(0)), dtdd)
    visit = {"tree": "west", "viewer": {"topics": [153]}}
    for _ in range(LOOKUPS_PER_HOUR):
        assert client.post("/api/pick", json=visit).json()["unchecked"] is None
    assert client.post("/api/pick", json=visit).json()["unchecked"].startswith("I've checked a lot of films")
    other = site_with(tmp_path / "b", Picker(dtdd, cap, random.Random(0)), dtdd)
    assert other.post("/api/pick", json=visit).json()["unchecked"] is None  # another device, its own hour


def test_the_reveal_names_the_first_failed_film(tmp_path: Path) -> None:
    dtdd = ScriptedDtdd({1: [stat(153, 9, 0)], 2: [stat(153, 9, 0)], 3: [stat(153, 0, 9)]})

    client = site_with(tmp_path, Picker(dtdd, DeviceCap(), InOrder()), dtdd)
    body = client.post("/api/pick", json={"tree": "west", "viewer": {"topics": [153]}}).json()
    assert body["film"]["tmdb"] == 3 and body["swapped"]["film"]["tmdb"] == 1
    assert dtdd.looked_up() == [1, 2, 3]


def test_the_hour_is_a_sliding_window() -> None:
    now = [0.0]
    cap = DeviceCap(clock=lambda: now[0])
    for _ in range(LOOKUPS_PER_HOUR - 1):
        cap.take("a")
    now[0] = 1800.0
    cap.take("a")
    now[0] = 3600.0  # the first fifty-nine have just left the window; the one at 1800 has not
    assert cap.take("a")


def test_a_film_with_no_vote_list_or_another_films_record_is_unchecked() -> None:
    class Odd(ScriptedDtdd):
        def get(self, path: str, timeout: float, wait: float) -> Any:
            self.paths.append(path)
            if path.startswith("/items?tmdb=7"):
                return [{"id": 1007, "tmdbId": 7}]
            if path.startswith("/items?tmdb=8"):
                return [{"id": 1099, "tmdbId": 99}]
            if path == "/items/1099":
                return {"topicItemStats": [stat(153, 9, 0)]}  # another film's votes must never be read as this one's
            return {"name": "no votes here"}

    assert look_up(Odd({}), 7, frozenset({153}), ItemIds()).unchecked == "no_record"
    assert look_up(Odd({}), 8, frozenset({153}), ItemIds()).unchecked == "no_record"


class InOrder(random.Random):
    def randrange(self, n: int) -> int:  # type: ignore[override]
        return 0


def test_the_swap_line_names_the_first_topic_hit(tmp_path: Path) -> None:
    two = [stat(153, 9, 0), stat(188, 9, 0)]
    dtdd = ScriptedDtdd({1: two, 2: [stat(153, 0, 9)], 3: [stat(153, 0, 9)]})
    client = site_with(tmp_path, Picker(dtdd, DeviceCap(), InOrder()), dtdd)
    body = client.post("/api/pick", json={"tree": "west", "viewer": {"topics": [153, 188]}}).json()
    assert body["swapped"]["topics"] == ["topic 153", "topic 188"]
    assert body["swapped"]["line"].startswith("Oh, I almost recommended a film where topic 153.")


def test_the_route_honours_the_rating_half(tmp_path: Path) -> None:
    data = write_data(tmp_path / "data")
    write_film_table(tmp_path / "films.sqlite")

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data, reference())

    theatre = Theatre(FakeLibrary(), tmp_path / "films.sqlite", catalog_of=catalog_of)
    config = Config(SECRET_URL, SECRET_KEY, tmp_path, "https://seerr.invalid", "d" * 16)
    dtdd = ScriptedDtdd({})
    picker = Picker(dtdd, DeviceCap(), InOrder())
    client = TestClient(
        create_app(config, theatre, Store(tmp_path / "s.sqlite"), dtdd, clock=lambda: 0.0, picker=picker),
        base_url="https://testserver",
    )
    long = [{"question": "era", "option": 1}, {"question": "gore", "option": 1}]  # "long." asks for the best rated
    assert client.post("/api/pick", json={"tree": "west", "answers": long}).json()["film"]["tmdb"] == 39


def test_just_pick_one_before_any_answer_picks_from_the_viewers_whole_pool(tmp_path: Path) -> None:
    dtdd = ScriptedDtdd({})
    client = site_with(tmp_path, Picker(dtdd, DeviceCap(), random.Random(0)), dtdd)
    picked = {
        client.post("/api/pick", json={"viewer": {"exclusions": ["heroes"]}}).json()["film"]["tmdb"] for _ in range(30)
    }
    assert picked <= {1, 2} and picked  # film 3 carries the "heroes" exclusion
    refused = client.post("/api/pick", json={"answers": [{"question": "era", "option": 0}]})
    assert refused.status_code == 400


def test_a_film_looked_up_again_skips_the_search_for_thirty_days() -> None:
    now = [0.0]
    ids = ItemIds(clock=lambda: now[0])
    dtdd = ScriptedDtdd({1: [stat(153, 0, 9)], 2: None})
    for _ in range(2):
        assert look_up(dtdd, 1, frozenset({153}), ids).hits == ()
        assert look_up(dtdd, 2, frozenset({153}), ids).unchecked == "no_record"
    assert dtdd.paths == ["/items?tmdb=1", "/items/1001", "/items?tmdb=2", "/items/1001"]
    now[0] = ID_KEEP_S
    look_up(dtdd, 1, frozenset({153}), ids)
    assert dtdd.paths[-2:] == ["/items?tmdb=1", "/items/1001"]  # thirty days on, it searches again


def test_a_held_item_is_forgotten_only_when_doesthedogdie_says_it_is_gone() -> None:
    class Detail(ScriptedDtdd):
        def __init__(self, error: DtddError) -> None:
            super().__init__({1: [stat(153, 0, 9)]})
            self.error = error

        def get(self, path: str, timeout: float, wait: float) -> Any:
            if path.startswith("/items/"):
                self.paths.append(path)
                raise self.error
            return super().get(path, timeout, wait)

    for error, kept in [(DtddGone("404"), False), (DtddError("held"), True), (DtddError("HTTP 429"), True)]:
        ids = ItemIds()
        ids.put(1, 1001)
        assert look_up(Detail(error), 1, frozenset({153}), ids).unchecked in {"slow", "no_record"}
        assert ids.get(1) == ((True, 1001) if kept else (False, None))


def test_an_unreadable_search_answer_is_never_remembered() -> None:
    class Odd(ScriptedDtdd):
        def get(self, path: str, timeout: float, wait: float) -> Any:
            self.paths.append(path)
            return {"error": "maintenance"} if path.endswith("=1") else []

    ids = ItemIds()
    assert look_up(Odd({}), 1, frozenset({153}), ids).unchecked == "slow"
    assert ids.get(1) == (False, None)
    assert look_up(Odd({}), 2, frozenset({153}), ids).unchecked == "no_record"
    assert ids.get(2) == (True, None)  # a real "not found" is remembered


def test_the_servers_own_ceiling_shows_the_film_unchecked_for_the_house() -> None:
    dtdd = ScriptedDtdd({1: DtddCeiling("hour spent")})
    result = Picker(dtdd, DeviceCap(), random.Random(0)).pick([1], frozenset({153}), "dev")
    assert result.film == 1 and result.unchecked == "house"


def test_films_in_first_are_drawn_before_the_rest() -> None:
    dtdd = ScriptedDtdd({t: [stat(153, 9, 0)] for t in (1, 2, 3)} | {4: [stat(153, 0, 9)]})
    result = Picker(dtdd, DeviceCap(), InOrder()).pick([1, 2, 3, 4], frozenset({153}), "dev", frozenset({3, 4}))
    assert result.film == 4 and dtdd.looked_up() == [3, 4]


def test_the_route_draws_the_least_gory_third_first_for_a_blood_topic(tmp_path: Path) -> None:
    dtdd = ScriptedDtdd({t: [stat(188, 0, 9)] for t in range(1, 41)})
    data = write_data(tmp_path / "data", gore_cut_tree())
    write_film_table(tmp_path / "films.sqlite")

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data, reference())

    theatre = Theatre(FakeLibrary(), tmp_path / "films.sqlite", catalog_of=catalog_of)  # all forty films
    config = Config(SECRET_URL, SECRET_KEY, tmp_path, "https://seerr.invalid", "d" * 16)
    picker = Picker(dtdd, DeviceCap(), random.Random(0))
    client = TestClient(
        create_app(config, theatre, Store(tmp_path / "s.sqlite"), dtdd, clock=lambda: 0.0, picker=picker),
        base_url="https://testserver",
    )
    visit = {"tree": "west", "answers": [{"question": "era", "option": 1}], "viewer": {"topics": [188]}}
    picked = {client.post("/api/pick", json=visit).json()["film"]["tmdb"] for _ in range(20)}
    assert picked and picked <= set(range(6, 31))  # never the goriest (1-5) or the unscored (31-40) first
