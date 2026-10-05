"""The rebuild's report on itself, `rebuild.json` in the data directory, where the web server reads it.

The rebuild writes it as it starts, as it finishes, and when it stops early with
the reason. The file is replaced atomically, so a reader never sees half of one.
A file that cannot be read counts as absent.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

STATUS_FILE = "rebuild.json"
log = logging.getLogger("matinee.progress")

State = Literal["running", "finished", "stopped"]


@dataclass(frozen=True)
class RebuildStatus:
    state: State
    started_at: str
    updated_at: str
    done: int = 0  # records this run has fetched or found fresh
    total: int = 0  # records this run needs
    reason: str | None = None  # why it stopped early; None unless `state` is "stopped"


def write_status(data_dir: Path, status: RebuildStatus) -> None:
    """Replace the report atomically."""
    path = data_dir / STATUS_FILE
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(asdict(status)), encoding="utf-8")
    os.replace(partial, path)


def read_status(data_dir: Path) -> RebuildStatus | None:
    """The last report, or None when there is none or it cannot be read (logged)."""
    path = data_dir / STATUS_FILE
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        status = RebuildStatus(**raw)
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        log.warning(
            "the rebuild's report %s cannot be read: %s. Meanwhile it counts as absent; the next rebuild rewrites it.",
            path,
            exc,
        )
        return None
    if not _well_formed(status):
        log.warning(
            "the rebuild's report %s names no known state or holds a field of the wrong kind. Meanwhile it counts"
            " as absent; the next rebuild rewrites it.",
            path,
        )
        return None
    return status


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _well_formed(status: RebuildStatus) -> bool:
    """Every field of the kind the report promises: a known state, text times, counts, and text or no reason."""
    return (
        status.state in ("running", "finished", "stopped")
        and isinstance(status.started_at, str)
        and isinstance(status.updated_at, str)
        and _count(status.done)
        and _count(status.total)
        and (status.reason is None or isinstance(status.reason, str))
    )
