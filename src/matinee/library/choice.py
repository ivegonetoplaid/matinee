"""Which media server an installation reads, chosen by which settings are filled in.

Jellyfin is read when `JELLYFIN_URL` and `JELLYFIN_API_KEY` are set, Plex when
`PLEX_URL` and `PLEX_TOKEN` are. No setting names the server. An address must
start with `http://` or `https://`. Both servers set, neither, or an address
without its key is refused here; the caller decides what that means for the start.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from matinee.library import Library
from matinee.library.jellyfin import JellyfinReader
from matinee.library.plex import PlexReader

ServerKind = Literal["jellyfin", "plex"]
SETTINGS: dict[ServerKind, tuple[str, str]] = {
    "jellyfin": ("JELLYFIN_URL", "JELLYFIN_API_KEY"),
    "plex": ("PLEX_URL", "PLEX_TOKEN"),
}


class ServerChoiceError(ValueError):
    """The media server settings name no server, both servers, or an address without its key; never the key."""


@dataclass(frozen=True)
class MediaServer:
    kind: ServerKind
    url: str
    key: str = field(repr=False)


def _filled(env: Mapping[str, str], kind: ServerKind) -> MediaServer | None:
    url_name, key_name = SETTINGS[kind]
    url, key = env.get(url_name, "").strip(), env.get(key_name, "").strip()
    if not url and not key:
        return None
    if not url or not key:
        raise ServerChoiceError(f"{url_name} and {key_name} must be set together")
    if not url.startswith(("http://", "https://")):
        raise ServerChoiceError(f"{url_name} must start with http:// or https://")
    return MediaServer(kind, url.rstrip("/"), key)


def media_server(env: Mapping[str, str]) -> MediaServer:
    """The one media server the settings name; raises ServerChoiceError for none, both, or a half-set one."""
    filled = [s for s in (_filled(env, "jellyfin"), _filled(env, "plex")) if s is not None]
    if not filled:
        raise ServerChoiceError(
            "no media server is set: fill in JELLYFIN_URL and JELLYFIN_API_KEY, or PLEX_URL and PLEX_TOKEN"
        )
    if len(filled) == 2:
        raise ServerChoiceError("Jellyfin and Plex are both set; Matinee reads one, so remove one of them")
    return filled[0]


def open_reader(server: MediaServer) -> Library:
    """The reader for `server`."""
    if server.kind == "plex":
        return PlexReader(server.url, server.key)
    return JellyfinReader(server.url, server.key)
