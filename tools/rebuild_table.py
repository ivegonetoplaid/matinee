"""Rebuild the offline film table: refresh TMDB for every film the labels name and every library film, then write
the table.

Reads the media server when one is set (GET only), the shipped labels, the shipped
genome scores and the TMDB cache,
and writes `<state>/films.sqlite`, replacing the previous table only once the new
one is complete. Prints what it saw, including every file whose `{tmdb-N}` folder
tag differs from the server's TMDB id; it uses the server's id and changes
nothing. With `--daily HH:MM` it rebuilds now and then every day at that local
time, which is how the deployed stack runs it every night. It reports itself in
`rebuild.json` (`matinee.progress`): running, finished, or stopped with the reason,
such as no TMDB key, a refused key, or TMDB not answering. Without a key it
fetches nothing and writes no table.

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
from matinee.labels import LabelsError, load_labels, load_overrides
from matinee.library.choice import MediaServer, ServerChoiceError, configured_server, open_reader
from matinee.progress import RebuildStatus, write_status
from matinee.table import build_table, write_table
from matinee.tmdb import NO_KEY, compact, load_cache, refresh

log = logging.getLogger("rebuild_table")
DEFAULT_STATE = Path.home() / ".local/share/matinee"
FAILED = "the rebuild failed; its log says why"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def rebuild(server: MediaServer | None, state: Path, token: str) -> RebuildStatus:
    """One rebuild; returns, and leaves in `rebuild.json`, how it ended."""
    started = _now()
    cache = state / "tmdb" / "films.jsonl"
    if not token:
        if cache.exists():
            compact(cache, datetime.now(UTC))  # the six-month limit holds even when nothing can be fetched
        log.error("no TMDB key is set, so no film table can be built. Set TMDB_TOKEN and run the rebuild again.")
        return _report(state, RebuildStatus("stopped", started, _now(), reason=NO_KEY))
    try:
        return _rebuild(server, state, cache, token, started)
    except Exception:
        _report(state, RebuildStatus("stopped", started, _now(), reason=FAILED))
        raise


def _rebuild(server: MediaServer | None, state: Path, cache: Path, token: str, started: str) -> RebuildStatus:
    films = open_reader(server).films() if server is not None else []
    listed = load_labels().films() | household_films(state)
    ids = sorted(listed | {f.tmdb for f in films if f.tmdb is not None})
    write_status(state, RebuildStatus("running", started, _now(), total=len(ids)))
    result = refresh(ids, cache, token)
    log.info("TMDB: fetched %d, failed %d", result.fetched, result.failed)
    table, report = build_table(films, load_scores(), load_cache(cache), datetime.now(UTC), listed)
    write_table(table, state / "films.sqlite")
    for line in report.lines():
        log.info("%s", line)
    log.info("wrote %d films to %s", len(table.films), state / "films.sqlite")
    if result.stopped is not None:
        return _report(state, RebuildStatus("stopped", started, _now(), result.fetched, len(ids), result.stopped))
    return _report(state, RebuildStatus("finished", started, _now(), len(ids), len(ids)))


def household_films(state: Path) -> frozenset[int]:
    """The films the household override file names, so their records are fetched too; none when it cannot be
    read (the server's setup note names that)."""
    try:
        theirs = load_overrides(state)
    except LabelsError as exc:
        log.warning("the override file cannot be read, so the rebuild fetches only the shipped films: %s", exc)
        return frozenset()
    return frozenset() if theirs is None else theirs.named()


def _report(state: Path, status: RebuildStatus) -> RebuildStatus:
    write_status(state, status)
    return status


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
    try:
        server = configured_server(os.environ)
    except ServerChoiceError as exc:
        server = None
        log.warning("%s. Meanwhile the rebuild reads no library and fetches the films the labels name.", exc)
    if not args.state.is_dir():
        parser.error(f"the state directory {args.state} does not exist")
    if not args.daily:
        return 0 if rebuild(server, args.state, token).state == "finished" else 1
    while True:
        try:
            rebuild(server, args.state, token)
        except Exception as exc:  # any failure waits for the next night, never a restart loop
            log.warning("rebuild failed; the previous table stays in place: %s", exc, exc_info=True)
        time.sleep(seconds_until(args.daily, datetime.now()))


if __name__ == "__main__":
    sys.exit(main())
