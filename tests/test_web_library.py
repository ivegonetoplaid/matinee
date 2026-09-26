"""The library door: images and synopses through Matinee's own server, and a live film list with no stale fallback."""

from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from matinee.engine import load_catalog
from matinee.library import Image, LibraryError, LibraryFilm
from matinee.library.jellyfin import JellyfinReader
from matinee.reference import ReferenceError
from matinee.table import FilmTable, write_table
from matinee.web.app import create_app
from matinee.web.config import Config, ConfigError, from_env
from matinee.web.theatre import LIVE_TTL, RETRY_AFTER, Theatre
from test_engine import make_table, reference, write_data

SECRET_URL = "http://media.invalid:8096"
SECRET_KEY = "k" * 32


def item(tmdb: int) -> str:
    return f"{tmdb:032x}"


@dataclass
class FakeLibrary:
    held: list[int] = field(default_factory=lambda: [*range(1, 40), 99])
    down: bool = False
    broken: bool = False
    calls: list[tuple[str, Any]] = field(default_factory=list)

    def films(self) -> list[LibraryFilm]:
        self.calls.append(("films", None))
        if self.down:
            raise LibraryError(f"Jellyfin could not be reached at {SECRET_URL}")
        return [
            LibraryFilm(self.item_of(t), t, f"Film {t}", 2000, frozenset({"Western"}), "PG", 90.0, 6.0, None)
            for t in self.held
        ]

    def item_of(self, tmdb: int) -> str:
        """The item id the server reports now; film 5's has changed since the table was built."""
        return "f" * 32 if tmdb == 5 else item(tmdb)

    def synopsis(self, item_id: str) -> str | None:
        self.calls.append(("synopsis", item_id))
        if self.broken:
            raise LibraryError(f"Jellyfin at {SECRET_URL} answered HTTP 500 for /media/Movies/x.mkv")
        return "A stranger rides into town."

    def image(self, item_id: str, kind: str, width: int) -> Image:
        self.calls.append(("image", (item_id, kind, width)))
        if self.broken:
            raise LibraryError(f"Jellyfin at {SECRET_URL} answered HTTP 500 for /media/Movies/x.mkv")
        return Image(b"\xff\xd8jpeg", "image/jpeg")


def write_film_table(path: Path) -> None:
    table = make_table()
    table.films["item_id"] = [item(int(t)) for t in table.films.index]
    write_table(table, path)


@dataclass
class Clock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def world(tmp_path: Path) -> tuple[TestClient, FakeLibrary, Clock, Theatre]:
    data = write_data(tmp_path / "data")
    write_film_table(tmp_path / "films.sqlite")
    library, clock = FakeLibrary(), Clock()

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data, reference())

    theatre = Theatre(library, tmp_path / "films.sqlite", clock=clock, catalog_of=catalog_of)
    config = Config(SECRET_URL, SECRET_KEY, tmp_path, "https://seerr.invalid", "d" * 16)
    return TestClient(create_app(config, theatre)), library, clock, theatre


def test_image_is_served_by_tmdb_id_at_a_fixed_size(world: Any) -> None:
    client, library, _, _ = world
    resp = client.get("/img/poster/5/m")
    assert resp.status_code == 200 and resp.content == b"\xff\xd8jpeg"
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.headers["cache-control"] == "public, max-age=3600"
    assert ("image", ("f" * 32, "poster", 320)) in library.calls  # the live item id, not the table's
    assert client.get("/img/backdrop/6/l").status_code == 200
    assert ("image", (item(6), "backdrop", 1600)) in library.calls


@pytest.mark.parametrize(
    "path", ["/img/poster/5/xl", "/img/logo/5/m", "/img/backdrop/5/s", "/img/poster/40/m", "/img/poster/12345/m"]
)
def test_other_image_requests_are_refused_without_an_outbound_call(world: Any, path: str) -> None:
    client, library, _, _ = world
    assert client.get(path).status_code == 404
    assert not [c for c in library.calls if c[0] == "image"]


def test_film_card_reads_the_synopsis_live(world: Any) -> None:
    client, library, _, _ = world
    card = client.get("/api/film/5").json()
    assert card == {
        "tmdb": 5,
        "title": "Film 5",
        "year": 1975,
        "runtime_min": 85,
        "synopsis": "A stranger rides into town.",
    }
    assert ("synopsis", "f" * 32) in library.calls
    assert client.get("/api/film/40").status_code == 404  # gone from the library: never offered


def test_a_film_new_to_the_library_is_offered_by_its_tags(world: Any) -> None:
    client, _, _, theatre = world
    films = theatre.showing().catalog.table
    assert 99 in films.films.index and 40 not in films.films.index
    assert np.isnan(films.tag("p_fast")[99])
    assert client.get("/api/film/99").json()["title"] == "Film 99"


def test_an_unreachable_library_serves_nothing_stale(world: Any) -> None:
    client, library, clock, _ = world
    assert client.get("/api/film/5").status_code == 200
    library.down = True
    clock.now += LIVE_TTL + 1
    for path in ("/api/film/5", "/img/poster/5/m"):
        resp = client.get(path)
        assert resp.status_code == 503
        assert resp.json() == {"error": "library_unreachable", "message": "I can't reach the film library right now."}
        assert "media.invalid" not in resp.text
    reads = len([c for c in library.calls if c[0] == "films"])
    library.down = False
    assert client.get("/api/film/5").status_code == 503  # still inside the hold-off: no new read
    assert len([c for c in library.calls if c[0] == "films"]) == reads
    clock.now += RETRY_AFTER + 1
    assert client.get("/api/film/5").status_code == 200


def test_the_film_list_is_reread_only_after_its_time(world: Any) -> None:
    client, library, clock, _ = world
    client.get("/api/film/5")
    client.get("/api/film/6")
    assert [c for c in library.calls if c[0] == "films"] == [("films", None)]
    clock.now += LIVE_TTL + 1
    client.get("/api/film/5")
    assert len([c for c in library.calls if c[0] == "films"]) == 2


def test_a_replaced_film_table_is_reloaded(world: Any, tmp_path: Path) -> None:
    client, _, _, _ = world
    assert client.get("/api/film/6").json()["title"] == "Film 6"
    table = make_table()
    table.films["item_id"] = [item(int(t)) for t in table.films.index]
    table.films.loc[6, "name"] = "Renamed"
    write_table(table, tmp_path / "films.sqlite")
    stat = (tmp_path / "films.sqlite").stat()
    os.utime(tmp_path / "films.sqlite", (stat.st_atime, stat.st_mtime + 5))
    assert client.get("/api/film/6").json()["title"] == "Renamed"


def test_no_response_carries_the_server_address_or_key(world: Any) -> None:
    client, _, _, _ = world
    for path in ("/api/film/5", "/img/poster/5/m", "/api/film/12345", "/docs", "/openapi.json"):
        resp = client.get(path)
        assert SECRET_URL not in resp.text and SECRET_KEY not in resp.text
        assert all(SECRET_KEY not in v and "media.invalid" not in v for v in resp.headers.values())
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404


class _Resp:
    def __init__(self, content_type: str = "image/jpeg", body: bytes = b"img") -> None:
        self.headers = {"Content-Type": content_type}
        self.body = body

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, n: int) -> bytes:
        return self.body[:n]


def test_the_jellyfin_image_request_carries_no_key_and_refuses_odd_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[urllib.request.Request] = []

    def fake_urlopen(req: urllib.request.Request, timeout: float) -> _Resp:
        sent.append(req)
        return _Resp()

    monkeypatch.setattr("matinee.library.jellyfin.urllib.request.urlopen", fake_urlopen)
    reader = JellyfinReader(SECRET_URL, SECRET_KEY)
    assert reader.image(item(5), "backdrop", 960).body == b"img"
    assert sent[0].get_method() == "GET"
    assert sent[0].full_url == f"{SECRET_URL}/Items/{item(5)}/Images/Backdrop/0?maxWidth=960&quality=80"
    assert not {k.lower() for k in sent[0].headers} & {"x-emby-token", "authorization"}
    for bad in ("../../System", "5", item(5) + "/x"):
        with pytest.raises(LibraryError):
            reader.image(bad, "poster", 320)
    assert len(sent) == 1


def test_config_refuses_missing_settings_and_a_missing_state_dir(tmp_path: Path) -> None:
    env = {
        "MATINEE_STATE": str(tmp_path),
        "MATINEE_JELLYFIN_URL": SECRET_URL,
        "JELLYFIN_API_KEY": SECRET_KEY,
        "MATINEE_SEERR_URL": "https://seerr.invalid/",
        "DTDD_API_KEY": "d",
    }
    assert from_env(env).seerr_url == "https://seerr.invalid"
    with pytest.raises(ConfigError, match="JELLYFIN_API_KEY"):
        from_env({**env, "JELLYFIN_API_KEY": " "})
    with pytest.raises(ConfigError, match="does not exist"):
        from_env({**env, "MATINEE_STATE": str(tmp_path / "nope")})


def test_media_server_errors_never_reach_the_browser(world: Any) -> None:
    client, library, _, _ = world
    library.broken = True
    img = client.get("/img/poster/6/m")
    assert img.status_code == 404
    assert img.json() == {"error": "not_found", "message": "I don't have that one."}
    card = client.get("/api/film/6")
    assert card.status_code == 503 and card.json()["error"] == "library_unreachable"
    for resp in (img, card):
        assert "media.invalid" not in resp.text and "/media/" not in resp.text and "500" not in resp.text


def test_a_table_that_ages_past_six_months_stops_being_served(world: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _, theatre = world
    assert client.get("/api/film/6").status_code == 200
    aged = replace(theatre._table, oldest_tmdb=datetime.now(UTC) - timedelta(days=184))
    monkeypatch.setattr(theatre, "_table", aged)
    resp = client.get("/api/film/6")
    assert resp.status_code == 503 and resp.json()["error"] == "not_ready"


def test_start_up_refuses_missing_reference_statistics(tmp_path: Path) -> None:
    data = write_data(tmp_path / "data")
    write_film_table(tmp_path / "films.sqlite")

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data)  # no reference.json in this data directory

    with pytest.raises(ReferenceError):
        Theatre(FakeLibrary(), tmp_path / "films.sqlite", catalog_of=catalog_of)


def test_config_does_not_print_its_keys() -> None:
    text = repr(Config(SECRET_URL, SECRET_KEY, Path("/state"), "https://seerr.invalid", "d" * 16))
    assert SECRET_KEY not in text and "d" * 16 not in text


def test_the_jellyfin_reader_refuses_odd_answers_and_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = [_Resp("text/html", b"<html>login</html>"), _Resp("image/jpeg", b"x" * (8 * 1024 * 1024 + 1))]
    monkeypatch.setattr("matinee.library.jellyfin.urllib.request.urlopen", lambda req, timeout: answers.pop(0))
    reader = JellyfinReader(SECRET_URL, SECRET_KEY)
    for _ in range(2):
        with pytest.raises(LibraryError):
            reader.image(item(5), "poster", 320)
    with pytest.raises(LibraryError):
        reader.synopsis("../Users")
