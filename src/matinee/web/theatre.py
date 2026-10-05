"""What the server currently shows: the film table as the library holds it now, prepared for the engine.

The film list is read from the media server live, at most every `LIVE_TTL`
seconds. While it cannot be read the library cannot be used: no film counts as
held, and the films the labels name are offered alone. For `RETRY_AFTER` seconds
after a failed read no new read is attempted, so a hung server cannot queue every
request behind it. With no media server configured there is no list to read.

The table file is reloaded when the rebuild replaces it, and its TMDB age is
checked on every call: a table six months old or more is still served, and
`stale` says so (logged once each time it turns stale). A table that is absent, or that cannot be read, counts as
an empty one, so Matinee starts before its first rebuild has written anything.
Building the theatre prepares a catalog once, so shipped data that cannot make
one (stale reference statistics, a malformed tree) is logged at start-up; every
call tries again, and while it fails no film is offered (`NothingToShow`).
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from matinee.engine import Catalog, EngineError, load_catalog
from matinee.labels import LabelsError
from matinee.library import Library, LibraryError, LibraryFilm, LibraryRefused
from matinee.reference import ReferenceError
from matinee.table import FilmTable, TableError, empty_table, is_stale, load_table, with_live
from matinee.trees import TreeError

LIVE_TTL = 300.0
RETRY_AFTER = 15.0
log = logging.getLogger("matinee.theatre")

LibraryState = Literal["none", "usable", "unreachable", "refused"]
UNUSABLE: tuple[LibraryState, ...] = ("unreachable", "refused")  # a media server is set and cannot be read
BROKEN_DATA = (EngineError, LabelsError, ReferenceError, TreeError, TableError, OSError, KeyError, json.JSONDecodeError)


def warn_library(exc: LibraryError, failed_as: LibraryState) -> None:
    """Say once how the media server failed, with the check that fits: its key when it turned the key down, its
    address and whether it runs when it gave no usable answer."""
    check = "check the key in its settings" if failed_as == "refused" else "check that it is running and its address"
    log.warning(
        "the media server could not be read: %s. Meanwhile Matinee recommends from the films the labels name. It"
        " tries again every %d seconds; %s.",
        exc,
        int(RETRY_AFTER),
        check,
    )


class NothingToShow(RuntimeError):
    """Matinee's own shipped data cannot make a catalog, so no film can be offered until it is repaired."""


@dataclass(frozen=True)
class Showing:
    catalog: Catalog
    now_showing: int
    read_at: float
    library: LibraryState


class Theatre:
    def __init__(
        self,
        library: Library | None,
        table_path: Path,
        clock: Callable[[], float] = time.monotonic,
        catalog_of: Callable[[FilmTable], Catalog] = load_catalog,
        on_reload: Callable[[], None] = lambda: None,
        listed: frozenset[int] = frozenset(),
        tags: tuple[str, ...] = (),
    ) -> None:
        self._library = library
        self._table_path = table_path
        self._clock = clock
        self._catalog_of = catalog_of
        self._on_reload = on_reload
        self._listed = listed
        self._tags = tags
        self._lock = threading.Lock()
        self._table_mtime: float | None = None
        self._table = self._load()
        self._showing: Showing | None = None
        self._failed_at: float | None = None
        self._failed_as: LibraryState = "unreachable"  # how the last failed read failed
        self.broken: str | None = None  # why Matinee's own data cannot make a catalog, as last found
        self._stale_said = False
        with contextlib.suppress(NothingToShow):  # logged where it was found; every later call tries again
            self._catalog(self._table)

    def _mtime(self) -> float | None:
        try:
            return self._table_path.stat().st_mtime
        except FileNotFoundError:
            return None

    def _load(self) -> FilmTable:
        """The table on disk, or an empty one when it is absent or cannot be read."""
        self._table_mtime = self._mtime()
        if self._table_mtime is None:
            return empty_table(self._tags)
        try:
            return load_table(self._table_path)
        except (TableError, sqlite3.DatabaseError, KeyError, ValueError) as exc:
            log.warning(
                "the film table %s cannot be read, so Matinee treats it as absent until the next rebuild replaces it:"
                " %s",
                self._table_path,
                exc,
            )
            return empty_table(self._tags)

    def _reload_table_if_replaced(self) -> None:
        if self._mtime() != self._table_mtime:
            self._table = self._load()
            self._showing = None
            log.info("film table reloaded: %d films", len(self._table.films))
            self._on_reload()

    def _read_library(self, now: float) -> tuple[list[LibraryFilm] | None, LibraryState]:
        """The live film list and what state the library is in; the last list stands until a read fails."""
        if self._library is None:
            return None, "none"
        if self._failed_at is not None and now - self._failed_at < RETRY_AFTER:
            return None, self._failed_as
        try:
            films = self._library.films()
        except LibraryError as exc:
            failed_as: LibraryState = "refused" if isinstance(exc, LibraryRefused) else "unreachable"
            if self._failed_at is None or failed_as != self._failed_as:
                warn_library(exc, failed_as)
            self._failed_at, self._failed_as = now, failed_as
            return None, failed_as
        if self._failed_at is not None:
            log.info("the media server answers again")
        self._failed_at = None
        return films, "usable"

    def _catalog(self, table: FilmTable) -> Catalog:
        """The engine's catalog for `table`; NothingToShow when Matinee's own shipped data cannot make one."""
        try:
            catalog = self._catalog_of(table)
        except BROKEN_DATA as exc:
            if self.broken is None:
                log.error(
                    "Matinee's own data cannot be used, so it offers no film: %s. Update or reinstall Matinee.", exc
                )
            self.broken = str(exc)
            raise NothingToShow(self.broken) from exc
        self.broken = None
        return catalog

    def showing(self) -> Showing:
        """The current catalog, rebuilt from a fresh film list when the last read is older than LIVE_TTL."""
        with self._lock:
            self._reload_table_if_replaced()
            self._say_if_stale()
            now = self._clock()
            if self._showing is not None and now - self._showing.read_at < self._ttl(self._showing):
                return self._showing
            films, state = self._read_library(now)
            table, unknown = with_live(self._table, films, self._listed)
            if unknown:
                log.info("%d films not yet in the film table, offered by genre alone: %s", len(unknown), unknown)
            self._showing = Showing(self._catalog(table), len(table.films), now, state)
            return self._showing

    @property
    def stale(self) -> bool:
        """Whether the film table's TMDB facts are six months old or more, which TMDB's terms forbid keeping."""
        return is_stale(self._table)

    def _say_if_stale(self) -> None:
        stale = self.stale
        if stale and not self._stale_said:
            log.error(
                "the film table's TMDB facts were fetched %s, over six months ago, and TMDB's terms forbid keeping"
                " them. Meanwhile Matinee keeps picking and warns on every screen. Run the rebuild"
                " (tools/rebuild_table.py) to refresh them.",
                f"{self._table.oldest_tmdb:%Y-%m-%d}",
            )
        self._stale_said = stale

    @property
    def oldest_tmdb(self) -> datetime | None:
        """When the film table's oldest TMDB fact was fetched; None when it holds none."""
        return self._table.oldest_tmdb

    @property
    def table_films(self) -> int:
        """How many films the film table on disk holds, whether or not any is offered now."""
        return len(self._table.films)

    @staticmethod
    def _ttl(showing: Showing) -> float:
        """How long a showing stands: LIVE_TTL, or RETRY_AFTER while the library cannot be read."""
        return RETRY_AFTER if showing.library in UNUSABLE else LIVE_TTL

    @property
    def library(self) -> Library | None:
        return self._library
