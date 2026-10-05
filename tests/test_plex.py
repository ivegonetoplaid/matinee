"""The Plex reader: what it reads from Plex's answers, and that it only ever sends GETs with the token in a header."""

from __future__ import annotations

import io
import json
import logging
import urllib.error
import urllib.request
from typing import Any

import pytest

from matinee.library import LibraryError
from matinee.library.plex import PlexReader, certificate, parse_film
from matinee.pools import kids_band

URL, TOKEN = "http://plex.invalid:32400", "secret-plex-token"

ITEM: dict[str, Any] = {
    "ratingKey": "390193",
    "title": "The Naked Gun",
    "year": 1988,
    "contentRating": "gb/15",
    "duration": 5_100_000,
    "audienceRating": 7.3,
    "rating": 6.1,
    "Guid": [{"id": "imdb://tt0095705"}, {"id": "tmdb://37136"}],
    "Genre": [{"tag": "Comedy"}, {"tag": "Crime"}],
    "Media": [{"Part": [{"file": "/films/The Naked Gun (1988) {tmdb-37136}/film.mkv"}]}],
}


class Resp(io.BytesIO):
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        super().__init__(body)
        self.headers = {"Content-Type": content_type}

    def __enter__(self) -> Resp:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class Plex:
    """A fake Plex answering by path, recording every request."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.sent: list[urllib.request.Request] = []

    def __call__(self, req: urllib.request.Request, timeout: float) -> Resp:
        self.sent.append(req)
        path = req.full_url.removeprefix(URL)
        answer = self.answers.get(path.split("?")[0] if path.startswith("/photo") else path)
        if answer is None:
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)  # type: ignore[arg-type]
        if isinstance(answer, bytes):
            return Resp(answer, "image/jpeg")
        return Resp(json.dumps(answer).encode())


SECTIONS = {
    "/library/sections": {
        "MediaContainer": {
            "Directory": [{"key": "1", "type": "movie"}, {"key": "2", "type": "show"}, {"key": "3", "type": "movie"}]
        }
    },
    "/library/sections/1/all?type=1&includeGuids=1": {"MediaContainer": {"Metadata": [ITEM, {**ITEM, "Guid": []}]}},
    "/library/sections/3/all?type=1&includeGuids=1": {
        "MediaContainer": {"Metadata": [{**ITEM, "ratingKey": "8", "Guid": [{"id": "tmdb://578"}]}]}
    },
}


def reader(monkeypatch: pytest.MonkeyPatch, answers: dict[str, Any]) -> tuple[PlexReader, Plex]:
    plex = Plex(answers)
    monkeypatch.setattr("matinee.library.plex.urllib.request.urlopen", plex)
    return PlexReader(URL, TOKEN), plex


def test_a_plex_movie_reads_as_a_library_film() -> None:
    film = parse_film(ITEM)
    assert (film.item_id, film.tmdb, film.name, film.year) == ("390193", 37136, "The Naked Gun", 1988)
    assert film.genres == frozenset({"Comedy", "Crime"}) and film.certificate == "gb/15"
    assert film.runtime_min == pytest.approx(85.0) and film.rating == 7.3 and film.path_tmdb == 37136
    assert parse_film({**ITEM, "audienceRating": None}).rating == 6.1
    bare = parse_film({"ratingKey": "7"})
    assert (bare.tmdb, bare.name, bare.year, bare.genres, bare.certificate, bare.runtime_min) == (
        None,
        "",
        None,
        frozenset(),
        "",
        None,
    )


@pytest.mark.parametrize(
    ("raw", "read"),
    [("us/PG-13", "PG-13"), ("PG", "PG"), (None, ""), ("Not Rated", "Not Rated"), ("gb/U", "gb/U"), ("au/E", "au/E")],
)
def test_only_a_us_prefix_is_dropped(raw: str | None, read: str) -> None:
    assert certificate(raw) == read


def test_a_rating_from_another_countrys_system_never_passes_the_kids_gate_by_its_name() -> None:
    assert kids_band("family", certificate("au/E")) is None and kids_band("family", certificate("gb/PG")) is None
    assert kids_band("family", certificate("us/PG")) == "family" == kids_band("family", certificate("PG"))


def test_a_legacy_tmdb_agent_guid_names_the_film_and_nothing_else_does() -> None:
    legacy = {**ITEM, "Guid": [], "guid": "com.plexapp.agents.themoviedb://37136?lang=en"}
    assert parse_film(legacy).tmdb == 37136
    for other in (
        "com.plexapp.agents.imdb://tt0095705?lang=en",
        "plex://movie/5d776b59ad5437001f79c6f8",
        "local://2367",
    ):
        assert parse_film({**ITEM, "Guid": [{"id": "imdb://tt0095705"}], "guid": other}).tmdb is None


@pytest.mark.parametrize("key", [None, 5, "", "12a", "../1"])
def test_a_movie_without_a_usable_rating_key_is_refused(key: object) -> None:
    with pytest.raises(LibraryError):
        parse_film({**ITEM, "ratingKey": key})


def test_films_come_from_every_movie_section_by_get_with_the_token_in_a_header(monkeypatch: pytest.MonkeyPatch) -> None:
    plex_reader, plex = reader(monkeypatch, SECTIONS)
    films = plex_reader.films()
    assert [f.tmdb for f in films] == [37136, None, 578]  # both movie sections, never the show section
    assert [r.full_url.removeprefix(URL) for r in plex.sent] == list(SECTIONS)
    for req in plex.sent:
        assert req.get_method() == "GET" and TOKEN not in req.full_url
        assert req.unredirected_hdrs["X-plex-token"] == TOKEN and "X-plex-token" not in req.headers


def test_synopsis_and_pictures(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = {
        "/library/metadata/390193": {"MediaContainer": {"Metadata": [{"summary": "Drebin again."}]}},
        "/library/metadata/7": {"MediaContainer": {"Metadata": [{"summary": " "}]}},
        "/photo/:/transcode": b"jpeg",
    }
    plex_reader, plex = reader(monkeypatch, answers)
    assert plex_reader.synopsis("390193") == "Drebin again." and plex_reader.synopsis("7") is None
    assert plex_reader.image("390193", "poster", 160).body == b"jpeg"
    assert plex.sent[-1].full_url.endswith(
        "/photo/:/transcode?width=160&height=240&minSize=1&upscale=1&quality=60&url=/library/metadata/390193/thumb"
    )
    plex_reader.image("390193", "backdrop", 960)
    assert plex.sent[-1].full_url.endswith(
        "width=960&height=540&minSize=1&upscale=1&quality=80&url=/library/metadata/390193/art"
    )
    for bad in ("../../System", "abc", "1/x"):
        with pytest.raises(LibraryError):
            plex_reader.image(bad, "poster", 320)
        with pytest.raises(LibraryError):
            plex_reader.synopsis(bad)
    assert all(r.get_method() == "GET" for r in plex.sent)


def test_failures_are_library_errors_that_never_carry_the_token(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    plex_reader, _ = reader(monkeypatch, {})
    with caplog.at_level(logging.DEBUG), pytest.raises(LibraryError) as refused:
        plex_reader.films()
    assert TOKEN not in str(refused.value) and TOKEN not in caplog.text

    def unreachable(req: urllib.request.Request, timeout: float) -> Resp:
        raise urllib.error.URLError(f"no route to {req.full_url}")

    monkeypatch.setattr("matinee.library.plex.urllib.request.urlopen", unreachable)
    with pytest.raises(LibraryError) as down:
        plex_reader.synopsis("7")
    assert TOKEN not in str(down.value)
    with pytest.raises(LibraryError):
        PlexReader(URL, "")
    with pytest.raises(LibraryError, match="http"):
        PlexReader("file:///etc", TOKEN)


def test_an_answer_that_is_not_a_film_list_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    plex_reader, _ = reader(monkeypatch, {"/library/sections": ["not", "a", "container"]})
    with pytest.raises(LibraryError, match="MediaContainer"):
        plex_reader.films()
