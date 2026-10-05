"""The rebuild's settings: it reads the media server the settings name, and refuses what it cannot use."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import rebuild_table
from matinee.library.choice import MediaServer


def run(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> list[Any]:
    for name in ("DATA_DIR", "JELLYFIN_URL", "JELLYFIN_API_KEY", "PLEX_URL", "PLEX_TOKEN", "TMDB_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    calls: list[Any] = []
    monkeypatch.setattr(rebuild_table, "rebuild", lambda *a: calls.append(a))
    monkeypatch.setattr("sys.argv", ["rebuild_table.py"])
    assert rebuild_table.main() == 0
    return calls


def test_the_rebuild_reads_whichever_server_is_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = {"DATA_DIR": str(tmp_path), "TMDB_TOKEN": "t"}
    [jf] = run(monkeypatch, {**base, "JELLYFIN_URL": "http://jf.invalid", "JELLYFIN_API_KEY": "k"})
    assert jf == (MediaServer("jellyfin", "http://jf.invalid", "k"), tmp_path, "t")
    [plex] = run(monkeypatch, {**base, "PLEX_URL": "http://plex.invalid", "PLEX_TOKEN": "p"})
    assert plex[0] == MediaServer("plex", "http://plex.invalid", "p")


@pytest.mark.parametrize(
    "env",
    [
        {"JELLYFIN_URL": "http://jf.invalid", "JELLYFIN_API_KEY": "k"},  # no TMDB_TOKEN
        {"TMDB_TOKEN": "t"},  # no media server
        {
            "TMDB_TOKEN": "t",
            "JELLYFIN_URL": "http://a",
            "JELLYFIN_API_KEY": "k",
            "PLEX_URL": "http://b",
            "PLEX_TOKEN": "p",
        },
        {"TMDB_TOKEN": "t", "MATINEE_JELLYFIN_URL": "http://a", "JELLYFIN_API_KEY": "k", "TMDB_READ_TOKEN": "t"},
    ],
)
def test_the_rebuild_refuses_settings_it_cannot_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: dict[str, str]
) -> None:
    with pytest.raises(SystemExit):
        run(monkeypatch, {"DATA_DIR": str(tmp_path), **env})
