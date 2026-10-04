"""TMDB facts per film: collection, keywords, original language and picture paths, cached as JSON lines.

One GET per film (movie details with keywords appended), paced well under TMDB's
limits. New records are appended and the newest line per TMDB id wins; after
each refresh the file is rewritten atomically to hold only the newest record per
id, and nothing older than `MAX_AGE`, because TMDB's terms cap caching at six
months. A record is refetched after `REFETCH_AFTER`. A film TMDB does not know
(404) is never cached, so it reads as missing. A line that does not parse is
skipped with a warning and its film is fetched again.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

API = "https://api.themoviedb.org/3"
PAUSE_S = 0.15
REFETCH_AFTER = timedelta(days=150)
MAX_AGE = timedelta(days=183)
MAX_CONSECUTIVE_ERRORS = 5
PICTURE_PATH = re.compile(r"^/[A-Za-z0-9]+\.(?:jpg|png)$")

log = logging.getLogger("matinee.tmdb")


@dataclass(frozen=True)
class TmdbFilm:
    tmdb: int
    fetched_at: str
    collection_id: int | None
    collection_name: str | None
    keywords: list[str]
    original_language: str | None = None
    # A picture path is None in a record written before paths were kept, and "" where TMDB has no picture.
    poster_path: str | None = None
    backdrop_path: str | None = None

    @property
    def fetched(self) -> datetime:
        return datetime.fromisoformat(self.fetched_at)


def _record(line: str) -> TmdbFilm | None:
    try:
        rec = json.loads(line)
        return TmdbFilm(
            tmdb=int(rec["tmdb"]),
            fetched_at=str(rec["fetched_at"]),
            collection_id=rec.get("collection_id"),
            collection_name=rec.get("collection_name"),
            keywords=list(rec.get("keywords") or []),
            original_language=rec.get("original_language"),
            poster_path=rec.get("poster_path"),
            backdrop_path=rec.get("backdrop_path"),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError):
        return None


def load_cache(path: Path) -> dict[int, TmdbFilm]:
    """The newest record per TMDB id; an absent file is an empty cache.

    A damaged line (a cut-off write, two records glued together) is skipped and
    logged, so its film reads as missing and is fetched again.
    """
    latest: dict[int, TmdbFilm] = {}
    if not path.exists():
        return latest
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        rec = _record(line)
        if rec is None:
            log.warning("TMDB cache %s line %d does not parse; skipped", path, number)
            continue
        latest[rec.tmdb] = rec
    return latest


def compact(path: Path, now: datetime) -> None:
    """Rewrite the cache with only the newest record per id younger than MAX_AGE, replacing it atomically."""
    keep = [r for r in load_cache(path).values() if now - r.fetched < MAX_AGE]
    partial = path.with_name(path.name + ".partial")
    partial.write_text("".join(json.dumps(asdict(r)) + "\n" for r in keep), encoding="utf-8")
    os.replace(partial, path)


def needs_fetch(rec: TmdbFilm | None, now: datetime) -> bool:
    """True when a film has no record, a record due for refresh, or one written before languages or picture
    paths were kept."""
    if rec is None or now - rec.fetched >= REFETCH_AFTER:
        return True
    return rec.original_language is None or rec.poster_path is None or rec.backdrop_path is None


def get_json(url: str, token: str) -> dict[str, Any] | None:
    """One paced GET. Honours Retry-After on 429; a 404 returns None."""
    while True:
        time.sleep(PAUSE_S)
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, method="GET"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data: dict[str, Any] = json.load(resp)
                return data
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = int(exc.headers.get("Retry-After", 10))
                log.warning("TMDB answered 429, waiting %ss", wait)
                time.sleep(wait)
                continue
            if exc.code == 404:
                return None
            raise


def picture_path(tmdb: int, field: str, value: object) -> str:
    """TMDB's path for one picture, or "" when it gives none. A value not shaped like a TMDB image path is
    logged and kept as none, so nothing else is ever joined into a picture's address."""
    if value is None or value == "":
        return ""
    if isinstance(value, str) and PICTURE_PATH.fullmatch(value):
        return value
    log.warning("TMDB gave film %s a %s not shaped like an image path; it is kept as none: %r", tmdb, field, value)
    return ""


def fetch_film(tmdb: int, token: str) -> TmdbFilm | None:
    """The film's TMDB facts, or None when TMDB does not know the id."""
    body = get_json(f"{API}/movie/{tmdb}?append_to_response=keywords", token)
    if body is None:
        return None
    coll = body.get("belongs_to_collection") or {}
    words = [k["name"] for k in (body.get("keywords") or {}).get("keywords", [])]
    return TmdbFilm(
        tmdb,
        datetime.now(UTC).isoformat(),
        coll.get("id"),
        coll.get("name"),
        words,
        body.get("original_language") or "",
        picture_path(tmdb, "poster_path", body.get("poster_path")),
        picture_path(tmdb, "backdrop_path", body.get("backdrop_path")),
    )


def refresh(
    ids: Iterable[int], cache: Path, token: str, fetch: Callable[[int, str], TmdbFilm | None] = fetch_film
) -> tuple[int, int]:
    """Fetch every id the cache lacks or holds stale, append them, then compact. Returns (fetched, failed).

    A film TMDB does not know counts as failed and is not cached. Stops after
    MAX_CONSECUTIVE_ERRORS network failures in a row, since that is an outage
    rather than a film. Compaction runs only after the loop finishes.
    """
    now = datetime.now(UTC)
    have = load_cache(cache)
    todo = [t for t in ids if needs_fetch(have.get(t), now)]
    log.info("TMDB: %d films to fetch", len(todo))
    cache.parent.mkdir(parents=True, exist_ok=True)
    fetched = failed = streak = 0
    with cache.open("a", encoding="utf-8") as out:
        for tmdb in todo:
            try:
                rec = fetch(tmdb, token)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                failed += 1
                streak += 1
                log.warning("TMDB %s failed: %r", tmdb, exc)
                if streak >= MAX_CONSECUTIVE_ERRORS:
                    log.error("TMDB: %d consecutive failures, stopping", streak)
                    break
                continue
            streak = 0
            if rec is None:
                failed += 1
                log.warning("TMDB does not know film %s; it stays without TMDB facts", tmdb)
                continue
            fetched += 1
            out.write(json.dumps(asdict(rec)) + "\n")
            out.flush()
    compact(cache, datetime.now(UTC))
    return fetched, failed
