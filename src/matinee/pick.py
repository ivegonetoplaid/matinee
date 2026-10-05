"""The pick: one film from the pool, checked against the viewer's DoesTheDogDie topics before it is shown.

A viewer without topics causes no lookup. For a viewer with topics, the drawn
film is looked up by TMDB id; it fails a topic that has at least five votes and
more yes votes than no. A film that fails is replaced from the same pool, and a
film that already failed in this pick is never looked up again. After
`PICK_TRIES` films have failed with others still undrawn, the pick stops, says
so, and holds the last of them with the topics it trips, for the viewer to see
on asking. When
DoesTheDogDie is slow (over three seconds), refuses, holds no record, or the
device has spent its lookups or the server its requests for the hour, the film
is shown marked unchecked, with the reason. When every film in the pool fails, the pick
says so. Films in a pick's `first` set are drawn before the rest.

The only thing kept from a lookup is which DoesTheDogDie item a TMDB film is, or
that it has none, for at most `ID_KEEP_S`, so a later lookup of the same film
skips the search. Votes are never kept. An unchecked pick carries the item held
for its film at that moment, so the page can open the film's own page.
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, TypeGuard

from matinee.dtdd import Dtdd, DtddCeiling, DtddError, DtddGone

LOOKUP_S = 3.0
MIN_VOTES = 5
LOOKUPS_PER_HOUR = 60
HOUR_S = 3600.0
SWEEP_S = 60.0
ID_KEEP_S = 30 * 24 * HOUR_S
PICK_TRIES = 3
Unchecked = Literal["slow", "no_record", "cap", "house"]
log = logging.getLogger("matinee.pick")


@dataclass(frozen=True)
class Hit:
    id: int
    name: str


@dataclass(frozen=True)
class Verdict:
    """What a lookup found: the topics a film fails, or why it could not be checked."""

    hits: tuple[Hit, ...] = ()
    unchecked: Unchecked | None = None


@dataclass(frozen=True)
class Pick:
    film: int | None
    swapped: int | None = None
    swapped_hits: tuple[Hit, ...] = ()
    unchecked: Unchecked | None = None
    exhausted: bool = False
    turned: tuple[int, ...] = ()
    used_up: bool = False
    last: int | None = None  # set only when three in a row tripped: the last of them
    last_hits: tuple[Hit, ...] = ()
    item: int | None = None  # an unchecked film's DoesTheDogDie item, while one is held for it


class Unreadable(ValueError):
    """A vote row for one of the viewer's topics is not in the shape the check reads."""


def _count(value: object) -> TypeGuard[int]:
    """A number read from DoesTheDogDie: a plain non-negative integer, never a boolean (which Python counts as 1)."""
    return type(value) is int and value >= 0


def failing(stats: Sequence[Any], topics: frozenset[int]) -> tuple[Hit, ...]:
    """The viewer's topics a film fails: at least MIN_VOTES votes and more yes than no.

    A row that cannot be read might be one of the viewer's topics, so it raises
    Unreadable rather than counting as a pass: an unread vote must never show a
    film as checked.
    """
    hits = []
    for row in stats:
        if not isinstance(row, dict):
            raise Unreadable("a vote row is not an object")
        topic, yes, no = row.get("topicId"), row.get("yesSum"), row.get("noSum")
        if not _count(topic):
            raise Unreadable("a vote row has no topic id")
        if topic not in topics:
            continue
        if not (_count(yes) and _count(no)):
            raise Unreadable(f"the votes for topic {topic} are not counts")
        if yes + no >= MIN_VOTES and yes > no:
            hits.append(Hit(topic, str(row.get("topicName") or topic)))
    return tuple(hits)


def _the_film(found: Any, tmdb: int) -> int | None:
    """The DoesTheDogDie item for this TMDB film: the one Movie matching its TMDB id; else None.

    TMDB numbers films and TV shows apart, and DoesTheDogDie's search returns both, so only a Movie
    is ever taken: a TV show sharing the number is another title, and its votes and page are not
    this film's. Raises DtddError when the search answer is not a list, or the one Movie's id is not a
    positive integer, so an unreadable answer is never taken, or remembered, as "no record" or as an item.
    """
    if not isinstance(found, list):
        raise DtddError("DoesTheDogDie's search answer is not a list")
    items = [
        i
        for i in found
        if isinstance(i, dict)
        and type(i.get("tmdbId")) is int
        and i["tmdbId"] == tmdb
        and i.get("itemTypeName") == "Movie"
    ]
    if len(items) != 1:
        return None
    item = items[0].get("id")
    if not (_count(item) and item > 0):
        raise DtddError("DoesTheDogDie's item id for the film is not a positive integer")
    return int(item)


@dataclass
class ItemIds:
    """Which DoesTheDogDie item each looked-up TMDB film is (None: it has none), each kept ID_KEEP_S.

    NOTE: held in memory, so a restart forgets it and each film's next lookup searches
    again. Bounded by the films Matinee offers; move it into the store if restarts
    become frequent.
    """

    clock: Callable[[], float] = time.monotonic
    known: dict[int, tuple[int | None, float]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def _drop_expired(self, now: float) -> None:
        """Forget every answer ID_KEEP_S old, so none is kept past the terms' limit. Called under the lock."""
        for tmdb in [t for t, (_, at) in self.known.items() if now - at >= ID_KEEP_S]:
            del self.known[tmdb]

    def get(self, tmdb: int) -> tuple[bool, int | None]:
        """(True, item) while an answer younger than ID_KEEP_S is held; (False, None) otherwise."""
        with self.lock:
            self._drop_expired(self.clock())
            held = self.known.get(tmdb)
            if held is None:
                return False, None
            return True, held[0]

    def put(self, tmdb: int, item: int | None) -> None:
        with self.lock:
            now = self.clock()
            self._drop_expired(now)
            self.known[tmdb] = (item, now)

    def forget(self, tmdb: int) -> None:
        with self.lock:
            self.known.pop(tmdb, None)


def look_up(dtdd: Dtdd, tmdb: int, topics: frozenset[int], ids: ItemIds) -> Verdict:
    """One film, by TMDB id: its search (skipped when `ids` holds the answer), then its topic votes.

    Each request has the three-second budget. A held item id DoesTheDogDie answers
    404 for is forgotten, so a film it has moved is searched again next time; any
    other failure keeps the id.
    """
    known, item = ids.get(tmdb)
    try:
        if not known:
            item = _the_film(dtdd.get(f"/items?tmdb={int(tmdb)}", LOOKUP_S, LOOKUP_S), tmdb)
            ids.put(tmdb, item)
        if item is None:
            return Verdict(unchecked="no_record")
        body = dtdd.get(f"/items/{item}", LOOKUP_S, LOOKUP_S)
    except DtddCeiling as exc:
        log.warning(
            "the DoesTheDogDie check for tmdb %s did not run: %s. Meanwhile the pick is shown unchecked, saying so;"
            " checks resume as the hourly allowance refills.",
            tmdb,
            exc,
        )
        return Verdict(unchecked="house")
    except DtddGone as exc:
        log.warning(
            "DoesTheDogDie no longer has the record Matinee held for tmdb %s: %s. Meanwhile the pick is shown"
            " unchecked; the film is looked up afresh next time.",
            tmdb,
            exc,
        )
        ids.forget(tmdb)
        return Verdict(unchecked="no_record")
    except DtddError as exc:
        log.warning(
            "the DoesTheDogDie check for tmdb %s failed: %s. Meanwhile the pick is shown unchecked, saying so; check"
            " DTDD_API_KEY and that DoesTheDogDie answers if this repeats.",
            tmdb,
            exc,
        )
        return Verdict(unchecked="slow")
    stats = body.get("topicItemStats") if isinstance(body, dict) else None
    if not isinstance(stats, list):
        return Verdict(unchecked="no_record")
    try:
        return Verdict(hits=failing(stats, topics))
    except Unreadable as exc:
        log.warning(
            "DoesTheDogDie's votes for tmdb %s could not be read: %s. Meanwhile the pick is shown unchecked; if this"
            " repeats, DoesTheDogDie's answer may have changed, so report it as an issue.",
            tmdb,
            exc,
        )
        return Verdict(unchecked="no_record")


@dataclass
class DeviceCap:
    """At most LOOKUPS_PER_HOUR film lookups per device in any hour, held in memory.

    Devices idle for an hour are forgotten, swept at most once a minute, so random
    or missing device ids cannot grow the map without bound.
    """

    clock: Callable[[], float] = time.monotonic
    spent: dict[str, deque[float]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    swept_at: float = float("-inf")

    def _sweep(self, now: float) -> None:
        if now - self.swept_at < SWEEP_S:
            return
        self.swept_at = now
        for device in [d for d, times in self.spent.items() if not times or now - times[-1] >= HOUR_S]:
            del self.spent[device]

    def take(self, device: str) -> bool:
        """Spend one lookup for the device; False when it has none left this hour."""
        now = self.clock()
        with self.lock:
            self._sweep(now)
            times = self.spent.setdefault(device, deque())
            while times and now - times[0] >= HOUR_S:
                times.popleft()
            if len(times) >= LOOKUPS_PER_HOUR:
                return False
            times.append(now)
            return True


def candidates(pool: Sequence[int], seen: Sequence[int], ratings: Mapping[int, float], prefer: str | None) -> list[int]:
    """The films a pick draws from: the pool less those already shown, the better-rated half when asked.

    Empty once every film in the pool has been shown: the pool is used up, never started again.
    """
    shown = set(seen)
    fresh = [t for t in pool if t not in shown]
    if prefer != "rating":
        return fresh
    ranked = sorted(fresh, key=lambda t: -ratings.get(t, 0.0))
    return ranked[: math.ceil(len(ranked) / 2)]


@dataclass
class Picker:
    dtdd: Dtdd | None  # None without a DoesTheDogDie key: no viewer then carries topics, so nothing is looked up
    cap: DeviceCap
    rng: random.Random = field(default_factory=random.SystemRandom)
    ids: ItemIds = field(default_factory=ItemIds)

    def _item(self, film: int) -> int | None:
        """The film's DoesTheDogDie item as held now, after any lookup: none once forgotten or ID_KEEP_S old."""
        return self.ids.get(film)[1]

    def _draws(self, films: Sequence[int], first: frozenset[int]) -> Iterator[int]:
        """Every film once, in random order, those in `first` before the rest."""
        for group in ([f for f in films if f in first], [f for f in films if f not in first]):
            while group:
                yield group.pop(self.rng.randrange(len(group)))

    def pick(
        self, films: Sequence[int], topics: frozenset[int], device: str, first: frozenset[int] = frozenset()
    ) -> Pick:
        """Draw, check and replace until one film is clear or cannot be checked, PICK_TRIES fail, or none is left."""
        draws = self._draws(films, first)
        if not topics or self.dtdd is None:
            film = next(draws, None)
            return Pick(None, exhausted=True) if film is None else Pick(film)
        return self._checked(draws, len(films), topics, device, self.dtdd)

    def _checked(self, draws: Iterator[int], size: int, topics: frozenset[int], device: str, dtdd: Dtdd) -> Pick:
        """Look each drawn film up until one is clear or cannot be checked, PICK_TRIES fail, or none is left."""
        swapped: int | None = None
        swapped_hits: tuple[Hit, ...] = ()
        turned: list[int] = []
        for film in draws:
            if not self.cap.take(device):
                return Pick(film, swapped, swapped_hits, unchecked="cap", turned=tuple(turned), item=self._item(film))
            verdict = look_up(dtdd, film, topics, self.ids)
            if not verdict.hits:
                item = self._item(film) if verdict.unchecked else None
                return Pick(film, swapped, swapped_hits, unchecked=verdict.unchecked, turned=tuple(turned), item=item)
            if swapped is None:
                swapped, swapped_hits = film, verdict.hits
            turned.append(film)
            if len(turned) >= PICK_TRIES and len(turned) < size:
                return Pick(None, swapped, swapped_hits, turned=tuple(turned), last=film, last_hits=verdict.hits)
        return Pick(None, swapped, swapped_hits, exhausted=True, turned=tuple(turned))
