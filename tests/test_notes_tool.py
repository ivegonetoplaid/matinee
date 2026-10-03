"""The operator's notes tool: the open queue in words, and a ruling recorded on one note."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import notes as tool
from matinee.store import Note, Store, StoreError
from test_web_library import write_film_table


@pytest.fixture
def state(tmp_path: Path) -> Path:
    write_film_table(tmp_path / "films.sqlite")
    store = Store(tmp_path / "matinee.sqlite")
    ada, _ = store.create("Ada", None, [], [])
    gone, _ = store.create("Gone", None, [], [])
    store.note(Note(ada.id, 5, "horror", "genre", ("Scary.", "Slow."), True, "it is a thriller", ("thriller",)))
    store.note(Note(gone.id, 6, "comedy", "kind", ("Funny.",), False, ""))
    store.note(Note(ada.id, 7, "drama", "quality", (), False, ""))
    with sqlite3.connect(tmp_path / "matinee.sqlite") as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("DELETE FROM profiles WHERE name = 'Gone'")
    return tmp_path


def run(state: Path, *argv: str) -> int:
    return tool.main(["--state", str(state), *argv])


def test_list_shows_every_open_note_in_words(state: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(state, "list") == 0
    out = capsys.readouterr().out
    assert "#1  Film 5 (1975), under Horror" in out
    assert "by Ada" in out and "answers: Scary. > Slow. > Just pick one!" in out
    assert "wrong: Not horror at all; belongs in Thriller" in out and "comment: it is a thriller" in out
    assert "#2  Film 6 (1976), under Comedy" in out and "by a deleted profile" in out
    assert "wrong: Comedy, but not the kind I asked for" in out
    assert "wrong: The right kind, just not a good pick" in out and "answers: (none)" in out
    assert out.rstrip().endswith("3 open notes.")


def test_accept_prints_the_film_then_records_the_ruling(state: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(state, "accept", "1", "fair", "--ruling", "thriller, settle 2026-10-03") == 0
    out = capsys.readouterr().out
    assert out.index("comment: it is a thriller") < out.index("Recorded: accepted.")
    assert "answers: Scary. > Slow. > Just pick one!" in out and "Replaced" not in out
    note = Store(state / "matinee.sqlite").filed(1)
    assert (note.status, note.reason, note.ruling) == ("accepted", "fair", "thriller, settle 2026-10-03")
    run(state, "list")
    assert "#1 " not in capsys.readouterr().out


def test_a_second_ruling_replaces_the_first_and_says_so(state: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run(state, "accept", "2", "looked right", "--ruling", "r-1")
    capsys.readouterr()
    assert run(state, "reject", "2", "it is a comedy after all") == 0
    out = capsys.readouterr().out
    assert "Replaced the earlier ruling: accepted, looked right (r-1)." in out and "Recorded: rejected." in out
    note = Store(state / "matinee.sqlite").filed(2)
    assert (note.status, note.reason, note.ruling) == ("rejected", "it is a comedy after all", None)


def test_refusals_say_so_and_write_nothing(state: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(state, "reject", "99", "no such note") == 1
    assert "Refused: no note 99." in capsys.readouterr().err
    assert run(state, "reject", "1", "   ") == 1
    with pytest.raises(SystemExit):
        run(state, "accept", "1", "fair")  # an accepted note names its label ruling
    assert [n.id for n in Store(state / "matinee.sqlite").notes()] == [1, 2, 3]


def test_a_missing_store_is_never_created(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(tmp_path, "list") == 2
    assert not (tmp_path / "matinee.sqlite").exists()
    assert "No Matinee store" in capsys.readouterr().err


def test_clear_pin_clears_one_profiles_pin_and_lockout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = Store(tmp_path / "matinee.sqlite")
    locked, _ = store.create("Pat", "1234", [], [])
    other, _ = store.create("Sam", "5678", [], [])
    for _ in range(5):
        with pytest.raises(StoreError):
            store.open(locked.id, "0000", 1000.0)
    with pytest.raises(StoreError) as still:
        store.open(locked.id, "1234", 1001.0)
    assert still.value.code == "locked"
    assert run(tmp_path, "clear-pin", "  pAT ") == 0
    with sqlite3.connect(tmp_path / "matinee.sqlite") as db:
        assert db.execute("SELECT failed, locked_until FROM profiles WHERE name = 'Pat'").fetchone() == (0, 0)
    assert "Cleared the PIN on Pat." in capsys.readouterr().out
    opened, _ = store.open(locked.id, None, 1002.0)  # no PIN asked, no lockout left
    assert not opened.has_pin
    with pytest.raises(StoreError):
        store.open(other.id, None, 1002.0)  # Sam keeps a PIN
    assert run(tmp_path, "clear-pin", "Nobody") == 1
    assert "Refused: no profile is named 'Nobody'." in capsys.readouterr().err


def test_the_note_is_shown_before_anything_is_written(
    state: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_: object) -> None:
        raise StoreError("bad_reason", "stopped before writing")

    monkeypatch.setattr(Store, "rule", refuse)
    assert run(state, "reject", "1", "x") == 1
    assert "#1  Film 5 (1975), under Horror" in capsys.readouterr().out


def test_a_viewers_comment_cannot_forge_a_note_or_reach_the_terminal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = Store(tmp_path / "matinee.sqlite")
    me, _ = store.create("Me", None, [], [])
    store.note(
        Note(me.id, 5, "horror", "kind", (), False, "a\n#9  Forged\x1b[2K\u202e and caf\u00e9 \u2014 na\u00efve")
    )
    assert run(tmp_path, "list") == 0
    out = capsys.readouterr().out
    assert not [line for line in out.splitlines() if line.startswith("#9")]
    assert "\x1b" not in out and "\u202e" not in out
    assert "comment: a #9 Forged\ufffd[2K\ufffd and caf\u00e9 \u2014 na\u00efve" in out


def test_the_tool_refuses_odd_numbers_names_and_stores_in_words(
    state: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        run(state, "reject", "99999999999999999999", "x")
    store = Store(state / "matinee.sqlite")
    store.create("Mary Ann", "1234", [], [])
    assert run(state, "clear-pin", "mary   ANN") == 0
    with sqlite3.connect(state / "matinee.sqlite") as db:
        db.execute("PRAGMA user_version = 99")
    capsys.readouterr()
    assert run(state, "list") == 1
    assert "Refused: the store file has shape 99" in capsys.readouterr().err
