"""The web server's routes. Only Matinee's own page calls them; they are not a public API.

The browser names a film only by a TMDB id that is in the current film list, and
an image only by one of a fixed set of kinds and sizes. Anything else is refused
before any request leaves for the media server. No response carries the media
server's address or key, a file path or a disk location.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from matinee.dtdd import Dtdd
from matinee.engine import EngineError
from matinee.library import ImageKind, LibraryError
from matinee.pick import DeviceCap, Picker
from matinee.store import Locked, Store, StoreError
from matinee.table import TableError
from matinee.web.common import (
    PROFILE_LINES,
    Door,
    NameQuery,
    NewProfile,
    PinEntry,
    Seat,
    Suggestion,
    device_tokens,
    optional_int,
    problem,
    seat,
    set_tokens,
    with_token,
)
from matinee.web.config import Config
from matinee.web.theatre import LibraryUnavailable, Theatre
from matinee.web.viewing import add_correction_routes, add_pick_routes, add_viewing_routes, check_exclusions

log = logging.getLogger("matinee.web")
IMAGE_WIDTHS: dict[ImageKind, dict[str, int]] = {
    "poster": {"s": 160, "m": 320, "l": 640},
    "backdrop": {"m": 960, "l": 1600},
}
UNREACHABLE = "I can't reach the film library right now."
NOT_READY = "Matinee isn't ready: its film data needs rebuilding."
NOT_FOUND = "I don't have that one."


class FilmCard(BaseModel):
    tmdb: int
    title: str
    year: int | None
    runtime_min: int | None
    synopsis: str | None


@dataclass(frozen=True)
class Held:
    """A film in the current list: its media-server item and the facts shown with it."""

    item_id: str
    title: str
    year: int | None
    runtime_min: int | None


def held(theatre: Theatre, tmdb: int) -> Held:
    """The film if it is in the current list; 404 for any other id."""
    films = theatre.showing().catalog.table.films
    if tmdb not in films.index:
        raise HTTPException(status_code=404, detail="not_found")
    row = films.loc[tmdb]
    return Held(str(row.item_id), str(row["name"]), optional_int(row.year), optional_int(row.runtime_min))


def add_error_handlers(app: FastAPI, clock: Callable[[], float]) -> None:
    """Every error leaves as one Problem shape, and never with an exception's text."""

    @app.exception_handler(LibraryUnavailable)
    def unavailable(_request: Request, _exc: LibraryUnavailable) -> JSONResponse:
        return problem(503, "library_unreachable", UNREACHABLE)

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
        status = {"name_taken": 409, "full": 409, "no_profile": 404, "wrong_pin": 401, "locked": 423}.get(exc.code, 400)
        minutes = max(1, round((exc.until - clock()) / 60)) if isinstance(exc, Locked) else 0
        body = {"error": "profile", "code": exc.code, "message": PROFILE_LINES[exc.code].format(minutes=minutes)}
        return JSONResponse(status_code=status, content=body)


def add_film_routes(app: FastAPI, theatre: Theatre) -> None:
    @app.get("/img/{kind}/{tmdb}/{size}")
    def image(kind: str, tmdb: int, size: str) -> Response:
        image_kind: ImageKind = "backdrop" if kind == "backdrop" else "poster"
        if kind != image_kind or size not in IMAGE_WIDTHS[image_kind]:
            raise HTTPException(status_code=404, detail="not_found")
        film = held(theatre, tmdb)
        try:
            img = theatre.library.image(film.item_id, image_kind, IMAGE_WIDTHS[image_kind][size])
        except LibraryError as exc:
            log.warning("image %s for tmdb %s: %s", kind, tmdb, exc)
            raise HTTPException(status_code=404, detail="not_found") from exc
        return Response(img.body, media_type=img.content_type, headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/api/film/{tmdb}")
    def film(tmdb: int) -> FilmCard:
        film = held(theatre, tmdb)
        try:
            synopsis = theatre.library.synopsis(film.item_id)
        except LibraryError as exc:
            log.warning("synopsis for tmdb %s: %s", tmdb, exc)
            raise LibraryUnavailable("the library cannot be reached") from exc
        return FilmCard(tmdb=tmdb, title=film.title, year=film.year, runtime_min=film.runtime_min, synopsis=synopsis)


def add_door_routes(app: FastAPI, theatre: Theatre, store: Store, clock: Callable[[], float]) -> None:
    @app.get("/api/door")
    def door(request: Request, response: Response) -> Door:
        """What the box office shows this device: the film count and the profiles it holds a token for."""
        tokens = device_tokens(request)
        held_by_device = store.holding(tokens)
        if len(held_by_device) != len(tokens):
            set_tokens(response, [t for t in tokens if t in held_by_device])
        seats = {p.id: seat(p) for p in held_by_device.values()}
        return Door(now_showing=theatre.showing().now_showing, profiles=list(seats.values()))

    @app.post("/api/names")
    def names(query: NameQuery) -> list[Suggestion]:
        return [Suggestion(id=p.id, name=p.name, has_pin=p.has_pin) for p in store.suggest(query.typed)]

    @app.post("/api/profiles")
    def create_profile(body: NewProfile, request: Request, response: Response) -> Seat:
        check_exclusions(theatre, body.exclusions)
        profile, token = store.create(body.name, body.pin, body.topics, body.exclusions)
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


def create_app(
    config: Config,
    theatre: Theatre,
    store: Store,
    dtdd: Dtdd,
    clock: Callable[[], float] = time.time,
    picker: Picker | None = None,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    add_error_handlers(app, clock)
    add_film_routes(app, theatre)
    add_door_routes(app, theatre, store, clock)
    add_viewing_routes(app, theatre, store, dtdd)
    add_pick_routes(app, theatre, store, picker or Picker(dtdd, DeviceCap()))
    add_correction_routes(app, theatre, store)
    app.state.config = config
    return app
