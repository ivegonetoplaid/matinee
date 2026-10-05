"""The library door: images and synopses through Matinee's own server, and a live film list with no stale fallback."""

from __future__ import annotations

import contextlib
import io
import itertools
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from matinee.dtdd import Dtdd
from matinee.engine import load_catalog
from matinee.library import Image, LibraryError, LibraryFilm
from matinee.library.choice import MediaServer
from matinee.library.jellyfin import JellyfinReader
from matinee.store import Store
from matinee.table import FilmTable, write_table
from matinee.web.app import IMAGE_CACHE, STATIC, TMDB_IMAGE_CACHE, create_app
from matinee.web.config import Config, ConfigError, ImageSource, from_env
from matinee.web.seerr import SeerrCheck
from matinee.web.theatre import LIVE_TTL, RETRY_AFTER, Theatre
from test_engine import make_table, reference, write_data

SECRET_URL = "http://media.invalid:8096"
SECRET_KEY = "k" * 32
SERVER = MediaServer("jellyfin", SECRET_URL, SECRET_KEY)


_names = itertools.count(1)


def seat_for(client: TestClient, topics: list[int] | None = None) -> dict[str, int]:
    """A new profile held by this client's device, with these topics, as a request's viewer."""
    body = {"name": f"Viewer {next(_names)}", "topics": topics or []}
    made = client.post("/api/profiles", json=body)
    assert made.status_code == 200, made.text
    return {"profile_id": made.json()["id"]}


def item(tmdb: int) -> str:
    return f"{tmdb:032x}"


@dataclass
class FakeLibrary:
    held: list[int] = field(default_factory=lambda: [*range(1, 40), 99])
    down: bool = False
    broken: bool = False
    no_synopsis: bool = False
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
        if self.no_synopsis:
            return None
        if self.broken:
            raise LibraryError(f"Jellyfin at {SECRET_URL} answered HTTP 500 for /media/Movies/x.mkv")
        return "A stranger rides into town."

    def image(self, item_id: str, kind: str, width: int) -> Image:
        self.calls.append(("image", (item_id, kind, width)))
        if self.broken:
            raise LibraryError(f"Jellyfin at {SECRET_URL} answered HTTP 500 for /media/Movies/x.mkv")
        return Image(b"\xff\xd8jpeg", "image/jpeg")


def film_table() -> FilmTable:
    """The engine's films with their media-server items; film 5 alone has TMDB pictures."""
    table = make_table()
    table.films["item_id"] = [item(int(t)) for t in table.films.index]
    table.films["poster_path"] = ["/p5.jpg" if t == 5 else None for t in table.films.index]
    table.films["backdrop_path"] = ["/b5.jpg" if t == 5 else None for t in table.films.index]
    return table


def write_film_table(path: Path) -> None:
    write_table(film_table(), path)


@dataclass
class Clock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def world(tmp_path: Path) -> tuple[TestClient, FakeLibrary, Clock, Theatre]:
    return make_world(tmp_path)


def make_world(
    tmp_path: Path,
    images: ImageSource = "server",
    seerr: str | None = "https://seerr.invalid",
    listed: frozenset[int] = frozenset(),
) -> tuple[TestClient, FakeLibrary, Clock, Theatre]:
    data = write_data(tmp_path / "data")
    stored = film_table()
    stored.films["tmdb_title"] = [f"TMDB {t}" for t in stored.films.index]  # every film has a TMDB record
    stored.films["synopsis"] = [f"TMDB says {t}." for t in stored.films.index]
    write_table(stored, tmp_path / "films.sqlite")
    library, clock = FakeLibrary(), Clock()

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data, reference())

    theatre = Theatre(library, tmp_path / "films.sqlite", clock=clock, catalog_of=catalog_of, listed=listed)
    config = Config(SERVER, tmp_path, seerr, "d" * 16, images=images)
    app = create_app(
        config, theatre, Store(tmp_path / "store.sqlite"), Dtdd("k"), seerr=SeerrCheck(seerr, opener=answers)
    )
    return TestClient(app), library, clock, theatre


def answers(req: Any, timeout: float) -> Any:
    """A Seerr that answers its status page."""
    return contextlib.nullcontext()


def test_image_is_served_by_tmdb_id_at_a_fixed_size(world: Any) -> None:
    client, library, _, _ = world
    resp = client.get("/img/poster/5/m")
    assert resp.status_code == 200 and resp.content == b"\xff\xd8jpeg"
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.headers["cache-control"] == "private, max-age=2592000"  # never kept by a shared cache
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
        "link": "https://seerr.invalid/movie/5",
        "link_to": "seerr",
        "backdrop_path": None,  # the media server is the image source
    }
    assert ("synopsis", "f" * 32) in library.calls
    assert client.get("/api/film/40").status_code == 404  # gone from the library: never offered


def test_a_film_new_to_the_library_is_offered_by_its_tags(world: Any) -> None:
    client, _, _, theatre = world
    films = theatre.showing().catalog.table
    assert 99 in films.films.index and 40 not in films.films.index
    assert np.isnan(films.tag("p_fast")[99])
    assert client.get("/api/film/99").json()["title"] == "Film 99"


def test_an_unreachable_library_holds_no_film_and_says_so(world: Any) -> None:
    client, library, clock, _ = world
    assert client.get("/api/film/5").status_code == 200
    assert client.get("/api/setup").json()["lines"] == []
    library.down = True
    clock.now += LIVE_TTL + 1
    for path in ("/api/film/5", "/img/poster/5/m"):
        resp = client.get(path)
        assert resp.status_code == 404  # no film is held, and the labels name none here
        assert "media.invalid" not in resp.text
    note = client.get("/api/setup").json()
    assert note["lines"][0].startswith("I can't reach your Jellyfin right now.") and not note["go_on"]
    assert client.get("/api/door").status_code == 200  # the site still answers
    reads = len([c for c in library.calls if c[0] == "films"])
    library.down = False
    assert client.get("/api/film/5").status_code == 404  # still inside the hold-off: no new read
    assert len([c for c in library.calls if c[0] == "films"]) == reads
    clock.now += RETRY_AFTER + 1
    assert client.get("/api/film/5").status_code == 200
    assert client.get("/api/setup").json()["lines"] == []  # the note goes without a restart


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
    table = film_table()
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
    reader.image(item(5), "poster", 160)
    assert sent[1].full_url.endswith("/Images/Primary?maxWidth=160&quality=60")
    for bad in ("../../System", "5", item(5) + "/x"):
        with pytest.raises(LibraryError):
            reader.image(bad, "poster", 320)
    assert len(sent) == 2


def test_config_refuses_missing_settings_and_a_missing_state_dir(tmp_path: Path) -> None:
    env = {
        "DATA_DIR": str(tmp_path),
        "JELLYFIN_URL": SECRET_URL,
        "JELLYFIN_API_KEY": SECRET_KEY,
        "SEERR_URL": "https://seerr.invalid/",
        "DTDD_API_KEY": "d",
    }
    assert from_env(env).seerr_url == "https://seerr.invalid"
    half = from_env({**env, "JELLYFIN_API_KEY": " "})
    assert half.server is None and "JELLYFIN_API_KEY" in half.faults[0]
    with pytest.raises(ConfigError, match="DATA_DIR"):
        from_env({k: v for k, v in env.items() if k != "DATA_DIR"})
    with pytest.raises(ConfigError, match="does not exist"):
        from_env({**env, "DATA_DIR": str(tmp_path / "nope")})
    assert from_env(env).server == MediaServer("jellyfin", SECRET_URL, SECRET_KEY)
    plex = {**env, "JELLYFIN_URL": "", "JELLYFIN_API_KEY": "", "PLEX_URL": "http://plex.invalid/", "PLEX_TOKEN": "t"}
    assert from_env(plex).server == MediaServer("plex", "http://plex.invalid", "t")
    both = from_env({**env, "PLEX_URL": "http://plex.invalid", "PLEX_TOKEN": "t"})
    assert both.server is None and both.server_unusable and "both Jellyfin and Plex" in both.faults[0]
    none = from_env({**env, "JELLYFIN_URL": "", "JELLYFIN_API_KEY": ""})
    assert none.server is None and not none.server_unusable and none.faults == ()  # no library is no fault
    odd = from_env({**env, "JELLYFIN_URL": "file:///etc"})
    assert odd.server is None and "http" in odd.faults[0]
    bad_seerr = from_env({**env, "SEERR_URL": "seerr.lan"})
    assert bad_seerr.seerr_url is None and "SEERR_URL" in bad_seerr.faults[0]
    for old in ("MATINEE_STATE", "MATINEE_JELLYFIN_URL", "MATINEE_IMAGES", "MATINEE_SEERR_URL"):  # never read
        assert from_env({**env, old: "/elsewhere"}) == from_env(env)


def test_the_image_source_is_the_media_server_unless_tmdb_is_named(tmp_path: Path) -> None:
    env = {
        "DATA_DIR": str(tmp_path),
        "JELLYFIN_URL": SECRET_URL,
        "JELLYFIN_API_KEY": SECRET_KEY,
        "SEERR_URL": "https://seerr.invalid/",
        "DTDD_API_KEY": "d",
    }
    assert from_env(env).images == "server"
    assert from_env({**env, "POSTERS_FROM": " "}).images == "server"
    assert from_env({**env, "POSTERS_FROM": "tmdb"}).images == "tmdb"
    odd = from_env({**env, "POSTERS_FROM": "TMDB"})
    assert odd.images == "server" and "POSTERS_FROM" in odd.faults[0]


def test_the_media_server_as_source_gives_no_tmdb_paths(world: Any) -> None:
    client, _, _, _ = world
    assert client.get("/api/pictures").json() == {"source": "server", "posters": {}}
    assert client.get("/api/film/5").json()["backdrop_path"] is None
    assert "img-src 'self';" in client.get("/").headers["content-security-policy"]


def test_tmdb_as_source_gives_each_live_film_its_tmdb_paths(tmp_path: Path) -> None:
    client, library, clock, _ = make_world(tmp_path, "tmdb")
    assert client.get("/api/pictures").json() == {"source": "tmdb", "posters": {"5": "/p5.jpg"}}
    assert client.get("/api/film/5").json()["backdrop_path"] == "/b5.jpg"
    assert client.get("/api/film/6").json()["backdrop_path"] is None  # it keeps Matinee's image route
    assert client.get("/img/poster/6/m").status_code == 200
    library.held = [t for t in library.held if t != 5]
    clock.now += LIVE_TTL + 1
    assert client.get("/api/pictures").json()["posters"] == {}  # a film gone from the library is never named
    policy = client.get("/").headers["content-security-policy"]
    assert "img-src 'self' https://image.tmdb.org;" in policy and "default-src 'self';" in policy


def test_media_server_errors_never_reach_the_browser(world: Any) -> None:
    client, library, _, _ = world
    library.broken = True
    img = client.get("/img/poster/6/m")
    assert img.status_code == 404
    assert img.json() == {"error": "not_found", "message": "I don't have that one."}
    card = client.get("/api/film/6")
    assert card.status_code == 200 and card.json()["synopsis"] == "TMDB says 6."  # TMDB's, when the server fails
    for resp in (img, card):
        assert "media.invalid" not in resp.text and "/media/" not in resp.text and "500" not in resp.text


def test_a_table_past_six_months_still_serves_and_warns_until_it_is_fresh(
    world: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from matinee.web.setup import STALE

    client, _, _, theatre = world
    fresh = theatre._table
    assert client.get("/api/setup").json()["warning"] is None
    monkeypatch.setattr(theatre, "_table", replace(fresh, oldest_tmdb=datetime.now(UTC) - timedelta(days=184)))
    with caplog.at_level(logging.ERROR, logger="matinee.theatre"):
        assert client.get("/api/film/6").status_code == 200  # picks go on
        note = client.get("/api/setup").json()
    assert note["warning"] == STALE and "rebuild_table.py" in STALE and note["lines"] == []
    assert sum("over six months ago" in r.getMessage() for r in caplog.records) == 1  # said once, not per request
    monkeypatch.setattr(theatre, "_table", fresh)  # a rebuild refreshed the facts
    assert client.get("/api/setup").json()["warning"] is None


def test_start_up_refuses_missing_reference_statistics(tmp_path: Path) -> None:
    data = write_data(tmp_path / "data")
    write_film_table(tmp_path / "films.sqlite")

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data)  # no reference.json in this data directory

    theatre = Theatre(FakeLibrary(), tmp_path / "films.sqlite", catalog_of=catalog_of)
    assert theatre.broken is not None and "reference" in theatre.broken
    config = Config(SERVER, tmp_path, None, None)
    client = TestClient(create_app(config, theatre, Store(tmp_path / "s.sqlite"), None), base_url="https://testserver")
    note = client.get("/api/setup").json()
    assert note["films"] == 0 and not note["go_on"] and "Matinee's own files" in note["lines"][-1]
    assert client.post("/api/first", json={}).status_code == 503


def test_config_does_not_print_its_keys() -> None:
    text = repr(Config(SERVER, Path("/state"), "https://seerr.invalid", "d" * 16))
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


def test_every_response_carries_the_security_headers(world: Any) -> None:
    client, _, _, _ = world
    for path in ("/", "/static/css/matinee.css", "/img/poster/5/m", "/api/film/5", "/api/film/12345", "/img/logo/5/m"):
        resp = client.get(path)
        assert resp.headers["x-robots-tag"] == "noindex", path
        policy = resp.headers["content-security-policy"]
        assert "default-src 'self'" in policy and "frame-ancestors 'none'" in policy and "unsafe-inline" not in policy
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["referrer-policy"] == "same-origin"
    assert client.get("/").headers["content-type"].startswith("text/html")
    invalid = client.post("/api/walk", json={"tree": "x" * 41, "viewer": seat_for(client)})
    assert invalid.status_code == 422 and invalid.headers["x-robots-tag"] == "noindex"


def test_no_robots_file_blocks_crawling_the_header(world: Any) -> None:
    client, _, _, _ = world
    assert client.get("/robots.txt").status_code == 404


def test_the_page_and_its_static_files_revalidate_so_a_deploy_is_never_half_seen(world: Any) -> None:
    client, _, _, _ = world
    for path in ("/", "/static/css/matinee.css", "/static/js/main.js"):
        assert client.get(path).headers["cache-control"] == "no-cache", path


def test_no_api_reply_may_be_stored_since_the_door_depends_on_the_device(world: Any) -> None:
    client, _, _, _ = world
    for path in ("/api/door", "/api/film/5", "/api/quips", "/api/film/12345"):
        assert client.get(path).headers["cache-control"] == "no-store", path


def test_the_install_manifest_names_icons_that_exist() -> None:
    manifest = json.loads((STATIC / "manifest.webmanifest").read_text())
    assert manifest["start_url"] == "/" and manifest["icons"]
    for icon in manifest["icons"]:
        assert (STATIC / icon["src"].removeprefix("/static/")).is_file(), icon["src"]


def test_without_seerr_every_pick_links_to_its_tmdb_page(tmp_path: Path) -> None:
    client, _, _, _ = make_world(tmp_path, seerr=None)
    card = client.get("/api/film/5").json()
    assert (card["link"], card["link_to"]) == ("https://www.themoviedb.org/movie/5", "tmdb")


def test_now_showing_counts_the_films_the_labels_name_beside_the_library(tmp_path: Path) -> None:
    data = write_data(tmp_path / "data")
    stored = film_table()
    world = int(stored.films.index[-1])
    stored.films["tmdb_title"] = stored.films["tmdb_title"].astype(object)
    stored.films.loc[world, "tmdb_title"] = "World film"
    write_table(stored, tmp_path / "films.sqlite")
    library = FakeLibrary(held=[t for t in range(1, 40) if t != world])
    theatre = Theatre(
        library,
        tmp_path / "films.sqlite",
        catalog_of=lambda t: load_catalog(t, data, reference()),
        listed=frozenset({world}),
    )
    showing = theatre.showing()
    assert showing.now_showing == len(library.held) + 1
    assert not showing.catalog.table.films.loc[world, "held"]


def test_a_reloaded_table_does_not_rush_a_library_that_just_failed(world: Any, tmp_path: Path) -> None:
    client, library, clock, _ = world
    library.down = True
    clock.now += LIVE_TTL + 1
    client.get("/api/door")
    reads = len([c for c in library.calls if c[0] == "films"])
    later = time.time() + 5
    write_film_table(tmp_path / "films.sqlite")
    os.utime(tmp_path / "films.sqlite", (later, later))  # the rebuild replaced the table meanwhile
    client.get("/api/door")
    assert len([c for c in library.calls if c[0] == "films"]) == reads  # still inside the hold-off


def test_a_film_the_library_does_not_hold_shows_tmdb_pictures_through_matinee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetched: list[tuple[str, str, int]] = []

    def tmdb_picture(path: str, kind: str, width: int) -> tuple[bytes, str]:
        fetched.append((path, kind, width))
        return b"tmdb-jpeg", "image/jpeg"

    monkeypatch.setattr("matinee.web.app.fetch_picture", tmdb_picture)
    client, library, clock, _ = make_world(tmp_path, listed=frozenset({5}))
    library.held = [t for t in library.held if t != 5]  # sold since the rebuild; the labels still name it
    poster = client.get("/img/poster/5/m")
    assert poster.status_code == 200 and poster.content == b"tmdb-jpeg"
    assert poster.headers["cache-control"] == TMDB_IMAGE_CACHE and fetched == [("/p5.jpg", "poster", 320)]
    assert TMDB_IMAGE_CACHE.startswith("private, max-age=") and TMDB_IMAGE_CACHE != IMAGE_CACHE
    assert client.get("/img/backdrop/5/l").status_code == 200 and fetched[-1] == ("/b5.jpg", "backdrop", 1600)
    assert not [c for c in library.calls if c[0] == "image"]
    card = client.get("/api/film/5").json()
    assert card["synopsis"] == "TMDB says 5." and card["title"] == "TMDB 5"
    assert client.get("/img/poster/6/m").status_code == 200 and ("image", (item(6), "poster", 320)) in library.calls


def test_while_the_library_cannot_be_used_every_picture_and_synopsis_comes_from_tmdb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("matinee.web.app.fetch_picture", lambda path, kind, width: (b"tmdb-jpeg", "image/jpeg"))
    client, library, clock, _ = make_world(tmp_path, listed=frozenset({5, 6}))
    library.down = True
    clock.now += LIVE_TTL + 1
    assert client.get("/img/poster/5/m").content == b"tmdb-jpeg"
    assert client.get("/img/poster/6/m").status_code == 404  # TMDB has no poster for film 6
    card = client.get("/api/film/6")
    assert card.status_code == 200 and card.json()["synopsis"] == "TMDB says 6."
    library.down = False
    clock.now += RETRY_AFTER + 1
    assert client.get("/api/film/6").json()["synopsis"] == "A stranger rides into town."  # the library's again


def test_under_tmdb_the_page_reads_paths_for_films_the_library_does_not_hold(tmp_path: Path) -> None:
    client, library, _, _ = make_world(tmp_path, images="tmdb", listed=frozenset({5}))
    library.held = [t for t in library.held if t != 5]
    assert client.get("/api/pictures").json()["posters"] == {"5": "/p5.jpg"}
    assert client.get("/api/film/5").json()["backdrop_path"] == "/b5.jpg"


def test_a_tmdb_picture_is_fetched_by_a_get_at_the_mapped_size_and_checked() -> None:
    from matinee.tmdb import TmdbImageError, fetch_picture

    sent: list[urllib.request.Request] = []

    class Answer(io.BytesIO):
        def __init__(self, body: bytes, kind: str) -> None:
            super().__init__(body)
            self.headers = {"Content-Type": kind}

        def __enter__(self) -> Answer:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    def jpeg(req: urllib.request.Request, timeout: float) -> Answer:
        sent.append(req)
        return Answer(b"jpeg", "image/jpeg")

    assert fetch_picture("/p5.jpg", "poster", 160, opener=jpeg) == (b"jpeg", "image/jpeg")
    assert sent[0].full_url == "https://image.tmdb.org/t/p/w154/p5.jpg" and sent[0].get_method() == "GET"
    for bad in ("../x.jpg", "/p5.jpg?x=1", "http://elsewhere/p.jpg"):
        with pytest.raises(TmdbImageError):
            fetch_picture(bad, "poster", 160, opener=jpeg)
    assert len(sent) == 1
    with pytest.raises(TmdbImageError):
        fetch_picture("/p5.jpg", "poster", 160, opener=lambda req, timeout: Answer(b"<html>", "text/html"))


def test_a_picture_or_synopsis_the_media_server_cannot_give_comes_from_tmdb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from matinee.tmdb import TmdbImageError

    fetched: list[str] = []

    def tmdb_picture(path: str, kind: str, width: int) -> tuple[bytes, str]:
        fetched.append(path)
        return b"tmdb-jpeg", "image/jpeg"

    monkeypatch.setattr("matinee.web.app.fetch_picture", tmdb_picture)
    client, library, _, _ = make_world(tmp_path)
    ok = client.get("/img/poster/5/m")
    assert ok.content == b"\xff\xd8jpeg" and ok.headers["cache-control"] == IMAGE_CACHE and fetched == []
    library.broken = True
    stand_in = client.get("/img/poster/5/m")
    assert stand_in.content == b"tmdb-jpeg" and stand_in.headers["cache-control"] == TMDB_IMAGE_CACHE
    assert client.get("/img/poster/6/m").status_code == 404  # no TMDB path either
    library.broken = False
    library.no_synopsis = True
    assert client.get("/api/film/6").json()["synopsis"] == "TMDB says 6."

    def tmdb_down(path: str, kind: str, width: int) -> tuple[bytes, str]:
        raise TmdbImageError("no answer")

    monkeypatch.setattr("matinee.web.app.fetch_picture", tmdb_down)
    library.broken = True
    assert client.get("/img/poster/5/m").status_code == 404


@pytest.mark.parametrize(
    ("kind", "width", "size"),
    [("poster", 100, "w92"), ("poster", 160, "w154"), ("poster", 320, "w342"), ("poster", 640, "w780"),
     ("backdrop", 960, "w780"), ("backdrop", 1600, "w1280")],
)  # fmt: skip
def test_each_width_asks_tmdb_for_its_size(kind: str, width: int, size: str) -> None:
    from matinee.tmdb import fetch_picture

    sent: list[str] = []

    def jpeg(req: urllib.request.Request, timeout: float) -> Any:
        sent.append(req.full_url)
        return _Picture(b"jpeg", "image/jpeg")

    fetch_picture("/p.jpg", kind, width, opener=jpeg)
    assert sent == [f"https://image.tmdb.org/t/p/{size}/p.jpg"]


class _Picture(io.BytesIO):
    def __init__(self, body: bytes, kind: str) -> None:
        super().__init__(body)
        self.headers = {"Content-Type": kind}

    def __enter__(self) -> _Picture:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_a_tmdb_picture_that_fails_or_runs_too_large_is_refused() -> None:
    from matinee.tmdb import MAX_IMAGE_BYTES, TmdbImageError, fetch_picture

    def failing(error: Exception) -> Any:
        def opener(req: urllib.request.Request, timeout: float) -> Any:
            raise error

        return opener

    for error in (urllib.error.URLError("no route"), TimeoutError()):
        with pytest.raises(TmdbImageError):
            fetch_picture("/p.jpg", "poster", 160, opener=failing(error))
    fits = fetch_picture(
        "/p.jpg", "poster", 160, opener=lambda r, timeout: _Picture(b"x" * MAX_IMAGE_BYTES, "image/jpeg")
    )
    assert len(fits[0]) == MAX_IMAGE_BYTES
    with pytest.raises(TmdbImageError):
        fetch_picture(
            "/p.jpg", "poster", 160, opener=lambda r, timeout: _Picture(b"x" * (MAX_IMAGE_BYTES + 1), "image/jpeg")
        )
