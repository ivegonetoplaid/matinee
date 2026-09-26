"""The one client all DoesTheDogDie traffic passes through.

Requests are serialised and paced by a small allowance: `BURST` requests may go
back to back (one film lookup is a search and an item request), and the
allowance refills at `RATE_PER_S`, which keeps the sustained rate under the free
tier's 30 a minute; the public page shares that allowance with everyone. A
caller waits for its turn at most `wait` seconds and is then told DoesTheDogDie
is busy, so a burst of callers never parks the whole server.
Nothing fetched is stored: the topic list is fetched when a page that offers
topics opens, and a film is looked up only at the moment of a pick.
DoesTheDogDie refuses Python's default user agent with a 403 that looks like a
bad key, so every request names Matinee.
"""

from __future__ import annotations

import http.client
import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

API = "https://www.doesthedogdie.com/api/v3"
RATE_PER_S = 0.45  # 27 a minute, so BURST + 27 keeps any single minute under 30
BURST = 2
TOPICS_TIMEOUT_S = 10.0
TOPICS_WAIT_S = 1 / RATE_PER_S + 0.5  # two viewers opening the picker together both get the list
USER_AGENT = "Matinee/0.1 (+https://www.doesthedogdie.com)"


class DtddError(RuntimeError):
    """DoesTheDogDie was slow, refused, or answered in a shape this client does not read."""


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
            self._pace()
            return self._fetch(req, timeout)
        finally:
            self._lock.release()

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
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            raise DtddError(f"DoesTheDogDie answered HTTP {exc.code}") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise DtddError(f"DoesTheDogDie did not answer: {type(exc).__name__}") from exc
        except ValueError as exc:
            raise DtddError("DoesTheDogDie answered with something that is not JSON") from exc

    def topics(self) -> list[Topic]:
        """The topic list, fetched now and never stored."""
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
