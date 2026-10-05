"""The one client all DoesTheDogDie traffic passes through.

Requests are serialised and paced by a small allowance: `BURST` requests may go
back to back (one film lookup is a search and an item request), and the
allowance refills at `RATE_PER_S`, which keeps the sustained rate under the free
tier's 30 a minute; the public page shares that allowance with everyone. A
caller waits for its turn at most `wait` seconds and is then told DoesTheDogDie
is busy, so a burst of callers never parks the whole server.
Beyond the pace, the client holds its own requests rather than press on:
- at most `REQUESTS_PER_HOUR` in any hour for the whole server, whoever asks;
- after a 429 or 503, until the `Retry-After` it was given has passed, or for a
  backoff that doubles with each refusal when none was given;
- while DoesTheDogDie reports fewer than `MONTH_RESERVE` requests left this
  month, asking again only every `RESERVE_HOLD_S` to learn whether the allowance
  has recovered.
A held request raises without reaching DoesTheDogDie.
The topic list is kept in memory and fetched again once it is `TOPICS_REFRESH_S`
old; while a refresh fails, the kept list serves until it is `TOPICS_KEEP_S` old.
A film is looked up only at the moment of a pick, and nothing about it is kept
here.
DoesTheDogDie refuses Python's default user agent with a 403 that looks like a
bad key, so every request names Matinee.
"""

from __future__ import annotations

import http.client
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

API = "https://www.doesthedogdie.com/api/v3"
RATE_PER_S = 0.45  # 27 a minute, so BURST + 27 keeps any single minute under 30
BURST = 2
TOPICS_TIMEOUT_S = 10.0
TOPICS_WAIT_S = 1 / RATE_PER_S + 0.5  # two viewers opening the picker together both get the list
USER_AGENT = "Matinee/0.1 (+https://www.doesthedogdie.com)"
REQUESTS_PER_HOUR = 120  # the whole server's ceiling: twice one device's hourly lookups
HOUR_S = 3600.0
MONTH_RESERVE = 250  # 5 per cent of the free tier's 5,000 a month
RESERVE_HOLD_S = 6 * HOUR_S
BACKOFF_S = 60.0
BACKOFF_MAX_S = HOUR_S
REFUSALS = (429, 503)
TOPICS_REFRESH_S = 29 * 24 * HOUR_S
TOPICS_KEEP_S = 30 * 24 * HOUR_S
log = logging.getLogger("matinee.dtdd")


class DtddError(RuntimeError):
    """DoesTheDogDie was slow, refused, or answered in a shape this client does not read."""


class DtddCeiling(DtddError):
    """The server has made its REQUESTS_PER_HOUR requests this hour; nothing was sent."""


class DtddGone(DtddError):
    """DoesTheDogDie answered 404: the item asked for does not exist."""


@dataclass(frozen=True)
class Topic:
    id: int
    name: str
    short: str
    keywords: str
    category: int


Opener = Callable[[urllib.request.Request, float], Any]


def _open(req: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(req, timeout=timeout)


class Dtdd:
    def __init__(
        self,
        key: str,
        opener: Opener = _open,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._key = key
        self._opener = opener
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._tokens = float(BURST)
        self._filled_at = clock()
        self._sent: deque[float] = deque()
        self._held_until = float("-inf")
        self._held_why = ""
        self._refusals = 0
        self._topics: tuple[list[Topic], float] | None = None

    def get(self, path: str, timeout: float, wait: float) -> Any:
        """One paced GET; raises DtddError when no turn comes within `wait` seconds or no JSON within `timeout`."""
        req = urllib.request.Request(
            f"{API}{path}",
            headers={"X-API-KEY": self._key, "Accept": "application/json", "User-Agent": USER_AGENT},
            method="GET",
        )
        if not self._lock.acquire(timeout=wait):
            raise DtddError("DoesTheDogDie is busy with other requests")
        try:
            self._check_holds()
            self._pace()
            self._sent.append(self._clock())
            return self._fetch(req, timeout)
        finally:
            self._lock.release()

    def _check_holds(self) -> None:
        """Raise, sending nothing, while a backoff or the month's reserve holds or the hour's ceiling is reached."""
        now = self._clock()
        if now < self._held_until:
            raise DtddError(self._held_why)
        while self._sent and now - self._sent[0] >= HOUR_S:
            self._sent.popleft()
        if len(self._sent) >= REQUESTS_PER_HOUR:
            raise DtddCeiling(f"Matinee has made its {REQUESTS_PER_HOUR} DoesTheDogDie requests this hour")

    def _hold(self, seconds: float, why: str) -> None:
        self._held_until = self._clock() + seconds
        self._held_why = why

    def _refused(self, exc: urllib.error.HTTPError) -> None:
        """Hold every request for the Retry-After DoesTheDogDie gave, or a doubling backoff without one."""
        given = (exc.headers.get("Retry-After") or "").strip() if exc.headers else ""
        wait = float(given) if given.isdigit() else min(BACKOFF_S * 2 ** min(self._refusals, 6), BACKOFF_MAX_S)
        self._refusals += 1
        self._hold(wait, f"DoesTheDogDie refused with HTTP {exc.code}; holding for {wait:.0f} s")

    def _note_remaining(self, headers: Any) -> None:
        """Hold when DoesTheDogDie reports fewer than MONTH_RESERVE requests left this month."""
        left = (headers.get("X-RateLimit-Remaining-Month") or "").strip() if headers else ""
        if left.isdigit() and int(left) < MONTH_RESERVE:
            self._hold(RESERVE_HOLD_S, f"DoesTheDogDie reports {left} requests left this month")

    def _pace(self) -> None:
        """Spend one request from the allowance, sleeping until one has refilled when it is empty."""
        now = self._clock()
        self._tokens = min(float(BURST), self._tokens + (now - self._filled_at) * RATE_PER_S)
        self._filled_at = now
        if self._tokens < 1:
            self._sleep((1 - self._tokens) / RATE_PER_S)
            self._tokens, self._filled_at = 1.0, self._clock()
        self._tokens -= 1

    def _fetch(self, req: urllib.request.Request, timeout: float) -> Any:
        try:
            with self._opener(req, timeout) as resp:
                body = json.load(resp)
                self._refusals = 0
                self._note_remaining(getattr(resp, "headers", None))
                return body
        except urllib.error.HTTPError as exc:
            if exc.code in REFUSALS:
                self._refused(exc)
            if exc.code == 404:
                raise DtddGone(f"DoesTheDogDie answered HTTP {exc.code}") from exc
            raise DtddError(f"DoesTheDogDie answered HTTP {exc.code}") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise DtddError(f"DoesTheDogDie did not answer: {type(exc).__name__}") from exc
        except ValueError as exc:
            raise DtddError("DoesTheDogDie answered with something that is not JSON") from exc

    def topics(self) -> list[Topic]:
        """The topic list: the kept copy while younger than TOPICS_REFRESH_S, else fetched and kept.

        A failed refresh falls back to the kept copy while it is younger than
        TOPICS_KEEP_S, and raises otherwise.
        """
        held = self._topics
        age = self._clock() - held[1] if held else float("inf")
        if held and age < TOPICS_REFRESH_S:
            return list(held[0])
        try:
            fresh = self._fetch_topics()
        except DtddError as exc:
            if held and age < TOPICS_KEEP_S:
                log.warning(
                    "DoesTheDogDie's topic list could not be refreshed: %s. Meanwhile the copy fetched earlier is"
                    " offered, and it is fetched again on the next request; check DTDD_API_KEY and that"
                    " DoesTheDogDie answers.",
                    exc,
                )
                return list(held[0])
            raise
        self._topics = (fresh, self._clock())
        return list(fresh)

    def _fetch_topics(self) -> list[Topic]:
        body = self.get("/topics", TOPICS_TIMEOUT_S, TOPICS_WAIT_S)
        if not isinstance(body, list):
            raise DtddError("DoesTheDogDie's topic list is not a list")
        out = []
        for raw in body:
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), int) or not isinstance(raw.get("name"), str):
                continue
            out.append(
                Topic(
                    id=raw["id"],
                    name=raw["name"],
                    short=str(raw.get("minimalName") or raw["name"]),
                    keywords=str(raw.get("keywords") or ""),
                    category=int(raw.get("topicCategoryId") or 0),
                )
            )
        return out
