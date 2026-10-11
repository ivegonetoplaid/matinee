"""Whether the configured Seerr answers, checked at most every `outage.RETRY_S` seconds.

Matinee never acts on Seerr; it only links each pick to the film's Seerr page.
While Seerr cannot be reached the link goes to TMDB instead, and the walk's strip
says so. Seerr runs on the household's network, so it is never given up on: it is
checked again every `RETRY_S` seconds, answering or not, so a Seerr that stops
answering is seen within that time and one that comes back is too. The check is
one GET of Seerr's public status page, which needs no key.
"""

from __future__ import annotations

import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from matinee import USER_AGENT
from matinee.outage import RETRY_S, STARTING_S, Outage

TIMEOUT_S = 5.0
log = logging.getLogger("matinee.seerr")


class SeerrCheck:
    def __init__(
        self,
        url: str | None,
        clock: Callable[[], float] = time.monotonic,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self.url = url
        self._clock = clock
        self._opener = opener
        self._lock = threading.Lock()
        self._checked_at: float | None = None
        self._answers = True
        self._outage = Outage(clock())

    def _probe(self, now: float) -> bool:
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        req = urllib.request.Request(f"{self.url}/api/v1/status", headers=headers, method="GET")
        try:
            with self._opener(req, timeout=TIMEOUT_S):
                return True
        except (urllib.error.URLError, OSError, ValueError) as exc:
            level = self._outage.failed(now)
            if level is not None:
                say_away(exc, level)
            return False

    def answers(self) -> bool:
        """True while a configured Seerr answers; False with none configured."""
        if self.url is None:
            return False
        with self._lock:
            now = self._clock()
            if self._checked_at is None or now - self._checked_at >= RETRY_S:
                self._answers = self._probe(now)
                if self._answers and self._outage.answered():
                    log.info("Seerr answers again; picks link to it")
                self._checked_at = now
            return self._answers

    def away(self) -> bool:
        """True while a Seerr is configured and does not answer."""
        return self.url is not None and not self.answers()

    def link_base(self) -> str | None:
        """The Seerr address the pick's link uses, or None to link to TMDB."""
        return self.url if self.answers() else None


def say_away(exc: Exception, level: int) -> None:
    """Say that Seerr did not answer; at INFO, just after start, as a Seerr that may still be starting."""
    if level < logging.WARNING:
        log.log(
            level,
            "Seerr is not answering yet: %s. Matinee has just started, so it may still be starting too. Meanwhile"
            " each pick links to TMDB. It is checked again every %d seconds, and warned if it still does not answer"
            " %d seconds after start.",
            exc,
            int(RETRY_S),
            int(STARTING_S),
        )
        return
    log.warning(
        "Seerr could not be reached: %s. Meanwhile each pick links to TMDB. It is checked again every %d seconds;"
        " check that Seerr is running and SEERR_URL is right.",
        exc,
        int(RETRY_S),
    )
