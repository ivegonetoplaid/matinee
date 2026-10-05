"""Whether the configured Seerr answers, checked at most every `CHECK_EVERY` seconds.

Matinee never acts on Seerr; it only links each pick to the film's Seerr page.
While Seerr cannot be reached the link goes to TMDB instead. The check is one
GET of Seerr's public status page, which needs no key.
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

CHECK_EVERY = 300.0
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

    def _probe(self) -> bool:
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        req = urllib.request.Request(f"{self.url}/api/v1/status", headers=headers, method="GET")
        try:
            with self._opener(req, timeout=TIMEOUT_S):
                return True
        except (urllib.error.URLError, OSError, ValueError) as exc:
            log.warning(
                "Seerr could not be reached: %s. Meanwhile each pick links to TMDB. It is checked again in %d"
                " seconds; check that Seerr is running and SEERR_URL is right.",
                exc,
                int(CHECK_EVERY),
            )
            return False

    def answers(self) -> bool:
        """True while a configured Seerr answers; False with none configured."""
        if self.url is None:
            return False
        with self._lock:
            now = self._clock()
            if self._checked_at is None or now - self._checked_at >= CHECK_EVERY:
                was, self._answers = self._answers, self._probe()
                if self._answers and not was:
                    log.info("Seerr answers again; picks link to it")
                self._checked_at = now
            return self._answers

    def link_base(self) -> str | None:
        """The Seerr address the pick's link uses, or None to link to TMDB."""
        return self.url if self.answers() else None
