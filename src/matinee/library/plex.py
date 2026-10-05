"""The Plex reader. Every request it makes is an HTTP GET.

The server address and token arrive as arguments. The token travels only in the
`X-Plex-Token` header of requests to that server and is never logged or put in a
URL, and never follows a redirect. Films come from every movie section. A film's
TMDB id is read from its `tmdb://` guid, or from the guid the legacy "The Movie
Database" agent wrote. Plex writes a US age rating bare and every other country's
with its prefix (`gb/15`); a `us/` prefix is dropped, and any other is kept, so a
rating from another country's system never passes the kids gate by sharing a name
with a US one.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Iterator, Mapping
from typing import Any

from matinee.library import Image, ImageKind, LibraryError, LibraryFilm

TIMEOUT_S = 60
IMAGE_TIMEOUT_S = 10
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ITEM_ID = re.compile(r"^[0-9]{1,12}$")
TMDB_GUID = re.compile(r"^tmdb://([0-9]+)$")
LEGACY_TMDB_GUID = re.compile(r"^com\.plexapp\.agents\.themoviedb://([0-9]+)(?:\?|$)")
PATH_TMDB = re.compile(r"\{tmdb-(\d+)\}")
US_PREFIX = re.compile(r"^us/", re.IGNORECASE)
MS_PER_MINUTE = 60_000
IMAGE_PATHS = {"poster": "thumb", "backdrop": "art"}
IMAGE_SHAPES = {"poster": 1.5, "backdrop": 0.5625}  # height over width
SMALL_IMAGE_PX = 160  # an image this wide or narrower is a wall tile, shown dimmed, so it is fetched lighter
SMALL_IMAGE_QUALITY = 60
IMAGE_QUALITY = 80


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, int | float) else None


def _tags(item: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    found = item.get(key)
    return [t for t in found if isinstance(t, dict)] if isinstance(found, list) else []


def _tmdb(item: Mapping[str, Any]) -> int | None:
    for guid in _tags(item, "Guid"):
        match = TMDB_GUID.match(str(guid.get("id", "")))
        if match:
            return int(match.group(1))
    legacy = LEGACY_TMDB_GUID.match(str(item.get("guid") or ""))
    return int(legacy.group(1)) if legacy else None


def _files(item: Mapping[str, Any]) -> Iterator[str]:
    for media in _tags(item, "Media"):
        for part in _tags(media, "Part"):
            yield str(part.get("file") or "")


def certificate(raw: object) -> str:
    """The age rating as the kids pool reads it: a `us/` prefix is dropped, any other country's kept whole."""
    return US_PREFIX.sub("", str(raw or "").strip())


def parse_film(item: Mapping[str, Any]) -> LibraryFilm:
    """One Plex movie as a LibraryFilm; raises LibraryError when it has no ratingKey."""
    item_id = item.get("ratingKey")
    if not isinstance(item_id, str) or not ITEM_ID.match(item_id):
        raise LibraryError(f"a Plex movie has no usable ratingKey: keys {sorted(item)}")
    duration = _float_or_none(item.get("duration"))
    rating = _float_or_none(item.get("audienceRating"))
    tags = [t for f in _files(item) for t in PATH_TMDB.findall(f)]
    return LibraryFilm(
        item_id=item_id,
        tmdb=_tmdb(item),
        name=str(item.get("title") or ""),
        year=_int_or_none(item.get("year")),
        genres=frozenset(str(g["tag"]) for g in _tags(item, "Genre") if isinstance(g.get("tag"), str)),
        certificate=certificate(item.get("contentRating")),
        runtime_min=None if duration is None else duration / MS_PER_MINUTE,
        rating=_float_or_none(item.get("rating")) if rating is None else rating,
        path_tmdb=int(tags[-1]) if tags else None,
    )


class PlexReader:
    """Reads films from one Plex server."""

    def __init__(self, base_url: str, token: str) -> None:
        if not base_url or not token:
            raise LibraryError("the Plex reader needs a server address and a token")
        if not base_url.startswith(("http://", "https://")):
            raise LibraryError("the Plex address must start with http:// or https://")
        self._base = base_url.rstrip("/")
        self._token = token

    def _get(self, path: str, accept: str, timeout: float, limit: int = -1) -> tuple[str, bytes]:
        """One GET, reading at most `limit` bytes (all with -1); the token goes in the header only. Errors name
        the path, never the query or the token."""
        req = urllib.request.Request(f"{self._base}{path}", headers={"Accept": accept}, method="GET")
        req.add_unredirected_header("X-Plex-Token", self._token)  # a redirect elsewhere never carries it
        where = path.split("?")[0]
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.headers.get("Content-Type", ""), resp.read(limit)
        except urllib.error.HTTPError as exc:
            raise LibraryError(f"Plex answered HTTP {exc.code} to GET {where}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LibraryError(f"Plex could not be reached for GET {where}: {type(exc).__name__}") from exc

    def _get_json(self, path: str) -> Any:
        _, body = self._get(path, "application/json", TIMEOUT_S)
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise LibraryError(f"Plex answered GET {path.split('?')[0]} with something that is not JSON") from exc

    def _container(self, path: str, key: str) -> list[Mapping[str, Any]]:
        body = self._get_json(path)
        container = body.get("MediaContainer") if isinstance(body, dict) else None
        if not isinstance(container, dict):
            raise LibraryError(f"Plex's answer to GET {path.split('?')[0]} has no MediaContainer")
        return _tags(container, key)

    def _item(self, item_id: str) -> str:
        """The item id, refused unless it has Plex's shape, so nothing else is ever joined into a path."""
        if not ITEM_ID.match(item_id):
            raise LibraryError(f"not a Plex item id: {item_id!r}")
        return item_id

    def films(self) -> list[LibraryFilm]:
        sections = [d for d in self._container("/library/sections", "Directory") if d.get("type") == "movie"]
        films: list[LibraryFilm] = []
        for section in sections:
            key = str(section.get("key", ""))
            if not key.isdigit():
                raise LibraryError("a Plex movie section has no usable key")
            items = self._container(f"/library/sections/{key}/all?type=1&includeGuids=1", "Metadata")
            films.extend(parse_film(it) for it in items)
        return films

    def synopsis(self, item_id: str) -> str | None:
        items = self._container(f"/library/metadata/{self._item(item_id)}", "Metadata")
        summary = items[0].get("summary") if items else None
        return summary if isinstance(summary, str) and summary.strip() else None

    def image(self, item_id: str, kind: ImageKind, width: int) -> Image:
        """The poster or backdrop through Plex's photo transcoder, `width` pixels wide, its shape kept. An
        image at most SMALL_IMAGE_PX wide is asked for at SMALL_IMAGE_QUALITY, any other at IMAGE_QUALITY."""
        quality = SMALL_IMAGE_QUALITY if width <= SMALL_IMAGE_PX else IMAGE_QUALITY
        height = round(int(width) * IMAGE_SHAPES[kind])
        source = f"/library/metadata/{self._item(item_id)}/{IMAGE_PATHS[kind]}"
        query = f"width={int(width)}&height={height}&minSize=1&upscale=1&quality={quality}&url={source}"
        content_type, body = self._get(f"/photo/:/transcode?{query}", "image/*", IMAGE_TIMEOUT_S, MAX_IMAGE_BYTES + 1)
        if not content_type.startswith("image/") or len(body) > MAX_IMAGE_BYTES:
            raise LibraryError(f"Plex answered a {kind} image request with {content_type or 'no type'}")
        return Image(body, content_type)
