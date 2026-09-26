"""The pick: one film from the pool, checked against the viewer's DoesTheDogDie topics before it is shown.

A viewer without topics causes no lookup. For a viewer with topics, the drawn
film is looked up by TMDB id; it fails a topic that has at least five votes and
more yes votes than no. A film that fails is replaced from the same pool, and a
film that already failed in this pick is never looked up again. When
DoesTheDogDie is slow (over three seconds), refuses, holds no record, or the
device has spent its lookups for the hour, the film is shown with its topics
named as unchecked. When every film in the pool fails, the pick says so.
Nothing looked up is kept.
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from matinee.dtdd import Dtdd, DtddError

LOOKUP_S = 3.0
MIN_VOTES = 5
LOOKUPS_PER_HOUR = 20
HOUR_S = 3600.0
SWEEP_S = 60.0
Unchecked = Literal["slow", "no_record", "cap"]
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


class Unreadable(ValueError):
    """A vote row for one of the viewer's topics is not in the shape the check reads."""


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
        if not isinstance(topic, int):
            raise Unreadable("a vote row has no topic id")
        if topic not in topics:
            continue
        if not (isinstance(yes, int) and isinstance(no, int)):
            raise Unreadable(f"the votes for topic {topic} are not counts")
        if yes + no >= MIN_VOTES and yes > no:
            hits.append(Hit(topic, str(row.get("topicName") or topic)))
    return tuple(hits)


def _the_film(found: Any, tmdb: int) -> int | None:
    """The DoesTheDogDie item for this TMDB film: the one match, or the one Movie among several; else None."""
    items = [i for i in found if isinstance(i, dict) and i.get("tmdbId") == tmdb] if isinstance(found, list) else []
    if len(items) > 1:
        items = [i for i in items if i.get("itemTypeName") == "Movie"]
    if len(items) != 1 or not isinstance(items[0].get("id"), int):
        return None
    return int(items[0]["id"])


def look_up(dtdd: Dtdd, tmdb: int, topics: frozenset[int]) -> Verdict:
    """One film, by TMDB id: its search, then its topic votes, each within the three-second budget."""
    try:
        item = _the_film(dtdd.get(f"/items?tmdb={int(tmdb)}", LOOKUP_S, LOOKUP_S), tmdb)
        if item is None:
            return Verdict(unchecked="no_record")
        body = dtdd.get(f"/items/{item}", LOOKUP_S, LOOKUP_S)
    except DtddError as exc:
        log.warning("DoesTheDogDie lookup for tmdb %s: %s", tmdb, exc)
        return Verdict(unchecked="slow")
    stats = body.get("topicItemStats") if isinstance(body, dict) else None
    if not isinstance(stats, list):
        return Verdict(unchecked="no_record")
    try:
        return Verdict(hits=failing(stats, topics))
    except Unreadable as exc:
        log.warning("DoesTheDogDie votes for tmdb %s could not be read: %s", tmdb, exc)
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
    """The films a pick draws from: the pool less those already shown, the better-rated half when asked."""
    shown = set(seen)
    fresh = [t for t in pool if t not in shown] or list(pool)
    if prefer != "rating":
        return fresh
    ranked = sorted(fresh, key=lambda t: -ratings.get(t, 0.0))
    return ranked[: math.ceil(len(ranked) / 2)]


@dataclass
class Picker:
    dtdd: Dtdd
    cap: DeviceCap
    rng: random.Random = field(default_factory=random.SystemRandom)

    def pick(self, films: Sequence[int], topics: frozenset[int], device: str) -> Pick:
        """Draw, check and replace until one film is clear or cannot be checked, or none is left."""
        left = list(films)
        swapped: int | None = None
        swapped_hits: tuple[Hit, ...] = ()
        while left:
            film = left.pop(self.rng.randrange(len(left)))
            if not topics:
                return Pick(film)
            if not self.cap.take(device):
                return Pick(film, swapped, swapped_hits, unchecked="cap")
            verdict = look_up(self.dtdd, film, topics)
            if not verdict.hits:
                return Pick(film, swapped, swapped_hits, unchecked=verdict.unchecked)
            if swapped is None:
                swapped, swapped_hits = film, verdict.hits
        return Pick(None, swapped, swapped_hits, exhausted=True)
