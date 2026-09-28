"""The server's entry point: `uvicorn --factory matinee.web.main:build`.

Refuses to start when a setting is missing, the state directory does not exist,
the film table or reference statistics are absent or too old, or the labels file
or the pick's lines (data/quips.json) are malformed. Both are read once here;
replacing either takes a restart.
"""

from __future__ import annotations

import logging
from functools import partial

from fastapi import FastAPI

from matinee.dtdd import Dtdd
from matinee.engine import load_catalog
from matinee.labels import load_labels
from matinee.library.jellyfin import JellyfinReader
from matinee.quips import load_quips
from matinee.store import Store
from matinee.web.app import create_app
from matinee.web.config import from_env
from matinee.web.theatre import Theatre


def build() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = from_env()
    library = JellyfinReader(config.jellyfin_url, config.jellyfin_key)
    theatre = Theatre(
        library, config.table_path, catalog_of=partial(load_catalog, labels=load_labels(config.labels_path))
    )
    return create_app(config, theatre, Store(config.store_path), Dtdd(config.dtdd_key), quips=load_quips())
