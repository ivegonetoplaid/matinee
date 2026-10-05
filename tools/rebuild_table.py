"""Rebuild the offline film table: refresh TMDB for every library film, then write the table.

Reads the media server (GET only), the shipped genome scores and the TMDB cache,
and writes `<state>/films.sqlite`, replacing the previous table only once the new
one is complete. Prints what it saw, including every file whose `{tmdb-N}` folder
tag differs from the server's TMDB id; it uses the server's id and changes
nothing. With `--daily HH:MM` it rebuilds now and then every day at that local
time, which is how the deployed stack runs it every night.

Settings come from the environment: DATA_DIR (or `--state`), the media server
(JELLYFIN_URL and JELLYFIN_API_KEY, or PLEX_URL and PLEX_TOKEN) and TMDB_TOKEN.

Usage: python3 tools/rebuild_table.py [--state DIR] [--daily HH:MM]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from matinee.genome_file import load_scores
from matinee.library.choice import MediaServer, ServerChoiceError, media_server, open_reader
from matinee.table import build_table, write_table
from matinee.tmdb import load_cache, refresh

log = logging.getLogger("rebuild_table")
DEFAULT_STATE = Path.home() / ".local/share/matinee"


def rebuild(server: MediaServer, state: Path, token: str) -> None:
    films = open_reader(server).films()
    cache = state / "tmdb" / "films.jsonl"
    ids = sorted({f.tmdb for f in films if f.tmdb is not None})
    fetched, failed = refresh(ids, cache, token)
    log.info("TMDB: fetched %d, failed %d", fetched, failed)
    table, report = build_table(films, load_scores(), load_cache(cache), datetime.now(UTC))
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
    parser.add_argument("--state", type=Path, default=Path(os.environ.get("DATA_DIR", DEFAULT_STATE)))
    parser.add_argument(
        "--daily", type=daily_time, metavar="HH:MM", help="rebuild now, then every day at this local time"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    token = os.environ.get("TMDB_TOKEN", "").strip()
    if not token:
        parser.error("TMDB_TOKEN is required")
    try:
        server = media_server(os.environ)
    except ServerChoiceError as exc:
        parser.error(str(exc))
    if not args.state.is_dir():
        parser.error(f"the state directory {args.state} does not exist")
    if not args.daily:
        rebuild(server, args.state, token)
        return 0
    while True:
        try:
            rebuild(server, args.state, token)
        except Exception as exc:  # any failure waits for the next night, never a restart loop
            log.warning("rebuild failed; the previous table stays in place: %s", exc, exc_info=True)
        time.sleep(seconds_until(args.daily, datetime.now()))


if __name__ == "__main__":
    sys.exit(main())
