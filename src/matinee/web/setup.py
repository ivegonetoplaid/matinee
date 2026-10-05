"""The setup note: what Matinee sees wrong with its setup, in words, shown before any pick.

Matinee refuses to start only for door settings that are wrong and a store it
cannot read safely. Everything else it can run around, and says so here. A fault
in Matinee's own setup is named plainly, with the step that fixes it. A server
that does not answer is reported without instructions: Matinee says what it
sees and what it does meanwhile. The note offers no way in while there is no
film to recommend.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from matinee.progress import RebuildStatus
from matinee.tmdb import KEY_REFUSED, NO_KEY, NOT_ANSWERING

HEADING = "A word before the show."
STALLED_AFTER = timedelta(seconds=120)  # many times tmdb.TICK_EVERY, how often a running rebuild reports
MEANWHILE = "Until then, I'm picking from TMDB's most popular films instead of your library."
STOPPED = {
    NO_KEY: (
        "No TMDB key is set, so I can't fetch any film details. Add TMDB_TOKEN to your settings and run the rebuild."
    ),
    KEY_REFUSED: (
        "TMDB turned down the key in TMDB_TOKEN, so I can't fetch film details. Check the key and run the rebuild."
    ),
    NOT_ANSWERING: "TMDB wasn't answering when I last fetched film details, so some may be missing.",
}
SEERR_AWAY = "I can't reach your Seerr right now, so each pick links to TMDB until it's back."
FAILED = "My last rebuild of the film details failed. Its log says why; run it again once that's fixed."
FETCHING = "I'm still fetching film details from TMDB. Give me a minute and try again."
NEVER_BUILT = (
    "I don't have any film details yet, and nothing is fetching them. Run the rebuild (tools/rebuild_table.py)."
)
BROKEN = (
    "Some of Matinee's own files can't be used ({detail}), so I can't offer any films. Update or reinstall Matinee."
)


STALE = (
    "This film data is over six months old, and keeping it breaks TMDB's terms. Refresh it by running the rebuild:"
    " python tools/rebuild_table.py"
)


class SetupNote(BaseModel):
    """What the page shows before any pick: nothing when `lines` is empty. `warning` stands on every screen."""

    heading: str
    lines: list[str]
    films: int
    go_on: bool  # "Show me the films" is offered; never into an empty pool
    warning: str | None = None


KEY_SETTINGS = {"Jellyfin": "JELLYFIN_API_KEY", "Plex": "PLEX_TOKEN"}


def library_away(server: str, refused: bool) -> str:
    """The setup note's line while the media server cannot be read: a turned-down key names the setting to check."""
    if refused:
        return f"Your {server} turned down the key in {KEY_SETTINGS[server]}, so I can't see your library. {MEANWHILE}"
    return f"I can't reach your {server} right now. {MEANWHILE}"


def fallback_line(server: str, refused: bool) -> str:
    """The strip a walk shows when its source answer can no longer be kept: the library stopped answering, or
    turned down the key."""
    if refused:
        return (
            f"Your {server} turned down my key, so I'm picking from every film I know, in your library or not,"
            " until that's sorted."
        )
    return (
        f"I can't reach your {server} right now, so I'm picking from every film I know, in your library or not,"
        " until it's back."
    )


def stalled(status: RebuildStatus, now: datetime) -> bool:
    """Whether a running report has stood still past STALLED_AFTER (or names no time), so the rebuild has died."""
    try:
        return now - datetime.fromisoformat(status.updated_at) > STALLED_AFTER
    except (ValueError, TypeError):
        return True


def rebuild_lines(status: RebuildStatus | None, films: int, now: datetime | None = None) -> list[str]:
    """What the rebuild's report says: a stop's reason, and why there is no film when there is none. A running
    report that stood still too long reads as a failed rebuild."""
    lines: list[str] = []
    if status is not None and status.state == "running" and stalled(status, now or datetime.now(UTC)):
        lines.append(FAILED)
        return lines
    if status is not None and status.state == "stopped":
        lines.append(STOPPED.get(status.reason or "", FAILED))
    if films > 0:
        return lines
    if status is None or status.state == "finished":
        lines.append(NEVER_BUILT)
    elif status.state == "running":
        lines.append(FETCHING)
    return lines


def note(faults: list[str], films: int, stale: bool = False) -> SetupNote:
    """The note for these faults, or an empty one when there is nothing to say; the stale-data warning when
    `stale`."""
    return SetupNote(heading=HEADING, lines=faults, films=films, go_on=films > 0, warning=STALE if stale else None)
