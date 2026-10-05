"""The server's log: one line for the whole state, said at start and on change; repeating warnings held back."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from matinee.labels import LABELS, LabelsError, load_labels
from matinee.web.logbook import CHECK_EVERY, QUIET_FOR, Quiet, StateLog, describe
from test_web_library import SECRET_KEY, SECRET_URL, make_world


def test_the_state_is_said_once_and_again_only_when_it_changes(caplog: pytest.LogCaptureFixture) -> None:
    clock, state = [0.0], ["a"]
    logbook = StateLog(lambda: ((state[0],), f"state {state[0]}"), clock=lambda: clock[0])
    with caplog.at_level(logging.INFO, logger="matinee.web"):
        logbook.check()
        clock[0] += CHECK_EVERY
        logbook.check()  # unchanged: nothing more
        state[0] = "b"
        logbook.check()  # changed, but looked at too soon
        clock[0] += CHECK_EVERY
        logbook.check()
    assert [r.getMessage() for r in caplog.records] == ["state a", "state b"]


def test_the_state_line_names_every_part_and_no_secret(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from matinee.web.seerr import SeerrCheck
    from test_web_library import answers

    _, library, _, theatre = make_world(tmp_path)
    from matinee.web.config import Config
    from test_web_library import SERVER

    config = Config(SERVER, tmp_path, "https://seerr.invalid", "d" * 16)
    key, line = describe(theatre, config, SeerrCheck(config.seerr_url, opener=answers), False, datetime.now(UTC))
    for part in ("Jellyfin answers", "Seerr: answers", "DoesTheDogDie: not set", "film table:", "rebuild never"):
        assert part in line
    assert SECRET_KEY not in line and SECRET_URL not in line and "d" * 16 not in line
    library.down = True
    theatre._showing = None
    theatre._failed_at = None
    changed, line = describe(theatre, config, SeerrCheck(config.seerr_url, opener=answers), False, datetime.now(UTC))
    assert changed != key and "Jellyfin does not answer" in line
    library.down, library.refused = False, True
    theatre._showing = None
    theatre._failed_at = None
    _, line = describe(theatre, config, SeerrCheck(config.seerr_url, opener=answers), False, datetime.now(UTC))
    assert "Jellyfin turned down the key" in line


def test_a_repeating_warning_is_said_once_a_minute_with_a_count(caplog: pytest.LogCaptureFixture) -> None:
    clock = [0.0]
    quiet = Quiet(clock=lambda: clock[0])
    with caplog.at_level(logging.WARNING, logger="matinee.web"):
        for _ in range(5):
            quiet.warn("tmdb-picture", "no picture for %s", 1)
        clock[0] += QUIET_FOR
        quiet.warn("tmdb-picture", "no picture for %s", 2)
        quiet.warn("other", "something else")
    said = [r.getMessage() for r in caplog.records]
    assert said == [
        "no picture for 1",
        "no picture for 2 (4 more like this in the last minute were not logged)",
        "something else",
    ]


def test_a_broken_labels_file_says_how_to_mend_it_by_whose_it_is(tmp_path: Path, monkeypatch: Any) -> None:
    mine = tmp_path / "labels.json"
    mine.write_text("{half")
    with pytest.raises(LabelsError, match="your own file"):
        load_labels(mine)
    monkeypatch.setattr("matinee.labels.LABELS", mine)
    with pytest.raises(LabelsError, match="update or reinstall Matinee"):
        load_labels(mine)
    assert LABELS.name == "labels.json"


def test_the_state_line_says_one_day_and_many_days() -> None:
    from datetime import UTC, datetime, timedelta

    from matinee.web.logbook import _age

    now = datetime(2026, 10, 5, 12, tzinfo=UTC)
    assert _age(None, now) == "no TMDB facts"
    assert _age(now - timedelta(days=1), now) == "TMDB facts from 2026-10-04 (1 day old)"
    assert _age(now - timedelta(days=3), now) == "TMDB facts from 2026-10-02 (3 days old)"
