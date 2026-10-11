"""How Matinee keeps asking the household's own services, the media server and Seerr, and when it says they fail.

They run beside Matinee on the household's network, so Matinee never gives up on one and never backs off: it asks
again every `RETRY_S` seconds for as long as one does not answer, so a service that comes back is seen within
`RETRY_S` seconds. A failure in the
first `STARTING_S` seconds after Matinee starts is said at INFO, as a service that may still be starting beside it;
one still failing after that, or beginning later, is warned. Each run of failures is said once at each level. TMDB
and DoesTheDogDie are outside services and keep their own limits.
"""

from __future__ import annotations

import logging

RETRY_S = 15.0  # seconds between asks of a household service that does not answer
STARTING_S = 120.0  # seconds after start in which a failure may be a service still starting beside Matinee


class Outage:
    """One household service's run of failures: the level to say each at, and whether an answer ends one."""

    def __init__(self, started_at: float) -> None:
        self._started_at = started_at
        self._said: int | None = None  # the level this run of failures was said at; None while the service answers

    def failed(self, now: float, may_be_starting: bool = True) -> int | None:
        """The level to say this failure at, or None when the run was already said at it. `may_be_starting` is
        false for a failure no starting service gives, such as a turned-down key, which is warned at once."""
        starting = may_be_starting and now - self._started_at < STARTING_S
        level = logging.INFO if starting else logging.WARNING
        if self._said is not None and self._said >= level:
            return None
        self._said = level
        return level

    def answered(self) -> bool:
        """Notes an answer; True when it ends a run of failures."""
        ended = self._said is not None
        self._said = None
        return ended
