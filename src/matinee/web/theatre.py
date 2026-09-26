"""What the server currently shows: the film table as the library holds it now, prepared for the engine.

The film list is read from the media server live, at most every `LIVE_TTL`
seconds. When the media server cannot be read, nothing is served from an older
list: every call raises `LibraryUnavailable` until a read succeeds again, and
for `RETRY_AFTER` seconds after a failed read no new read is attempted, so a hung
server cannot queue every request behind it. The table file is reloaded when
the nightly rebuild replaces it, and its TMDB age is checked on every call.
Building the theatre prepares the catalog once from the table alone, so missing
reference statistics or malformed trees stop the server at start-up.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from matinee.engine import Catalog, load_catalog
from matinee.library import Library, LibraryError
from matinee.table import FilmTable, check_age, load_table, with_live

LIVE_TTL = 300.0
RETRY_AFTER = 15.0
log = logging.getLogger("matinee.theatre")


class LibraryUnavailable(RuntimeError):
    """The media server could not be read just now."""


@dataclass(frozen=True)
class Showing:
    catalog: Catalog
    now_showing: int
    read_at: float


class Theatre:
    def __init__(
        self,
        library: Library,
        table_path: Path,
        clock: Callable[[], float] = time.monotonic,
        catalog_of: Callable[[FilmTable], Catalog] = load_catalog,
    ) -> None:
        self._library = library
        self._table_path = table_path
        self._clock = clock
        self._catalog_of = catalog_of
        self._lock = threading.Lock()
        self._table = load_table(table_path)
        self._table_mtime = table_path.stat().st_mtime
        self._showing: Showing | None = None
        self._failed_at: float | None = None
        catalog_of(self._table)

    def _reload_table_if_replaced(self) -> None:
        mtime = self._table_path.stat().st_mtime
        if mtime != self._table_mtime:
            self._table = load_table(self._table_path)
            self._table_mtime = mtime
            self._showing = None
            log.info("film table reloaded: %d films", len(self._table.films))

    def showing(self) -> Showing:
        """The current catalog, rebuilt from a fresh film list when the last read is older than LIVE_TTL."""
        with self._lock:
            self._reload_table_if_replaced()
            check_age(self._table)
            now = self._clock()
            if self._showing is not None and now - self._showing.read_at < LIVE_TTL:
                return self._showing
            if self._failed_at is not None and now - self._failed_at < RETRY_AFTER:
                raise LibraryUnavailable("the library could not be reached moments ago")
            try:
                films = self._library.films()
            except LibraryError as exc:
                self._showing, self._failed_at = None, now
                log.warning("the media server could not be read: %s", exc)
                raise LibraryUnavailable("the library cannot be reached") from exc
            self._failed_at = None
            table, unknown = with_live(self._table, films)
            if unknown:
                log.info("%d films not yet in the film table, offered by genre alone: %s", len(unknown), unknown)
            count = len({f.tmdb for f in films if f.tmdb is not None})
            self._showing = Showing(self._catalog_of(table), count, now)
            return self._showing

    @property
    def library(self) -> Library:
        return self._library
