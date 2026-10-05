"""What the server currently shows: the film table as the library holds it now, prepared for the engine.

The film list is read from the media server live, at most every `LIVE_TTL`
seconds. While it cannot be read the library cannot be used: no film counts as
held, and the films the labels name are offered alone. For `RETRY_AFTER` seconds
after a failed read no new read is attempted, so a hung server cannot queue every
request behind it. With no media server configured there is no list to read.

The table file is reloaded when the rebuild replaces it, and its TMDB age is
checked on every call. A table that is absent, or that cannot be read, counts as
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
from pathlib import Path
from typing import Literal

from matinee.engine import Catalog, EngineError, load_catalog
from matinee.labels import LabelsError
from matinee.library import Library, LibraryError, LibraryFilm
from matinee.reference import ReferenceError
from matinee.table import FilmTable, TableError, check_age, empty_table, load_table, with_live
from matinee.trees import TreeError

LIVE_TTL = 300.0
RETRY_AFTER = 15.0
log = logging.getLogger("matinee.theatre")

LibraryState = Literal["none", "usable", "unreachable"]
BROKEN_DATA = (EngineError, LabelsError, ReferenceError, TreeError, TableError, OSError, KeyError, json.JSONDecodeError)


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
        self.broken: str | None = None  # why Matinee's own data cannot make a catalog, as last found
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
            return None, "unreachable"
        try:
            films = self._library.films()
        except LibraryError as exc:
            if self._failed_at is None:
                log.warning(
                    "the media server could not be read: %s. Meanwhile Matinee recommends from the films the labels"
                    " name. It tries again every %d seconds; check that the server is running and its address is"
                    " right.",
                    exc,
                    int(RETRY_AFTER),
                )
            self._failed_at = now
            return None, "unreachable"
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
            check_age(self._table)
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
    def table_films(self) -> int:
        """How many films the film table on disk holds, whether or not any is offered now."""
        return len(self._table.films)

    @staticmethod
    def _ttl(showing: Showing) -> float:
        """How long a showing stands: LIVE_TTL, or RETRY_AFTER while the library cannot be read."""
        return RETRY_AFTER if showing.library == "unreachable" else LIVE_TTL

    @property
    def library(self) -> Library | None:
        return self._library
