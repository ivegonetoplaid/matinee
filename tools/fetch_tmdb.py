"""Fetch TMDB collection membership and keywords for every library film.

One request per film (movie details with keywords appended), paced well under
TMDB's limits, resumable: a film fetched less than MAX_AGE ago is skipped, so
re-running refreshes only what is stale. TMDB's terms allow caching for at most
six months and require attribution in the application.

Output: one JSON line per film in OUT; the newest line per TMDB id wins.

Usage: JELLYFIN_API_KEY=... TMDB_READ_TOKEN=... python3 tools/fetch_tmdb.py --jellyfin URL [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from check_trees import load_library

API = "https://api.themoviedb.org/3"
PAUSE_S = 0.15
MAX_AGE = timedelta(days=150)
MAX_CONSECUTIVE_ERRORS = 5

log = logging.getLogger("fetch_tmdb")


@dataclass(frozen=True)
class TmdbFilm:
    tmdb: int
    fetched_at: str
    collection_id: int | None
    collection_name: str | None
    keywords: list[str]


def get_json(url: str, token: str) -> dict[str, Any] | None:
    """One paced GET. Honours Retry-After on 429; a 404 returns None."""
    while True:
        time.sleep(PAUSE_S)
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data: dict[str, Any] = json.load(resp)
                return data
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = int(exc.headers.get("Retry-After", 10))
                log.warning("429, waiting %ss", wait)
                time.sleep(wait)
                continue
            if exc.code == 404:
                return None
            raise


def fetch_film(tmdb: int, token: str) -> TmdbFilm:
    body = get_json(f"{API}/movie/{tmdb}?append_to_response=keywords", token) or {}
    coll = body.get("belongs_to_collection") or {}
    words = [k["name"] for k in (body.get("keywords") or {}).get("keywords", [])]
    return TmdbFilm(tmdb, datetime.now(UTC).isoformat(), coll.get("id"), coll.get("name"), words)


def fresh_ids(out: Path) -> set[int]:
    """TMDB ids fetched less than MAX_AGE ago."""
    if not out.exists():
        return set()
    now = datetime.now(UTC)
    fresh = set()
    for line in out.read_text().splitlines():
        rec = json.loads(line)
        if now - datetime.fromisoformat(rec["fetched_at"]) < MAX_AGE:
            fresh.add(rec["tmdb"])
    return fresh


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jellyfin", required=True)
    parser.add_argument("--out", type=Path, default=Path.home() / ".local/share/matinee/tmdb/films.jsonl")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    token = os.environ.get("TMDB_READ_TOKEN", "").strip()
    jf_key = os.environ.get("JELLYFIN_API_KEY", "").strip()
    if not token or not jf_key:
        parser.error("TMDB_READ_TOKEN and JELLYFIN_API_KEY must be set")
    lib, _ = load_library(args.jellyfin, jf_key)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    todo = [t for t in lib.index if t not in fresh_ids(args.out)]
    log.info("%d of %d films to fetch", len(todo), len(lib))
    errors = 0
    with args.out.open("a") as out:
        for n, tmdb in enumerate(todo, 1):
            try:
                rec = fetch_film(int(tmdb), token)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                errors += 1
                log.warning("tmdb %s failed: %r", tmdb, exc)
                if errors >= MAX_CONSECUTIVE_ERRORS:
                    log.error("%d consecutive errors, stopping", errors)
                    return 1
                continue
            errors = 0
            out.write(json.dumps(asdict(rec)) + "\n")
            out.flush()
            if n % 250 == 0:
                log.info("%d/%d", n, len(todo))
    log.info("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
