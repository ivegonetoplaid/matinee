"""Routes for what a profile keeps of its own: its ratings and their short reviews, and its hidden films.

Every route here answers only a device holding the profile, checked by the
store in the same transaction as any write; any other device is refused as
`not_held` (403). No reply carries another profile's records.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from matinee.records import Hidden, Rating, Records
from matinee.web.common import device_tokens
from matinee.web.theatre import Theatre

# The request's own cap; a short review between this and the store's limit is refused by the store, in words.
REVIEW_CAP = 1000


class ScoreIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review: str | None = Field(default=None, max_length=REVIEW_CAP)


class HideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    length: str = Field(max_length=8)  # 3m, 6m, 1y or good; the store refuses any other, and a missing one is 422


class HiddenOut(BaseModel):
    """A film the viewer has hidden: the length chosen, when, and when it comes back (null when hidden for good)."""

    tmdb: int
    length: str
    at: str
    until: str | None


class RatingOut(BaseModel):
    """One of the viewer's own ratings: the answer (1 to 5), when it was made, and its short review, if any."""

    tmdb: int
    score: int
    at: str
    review: str | None


class Cleared(BaseModel):
    tmdb: int
    cleared: bool  # False when there was nothing to clear


def rating_out(r: Rating) -> RatingOut:
    return RatingOut(tmdb=r.tmdb, score=r.score, at=r.at, review=r.review)


def offered(theatre: Theatre, tmdb: int) -> int:
    """The film when it is in the current film list; 404 otherwise, as for every other route naming a film."""
    if tmdb not in theatre.showing().catalog.table.films.index:
        raise HTTPException(status_code=404, detail="not_found")
    return tmdb


def add_rating_routes(app: FastAPI, theatre: Theatre, records: Records) -> None:
    @app.get("/api/profiles/{profile_id}/ratings")
    def ratings(profile_id: int, request: Request) -> list[RatingOut]:
        """Every rating the held profile has made, newest first."""
        return [rating_out(r) for r in records.ratings(profile_id, device_tokens(request))]

    @app.put("/api/profiles/{profile_id}/ratings/{tmdb}")
    def rate(profile_id: int, tmdb: int, body: ScoreIn, request: Request) -> RatingOut:
        """Save or change the held profile's answer for a film Matinee offers now."""
        return rating_out(records.rate(profile_id, offered(theatre, tmdb), body.score, device_tokens(request)))

    @app.delete("/api/profiles/{profile_id}/ratings/{tmdb}")
    def unrate(profile_id: int, tmdb: int, request: Request) -> Cleared:
        """Clear the held profile's rating of a film, with its short review."""
        return Cleared(tmdb=tmdb, cleared=records.unrate(profile_id, tmdb, device_tokens(request)))

    @app.put("/api/profiles/{profile_id}/ratings/{tmdb}/review")
    def review(profile_id: int, tmdb: int, body: ReviewIn, request: Request) -> RatingOut:
        """Save, change or clear the short review of a film the held profile has rated."""
        return rating_out(records.review(profile_id, tmdb, body.review, device_tokens(request)))


def hidden_out(h: Hidden) -> HiddenOut:
    return HiddenOut(tmdb=h.tmdb, length=h.length, at=h.at, until=h.until)


def add_hide_routes(app: FastAPI, theatre: Theatre, records: Records) -> None:
    @app.get("/api/profiles/{profile_id}/hidden")
    def hidden(profile_id: int, request: Request) -> list[HiddenOut]:
        """The held profile's hidden films whose hide has not ended, newest first."""
        return [hidden_out(h) for h in records.hidden(profile_id, device_tokens(request))]

    @app.put("/api/profiles/{profile_id}/hidden/{tmdb}")
    def hide(profile_id: int, tmdb: int, body: HideIn, request: Request) -> HiddenOut:
        """Hide a film Matinee offers now from the held profile's picks, for the length chosen."""
        return hidden_out(records.hide(profile_id, offered(theatre, tmdb), body.length, device_tokens(request)))

    @app.delete("/api/profiles/{profile_id}/hidden/{tmdb}")
    def unhide(profile_id: int, tmdb: int, request: Request) -> Cleared:
        """Bring a hidden film back to the held profile's picks."""
        return Cleared(tmdb=tmdb, cleared=records.unhide(profile_id, tmdb, device_tokens(request)))
