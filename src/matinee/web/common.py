"""Pieces every route module shares: the one error shape, a profile as the page sees it, and the device cookie."""

from __future__ import annotations

from typing import Literal

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from matinee.store import Profile

ErrorCode = Literal[
    "library_unreachable",
    "not_ready",
    "not_found",
    "refused",
    "profile",
    "topics_unavailable",
    "not_admitted",
    "wrong_word",
]
TOKENS_COOKIE = "matinee_tokens"
MAX_TOKENS = 8
COOKIE_AGE_S = 400 * 24 * 3600
PROFILE_LINES = {
    "bad_name": "Names are 1 to 40 letters, numbers or spaces.",
    "bad_pin": "A PIN is four digits.",
    "bad_avatar": "I don't have that avatar.",
    "name_taken": "Someone already goes by that name here. Try another?",
    "full": "The theatre's full up on regulars. Ask whoever runs this place to make room.",
    "no_profile": "I can't find that one any more.",
    "not_held": "I can't find that one any more.",
    "wrong_pin": "That PIN isn't right.",
    "locked": "Too many wrong PINs. That profile is locked for {minutes} minutes.",
}


class Seat(BaseModel):
    """A profile as the page sees it: never its PIN or its token."""

    id: int
    name: str
    has_pin: bool
    topics: list[int]
    avatar: str | None


class Tile(BaseModel):
    """A profile on the front door: never its topics, which say what frightens a person and only its holder sees."""

    id: int
    name: str
    avatar: str | None
    has_pin: bool
    held: bool  # this device holds a token for it, so it opens without its PIN


class Deleted(BaseModel):
    """A profile just deleted: its name, for the page's last word on it."""

    name: str


class Door(BaseModel):
    now_showing: int
    profiles: list[Tile]
    avatars: list[str]
    dtdd: bool  # the installation has a DoesTheDogDie key, so it offers the list of topics to steer around


class NewProfile(BaseModel):
    name: str = Field(max_length=80)
    pin: str | None = Field(default=None, max_length=8)
    avatar: str | None = Field(default=None, max_length=40)
    topics: list[int] = Field(default=[], max_length=400)


class AvatarChoice(BaseModel):
    """An avatar to show, or None for the profile's initials."""

    avatar: str | None = Field(max_length=40)


class PinEntry(BaseModel):
    pin: str | None = Field(default=None, max_length=8)


def seat(profile: Profile) -> Seat:
    return Seat(
        id=profile.id,
        name=profile.name,
        has_pin=profile.has_pin,
        topics=sorted(profile.topics),
        avatar=profile.avatar,
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


def optional_int(value: object) -> int | None:
    """An integer, or None for a missing value (None, NaN or pandas' NA)."""
    try:
        number = float(str(value))
    except ValueError:
        return None
    return None if number != number else round(number)
