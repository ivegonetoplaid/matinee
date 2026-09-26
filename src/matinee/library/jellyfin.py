"""The Jellyfin reader. Every request it makes is an HTTP GET.

The server address and key arrive as arguments. The key travels only in the
`X-Emby-Token` header of requests to that server and is never logged.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

from matinee.library import Image, ImageKind, LibraryError, LibraryFilm

FIELDS = "Genres,ProviderIds,ProductionYear,OfficialRating,RunTimeTicks,CommunityRating,Path"
TICKS_PER_MINUTE = 600_000_000
PATH_TMDB = re.compile(r"\{tmdb-(\d+)\}")
TIMEOUT_S = 60
IMAGE_TIMEOUT_S = 10
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ITEM_ID = re.compile(r"^[0-9a-f]{32}$")
IMAGE_PATHS = {"poster": "Primary", "backdrop": "Backdrop/0"}


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _float_or_none(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def parse_film(item: Mapping[str, Any]) -> LibraryFilm:
    """One Jellyfin movie item as a LibraryFilm; raises LibraryError when it has no id or name."""
    item_id, name = item.get("Id"), item.get("Name")
    if not isinstance(item_id, str) or not isinstance(name, str):
        raise LibraryError(f"a Jellyfin movie item has no Id or Name: keys {sorted(item)}")
    ticks = _float_or_none(item.get("RunTimeTicks"))
    tags = PATH_TMDB.findall(str(item.get("Path") or ""))
    return LibraryFilm(
        item_id=item_id,
        tmdb=_int_or_none((item.get("ProviderIds") or {}).get("Tmdb")),
        name=name,
        year=_int_or_none(item.get("ProductionYear")),
        genres=frozenset(g for g in item.get("Genres") or [] if isinstance(g, str)),
        certificate=str(item.get("OfficialRating") or ""),
        runtime_min=None if ticks is None else ticks / TICKS_PER_MINUTE,
        rating=_float_or_none(item.get("CommunityRating")),
        path_tmdb=int(tags[-1]) if tags else None,
    )


class JellyfinReader:
    """Reads films from one Jellyfin server."""

    def __init__(self, base_url: str, api_key: str) -> None:
        if not base_url or not api_key:
            raise LibraryError("the Jellyfin reader needs a server address and an API key")
        self._base = base_url.rstrip("/")
        self._key = api_key

    def _get_json(self, path: str) -> Any:
        req = urllib.request.Request(f"{self._base}{path}", headers={"X-Emby-Token": self._key}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            raise LibraryError(f"Jellyfin answered HTTP {exc.code} to GET {path.split('?')[0]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LibraryError(f"Jellyfin could not be reached: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LibraryError(f"Jellyfin answered GET {path.split('?')[0]} with something that is not JSON") from exc

    def _item(self, item_id: str) -> str:
        """The item id, refused unless it has Jellyfin's shape, so nothing else is ever joined into a path."""
        if not ITEM_ID.match(item_id):
            raise LibraryError(f"not a Jellyfin item id: {item_id!r}")
        return item_id

    def synopsis(self, item_id: str) -> str | None:
        body = self._get_json(f"/Items?Ids={self._item(item_id)}&Fields=Overview")
        items = body.get("Items") if isinstance(body, dict) else None
        if not isinstance(items, list) or not items:
            return None
        overview = items[0].get("Overview")
        return overview if isinstance(overview, str) and overview.strip() else None

    def image(self, item_id: str, kind: ImageKind, width: int) -> Image:
        """Jellyfin serves images without a key, so the request carries none."""
        url = f"{self._base}/Items/{self._item(item_id)}/Images/{IMAGE_PATHS[kind]}?maxWidth={int(width)}&quality=80"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=IMAGE_TIMEOUT_S) as resp:
                content_type = resp.headers.get("Content-Type", "")
                body = resp.read(MAX_IMAGE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise LibraryError(f"Jellyfin answered HTTP {exc.code} for a {kind} image") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LibraryError(f"Jellyfin could not be reached for a {kind} image: {exc}") from exc
        if not content_type.startswith("image/") or len(body) > MAX_IMAGE_BYTES:
            raise LibraryError(f"Jellyfin answered a {kind} image request with {content_type or 'no type'}")
        return Image(body, content_type)

    def films(self) -> list[LibraryFilm]:
        body = self._get_json(f"/Items?IncludeItemTypes=Movie&Recursive=true&Fields={FIELDS}")
        items = body.get("Items") if isinstance(body, dict) else None
        if not isinstance(items, list):
            raise LibraryError("Jellyfin's film list has no Items array")
        return [parse_film(it) for it in items]
