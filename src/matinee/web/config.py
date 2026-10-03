"""Settings for the web server, read once from the environment at start-up.

Server addresses and keys arrive only here, as configuration; none is ever
committed, logged or sent to a browser. The door word is optional: unset or
empty means no lock. It is never written to a log, a reply or an error.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from matinee.web.admission import MAX_TYPED, RELAXED_MIN, STRICT_MIN, Mode, too_long, too_short

GREETINGS = {
    "show": "State your business. Make it quick, the show's about to start.",
    "gin": "State your business. And it better be sweeter than bathtub gin, or I'll feed you to the copper pipes.",
}


class ConfigError(ValueError):
    """A required setting is missing or points at nothing."""


@dataclass(frozen=True)
class Config:
    jellyfin_url: str
    jellyfin_key: str = field(repr=False)
    state: Path
    seerr_url: str
    dtdd_key: str = field(repr=False)
    door_word: str | None = field(default=None, repr=False)
    door_match: Mode = "relaxed"
    door_greeting: str = GREETINGS["show"]

    @property
    def table_path(self) -> Path:
        return self.state / "films.sqlite"

    @property
    def labels_path(self) -> Path:
        return self.state / "labels.json"

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
    word = env.get("MATINEE_DOOR_WORD", "")
    raw_mode = env.get("MATINEE_DOOR_MATCH", "").strip() or "relaxed"
    if raw_mode not in ("relaxed", "strict"):
        raise ConfigError("MATINEE_DOOR_MATCH names no mode; it is relaxed or strict")
    mode: Mode = "strict" if raw_mode == "strict" else "relaxed"
    greeting = env.get("MATINEE_DOOR_GREETING", "").strip() or "show"
    if not word.strip():
        return None, mode, GREETINGS.get(greeting, greeting)
    if too_long(word):
        raise ConfigError(f"MATINEE_DOOR_WORD is longer than {MAX_TYPED} characters, more than the door compares")
    if too_short(word, mode):
        floor = f"{RELAXED_MIN} letters and digits" if mode == "relaxed" else f"{STRICT_MIN} characters"
        raise ConfigError(f"MATINEE_DOOR_WORD is shorter than {floor}, the least {mode} mode allows")
    return word, mode, GREETINGS.get(greeting, greeting)


def from_env(env: Mapping[str, str] = os.environ) -> Config:
    """Read the settings; raises ConfigError naming the first missing one, or a state directory that does not exist."""
    state = Path(_required(env, "MATINEE_STATE"))
    if not state.is_dir():
        raise ConfigError(f"the state directory {state} does not exist; Matinee will not start empty")
    word, mode, greeting = _door(env)
    return Config(
        jellyfin_url=_required(env, "MATINEE_JELLYFIN_URL"),
        jellyfin_key=_required(env, "JELLYFIN_API_KEY"),
        state=state,
        seerr_url=_required(env, "MATINEE_SEERR_URL").rstrip("/"),
        dtdd_key=_required(env, "DTDD_API_KEY"),
        door_word=word,
        door_match=mode,
        door_greeting=greeting,
    )
