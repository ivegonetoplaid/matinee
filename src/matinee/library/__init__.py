"""The one door to the media server. No other module calls a media server directly.

A reader only ever reads. The first build has one implementation, Jellyfin; a
Plex reader would sit behind the same `Library` protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LibraryError(RuntimeError):
    """The media server could not be read, or answered in a shape this reader does not understand."""


@dataclass(frozen=True)
class LibraryFilm:
    """One film file the media server holds, as far as Matinee needs it.

    `path_tmdb` is the TMDB id written in the file's folder name as `{tmdb-N}`,
    when there is one; the path itself never leaves the reader.
    """

    item_id: str
    tmdb: int | None
    name: str
    year: int | None
    genres: frozenset[str]
    certificate: str
    runtime_min: float | None
    rating: float | None
    path_tmdb: int | None


class Library(Protocol):
    def films(self) -> list[LibraryFilm]:
        """Every film the library holds, one entry per file."""
        ...
