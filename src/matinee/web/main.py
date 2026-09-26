"""The server's entry point: `uvicorn --factory matinee.web.main:build`.

Refuses to start when a setting is missing, the state directory does not exist,
or the film table or reference statistics are absent or too old.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from matinee.dtdd import Dtdd
from matinee.library.jellyfin import JellyfinReader
from matinee.store import Store
from matinee.web.app import create_app
from matinee.web.config import from_env
from matinee.web.theatre import Theatre


def build() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = from_env()
    library = JellyfinReader(config.jellyfin_url, config.jellyfin_key)
    return create_app(config, Theatre(library, config.table_path), Store(config.store_path), Dtdd(config.dtdd_key))
