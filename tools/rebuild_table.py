"""Rebuild the offline film table: refresh TMDB for every library film, then write the table.

Reads the media server (GET only), the local ml-latest genome and the TMDB cache,
and writes `<state>/films.sqlite`, replacing the previous table only once the new
one is complete. Prints what it saw, including every file whose `{tmdb-N}` folder
tag differs from the server's TMDB id; it uses the server's id and changes
nothing. With `--daily HH:MM` it rebuilds now and then every day at that local
time, which is how the deployed stack runs it every night.

Settings come from flags or the environment: MATINEE_JELLYFIN_URL, MATINEE_STATE,
MATINEE_ML, and the keys JELLYFIN_API_KEY and TMDB_READ_TOKEN (environment only).

Usage: python3 tools/rebuild_table.py [--jellyfin URL] [--state DIR] [--ml DIR] [--daily HH:MM]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path

from matinee.genome import GenomeError, load_genome
from matinee.library import LibraryError
from matinee.library.jellyfin import JellyfinReader
from matinee.table import TableError, build_table, write_table
from matinee.tmdb import load_cache, refresh

log = logging.getLogger("rebuild_table")
DEFAULT_STATE = Path.home() / ".local/share/matinee"


def rebuild(jellyfin: str, state: Path, ml: Path, jf_key: str, token: str) -> None:
    films = JellyfinReader(jellyfin, jf_key).films()
    cache = state / "tmdb" / "films.jsonl"
    ids = sorted({f.tmdb for f in films if f.tmdb is not None})
    fetched, failed = refresh(ids, cache, token)
    log.info("TMDB: fetched %d, failed %d", fetched, failed)
    genome = load_genome(ml, cache=ml / "genome-matrix.npz")
    table, report = build_table(films, genome, load_cache(cache), datetime.now(UTC))
    write_table(table, state / "films.sqlite")
    for line in report.lines():
        log.info("%s", line)
    log.info("wrote %d films to %s", len(table.films), state / "films.sqlite")


def daily_time(text: str) -> tuple[int, int]:
    """An HH:MM time of day, checked before the first rebuild so a typo fails at once."""
    try:
        hour, minute = (int(x) for x in text.split(":"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected HH:MM, got {text!r}") from exc
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise argparse.ArgumentTypeError(f"expected HH:MM, got {text!r}")
    return hour, minute


def seconds_until(at: tuple[int, int], now: datetime) -> float:
    hour, minute = at
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jellyfin", default=os.environ.get("MATINEE_JELLYFIN_URL", ""))
    parser.add_argument("--state", type=Path, default=Path(os.environ.get("MATINEE_STATE", DEFAULT_STATE)))
    parser.add_argument("--ml", type=Path, default=None, help="ml-latest directory (default <state>/ml-latest)")
    parser.add_argument(
        "--daily", type=daily_time, metavar="HH:MM", help="rebuild now, then every day at this local time"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    jf_key = os.environ.get("JELLYFIN_API_KEY", "").strip()
    token = os.environ.get("TMDB_READ_TOKEN", "").strip()
    if not (args.jellyfin and jf_key and token):
        parser.error("the Jellyfin address, JELLYFIN_API_KEY and TMDB_READ_TOKEN are all required")
    if not args.state.is_dir():
        parser.error(f"the state directory {args.state} does not exist")
    ml = args.ml or Path(os.environ.get("MATINEE_ML", args.state / "ml-latest"))
    if not args.daily:
        rebuild(args.jellyfin, args.state, ml, jf_key, token)
        return 0
    while True:
        try:
            rebuild(args.jellyfin, args.state, ml, jf_key, token)
        except (LibraryError, GenomeError, TableError, OSError, urllib.error.URLError) as exc:
            log.warning("rebuild failed; the previous table stays in place: %s", exc, exc_info=True)
        time.sleep(seconds_until(args.daily, datetime.now()))


if __name__ == "__main__":
    sys.exit(main())
