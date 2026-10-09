"""The server's entry point: which labels it serves, and what it says about a stale labels file."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from matinee.labels import load_labels
from matinee.store import Store
from matinee.web import main


class Recorded:
    """Stands in for the Theatre and the app, keeping what `build()` hands them."""

    def __init__(self) -> None:
        self.catalog_of: Any = None
        self.on_reload: Any = None
        self.listed: Any = None


def run_build(monkeypatch: pytest.MonkeyPatch, state: Path, dtdd_key: str = "d") -> Recorded:
    seen = Recorded()

    def theatre(_library: object, _table: object, catalog_of: Any, on_reload: Any, listed: Any, tags: Any) -> object:
        seen.catalog_of, seen.on_reload, seen.listed = catalog_of, on_reload, listed
        return object()

    monkeypatch.setattr(main, "Theatre", theatre)
    monkeypatch.setattr(main, "create_app", lambda *a, **k: None)
    env = {
        "DATA_DIR": str(state),
        "JELLYFIN_URL": "http://127.0.0.1:1",
        "JELLYFIN_API_KEY": "k",
        "SEERR_URL": "http://127.0.0.1:2",
        "DTDD_API_KEY": dtdd_key,
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
    assert seen.listed == load_labels().films()  # every film the labels name may be offered
    assert any("labels.json is not read" in r.getMessage() for r in caplog.records)


def test_no_word_about_a_labels_file_the_state_directory_does_not_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="matinee.web"):
        seen = run_build(monkeypatch, tmp_path)
    assert len(seen.catalog_of.keywords["labels"].films()) >= 10_272
    assert not caplog.records


def test_without_a_key_kept_topics_are_warned_of_at_start_and_at_most_twice_a_day_on_reloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from matinee.web.main import WARN_EVERY

    now = [1000.0]
    monkeypatch.setattr("matinee.web.main.time.monotonic", lambda: now[0])
    Store(tmp_path / "matinee.sqlite").create("Ada", None, [188])
    with caplog.at_level(logging.WARNING, logger="matinee.web"):
        seen = run_build(monkeypatch, tmp_path, dtdd_key="")
        assert ["now missing" in r.getMessage() for r in caplog.records] == [True]
        caplog.clear()
        now[0] += 60
        seen.on_reload()  # the rebuild saves many times a run: no second warning so soon
        assert caplog.records == []
        now[0] += WARN_EVERY
        seen.on_reload()
    assert ["now missing" in r.getMessage() for r in caplog.records] == [True]


def test_the_household_file_in_the_data_directory_reaches_the_catalog_and_the_offered_films(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = {"format": 2, "trees": {"comedy": {"kinds": {"999999999": ["slapstick"]}}}}
    (tmp_path / "overrides.json").write_text(json.dumps(doc))
    seen = run_build(monkeypatch, tmp_path)
    labels = seen.catalog_of.keywords["labels"]
    assert labels.of("comedy").kinds[999_999_999] == frozenset({"slapstick"})
    assert 999_999_999 in seen.listed and labels.overridden == frozenset({999_999_999})


def until(done: Any, timeout_s: float = 10.0) -> bool:
    """Waits for `done()` to hold, checking every 20 ms; False when it never does within `timeout_s`."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if done():
            return True
        time.sleep(0.02)
    return False


def test_a_rebuild_process_that_exits_is_started_again(tmp_path: Path) -> None:
    starts = tmp_path / "starts"
    rebuilds = main.Rebuilds([sys.executable, "-c", f"open({str(starts)!r}, 'a').write('x')"], restart_after_s=0)
    rebuilds.start()
    try:
        assert until(lambda: starts.exists() and len(starts.read_text()) >= 2)
    finally:
        rebuilds.stop()


def test_stopping_the_server_ends_its_rebuild_process(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    script = f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(60)"
    rebuilds = main.Rebuilds([sys.executable, "-c", script])
    rebuilds.start()
    assert until(lambda: pid_file.exists() and pid_file.read_text())
    stopper = threading.Thread(target=rebuilds.stop)
    stopper.start()
    stopper.join(10)  # a stop that only waited the rebuild out would take its whole minute
    assert not stopper.is_alive()
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
