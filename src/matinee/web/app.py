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
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from matinee.library import ImageKind, LibraryError
from matinee.store import Locked, Profile, Store, StoreError
from matinee.table import TableError
from matinee.web.config import Config
from matinee.web.theatre import LibraryUnavailable, Theatre

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


ErrorCode = Literal["library_unreachable", "not_ready", "not_found", "refused", "profile"]
TOKENS_COOKIE = "matinee_tokens"
MAX_TOKENS = 8
COOKIE_AGE_S = 400 * 24 * 3600
PROFILE_LINES = {
    "bad_name": "Names are 1 to 40 letters, numbers or spaces.",
    "bad_pin": "A PIN is four digits.",
    "name_taken": "Someone already goes by that name here. Try another?",
    "full": "The theatre's full up on regulars. Ask whoever runs this place to make room.",
    "no_profile": "I can't find that one any more.",
    "wrong_pin": "That PIN isn't right.",
    "locked": "Too many wrong PINs. That profile is locked for {minutes} minutes.",
}


class Seat(BaseModel):
    """A profile as the page sees it: never its PIN or its token."""

    id: int
    name: str
    has_pin: bool
    topics: list[int]
    exclusions: list[str]


class Suggestion(BaseModel):
    """A name suggestion: never the profile's exclusions, which only its device or its PIN may see."""

    id: int
    name: str
    has_pin: bool


class Door(BaseModel):
    now_showing: int
    profiles: list[Seat]


class NameQuery(BaseModel):
    typed: str = Field(max_length=80)


class NewProfile(BaseModel):
    name: str = Field(max_length=80)
    pin: str | None = Field(default=None, max_length=8)
    topics: list[int] = Field(default=[], max_length=400)
    exclusions: list[str] = Field(default=[], max_length=20)


class PinEntry(BaseModel):
    pin: str | None = Field(default=None, max_length=8)


def seat(profile: Profile) -> Seat:
    return Seat(
        id=profile.id,
        name=profile.name,
        has_pin=profile.has_pin,
        topics=sorted(profile.topics),
        exclusions=sorted(profile.exclusions),
    )


def device_tokens(request: Request) -> list[str]:
    raw = request.cookies.get(TOKENS_COOKIE, "")
    return [t for t in raw.split(".") if t][:MAX_TOKENS]


def set_tokens(response: Response, tokens: list[str]) -> None:
    """The device's token list: random tokens only, never a name or a PIN; HttpOnly, Secure, SameSite=Lax."""
    if not tokens:
        response.delete_cookie(TOKENS_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
        return
    response.set_cookie(
        TOKENS_COOKIE,
        ".".join(tokens[-MAX_TOKENS:]),
        max_age=COOKIE_AGE_S,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def with_token(request: Request, response: Response, token: str) -> None:
    kept = [t for t in device_tokens(request) if t != token]
    set_tokens(response, [*kept, token])


class Problem(BaseModel):
    """The one shape every error response takes."""

    error: ErrorCode
    message: str


def problem(status: int, error: ErrorCode, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=Problem(error=error, message=message).model_dump())


@dataclass(frozen=True)
class Held:
    """A film in the current list: its media-server item and the facts shown with it."""

    item_id: str
    title: str
    year: int | None
    runtime_min: int | None


def _optional_int(value: object) -> int | None:
    """An integer, or None for a missing value (None, NaN or pandas' NA)."""
    try:
        number = float(str(value))
    except ValueError:
        return None
    return None if number != number else round(number)


def held(theatre: Theatre, tmdb: int) -> Held:
    """The film if it is in the current list; 404 for any other id."""
    films = theatre.showing().catalog.table.films
    if tmdb not in films.index:
        raise HTTPException(status_code=404, detail="not_found")
    row = films.loc[tmdb]
    return Held(str(row.item_id), str(row["name"]), _optional_int(row.year), _optional_int(row.runtime_min))


def add_error_handlers(app: FastAPI, clock: Callable[[], float]) -> None:
    """Every error leaves as one Problem shape, and never with an exception's text."""

    @app.exception_handler(LibraryUnavailable)
    def unavailable(_request: Request, _exc: LibraryUnavailable) -> JSONResponse:
        return problem(503, "library_unreachable", UNREACHABLE)

    @app.exception_handler(TableError)
    def not_ready(_request: Request, exc: TableError) -> JSONResponse:
        log.error("refusing to serve: %s", exc)
        return problem(503, "not_ready", NOT_READY)

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


def create_app(config: Config, theatre: Theatre, store: Store, clock: Callable[[], float] = time.time) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    add_error_handlers(app, clock)
    add_film_routes(app, theatre)
    add_door_routes(app, theatre, store, clock)
    app.state.config = config
    return app
