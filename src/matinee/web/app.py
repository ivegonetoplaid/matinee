"""The web server's routes. Only Matinee's own page calls them; they are not a public API.

The browser names a film only by a TMDB id that is in the current film list, and
an image only by one of a fixed set of kinds and sizes. Anything else is refused
before any request leaves for the media server. No response carries the media
server's address or key, a file path or a disk location. With TMDB as the image
source, the page loads a picture TMDB has straight from TMDB's image server.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from matinee.dtdd import Dtdd
from matinee.engine import EngineError
from matinee.library import Image, ImageKind, LibraryError
from matinee.pick import DeviceCap, Picker
from matinee.progress import read_status
from matinee.quips import Quips, QuipsError, load_quips
from matinee.store import AVATARS, Locked, Store, StoreError
from matinee.table import TableError
from matinee.tmdb import TmdbImageError, fetch_picture
from matinee.web.admission import COOKIE as ADMISSION_COOKIE
from matinee.web.admission import LIFE_S as ADMISSION_LIFE_S
from matinee.web.admission import Admission, load_secret
from matinee.web.common import (
    PROFILE_LINES,
    AvatarChoice,
    Deleted,
    Door,
    NewProfile,
    PinEntry,
    Seat,
    Tile,
    device_tokens,
    optional_int,
    problem,
    seat,
    set_tokens,
    with_token,
)
from matinee.web.config import Config, ImageSource
from matinee.web.seerr import SeerrCheck
from matinee.web.setup import BROKEN, SEERR_AWAY, SetupNote, note, rebuild_lines, unreachable
from matinee.web.theatre import NothingToShow, Theatre
from matinee.web.viewing import (
    add_note_routes,
    add_pick_routes,
    add_topic_routes,
    add_viewing_routes,
)

log = logging.getLogger("matinee.web")
IMAGE_WIDTHS: dict[ImageKind, dict[str, int]] = {
    "poster": {"xs": 100, "s": 160, "m": 320, "l": 640},
    "backdrop": {"m": 960, "l": 1600},
}
# A film's poster seldom changes; a month spares every return visit the wall's downloads. Only the viewer's
# own browser may keep one: a shared cache would hand it to a device the locked door has not admitted.
IMAGE_CACHE = f"private, max-age={30 * 24 * 3600}"
# A TMDB picture may stand in for the library's while it cannot answer; kept one day, the library's art returns soon
# after the library does.
TMDB_IMAGE_CACHE = f"private, max-age={24 * 3600}"
TMDB_IMAGES = "https://image.tmdb.org"
TMDB_FILM = "https://www.themoviedb.org/movie"
NOT_READY = "Matinee isn't ready: its film data needs rebuilding."
NOT_FOUND = "I don't have that one."


class FilmCard(BaseModel):
    tmdb: int
    title: str
    year: int | None
    runtime_min: int | None
    synopsis: str | None
    link: str  # the film's page on the configured Seerr, or on TMDB without one
    link_to: Literal["seerr", "tmdb"]
    backdrop_path: str | None  # TMDB's path for the backdrop, given only when TMDB is the image source


class Pictures(BaseModel):
    """Where the page's pictures come from, and each live film's TMDB poster path when that is TMDB."""

    source: ImageSource
    posters: dict[int, str]


@dataclass(frozen=True)
class Held:
    """A film Matinee offers now: its media-server item (None when the library does not hold it), the facts shown
    with it, and TMDB's synopsis."""

    item_id: str | None
    title: str
    year: int | None
    runtime_min: int | None
    backdrop_path: str | None
    synopsis: str | None
    poster_path: str | None


def held(theatre: Theatre, tmdb: int) -> Held:
    """The film if Matinee offers it now; 404 for any other id."""
    films = theatre.showing().catalog.table.films
    if tmdb not in films.index:
        raise HTTPException(status_code=404, detail="not_found")
    row = films.loc[tmdb]
    return Held(
        stored_path(row.item_id),
        str(row["name"]),
        optional_int(row.year),
        optional_int(row.runtime_min),
        stored_path(row.backdrop_path),
        stored_path(row.synopsis),
        stored_path(row.poster_path),
    )


def stored_path(value: Any) -> str | None:
    """A TMDB picture path as the table holds it, or None for a film that has none (None or NaN)."""
    return value if isinstance(value, str) and value else None


def add_error_handlers(app: FastAPI, clock: Callable[[], float]) -> None:
    """Every error leaves as one Problem shape, and never with an exception's text."""

    @app.exception_handler(NothingToShow)
    def nothing(_request: Request, exc: NothingToShow) -> JSONResponse:
        log.error("refusing to serve: Matinee's own data cannot be used: %s", exc)
        return problem(503, "not_ready", NOT_READY)

    @app.exception_handler(TableError)
    def not_ready(_request: Request, exc: TableError) -> JSONResponse:
        log.error("refusing to serve: %s", exc)
        return problem(503, "not_ready", NOT_READY)

    @app.exception_handler(EngineError)
    def misfit(_request: Request, exc: EngineError) -> JSONResponse:
        log.info("refused a walk: %s", exc)
        return problem(400, "refused", "Those answers don't fit that question any more. Let's start over.")

    @app.exception_handler(StarletteHTTPException)
    def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return problem(404, "not_found", NOT_FOUND)
        return problem(exc.status_code, "refused", "That request isn't something I can answer.")

    @app.exception_handler(StoreError)
    def refused(_request: Request, exc: StoreError) -> JSONResponse:
        statuses = {"name_taken": 409, "full": 409, "no_profile": 404, "not_held": 403, "wrong_pin": 401, "locked": 423}
        status = statuses.get(exc.code, 400)
        minutes = max(1, round((exc.until - clock()) / 60)) if isinstance(exc, Locked) else 0
        body = {"error": "profile", "code": exc.code, "message": PROFILE_LINES[exc.code].format(minutes=minutes)}
        return JSONResponse(status_code=status, content=body)


def film_link(seerr: str | None, tmdb: int) -> tuple[str, Literal["seerr", "tmdb"]]:
    """The pick's "More on" link: the film's Seerr page where Seerr is configured, else its TMDB page."""
    if seerr:
        return f"{seerr}/movie/{tmdb}", "seerr"
    return f"{TMDB_FILM}/{tmdb}", "tmdb"


def film_image(theatre: Theatre, film: Held, tmdb: int, kind: ImageKind, width: int) -> tuple[Image, str]:
    """The film's picture and how long a browser keeps it: from the media server for a film it holds; from TMDB's
    image server, through Matinee, for any other film, while the library cannot be used, and when the media server
    gives none. 404 when neither gives one."""
    if film.item_id is not None and theatre.library is not None:
        try:
            return theatre.library.image(film.item_id, kind, width), IMAGE_CACHE
        except LibraryError as exc:
            log.warning("the media server gave no %s for tmdb %s, so it comes from TMDB: %s", kind, tmdb, exc)
    return tmdb_image(film, tmdb, kind, width), TMDB_IMAGE_CACHE


def tmdb_image(film: Held, tmdb: int, kind: ImageKind, width: int) -> Image:
    """The film's TMDB picture, fetched by the server so the viewer's browser talks only to Matinee."""
    path = film.poster_path if kind == "poster" else film.backdrop_path
    if path is None:
        raise HTTPException(status_code=404, detail="not_found")
    try:
        body, content_type = fetch_picture(path, kind, width)
    except TmdbImageError as exc:
        log.warning("image %s for tmdb %s from TMDB: %s", kind, tmdb, exc)
        raise HTTPException(status_code=404, detail="not_found") from exc
    return Image(body, content_type)


def film_synopsis(theatre: Theatre, film: Held, tmdb: int) -> str | None:
    """The media server's synopsis for a film it holds, else TMDB's; TMDB's too when the server has none or fails."""
    if film.item_id is None or theatre.library is None:
        return film.synopsis
    try:
        return theatre.library.synopsis(film.item_id) or film.synopsis
    except LibraryError as exc:
        log.warning("the media server gave no synopsis for tmdb %s, so the card shows TMDB's: %s", tmdb, exc)
        return film.synopsis


def add_film_routes(app: FastAPI, theatre: Theatre, seerr: SeerrCheck, images: ImageSource) -> None:
    @app.get("/img/{kind}/{tmdb}/{size}")
    def image(kind: str, tmdb: int, size: str) -> Response:
        image_kind: ImageKind = "backdrop" if kind == "backdrop" else "poster"
        if kind != image_kind or size not in IMAGE_WIDTHS[image_kind]:
            raise HTTPException(status_code=404, detail="not_found")
        img, kept = film_image(theatre, held(theatre, tmdb), tmdb, image_kind, IMAGE_WIDTHS[image_kind][size])
        return Response(img.body, media_type=img.content_type, headers={"Cache-Control": kept})

    @app.get("/api/pictures")
    def pictures() -> Pictures:
        """The image source and, when it is TMDB, the TMDB poster path of every live film that has one."""
        if images == "server":
            return Pictures(source=images, posters={})
        films = theatre.showing().catalog.table.films
        paths = {int(str(tmdb)): stored_path(path) for tmdb, path in films.poster_path.items()}
        return Pictures(source=images, posters={tmdb: path for tmdb, path in paths.items() if path})

    @app.get("/api/film/{tmdb}")
    def film(tmdb: int) -> FilmCard:
        film = held(theatre, tmdb)
        synopsis = film_synopsis(theatre, film, tmdb)
        link, link_to = film_link(seerr.link_base(), tmdb)
        return FilmCard(
            tmdb=tmdb,
            title=film.title,
            year=film.year,
            runtime_min=film.runtime_min,
            synopsis=synopsis,
            link=link,
            link_to=link_to,
            backdrop_path=film.backdrop_path if images == "tmdb" else None,
        )


def add_door_routes(app: FastAPI, theatre: Theatre, store: Store, clock: Callable[[], float], topics_on: bool) -> None:
    @app.get("/api/door")
    def door(request: Request, response: Response) -> Door:
        """What the front door shows an admitted device: the film count, every profile by name, and the avatars.

        Each profile says whether this device holds it; none carries its topics. A token for a profile that
        is gone is cleared from the cookie.
        """
        tokens = device_tokens(request)
        held_by_device = store.holding(tokens)
        if len(held_by_device) != len(tokens):
            set_tokens(response, [t for t in tokens if t in held_by_device])
        held = {p.id for p in held_by_device.values()}
        tiles = [
            Tile(id=p.id, name=p.name, avatar=p.avatar, has_pin=p.has_pin, held=p.id in held) for p in store.everyone()
        ]
        now = theatre.showing().now_showing
        return Door(now_showing=now, profiles=tiles, avatars=list(AVATARS), dtdd=topics_on)

    @app.post("/api/profiles")
    def create_profile(body: NewProfile, request: Request, response: Response) -> Seat:
        profile, token = store.create(body.name, body.pin, body.topics, body.avatar)
        with_token(request, response, token)
        return seat(profile)

    @app.post("/api/profiles/{profile_id}/open")
    def open_profile(profile_id: int, body: PinEntry, request: Request, response: Response) -> Seat:
        """A device that already holds this profile is not asked for its PIN and keeps its token."""
        for token, profile in store.holding(device_tokens(request)).items():
            if profile.id == profile_id:
                with_token(request, response, token)
                return seat(profile)
        profile, token = store.open(profile_id, body.pin, clock())
        with_token(request, response, token)
        return seat(profile)


def add_avatar_route(app: FastAPI, store: Store) -> None:
    @app.put("/api/profiles/{profile_id}/avatar")
    def set_avatar(profile_id: int, body: AvatarChoice, request: Request) -> Seat:
        """A device holding the profile sets its avatar, or clears it for initials."""
        if not any(p.id == profile_id for p in store.holding(device_tokens(request)).values()):
            raise HTTPException(status_code=403, detail="refused")
        return seat(store.set_avatar(profile_id, body.avatar, device_tokens(request)))


def add_delete_route(app: FastAPI, store: Store) -> None:
    @app.delete("/api/profiles/{profile_id}")
    def delete_profile(profile_id: int, request: Request, response: Response) -> Deleted:
        """Only a device holding the profile may delete it; the profile's tokens go with it, on every device."""
        tokens = device_tokens(request)
        held = store.holding(tokens)
        mine = [t for t, p in held.items() if p.id == profile_id]
        if not mine:
            raise HTTPException(status_code=403, detail="refused")
        gone = store.delete(profile_id, tokens)
        set_tokens(response, [t for t in tokens if t in held and t not in mine])
        return Deleted(name=gone.name)


NOT_ADMITTED = "Matinee is a private screening. Give the word at the door."
WRONG_WORD = "That's not the word."
WRONG_WORD_DELAY_S = 2.0


class AdmissionOut(BaseModel):
    """Whether the site is locked, whether this device is admitted, and the locked door's greeting."""

    locked: bool
    admitted: bool
    greeting: str | None


class WordIn(BaseModel):
    word: str


def open_before_admission(path: str) -> bool:
    """The page, its static files (the locked door's art among them) and the word check; nothing else."""
    return path in ("/", "/api/admission") or path.startswith("/static/")


def add_admission(app: FastAPI, admission: Admission, greeting: str, clock: Callable[[], float], delay: float) -> None:
    """The locked door: every other route refuses a device the door word has not admitted.

    A wrong word is answered after `delay` seconds, and words are checked one at a time across the installation.
    The wait is an asynchronous sleep, so waiting guesses hold no worker and delay no other route.
    """
    checking = asyncio.Lock()

    def status(request: Request) -> AdmissionOut:
        admitted = admission.admits(request.cookies.get(ADMISSION_COOKIE), clock())
        return AdmissionOut(locked=admission.locked, admitted=admitted, greeting=greeting if admission.locked else None)

    @app.middleware("http")
    async def gate(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        if open_before_admission(path) or admission.admits(request.cookies.get(ADMISSION_COOKIE), clock()):
            return await call_next(request)
        return problem(401, "not_admitted", NOT_ADMITTED)

    @app.get("/api/admission")
    def admitted(request: Request) -> AdmissionOut:
        return status(request)

    @app.post("/api/admission", response_model=None)
    async def give_word(body: WordIn, request: Request, response: Response) -> AdmissionOut | JSONResponse:
        async with checking:
            if admission.matches(body.word):
                response.set_cookie(
                    ADMISSION_COOKIE,
                    admission.issue(clock()),
                    max_age=ADMISSION_LIFE_S,
                    path="/",
                    secure=True,
                    httponly=True,
                    samesite="lax",
                )
                return AdmissionOut(locked=admission.locked, admitted=True, greeting=None)
            await asyncio.sleep(delay)
        return problem(401, "wrong_word", WRONG_WORD)


STATIC = Path(__file__).resolve().parent / "static"
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src {img}; style-src 'self'; font-src 'self'; script-src 'self'; "
    "connect-src 'self'; manifest-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'"
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    # Search engines must read this header, so no robots.txt ever blocks crawling.
    "X-Robots-Tag": "noindex",
}


def security_headers(images: ImageSource) -> dict[str, str]:
    """The headers every response carries. Images may come from TMDB's image server only when it is the source."""
    img = "'self'" if images == "server" else f"'self' {TMDB_IMAGES}"
    return {"Content-Security-Policy": CONTENT_SECURITY_POLICY.format(img=img), **SECURITY_HEADERS}


def add_page(app: FastAPI, images: ImageSource) -> None:
    """The page, its scripts, styles, fonts and images; every response carries the security headers.

    The page and its static files are served `no-cache`: a browser or an edge cache may keep a copy but must
    revalidate it, so a deploy reaches every viewer on the next load and a page never mixes old and new files.
    Every `/api/` reply is served `no-store`: several read the device's cookie, so no cache may keep any copy.
    """
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    every = security_headers(images)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @app.middleware("http")
    async def headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        for name, value in every.items():
            response.headers.setdefault(name, value)
        if request.url.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "no-cache")
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response


def add_quip_routes(app: FastAPI, quips: Quips | None) -> None:
    @app.get("/api/quips", response_model=None)
    def pick_lines() -> Quips | JSONResponse:
        """Matinee's lines for a pick and their caps, as data/quips.json holds them; 503 when it cannot be read."""
        if quips is None:
            return problem(503, "not_ready", "My lines for a pick can't be read right now.")
        return quips


SERVER_NAMES = {"jellyfin": "Jellyfin", "plex": "Plex"}


def setup_faults(theatre: Theatre, config: Config, seerr: SeerrCheck, faults: Sequence[str]) -> tuple[list[str], int]:
    """Everything Matinee sees wrong now, in words, and how many films it can offer."""
    found = [*config.faults, *faults]
    try:
        showing = theatre.showing()
    except NothingToShow as exc:
        return [*found, BROKEN.format(detail=exc)], 0
    if showing.library == "unreachable" and config.server is not None:
        found.append(unreachable(SERVER_NAMES[config.server.kind]))
    if config.seerr_url is not None and not seerr.answers():
        found.append(SEERR_AWAY)
    return [*found, *rebuild_lines(read_status(config.state), theatre.table_films)], showing.now_showing


def add_setup_route(app: FastAPI, theatre: Theatre, config: Config, seerr: SeerrCheck, faults: Sequence[str]) -> None:
    @app.get("/api/setup")
    def setup() -> SetupNote:
        """The setup note the page shows before any pick; empty lines when all is well."""
        found, films = setup_faults(theatre, config, seerr, faults)
        return note(found, films, theatre.stale)


def create_app(
    config: Config,
    theatre: Theatre,
    store: Store,
    dtdd: Dtdd | None,
    clock: Callable[[], float] = time.time,
    picker: Picker | None = None,
    quips: Quips | None = None,
    wrong_word_delay_s: float = WRONG_WORD_DELAY_S,
    seerr: SeerrCheck | None = None,
    faults: Sequence[str] = (),
) -> FastAPI:
    """The app. `quips` defaults to data/quips.json, read now. `faults` are setup faults found before the app,
    in words for the setup note.

    With a door word set, the installation secret is read, or made at the first start, now; an unreadable one
    stops the start.
    """
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    faults = list(faults)
    try:
        lines: Quips | None = quips or load_quips()
    except QuipsError as exc:
        lines = None
        log.error("the pick's lines (data/quips.json) cannot be read, so picks show no line: %s", exc)
        faults.append(
            f"My lines for a pick can't be read ({exc}), so picks come without one. Update or reinstall Matinee."
        )
    secret = load_secret(config.state) if config.door_word is not None else b""
    admission = Admission(config.door_word, config.door_match, secret)
    add_error_handlers(app, clock)
    # Registered before the page's headers, so the headers wrap the locked door's refusals too.
    add_admission(app, admission, config.door_greeting, clock, wrong_word_delay_s)
    seerr = seerr or SeerrCheck(config.seerr_url)
    add_film_routes(app, theatre, seerr, config.images)
    add_setup_route(app, theatre, config, seerr, faults)
    add_page(app, config.images)
    add_door_routes(app, theatre, store, clock, dtdd is not None)
    add_delete_route(app, store)
    add_avatar_route(app, store)
    topics_on = dtdd is not None
    picker = picker or Picker(dtdd, DeviceCap())
    if (picker.dtdd is None) != (dtdd is None):
        raise ValueError("the picker and the app must agree on whether a DoesTheDogDie key is set")
    if dtdd is not None:
        add_topic_routes(app, store, dtdd)
    add_viewing_routes(app, theatre, store, topics_on)
    add_pick_routes(app, theatre, store, picker, topics_on)
    add_note_routes(app, theatre, store)
    add_quip_routes(app, lines)
    app.state.config = config
    return app
