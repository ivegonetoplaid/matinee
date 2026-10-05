"""Settings for the web server, read once from the environment at start-up.

Server addresses and keys arrive only here, as configuration; none is ever
committed, logged or sent to a browser. The media server is whichever of Jellyfin
and Plex has its address and key set (`matinee.library.choice`). Seerr and
DoesTheDogDie are on when their setting is filled in. The door word is optional:
unset or empty means no lock. It is never written to a log, a reply or an error.
`POSTERS_FROM` says where the page's pictures come from: `server`, the media
server (the default), or `tmdb`, TMDB's image server.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from matinee.library.choice import MediaServer, ServerChoiceError, media_server
from matinee.web.admission import MAX_TYPED, RELAXED_MIN, STRICT_MIN, Mode, too_long, too_short

GREETINGS = {
    "show": "State your business. Make it quick, the show's about to start.",
    "gin": "State your business. And it better be sweeter than bathtub gin, or I'll feed you to the copper pipes.",
}

ImageSource = Literal["server", "tmdb"]


class ConfigError(ValueError):
    """A required setting is missing or points at nothing."""


@dataclass(frozen=True)
class Config:
    server: MediaServer
    state: Path
    seerr_url: str | None
    dtdd_key: str | None = field(repr=False)
    door_word: str | None = field(default=None, repr=False)
    door_match: Mode = "relaxed"
    door_greeting: str = GREETINGS["show"]
    images: ImageSource = "server"

    @property
    def table_path(self) -> Path:
        return self.state / "films.sqlite"

    @property
    def store_path(self) -> Path:
        return self.state / "matinee.sqlite"


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set")
    return value


def _door(env: Mapping[str, str]) -> tuple[str | None, Mode, str]:
    """The door word, its match mode and the greeting; a word too short for its mode stops the start, unnamed."""
    word = env.get("DOOR_WORD", "")
    raw_mode = env.get("DOOR_MATCH", "").strip() or "relaxed"
    if raw_mode not in ("relaxed", "strict"):
        raise ConfigError("DOOR_MATCH names no mode; it is relaxed or strict")
    mode: Mode = "strict" if raw_mode == "strict" else "relaxed"
    greeting = env.get("DOOR_GREETING", "").strip() or "show"
    if not word.strip():
        return None, mode, GREETINGS.get(greeting, greeting)
    if too_long(word):
        raise ConfigError(f"DOOR_WORD is longer than {MAX_TYPED} characters, more than the door compares")
    if too_short(word, mode):
        floor = f"{RELAXED_MIN} letters and digits" if mode == "relaxed" else f"{STRICT_MIN} characters"
        raise ConfigError(f"DOOR_WORD is shorter than {floor}, the least {mode} mode allows")
    return word, mode, GREETINGS.get(greeting, greeting)


def _images(env: Mapping[str, str]) -> ImageSource:
    """Where the page's pictures come from; unset or empty is the media server."""
    raw = env.get("POSTERS_FROM", "").strip() or "server"
    if raw == "server":
        return "server"
    if raw == "tmdb":
        return "tmdb"
    raise ConfigError("POSTERS_FROM names no picture source; it is server or tmdb")


def from_env(env: Mapping[str, str] = os.environ) -> Config:
    """Read the settings; raises ConfigError naming the first missing one, or a state directory that does not exist."""
    state = Path(_required(env, "DATA_DIR"))
    if not state.is_dir():
        raise ConfigError(f"the data directory {state} does not exist; Matinee will not start empty")
    word, mode, greeting = _door(env)
    try:
        server = media_server(env)
    except ServerChoiceError as exc:
        raise ConfigError(str(exc)) from exc
    return Config(
        server=server,
        state=state,
        seerr_url=env.get("SEERR_URL", "").strip().rstrip("/") or None,
        dtdd_key=env.get("DTDD_API_KEY", "").strip() or None,
        door_word=word,
        door_match=mode,
        door_greeting=greeting,
        images=_images(env),
    )
