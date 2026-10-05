"""The server's entry point: `uvicorn --factory matinee.web.main:build`.

Refuses to start when a setting is missing, the state directory does not exist,
the film table or reference statistics are absent or too old, or the labels file
or the pick's lines (data/quips.json) are malformed. Both are read once here;
replacing either takes a restart.
"""

from __future__ import annotations

import logging
import math
import time
from functools import partial
from pathlib import Path

from fastapi import FastAPI

from matinee.dtdd import Dtdd
from matinee.engine import household_problems, load_catalog
from matinee.genome_file import tags_read
from matinee.labels import LABELS, OVERRIDES, Labels, LabelsError, load_labels, load_overrides, with_overrides
from matinee.library.choice import open_reader
from matinee.store import Store
from matinee.trees import load_trees
from matinee.web.app import create_app
from matinee.web.config import from_env
from matinee.web.theatre import BROKEN_DATA, Theatre

log = logging.getLogger("matinee.web")


TOPICS_KEPT = (
    "A DoesTheDogDie key was set before and is now missing, and %d %s still hold DoesTheDogDie topics. "
    "Meanwhile those topics change nothing: no pick is checked against them and no question is skipped for them. "
    "Set DTDD_API_KEY again, or clear the topics with: python tools/notes.py clear-topics"
)


def warn_kept_topics(store: Store) -> None:
    """Warn while profiles hold DoesTheDogDie topics that no key lets Matinee check."""
    held = sum(1 for p in store.everyone() if p.topics)
    if held:
        log.warning(TOPICS_KEPT, held, "profile" if held == 1 else "profiles")


WARN_EVERY = 12 * 3600.0  # seconds at least between the kept-topics warnings a reloaded table raises
OVERRIDES_BROKEN = (
    "Your override file ({path}) can't be used: {problem}. Until it's fixed, films sit where Matinee ships them."
)


def household(shipped: Labels, data_dir: Path, faults: list[str]) -> Labels:
    """The shipped labels with the household override file laid over them; the shipped alone, with a fault, when
    the file cannot be used. Matinee only reads the file."""
    try:
        theirs = load_overrides(data_dir)
        trees = load_trees() if theirs is not None else {}
    except LabelsError as exc:
        theirs, trees = None, {}
        problems = [str(exc)]
    except BROKEN_DATA as exc:  # Matinee's own tree files: the theatre meets them too, and the note names them
        log.error("the override file cannot be checked, since Matinee's own tree files cannot be read: %s", exc)
        return shipped
    else:
        problems = [] if theirs is None else household_problems(theirs, trees)
    if problems:
        log.error(
            "the override file %s cannot be used, so the shipped placements apply alone: %s. Fix it and restart.",
            data_dir / OVERRIDES,
            problems[0],
        )
        faults.append(OVERRIDES_BROKEN.format(path=OVERRIDES, problem=problems[0]))
        return shipped
    if theirs is None:
        return shipped
    log.info("the override file places %d films its own way", len(theirs.named()))
    return with_overrides(shipped, theirs)


def build() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = from_env()
    if (config.state / "labels.json").exists():
        log.warning(
            "%s is not read: the labels ship with Matinee in %s. Remove it; household placements belong in the "
            "override file.",
            config.state / "labels.json",
            LABELS,
        )
    library = open_reader(config.server) if config.server is not None else None
    store = Store(config.store_path)
    dtdd = Dtdd(config.dtdd_key) if config.dtdd_key else None

    warned_at = -math.inf

    def on_reload() -> None:
        nonlocal warned_at
        if dtdd is None and time.monotonic() - warned_at >= WARN_EVERY:  # the rebuild saves many times a run
            warn_kept_topics(store)
            warned_at = time.monotonic()

    on_reload()
    faults: list[str] = []
    try:
        labels = load_labels()
    except LabelsError as exc:
        labels = Labels()
        log.error("the shipped labels cannot be read, so no film is placed behind a door: %s", exc)
        faults.append(
            f"My labels file can't be read ({exc}), so films wait behind their genres. Update or reinstall Matinee."
        )
    labels = household(labels, config.state, faults)
    try:
        tags = tags_read()
    except BROKEN_DATA as exc:
        tags = ()  # the theatre meets the same file, and the setup note names it
        log.error(
            "Matinee's own tree files cannot be read, so it offers no film: %s. Update or reinstall Matinee.", exc
        )
    catalog_of = partial(load_catalog, labels=labels)
    theatre = Theatre(
        library,
        config.table_path,
        catalog_of=catalog_of,
        on_reload=on_reload,
        listed=labels.films(),
        tags=tags,
    )
    return create_app(config, theatre, store, dtdd, faults=faults)
