"""The setup note: what Matinee sees wrong with its setup, in words, shown before any pick.

Matinee refuses to start only for door settings that are wrong and a store it
cannot read safely. Everything else it can run around, and says so here. A fault
in Matinee's own setup is named plainly, with the step that fixes it. A server
that does not answer is reported without instructions: Matinee says what it
sees and what it does meanwhile. The note offers no way in while there is no
film to recommend.
"""

from __future__ import annotations

from pydantic import BaseModel

from matinee.progress import RebuildStatus
from matinee.tmdb import KEY_REFUSED, NO_KEY, NOT_ANSWERING

HEADING = "A word before the show."
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


class SetupNote(BaseModel):
    """What the page shows before any pick: nothing when `lines` is empty."""

    heading: str
    lines: list[str]
    films: int
    go_on: bool  # "Show me the films" is offered; never into an empty pool


def unreachable(server: str) -> str:
    return f"I can't reach your {server} right now. {MEANWHILE}"


def rebuild_lines(status: RebuildStatus | None, films: int) -> list[str]:
    """What the rebuild's report says: a stop's reason, and why there is no film when there is none."""
    lines: list[str] = []
    if status is not None and status.state == "stopped":
        lines.append(STOPPED.get(status.reason or "", FAILED))
    if films > 0:
        return lines
    if status is None or status.state == "finished":
        lines.append(NEVER_BUILT)
    elif status.state == "running":
        lines.append(FETCHING)
    return lines


def note(faults: list[str], films: int) -> SetupNote:
    """The note for these faults, or an empty one when there is nothing to say."""
    return SetupNote(heading=HEADING, lines=faults, films=films, go_on=films > 0)
