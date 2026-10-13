"""The one door to the media server. No other module calls a media server directly.

A reader only ever reads. The Jellyfin reader and the Plex reader both implement
the `Library` protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

ImageKind = Literal["poster", "backdrop"]


class LibraryError(RuntimeError):
    """The media server could not be read, or answered in a shape this reader does not understand."""


class LibraryRefused(LibraryError):
    """The media server answered, and turned down Matinee's key (HTTP 401 or 403)."""


REFUSED_CODES = (401, 403)


@dataclass(frozen=True)
class LibraryFilm:
    """One film file the media server holds, as far as Matinee needs it.

    `path_tmdb` is the TMDB id written in the file's folder name as `{tmdb-N}`,
    when there is one; the path itself never leaves the reader. `audio` is the
    two-letter languages its audio tracks are tagged with (`matinee.languages`),
    read only when asked for, and None when not read or when every track is
    untagged.
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
    audio: frozenset[str] | None = None


@dataclass(frozen=True)
class Image:
    body: bytes
    content_type: str


class Library(Protocol):
    def films(self, audio: bool = False) -> list[LibraryFilm]:
        """Every film the library holds, one entry per file; with `audio`, each with its audio tracks' languages,
        which costs the server more and is asked for only by the nightly rebuild."""
        ...

    def synopsis(self, item_id: str) -> str | None:
        """The film's synopsis as the media server holds it, or None when it has none."""
        ...

    def image(self, item_id: str, kind: ImageKind, width: int) -> Image:
        """The film's poster or backdrop, scaled by the server to `width` pixels."""
        ...
