"""The web server's routes. Only Matinee's own page calls them; they are not a public API.

The browser names a film only by a TMDB id that is in the current film list, and
an image only by one of a fixed set of kinds and sizes. Anything else is refused
before any request leaves for the media server. No response carries the media
server's address or key, a file path or a disk location.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from matinee.library import ImageKind, LibraryError
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


ErrorCode = Literal["library_unreachable", "not_ready", "not_found", "refused"]


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


def create_app(config: Config, theatre: Theatre) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

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

    app.state.config = config
    return app
