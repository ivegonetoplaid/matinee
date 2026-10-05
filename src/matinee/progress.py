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
    if status.state not in ("running", "finished", "stopped"):
        log.warning(
            "the rebuild's report %s names no known state. Meanwhile it counts as absent; the next rebuild"
            " rewrites it.",
            path,
        )
        return None
    return status
