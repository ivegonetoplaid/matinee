"""Rebuild the offline film table: refresh TMDB for every film the labels name and every library film, then write
the table.

Reads the media server when one is set (GET only), the shipped labels, the shipped
genome scores and the TMDB cache, and writes `<state>/films.sqlite`: once before
any fetch, every SAVE_EVERY new records while it fetches, most-voted first, and at
the end. Each write replaces the previous table whole. Prints what it saw, including every file whose `{tmdb-N}` folder
tag differs from the server's TMDB id; it uses the server's id and changes
nothing. With `--daily HH:MM` it rebuilds now and then every day at that local
time, which is how the deployed stack runs it every night; `--daily` alone takes
the time from REBUILD_TIME, 04:30 when unset. It reports itself in
`rebuild.json` (`matinee.progress`): running, with its progress at least every few
seconds while it fetches, finished, or stopped with the reason, such as no TMDB
key, a refused key, or TMDB not answering. Without a key it
fetches nothing and writes no table.

Settings come from the environment: DATA_DIR (or `--state`), the media server
(JELLYFIN_URL and JELLYFIN_API_KEY, or PLEX_URL and PLEX_TOKEN), TMDB_TOKEN,
TMDB_RATE and REBUILD_TIME.

Usage: python3 tools/rebuild_table.py [--state DIR] [--daily [HH:MM]]
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import shutil
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

from matinee.genome import Scores
from matinee.genome_file import load_scores
from matinee.labels import LabelsError, load_labels, load_overrides
from matinee.library import LibraryFilm
from matinee.library.choice import MediaServer, ServerChoiceError, configured_server, open_reader
from matinee.progress import RebuildStatus, write_status
from matinee.table import BuildReport, build_table, write_table
from matinee.tmdb import (
    DEFAULT_RATE,
    NO_KEY,
    Pacer,
    Refreshed,
    TmdbFilm,
    compact,
    fetch_order,
    load_cache,
    most_voted,
    needs_fetch,
    refresh,
    workers_for,
)

log = logging.getLogger("rebuild_table")
DEFAULT_STATE = Path.home() / ".local/share/matinee"
FAILED = "the rebuild failed; its log says why"
SAVE_EVERY = 500  # new records between saves of the film table while the rebuild fetches
DEFAULT_DAILY = "04:30"  # the nightly rebuild's time when REBUILD_TIME is unset
FROM_SETTING = "REBUILD_TIME"  # what `--daily` given alone stands for


def _now() -> str:
    return datetime.now(UTC).isoformat()


def rebuild(server: MediaServer | None, state: Path, token: str, rate: float = DEFAULT_RATE) -> RebuildStatus:
    """One rebuild; returns, and leaves in `rebuild.json`, how it ended."""
    started = _now()
    cache = state / "tmdb" / "films.jsonl"
    if not token:
        _compact_without_key(cache)
        log.error("no TMDB key is set, so no film table can be built. Set TMDB_TOKEN and run the rebuild again.")
        return _report(state, RebuildStatus("stopped", started, _now(), reason=NO_KEY))
    table = state / "films.sqlite"
    kept = _keep(table)
    try:
        status = _rebuild(server, state, cache, token, started, rate)
    except Exception:
        if kept is not None:
            os.replace(kept, table)  # an unexpected failure puts back the table this run started with
            log.warning("the rebuild failed, so the film table it started with is back in place")
        _report(state, RebuildStatus("stopped", started, _now(), reason=FAILED))
        raise
    if kept is not None:
        kept.unlink(missing_ok=True)
    return status


def _compact_without_key(cache: Path) -> None:
    """The six-month limit holds even when nothing can be fetched; a cache that cannot be rewritten is logged."""
    if not cache.exists():
        return
    try:
        compact(cache, datetime.now(UTC))
    except OSError as exc:
        log.error(
            "the TMDB cache %s could not be rewritten to drop records past six months: %s. Meanwhile it stays as it"
            " is; check the data directory's permissions and free space.",
            cache,
            exc,
        )


def _keep(table: Path) -> Path | None:
    """A second name for the table this run starts with, so an unexpected failure can put it back; every save
    replaces the table's own name, so the kept one stays whole. None on a first start, with no table yet."""
    if not table.exists():
        return None
    kept = table.with_name(table.name + ".kept")
    kept.unlink(missing_ok=True)
    try:
        os.link(table, kept)
    except OSError:
        shutil.copy2(table, kept)
    return kept


def _rebuild(
    server: MediaServer | None, state: Path, cache: Path, token: str, started: str, rate: float
) -> RebuildStatus:
    films = open_reader(server).films() if server is not None else []
    listed = load_labels().films() | household_films(state)
    ids = listed | {f.tmdb for f in films if f.tmdb is not None}
    have = load_cache(cache)
    todo = [t for t in ids if needs_fetch(have.get(t), datetime.now(UTC))]
    log.info(
        "the rebuild starts: library: %s; %d films the labels name; %d TMDB records held, %d to fetch at %g a second",
        "no media server set" if server is None else f"{server.kind}, {len(films):,} films",
        len(listed),
        len(have),
        len(todo),
        rate,
    )
    run = _Run(state, started, films, load_scores(), listed)
    run.tick(Refreshed(0, 0), len(todo), have)  # the library and the films already held, before any fetch
    pacer = Pacer(rate)
    still = partial(run.tick, Refreshed(0, 0), len(todo), have, save=False)  # a slow order read is not a stall
    order = fetch_order(todo, have, lambda: most_voted(token, pacer, workers_for(rate), on_page=still))
    result = refresh(order, cache, token, rate=rate, pacer=pacer, tick=run.tick)
    log.info("TMDB: fetched %d, failed %d", result.fetched, result.failed)
    report = run.save(load_cache(cache))
    for line in report.lines():
        log.info("%s", line)
    done = result.fetched + result.failed
    if result.stopped is not None:
        return _report(state, RebuildStatus("stopped", started, _now(), done, len(todo), result.stopped))
    return _report(state, RebuildStatus("finished", started, _now(), len(todo), len(todo)))


@dataclass
class _Run:
    """One rebuild's film table and report while it fetches: the table is saved every SAVE_EVERY new records."""

    state: Path
    started: str
    films: Sequence[LibraryFilm]
    scores: Scores
    listed: frozenset[int]
    saved_at: int | None = None  # records fetched at the last save; None before the first

    def save(self, records: Mapping[int, TmdbFilm]) -> BuildReport:
        """Build the table from `records` and replace the one on disk whole."""
        table, report = build_table(self.films, self.scores, records, datetime.now(UTC), self.listed)
        write_table(table, self.state / "films.sqlite")
        log.info("wrote %d films to %s", len(table.films), self.state / "films.sqlite")
        return report

    def tick(self, so_far: Refreshed, total: int, records: Mapping[int, TmdbFilm], save: bool = True) -> None:
        """Report progress, and save the table when SAVE_EVERY records have come since the last save."""
        done = so_far.fetched + so_far.failed
        write_status(self.state, RebuildStatus("running", self.started, _now(), done, total))
        if save and (self.saved_at is None or so_far.fetched - self.saved_at >= SAVE_EVERY):
            if total:
                log.info("rebuild progress: %d of %d films fetched or failed (%d%%)", done, total, 100 * done // total)
            self.save(records)
            self.saved_at = so_far.fetched


def household_films(state: Path) -> frozenset[int]:
    """The films the household override file names, so their records are fetched too; none when it cannot be
    read (the server's setup note names that)."""
    try:
        theirs = load_overrides(state)
    except LabelsError as exc:
        log.warning(
            "the override file cannot be read: %s. Meanwhile the rebuild fetches only the films Matinee ships"
            " labels for; fix the file (the server's setup note names the problem) and rebuild.",
            exc,
        )
        return frozenset()
    return frozenset() if theirs is None else theirs.named()


def _report(state: Path, status: RebuildStatus) -> RebuildStatus:
    write_status(state, status)
    return status


def tmdb_rate(text: str) -> float:
    """TMDB_RATE, requests a second: any positive number; unset, empty or anything else is the default (logged)."""
    if not text.strip():
        return DEFAULT_RATE
    try:
        rate = float(text)
    except ValueError:
        rate = 0.0
    if rate > 0 and math.isfinite(rate):
        return rate
    log.warning(
        "TMDB_RATE is %r, which is no positive number of requests a second. Meanwhile the rebuild uses %g; set"
        " TMDB_RATE to a positive number, or remove it.",
        text,
        DEFAULT_RATE,
    )
    return DEFAULT_RATE


def daily_time(text: str) -> tuple[int, int]:
    """An HH:MM time of day, checked before the first rebuild so a typo fails at once."""
    try:
        hour, minute = (int(x) for x in text.split(":"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected HH:MM, got {text!r}") from exc
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise argparse.ArgumentTypeError(f"expected HH:MM, got {text!r}")
    return hour, minute


def daily_arg(text: str) -> tuple[int, int] | str:
    """`--daily`'s value: an HH:MM time, or FROM_SETTING when the flag stands alone."""
    return text if text == FROM_SETTING else daily_time(text)


def rebuild_time(text: str) -> tuple[int, int]:
    """REBUILD_TIME, HH:MM: the nightly rebuild's time; unset, empty or anything else is DEFAULT_DAILY (logged)."""
    if not text.strip():
        return daily_time(DEFAULT_DAILY)
    try:
        return daily_time(text.strip())
    except argparse.ArgumentTypeError:
        log.warning(
            "REBUILD_TIME is %r, which is no HH:MM time of day. Meanwhile the rebuild runs nightly at %s; set"
            " REBUILD_TIME to a time such as 04:30, or remove it.",
            text,
            DEFAULT_DAILY,
        )
        return daily_time(DEFAULT_DAILY)


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
        "--daily",
        type=daily_arg,
        nargs="?",
        const=FROM_SETTING,
        metavar="HH:MM",
        help="rebuild now, then every day at this local time; alone, at REBUILD_TIME",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.daily == FROM_SETTING:
        args.daily = rebuild_time(os.environ.get("REBUILD_TIME", ""))
    token = os.environ.get("TMDB_TOKEN", "").strip()
    rate = tmdb_rate(os.environ.get("TMDB_RATE", ""))
    try:
        server = configured_server(os.environ)
    except ServerChoiceError as exc:
        server = None
        log.warning("%s. Meanwhile the rebuild reads no library and fetches the films the labels name.", exc)
    if not args.state.is_dir():
        parser.error(f"the state directory {args.state} does not exist")
    if not args.daily:
        return 0 if rebuild(server, args.state, token, rate).state == "finished" else 1
    while True:
        try:
            rebuild(server, args.state, token, rate)
        except Exception as exc:  # any failure waits for the next night, never a restart loop
            log.warning(
                "the rebuild failed: %s. Meanwhile the previous table stays in place and the rebuild tries again at"
                " the next scheduled time; the traceback below says where it broke.",
                exc,
                exc_info=True,
            )
        time.sleep(seconds_until(args.daily, datetime.now()))


if __name__ == "__main__":
    sys.exit(main())
