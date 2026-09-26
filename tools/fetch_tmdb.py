"""Fetch TMDB collection membership, keywords and original language for every library film.

Resumable: a film fetched less than 150 days ago is skipped, so re-running
refreshes only what is stale or missing. The nightly rebuild runs the same fetch
first; this tool runs it alone.

Usage: JELLYFIN_API_KEY=... TMDB_READ_TOKEN=... python3 tools/fetch_tmdb.py --jellyfin URL [--out FILE]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from matinee.library.jellyfin import JellyfinReader
from matinee.tmdb import refresh

DEFAULT_CACHE = Path.home() / ".local/share/matinee/tmdb/films.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jellyfin", required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    token = os.environ.get("TMDB_READ_TOKEN", "").strip()
    jf_key = os.environ.get("JELLYFIN_API_KEY", "").strip()
    if not token or not jf_key:
        parser.error("TMDB_READ_TOKEN and JELLYFIN_API_KEY must be set")
    ids = sorted({f.tmdb for f in JellyfinReader(args.jellyfin, jf_key).films() if f.tmdb is not None})
    fetched, failed = refresh(ids, args.out, token)
    logging.info("fetched %d, failed %d", fetched, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
