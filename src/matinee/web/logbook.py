"""What Matinee's server log says about its whole state, and how often a repeating warning is said.

At start, and whenever its state changes (checked at most every `CHECK_EVERY`
seconds, on the next request), the server logs one line: the media server it
reads and whether it answers, Seerr and DoesTheDogDie, the film table's size and
age, and the rebuild's progress. A warning that one bad answer per picture would
repeat (a wall of posters during an outage) is said at most once a minute, with a
count of the ones held back. No line carries a key, token or door word: the
settings are named, never their values.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime

from matinee.progress import RebuildStatus, read_status
from matinee.web.config import Config
from matinee.web.seerr import SeerrCheck
from matinee.web.theatre import NothingToShow, Theatre

CHECK_EVERY = 15.0
QUIET_FOR = 60.0
SERVER_NAMES = {"jellyfin": "Jellyfin", "plex": "Plex"}
log = logging.getLogger("matinee.web")

State = tuple[object, ...]


def _library(theatre: Theatre, config: Config) -> tuple[str, int]:
    """The library's state in words, and how many films are offered now."""
    try:
        showing = theatre.showing()
    except NothingToShow:
        return "no film offered: Matinee's own data cannot be used", 0
    if config.server is None:
        return "no media server set", showing.now_showing
    name = SERVER_NAMES[config.server.kind]
    words = {"usable": "answers", "refused": "turned down the key"}.get(showing.library, "does not answer")
    return f"{name} {words}", showing.now_showing


def _rebuild(status: RebuildStatus | None) -> str:
    if status is None:
        return "rebuild never reported"
    if status.state == "running":
        share = f" {100 * status.done // status.total}%" if status.total else ""
        return f"rebuild running{share} ({status.done:,} of {status.total:,} films)"
    if status.state == "stopped":
        return f"rebuild stopped at {status.updated_at[:16]} UTC: {status.reason}"
    return f"rebuild finished at {status.updated_at[:16]} UTC"


def _seerr(config: Config, seerr: SeerrCheck) -> str:
    if config.seerr_url is None:
        return "not set"
    return "answers" if seerr.answers() else "does not answer"


def _age(oldest: datetime | None, now: datetime) -> str:
    """How old the film table's oldest TMDB fact is, in words: "1 day old", "2 days old"."""
    if oldest is None:
        return "no TMDB facts"
    days = (now - oldest).days
    unit = "day" if days == 1 else "days"
    return f"TMDB facts from {oldest:%Y-%m-%d} ({days} {unit} old)"


def describe(theatre: Theatre, config: Config, seerr: SeerrCheck, dtdd_on: bool, now: datetime) -> tuple[State, str]:
    """The state as a comparable key and as the line the log says."""
    library, offered = _library(theatre, config)
    seerr_text = _seerr(config, seerr)
    oldest = theatre.oldest_tmdb
    age = _age(oldest, now)
    stale = theatre.stale
    status = read_status(config.state)
    key: State = (library, seerr_text, dtdd_on, theatre.table_films, offered, stale, getattr(status, "state", None))
    line = (
        f"Matinee's state: library: {library}; Seerr: {seerr_text}; DoesTheDogDie: "
        f"{'set, checked at each pick' if dtdd_on else 'not set'}; film table: {theatre.table_films:,} films, "
        f"{age}{', past TMDB terms' if stale else ''}; {offered:,} films offered; {_rebuild(status)}."
    )
    return key, line


class StateLog:
    """Logs the state at start and whenever it changes, looking at most every CHECK_EVERY seconds."""

    def __init__(
        self, describe_now: Callable[[], tuple[State, str]], clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._describe = describe_now
        self._clock = clock
        self._said: State | None = None
        self._looked_at = -math.inf

    def check(self) -> None:
        now = self._clock()
        if now - self._looked_at < CHECK_EVERY:
            return
        self._looked_at = now
        key, line = self._describe()
        if key != self._said:
            log.info("%s", line)
            self._said = key


def state_log(theatre: Theatre, config: Config, seerr: SeerrCheck, dtdd_on: bool) -> StateLog:
    """The state log for this installation; the app builds it once its Seerr check exists."""
    return StateLog(lambda: describe(theatre, config, seerr, dtdd_on, datetime.now(UTC)))


class Quiet:
    """Says a repeating warning at most once every QUIET_FOR seconds per `kind`, counting the ones held back."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._said_at: dict[str, float] = {}
        self._held: dict[str, int] = {}

    def warn(self, kind: str, message: str, *args: object) -> None:
        now = self._clock()
        if now - self._said_at.get(kind, -math.inf) < QUIET_FOR:
            self._held[kind] = self._held.get(kind, 0) + 1
            return
        self._said_at[kind] = now
        held = self._held.pop(kind, 0)
        suffix = f" ({held} more like this in the last minute were not logged)" if held else ""
        log.warning(message + suffix, *args)
