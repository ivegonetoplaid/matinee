"""TMDB facts per film, cached as JSON lines: the title, year, runtime, rating, genres, synopsis, vote count,
US age rating, collection, keywords, original language and picture paths.

One GET per film (movie details with keywords and release dates appended), paced
well under TMDB's limits. The US age rating is the film's US theatrical
certification, else its first other non-empty US certification, else "" (none).
New records are appended and the newest line per TMDB id wins; after
each refresh the file is rewritten atomically to hold only the newest record per
id, and nothing older than `MAX_AGE`, because TMDB's terms cap caching at six
months. A record is refetched after `REFETCH_AFTER`. A film TMDB does not know
(404) is never cached, so it reads as missing. A line that does not parse is
skipped with a warning and its film is fetched again.
"""

from __future__ import annotations

import http.client
import itertools
import json
import logging
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TextIO

from matinee import USER_AGENT

API = "https://api.themoviedb.org/3"
DEFAULT_RATE = 30.0  # requests a second, the TMDB_RATE default; TMDB's limit sits around 40
MAX_WORKERS = 32  # requests in flight at most, however high the rate
VOTE_PAGES = 500  # TMDB serves its list of films by vote count 20 to a page, 500 pages at most
TICK_EVERY = 5.0  # seconds at most between a refresh's progress calls
REFETCH_AFTER = timedelta(days=150)
MAX_AGE = timedelta(days=183)
MAX_CONSECUTIVE_ERRORS = 5
THEATRICAL = 3  # TMDB's release type for a theatrical release
NO_KEY = "no TMDB key is set"
KEY_REFUSED = "TMDB refused the key"
NOT_ANSWERING = "TMDB is not answering"
NETWORK_FAILURES = (OSError, http.client.HTTPException, json.JSONDecodeError)  # URLError and timeouts are OSErrors
PICTURE_PATH = re.compile(r"^/[A-Za-z0-9]+\.(?:jpg|png)$")

log = logging.getLogger("matinee.tmdb")


class TmdbRefused(RuntimeError):
    """TMDB answered 401: the key is wrong or revoked, so no further request can succeed."""


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
    # None in a record written before these were kept; such a record is fetched again.
    title: str | None = None
    year: int | None = None
    runtime_min: float | None = None
    rating: float | None = None
    genres: list[str] | None = None
    synopsis: str | None = None  # "" where TMDB has none
    vote_count: int | None = None
    certification: str | None = None  # the US age rating; "" where TMDB has none

    @property
    def fetched(self) -> datetime:
        return datetime.fromisoformat(self.fetched_at)


def _record(line: str) -> TmdbFilm | None:
    """One cache line as a record; None when it is damaged, its fetch time included (unreadable or without a zone)."""
    try:
        rec = json.loads(line)
        film = TmdbFilm(
            tmdb=int(rec["tmdb"]),
            fetched_at=str(rec["fetched_at"]),
            collection_id=rec.get("collection_id"),
            collection_name=rec.get("collection_name"),
            keywords=list(rec.get("keywords") or []),
            original_language=rec.get("original_language"),
            poster_path=rec.get("poster_path"),
            backdrop_path=rec.get("backdrop_path"),
            title=rec.get("title"),
            year=rec.get("year"),
            runtime_min=rec.get("runtime_min"),
            rating=rec.get("rating"),
            genres=rec.get("genres"),
            synopsis=rec.get("synopsis"),
            vote_count=rec.get("vote_count"),
            certification=rec.get("certification"),
        )
        return film if film.fetched.tzinfo is not None else None
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
            log.warning(
                "TMDB cache %s line %d does not parse. Meanwhile it is skipped, and its film is fetched again by the"
                " next rebuild.",
                path,
                number,
            )
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
    """True when a film has no record, a record due for refresh, or one written before languages, picture
    paths or the title and its other shown facts were kept."""
    if rec is None or now - rec.fetched >= REFETCH_AFTER:
        return True
    return rec.original_language is None or rec.poster_path is None or rec.backdrop_path is None or rec.title is None


class Pacer:
    """Spaces requests from every thread at most `rate` a second; a 429 holds every request for its Retry-After.

    Any positive rate is accepted: the setting carries no ceiling (TMDB's own limit is about 40 a second).
    """

    def __init__(
        self, rate: float, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        if not rate > 0:
            raise ValueError("a pace is a positive number of requests a second")
        self._gap = 1.0 / rate
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next = 0.0
        self._held_until = 0.0

    def wait(self) -> None:
        """Wait for this request's turn; a hold that lands while it waits sends it back for a turn after the hold."""
        while True:
            with self._lock:
                now = self._clock()
                if now < self._held_until:
                    self._next = max(self._next, self._held_until)
                slot = max(now, self._next)
                self._next = slot + self._gap
            if slot > now:
                self._sleep(slot - now)
            with self._lock:
                if self._clock() >= self._held_until:
                    return

    def held(self) -> bool:
        """Whether a hold from a 429 is still running."""
        with self._lock:
            return self._clock() < self._held_until

    def hold(self, seconds: float) -> None:
        """Hold every request, those already waiting included, for `seconds`: a 429's Retry-After."""
        with self._lock:
            self._held_until = max(self._held_until, self._clock() + seconds)
            self._next = max(self._next, self._held_until)


def get_json(url: str, token: str, pacer: Pacer) -> dict[str, Any] | None:
    """One paced GET. Honours Retry-After on 429; a 404 returns None."""
    while True:
        pacer.wait()
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": USER_AGENT},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data: dict[str, Any] = json.load(resp)
                return data
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = int(exc.headers.get("Retry-After", 10))
                log.warning("TMDB answered 429, so every request waits %ss; consider a lower TMDB_RATE", wait)
                pacer.hold(wait)
                continue
            if exc.code == 404:
                return None
            if exc.code == 401:
                raise TmdbRefused(KEY_REFUSED) from exc
            raise


IMAGES = "https://image.tmdb.org/t/p/"
IMAGE_TIMEOUT_S = 10
IMAGE_RATE = 50.0  # picture requests a second to TMDB's image server, at most
IMAGE_PER_HOUR = 20_000  # Matinee's own ceiling on picture requests to TMDB in any hour
IMAGE_BACKOFF_S = 10.0  # the first hold after a 429 or 503 that names no Retry-After; it doubles
IMAGE_BACKOFF_MAX_S = 600.0
MAX_IMAGE_BYTES = 8 * 1024 * 1024
# Matinee's picture widths as TMDB's sizes: the nearest TMDB width, as the page maps them under `tmdb`.
IMAGE_SIZES: dict[str, dict[int, str]] = {
    "poster": {100: "w92", 160: "w154", 320: "w342", 640: "w780"},
    "backdrop": {960: "w780", 1600: "w1280"},
}


class TmdbImageError(RuntimeError):
    """TMDB's image server gave no usable picture."""


class ImageGate:
    """The one door to TMDB's image server: a pace, an hourly ceiling of Matinee's own, and a hold after a 429 or 503
    (its Retry-After, else a backoff doubling from IMAGE_BACKOFF_S). A request the gate will not admit fails at once,
    so a viewer's wall shows no picture rather than a server thread waiting."""

    def __init__(
        self, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self._pacer = Pacer(IMAGE_RATE, clock, sleep)
        self._clock = clock
        self._lock = threading.Lock()
        self._hour: tuple[float, int] = (-math.inf, 0)  # when the current hour began, and requests sent in it
        self._backoff = 0.0

    def admit(self) -> None:
        """Take a turn, or raise TmdbImageError while TMDB has asked Matinee to wait or the hour's ceiling is spent."""
        with self._lock:
            if self._pacer.held():
                raise TmdbImageError("TMDB's image server asked Matinee to wait")
            now = self._clock()
            start, sent = self._hour if now - self._hour[0] < 3600 else (now, 0)
            if sent >= IMAGE_PER_HOUR:
                raise TmdbImageError(f"Matinee's ceiling of {IMAGE_PER_HOUR} TMDB pictures an hour is spent")
            self._hour = (start, sent + 1)
        self._pacer.wait()

    def refused(self, retry_after: str | None) -> None:
        """TMDB answered 429 or 503: hold every picture request for its Retry-After, else a doubling backoff."""
        with self._lock:
            try:
                seconds = float(retry_after) if retry_after else 0.0
            except ValueError:
                seconds = 0.0
            if seconds <= 0:
                self._backoff = min(IMAGE_BACKOFF_MAX_S, max(IMAGE_BACKOFF_S, 2 * self._backoff))
                seconds = self._backoff
        self._pacer.hold(seconds)

    def answered(self) -> None:
        with self._lock:
            self._backoff = 0.0


IMAGE_GATE = ImageGate()


def fetch_picture(
    path: str,
    kind: str,
    width: int,
    opener: Callable[..., Any] = urllib.request.urlopen,
    gate: ImageGate = IMAGE_GATE,
) -> tuple[bytes, str]:
    """One TMDB picture at the TMDB size nearest `width`, as (body, content type), through `gate`. Needs no key; a
    path not shaped like a TMDB picture path is refused before any request."""
    if not PICTURE_PATH.fullmatch(path):
        raise TmdbImageError(f"not a TMDB picture path: {path!r}")
    size = IMAGE_SIZES[kind][width]
    gate.admit()
    req = urllib.request.Request(
        f"{IMAGES}{size}{path}", headers={"Accept": "image/*", "User-Agent": USER_AGENT}, method="GET"
    )
    try:
        with opener(req, timeout=IMAGE_TIMEOUT_S) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read(MAX_IMAGE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (429, 503):
            gate.refused(exc.headers.get("Retry-After") if exc.headers else None)
        raise TmdbImageError(f"TMDB's image server gave no {kind}: {exc}") from exc
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        raise TmdbImageError(f"TMDB's image server gave no {kind}: {exc}") from exc
    gate.answered()
    if not content_type.startswith("image/") or len(body) > MAX_IMAGE_BYTES:
        raise TmdbImageError(f"TMDB's image server answered a {kind} with {content_type or 'no type'}")
    return body, content_type


def picture_path(tmdb: int, field: str, value: object) -> str:
    """TMDB's path for one picture, or "" when it gives none. A value not shaped like a TMDB image path is
    logged and kept as none, so nothing else is ever joined into a picture's address."""
    if value is None or value == "":
        return ""
    if isinstance(value, str) and PICTURE_PATH.fullmatch(value):
        return value
    log.warning("TMDB gave film %s a %s not shaped like an image path; it is kept as none: %r", tmdb, field, value)
    return ""


def _us_certification(body: Mapping[str, Any]) -> str:
    """The film's US age rating: its theatrical certification, else its first other non-empty one, else ""."""
    countries = (body.get("release_dates") or {}).get("results") or []
    us = next((c for c in countries if isinstance(c, dict) and c.get("iso_3166_1") == "US"), {})
    dates = [
        d for d in us.get("release_dates") or [] if isinstance(d, dict) and str(d.get("certification") or "").strip()
    ]
    dates.sort(key=lambda d: d.get("type") != THEATRICAL)
    return str(dates[0]["certification"]).strip() if dates else ""


def _year(release_date: object) -> int | None:
    text = str(release_date or "")
    return int(text[:4]) if len(text) >= 4 and text[:4].isdigit() else None


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) and value > 0 else None


def fetch_film(tmdb: int, token: str, pacer: Pacer) -> TmdbFilm | None:
    """The film's TMDB facts, or None when TMDB does not know the id. Raises TmdbRefused when TMDB refuses the key."""
    body = get_json(f"{API}/movie/{tmdb}?append_to_response=keywords,release_dates", token, pacer)
    if body is None:
        return None
    coll = body.get("belongs_to_collection") or {}
    words = [k["name"] for k in (body.get("keywords") or {}).get("keywords", [])]
    votes = body.get("vote_count")
    return TmdbFilm(
        tmdb,
        datetime.now(UTC).isoformat(),
        coll.get("id"),
        coll.get("name"),
        words,
        body.get("original_language") or "",
        picture_path(tmdb, "poster_path", body.get("poster_path")),
        picture_path(tmdb, "backdrop_path", body.get("backdrop_path")),
        title=str(body.get("title") or ""),
        year=_year(body.get("release_date")),
        runtime_min=_number(body.get("runtime")),
        rating=_number(body.get("vote_average")),
        genres=[str(g["name"]) for g in body.get("genres") or [] if isinstance(g, dict) and g.get("name")],
        synopsis=str(body.get("overview") or "").strip(),
        vote_count=votes if isinstance(votes, int) and not isinstance(votes, bool) else 0,
        certification=_us_certification(body),
    )


@dataclass(frozen=True)
class Refreshed:
    """What a refresh did: records fetched, films that failed, and why it stopped early (None when it did not)."""

    fetched: int
    failed: int
    stopped: str | None = None


# A refresh's progress: what it has done so far, how many films it set out to fetch, and every record it holds now.
Tick = Callable[[Refreshed, int, Mapping[int, TmdbFilm]], None]


def workers_for(rate: float) -> int:
    """Requests in flight at `rate` a second: enough for the pace when each takes up to a second, MAX_WORKERS at
    most."""
    return max(1, min(MAX_WORKERS, math.ceil(rate)))


def most_voted(
    token: str, pacer: Pacer, workers: int, pages: int = VOTE_PAGES, on_page: Callable[[], None] = lambda: None
) -> list[int]:
    """TMDB's films by vote count, most first, read now and never stored; `on_page` is called after each page, so a
    slow read still shows progress. Reading stops at the first page that cannot be read, keeping the pages before
    it (logged)."""

    def page(n: int) -> list[int]:
        body = get_json(f"{API}/discover/movie?sort_by=vote_count.desc&page={n}", token, pacer)
        results = (body or {}).get("results")
        if not isinstance(results, list):
            raise ValueError(f"page {n} holds no list of films")
        return [r["id"] for r in results if isinstance(r, dict) and isinstance(r.get("id"), int)]

    order: list[int] = []
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        for found in pool.map(page, range(1, pages + 1)):
            order.extend(found)
            on_page()
    except (*NETWORK_FAILURES, TmdbRefused, ValueError) as exc:
        log.warning(
            "TMDB's list of films by vote count was read only to %d films: %s. Meanwhile the rest are fetched last,"
            " by id; nothing to do unless TMDB is not answering.",
            len(order),
            exc,
        )
    finally:
        pool.shutdown(cancel_futures=True)
    return order


def fetch_order(ids: Iterable[int], have: Mapping[int, TmdbFilm], voted: Callable[[], list[int]]) -> list[int]:
    """`ids` most-voted first. Held records give their vote counts; with no vote count held (a first start, or
    records kept before vote counts were) the order is TMDB's list by vote count, which `voted` reads. Films
    outside the order come last, by id."""
    ids = list(ids)
    if not ids:
        return []
    rank: dict[int, int] = {}
    if any(r.vote_count for r in have.values()):
        rank = {t: -(have[t].vote_count or 0) for t in ids if t in have}
    else:
        for i, t in enumerate(voted()):
            rank.setdefault(t, i)
        if not rank:
            log.warning(
                "TMDB's order by votes could not be read. Meanwhile the rebuild fetches its films by id, so the"
                " first picks may be less well known; the next first start reads it again."
            )
    return sorted(ids, key=lambda t: (t not in rank, rank.get(t, 0), t))


def refresh(
    ids: Iterable[int],
    cache: Path,
    token: str,
    fetch: Callable[[int, str], TmdbFilm | None] | None = None,
    rate: float = DEFAULT_RATE,
    pacer: Pacer | None = None,
    tick: Tick | None = None,
) -> Refreshed:
    """Fetch every id the cache lacks or holds stale, in the order given, append them, then compact.

    Requests go out at `rate` a second, several in flight at once, all spaced by one pacer (`pacer`, or a new one
    at `rate`; `fetch` is the real fetch, paced, unless a test gives its own). A film TMDB does not know counts as
    failed and is not cached. Stops after MAX_CONSECUTIVE_ERRORS network failures in a row, since that is an
    outage rather than a film, and at once when TMDB refuses the key. `tick` is called at least every TICK_EVERY
    seconds while requests are out, a 429's hold included. Compaction runs after the loop however it ends, an
    unexpected error included.
    """
    now = datetime.now(UTC)
    have = load_cache(cache)
    todo = [t for t in ids if needs_fetch(have.get(t), now)]
    log.info("TMDB: %d films to fetch at %g a second", len(todo), rate)
    cache.parent.mkdir(parents=True, exist_ok=True)
    if fetch is None:
        paced = pacer or Pacer(rate)

        def fetch(tmdb: int, key: str) -> TmdbFilm | None:
            return fetch_film(tmdb, key, paced)

    tally = _Tally(records=have)
    try:
        with cache.open("a", encoding="utf-8") as out:
            _fetch_all(todo, out, token, fetch, workers_for(rate), tally, tick or (lambda *_: None))
    finally:
        compact(cache, datetime.now(UTC))
    return tally.so_far()


def _fetch_all(
    todo: Sequence[int],
    out: TextIO,
    token: str,
    fetch: Callable[[int, str], TmdbFilm | None],
    workers: int,
    tally: _Tally,
    tick: Tick,
) -> None:
    """Fetch each record with `workers` requests in flight and append it from this thread, counting into `tally`.
    Results are counted as they finish, so a streak of failures is a streak in time."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = iter(todo)
        running = {pool.submit(fetch, t, token): t for t in itertools.islice(pending, workers)}
        ticked = time.monotonic()
        while running and tally.stopped is None:
            done, _ = wait(running, timeout=TICK_EVERY, return_when=FIRST_COMPLETED)
            tally.take(done, running, out)
            if tally.stopped is None:
                running |= {pool.submit(fetch, t, token): t for t in itertools.islice(pending, len(done))}
            if time.monotonic() - ticked >= TICK_EVERY:
                tick(tally.so_far(), len(todo), tally.records)
                ticked = time.monotonic()
        for future in running:
            future.cancel()


@dataclass
class _Tally:
    records: dict[int, TmdbFilm] = field(default_factory=dict)  # every record held, the new ones included
    fetched: int = 0
    failed: int = 0
    streak: int = 0
    stopped: str | None = None

    def so_far(self) -> Refreshed:
        return Refreshed(self.fetched, self.failed, self.stopped)

    def take(
        self, done: Iterable[Future[TmdbFilm | None]], running: dict[Future[TmdbFilm | None], int], out: TextIO
    ) -> None:
        """Count each finished fetch in `done`, taking it out of `running`; once stopped, a result that finished
        alongside is not counted."""
        for future in done:
            tmdb = running.pop(future)
            if self.stopped is None:
                self.add(tmdb, future, out)

    def add(self, tmdb: int, future: Future[TmdbFilm | None], out: TextIO) -> None:
        """Count one finished fetch and append its record."""
        try:
            rec = future.result()
        except TmdbRefused:
            self.stopped = KEY_REFUSED
            return
        except NETWORK_FAILURES as exc:
            self.failed += 1
            self.streak += 1
            log.warning(
                "TMDB's record for film %s could not be fetched: %r. Meanwhile the rebuild goes on and fetches it"
                " again next time; %d failures in a row stop it, so check the network if this repeats.",
                tmdb,
                exc,
                MAX_CONSECUTIVE_ERRORS,
            )
            if self.streak >= MAX_CONSECUTIVE_ERRORS:
                self.stopped = NOT_ANSWERING
            return
        self.streak = 0
        if rec is None:
            self.failed += 1
            log.warning("TMDB does not know film %s; it stays without TMDB facts", tmdb)
            return
        self.fetched += 1
        self.records[tmdb] = rec
        out.write(json.dumps(asdict(rec)) + "\n")
        out.flush()
