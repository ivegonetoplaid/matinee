"""The server's entry point: which labels it serves, and what it says about a stale labels file."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from matinee.labels import load_labels
from matinee.web import main


class Recorded:
    """Stands in for the Theatre and the app, keeping what `build()` hands them."""

    def __init__(self) -> None:
        self.catalog_of: Any = None


def run_build(monkeypatch: pytest.MonkeyPatch, state: Path) -> Recorded:
    seen = Recorded()

    def theatre(_library: object, _table: object, catalog_of: Any) -> object:
        seen.catalog_of = catalog_of
        return object()

    monkeypatch.setattr(main, "Theatre", theatre)
    monkeypatch.setattr(main, "create_app", lambda *a, **k: None)
    env = {
        "MATINEE_STATE": str(state),
        "MATINEE_JELLYFIN_URL": "http://127.0.0.1:1",
        "JELLYFIN_API_KEY": "k",
        "MATINEE_SEERR_URL": "http://127.0.0.1:2",
        "DTDD_API_KEY": "d",
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    main.build()
    return seen


def test_the_server_serves_the_shipped_labels_whatever_the_state_directory_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    stale = {"format": 2, "trees": {"horror": {"kinds": {"1": []}}}}
    (tmp_path / "labels.json").write_text(json.dumps(stale))
    with caplog.at_level(logging.WARNING, logger="matinee.web"):
        seen = run_build(monkeypatch, tmp_path)
    assert seen.catalog_of.keywords["labels"].films() == load_labels().films()
    assert any("labels.json is not read" in r.getMessage() for r in caplog.records)


def test_no_word_about_a_labels_file_the_state_directory_does_not_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="matinee.web"):
        seen = run_build(monkeypatch, tmp_path)
    assert len(seen.catalog_of.keywords["labels"].films()) >= 10_272
    assert not caplog.records
