"""Settings for the web server, read once from the environment at start-up.

Server addresses and keys arrive only here, as configuration; none is ever
committed, logged or sent to a browser.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    """A required setting is missing or points at nothing."""


@dataclass(frozen=True)
class Config:
    jellyfin_url: str
    jellyfin_key: str = field(repr=False)
    state: Path
    seerr_url: str
    dtdd_key: str = field(repr=False)

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


def from_env(env: Mapping[str, str] = os.environ) -> Config:
    """Read the settings; raises ConfigError naming the first missing one, or a state directory that does not exist."""
    state = Path(_required(env, "MATINEE_STATE"))
    if not state.is_dir():
        raise ConfigError(f"the state directory {state} does not exist; Matinee will not start empty")
    return Config(
        jellyfin_url=_required(env, "MATINEE_JELLYFIN_URL"),
        jellyfin_key=_required(env, "JELLYFIN_API_KEY"),
        state=state,
        seerr_url=_required(env, "MATINEE_SEERR_URL").rstrip("/"),
        dtdd_key=_required(env, "DTDD_API_KEY"),
    )
