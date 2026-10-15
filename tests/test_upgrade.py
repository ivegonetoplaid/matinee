"""The store file's upgrade: an older store comes through whole, or not at all."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from matinee import upgrade
from matinee.store import Store
from matinee.upgrade import SHAPE, ShapeError

# The store's tables as every file written before shapes were recorded holds them (user_version 0).
SHAPE_0 = """
CREATE TABLE profiles (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    pin_salt BLOB,
    pin_hash BLOB,
    failed INTEGER NOT NULL DEFAULT 0,
    locked_until REAL NOT NULL DEFAULT 0,
    topics TEXT NOT NULL DEFAULT '[]',
    exclusions TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE TABLE corrections (
    id INTEGER PRIMARY KEY,
    override_id TEXT NOT NULL,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    tmdb INTEGER NOT NULL,
    tree TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('remove', 'add')),
    at TEXT NOT NULL
);
CREATE INDEX corrections_by_profile ON corrections (profile_id);
CREATE TABLE feedback (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    tmdb INTEGER NOT NULL,
    tree TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('genre', 'kind', 'quality')),
    path TEXT NOT NULL,
    rushed INTEGER NOT NULL,
    comment TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE TABLE tokens (
    token_hash TEXT PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
"""
TOKEN = "a-device-token-issued-before-the-upgrade"
PROFILES = [
    (1, "Ada", "ada", None, None, 0, 0.0, "[188]", '["superheroes"]', "2026-09-01T00:00:00+00:00"),
    (2, "Bo", "bo", b"s" * 16, b"h" * 32, 2, 0.0, "[]", "[]", "2026-09-02T00:00:00+00:00"),
]
NOTES = [
    (4, 1, 603, "horror", "genre", '["Scary."]', 0, "", "2026-09-10T00:00:00+00:00"),
    (9, 2, 105, "comedy", "kind", '["Funny.", "Silly."]', 1, "too goofy", "2026-09-11T00:00:00+00:00"),
    (11, 1, 603, "horror", "genre", "[]", 0, "again", "2026-09-12T00:00:01+00:00"),
    (12, 2, 77, "drama", "genre", "[]", 0, "", "2026-09-12T00:00:00+00:00"),
    (13, 1, 603, "horror", "kind", "[]", 0, "", "2026-09-14T00:00:00+00:00"),
]
# Two decoys sit after note 11's own correction and before the note, so only the profile and tree clauses tell them
# apart from it.
LATER = "2026-09-12T00:00:00.500000+00:00"
# Note 4's correction, saved with it; note 11's, saved later for the same film, which a match must tell apart;
# Bo's correction of film 77 under drama, saved after note 12 and so not its own.
CORRECTIONS = [
    (1, "ab", 1, 603, "horror", "remove", "2026-09-10T00:00:00+00:00"),
    (2, "ab", 1, 603, "thriller", "add", "2026-09-10T00:00:00+00:00"),
    (3, "cd", 1, 603, "horror", "remove", "2026-09-12T00:00:00+00:00"),
    (4, "cd", 1, 603, "war", "add", "2026-09-12T00:00:00+00:00"),
    (5, "cd", 1, 603, "drama", "add", "2026-09-12T00:00:00+00:00"),
    (6, "ef", 2, 77, "drama", "remove", "2026-09-13T00:00:00+00:00"),
    (7, "ef", 2, 77, "comedy", "add", "2026-09-13T00:00:00+00:00"),
    (8, "gh", 2, 603, "horror", "remove", LATER),  # Bo, the same film and tree: not Ada's
    (9, "gh", 2, 603, "western", "add", LATER),
    (10, "ij", 1, 603, "thriller", "remove", LATER),  # Ada, the same film, another tree
    (11, "ij", 1, 603, "comedy", "add", LATER),
]


# The tables of a shape-1 store, as every store from the shape-0 upgrade to this feature holds them.
SHAPE_1 = """
CREATE TABLE profiles (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    pin_salt BLOB,
    pin_hash BLOB,
    failed INTEGER NOT NULL DEFAULT 0,
    locked_until REAL NOT NULL DEFAULT 0,
    topics TEXT NOT NULL DEFAULT '[]',
    exclusions TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    avatar TEXT
);
CREATE TABLE notes (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER REFERENCES profiles(id) ON DELETE SET NULL,
    tmdb INTEGER NOT NULL,
    tree TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('genre', 'kind', 'quality')),
    path TEXT NOT NULL,
    rushed INTEGER NOT NULL,
    comment TEXT NOT NULL,
    at TEXT NOT NULL,
    belongs TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'open',
    reason TEXT,
    ruling TEXT,
    ruled_at TEXT,
    CHECK (
        (status = 'open' AND reason IS NULL AND ruling IS NULL AND ruled_at IS NULL)
        OR (status = 'rejected' AND reason IS NOT NULL AND ruling IS NULL AND ruled_at IS NOT NULL)
        OR (status = 'accepted' AND reason IS NOT NULL AND ruling IS NOT NULL AND ruled_at IS NOT NULL)
    )
);
CREATE TABLE tokens (
    token_hash TEXT PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
PRAGMA user_version = 1;
"""
SHAPE_1_PROFILES = [(*p, a) for p, a in zip(PROFILES, ("popcorn", None), strict=True)]
SHAPE_1_NOTES = [
    (*NOTES[0], '["thriller"]', "accepted", "fair", "moved to thriller", "2026-09-20T00:00:00+00:00"),
    (*NOTES[1], "[]", "rejected", "it is comedy", None, "2026-09-21T00:00:00+00:00"),
    (*NOTES[2], "[]", "open", None, None, None),
]
# Each upgraded profile's settings, in column order: rating floor, languages, rated-films setting, sharing, welcomed.
DEFAULTS = ("anything", "[]", 1, 0, 0)
RECORD_TABLES = {"ratings", "hidden", "runs", "run_films"}


def shape_1(path: Path) -> Path:
    """A store file at shape 1 holding two profiles, a token and notes in every review status."""
    with sqlite3.connect(path) as db:
        db.executescript(SHAPE_1)
        db.executemany("INSERT INTO profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", SHAPE_1_PROFILES)
        db.execute(
            "INSERT INTO tokens VALUES (?, 1, '2026-09-01T00:00:00+00:00')",
            (hashlib.sha256(TOKEN.encode()).hexdigest(),),
        )
        db.executemany("INSERT INTO notes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", SHAPE_1_NOTES)
    return path


def shape_0(path: Path) -> Path:
    """A store file in the shape every store held before this upgrade, holding two profiles, a token and notes."""
    with sqlite3.connect(path) as db:
        db.executescript(SHAPE_0)
        db.executemany("INSERT INTO profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", PROFILES)
        db.execute(
            "INSERT INTO tokens VALUES (?, 1, '2026-09-01T00:00:00+00:00')",
            (hashlib.sha256(TOKEN.encode()).hexdigest(),),
        )
        db.executemany("INSERT INTO feedback VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", NOTES)
        db.executemany("INSERT INTO corrections VALUES (?, ?, ?, ?, ?, ?, ?)", CORRECTIONS)
    return path


def rows(path: Path, sql: str) -> list[Any]:
    with sqlite3.connect(path) as db:
        return db.execute(sql).fetchall()


def copies(path: Path) -> list[Path]:
    return sorted(path.parent.glob(f"{path.name}.before-shape-*"))


def test_an_old_store_loses_only_its_corrections(tmp_path: Path) -> None:
    path = shape_0(tmp_path / "matinee.sqlite")
    store = Store(path)
    assert rows(path, "PRAGMA user_version") == [(SHAPE,)]
    # no avatar yet, every setting at its default, and not yet welcomed
    assert rows(path, "SELECT * FROM profiles ORDER BY id") == [(*p, None, *DEFAULTS) for p in PROFILES]
    assert rows(path, "SELECT id, profile_id, tmdb, tree, kind, path, rushed, comment, at FROM notes") == NOTES
    tables = {r[0] for r in rows(path, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tables == {"profiles", "notes", "tokens", *RECORD_TABLES}
    assert [p.name for p in store.holding([TOKEN]).values()] == ["Ada"]  # the device keeps its profile


def test_a_genre_note_keeps_where_its_own_correction_said_the_film_belongs(tmp_path: Path) -> None:
    path = shape_0(tmp_path / "matinee.sqlite")
    Store(path)
    belongs = dict(rows(path, "SELECT id, belongs FROM notes"))
    assert belongs == {4: '["thriller"]', 9: "[]", 11: '["drama","war"]', 12: "[]", 13: "[]"}


def test_every_note_arrives_open_in_the_review_queue(tmp_path: Path) -> None:
    path = shape_0(tmp_path / "matinee.sqlite")
    queue = Store(path).notes()
    assert [n.id for n in queue] == [n[0] for n in NOTES]
    assert {(n.status, n.reason, n.ruling, n.ruled_at) for n in queue} == {("open", None, None, None)}


def test_the_upgrade_keeps_a_copy_of_the_old_file_and_never_overwrites_it(tmp_path: Path) -> None:
    path = shape_0(tmp_path / "matinee.sqlite")
    before = path.read_bytes()
    Store(path)
    [kept] = copies(path)
    assert rows(kept, "PRAGMA user_version") == [(0,)]
    assert rows(kept, "SELECT * FROM corrections ORDER BY id") == CORRECTIONS
    assert rows(kept, "SELECT * FROM feedback ORDER BY id") == NOTES
    kept_bytes = kept.read_bytes()
    assert path.read_bytes() != before
    Store(path)  # a later start on the upgraded file
    assert copies(path) == [kept] and kept.read_bytes() == kept_bytes


def test_a_new_store_is_made_at_the_current_shape_with_no_copy(tmp_path: Path) -> None:
    path = tmp_path / "matinee.sqlite"
    Store(path).create("Cy", None, [])
    assert rows(path, "PRAGMA user_version") == [(SHAPE,)]
    assert copies(path) == []


def test_a_shape_1_store_keeps_every_profile_token_and_note_and_arrives_unwelcomed(tmp_path: Path) -> None:
    path = shape_1(tmp_path / "matinee.sqlite")
    store = Store(path)
    assert rows(path, "PRAGMA user_version") == [(SHAPE,)]
    assert rows(path, "SELECT * FROM profiles ORDER BY id") == [(*p, *DEFAULTS) for p in SHAPE_1_PROFILES]
    assert rows(path, "SELECT * FROM notes ORDER BY id") == [(*n, 0) for n in SHAPE_1_NOTES]  # tags: none
    assert rows(path, "SELECT profile_id FROM tokens") == [(1,)]
    assert [p.name for p in store.holding([TOKEN]).values()] == ["Ada"]
    tables = {r[0] for r in rows(path, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tables == {"profiles", "notes", "tokens", *RECORD_TABLES}


def test_a_shape_1_upgrade_keeps_a_copy_of_the_file_as_it_stood(tmp_path: Path) -> None:
    path = shape_1(tmp_path / "matinee.sqlite")
    Store(path)
    [kept] = copies(path)
    assert kept.name.startswith(f"matinee.sqlite.before-shape-{SHAPE}-")
    assert rows(kept, "PRAGMA user_version") == [(1,)]
    assert rows(kept, "SELECT * FROM notes ORDER BY id") == SHAPE_1_NOTES


def layout(path: Path) -> dict[str, Any]:
    """Every table's columns, foreign keys and indexes, and the rows each CHECK refuses, as SQLite reports them."""
    with sqlite3.connect(path) as db:
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        return {
            t: (
                db.execute(f"PRAGMA table_info({t})").fetchall(),
                db.execute(f"PRAGMA foreign_key_list({t})").fetchall(),
                sorted(r[1:3] for r in db.execute(f"PRAGMA index_list({t})")),
            )
            for t in tables
        }


REFUSED_ROWS = [
    "UPDATE profiles SET floor = 'everything'",
    "UPDATE profiles SET rated_out = 6",
    "UPDATE profiles SET sharing = 2",
    "UPDATE profiles SET welcomed = -1",
    "INSERT INTO ratings VALUES (1, 5, 6, 'now', 'matinee', NULL, NULL)",
    "INSERT INTO ratings VALUES (1, 5, 3, 'now', 'matinee', NULL, '')",
    "INSERT INTO ratings VALUES (1, 5, 3, 'now', 'matinee', NULL, substr(hex(zeroblob(71)), 1, 141))",
    "INSERT INTO hidden VALUES (1, 5, '2y', 'now', 'later')",
    "INSERT INTO hidden VALUES (1, 5, 'good', 'now', 'later')",
    "INSERT INTO hidden VALUES (1, 5, '3m', 'now', NULL)",
    "INSERT INTO runs (profile_id, run_key, began) VALUES (99, 'r', 'now')",
    "UPDATE profiles SET rated_out = -1",
    # each a second row where KEPT_ROWS already holds one, or a mark no film in a run can carry
    "INSERT INTO ratings VALUES (1, 5, 2, 'later', 'matinee', NULL, NULL)",
    "INSERT INTO hidden VALUES (1, 5, 'good', 'later', NULL)",
    "INSERT INTO runs (profile_id, run_key, began) VALUES (1, 'r1', 'later')",
    "INSERT INTO run_films (run_id, seq, tmdb, mark) VALUES (1, 1, 6, 'liked')",
]
# Rows the refusals above stand beside: one rating, one hidden film and one run, all Ada's.
KEPT_ROWS = [
    "INSERT INTO ratings VALUES (1, 5, 3, 'now', 'matinee', NULL, NULL)",
    "INSERT INTO hidden VALUES (1, 5, '3m', 'now', 'later')",
    "INSERT INTO runs (id, profile_id, run_key, began) VALUES (1, 1, 'r1', 'now')",
    "INSERT INTO run_films (run_id, seq, tmdb, mark) VALUES (1, 0, 5, 'rated')",
]


@pytest.mark.parametrize("older", [shape_0, shape_1])
def test_an_upgraded_store_has_exactly_the_shape_a_new_one_is_made_with(tmp_path: Path, older: Any) -> None:
    fresh, upgraded = tmp_path / "fresh.sqlite", older(tmp_path / "old.sqlite")
    Store(fresh).create("Ada", None, [])
    Store(upgraded)
    assert layout(upgraded) == layout(fresh)
    for path in (fresh, upgraded):
        with sqlite3.connect(path) as db:
            for sql in KEPT_ROWS:
                db.execute(sql)
        for sql in REFUSED_ROWS:
            with sqlite3.connect(path) as db, pytest.raises(sqlite3.IntegrityError):
                db.execute("PRAGMA foreign_keys = ON")
                db.execute(sql)


def test_a_profile_made_now_has_seen_the_welcome(tmp_path: Path) -> None:
    path = shape_1(tmp_path / "matinee.sqlite")
    Store(path).create("Cy", None, [])
    assert rows(path, "SELECT name, welcomed FROM profiles ORDER BY id") == [("Ada", 0), ("Bo", 0), ("Cy", 1)]


def keep_records(path: Path, profile_id: int, tmdb: int) -> None:
    """One rating, one hidden film and one run showing one film, kept for a profile."""
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO ratings VALUES (?, ?, 4, 'now', 'matinee', NULL, 'fine')", (profile_id, tmdb))
        db.execute("INSERT INTO hidden VALUES (?, ?, 'good', 'now', NULL)", (profile_id, tmdb))
        run = db.execute(
            "INSERT INTO runs (profile_id, run_key, began) VALUES (?, ?, 'now')", (profile_id, f"run-{profile_id}")
        ).lastrowid
        db.execute("INSERT INTO run_films (run_id, seq, tmdb) VALUES (?, 0, ?)", (run, tmdb))


def test_deleting_a_profile_takes_everything_it_keeps_but_its_notes(tmp_path: Path) -> None:
    path = shape_1(tmp_path / "matinee.sqlite")
    store = Store(path)
    keep_records(path, 1, 603)
    keep_records(path, 2, 77)
    store.delete(1, [TOKEN])
    assert rows(path, "SELECT profile_id FROM ratings") == [(2,)]
    assert rows(path, "SELECT profile_id FROM hidden") == [(2,)]
    assert rows(path, "SELECT profile_id FROM runs") == [(2,)]
    assert rows(path, "SELECT tmdb FROM run_films") == [(77,)]
    assert rows(path, "SELECT id, profile_id FROM notes ORDER BY id") == [(4, None), (9, 2), (11, None)]


def test_a_shape_1_upgrade_that_would_lose_a_note_is_undone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = shape_1(tmp_path / "matinee.sqlite")
    monkeypatch.setattr(upgrade, "FROM_SHAPE_1", (*upgrade.FROM_SHAPE_1, "DELETE FROM notes WHERE id = 9"))
    before = path.read_bytes()
    with pytest.raises(ShapeError, match="profiles, tokens and notes"):
        Store(path)
    assert path.read_bytes() == before


def test_an_upgrade_that_would_leave_a_row_pointing_at_nothing_is_undone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = shape_1(tmp_path / "matinee.sqlite")
    monkeypatch.setattr(upgrade, "FROM_SHAPE_1", (*upgrade.FROM_SHAPE_1, "UPDATE tokens SET profile_id = 99"))
    before = path.read_bytes()
    with pytest.raises(ShapeError, match="pointing at nothing"):
        Store(path)
    assert path.read_bytes() == before


class CutShort(sqlite3.Connection):
    """A store connection whose copy writes one table into the copy, then fails as a full disk does."""

    def backup(self, target: sqlite3.Connection, *args: Any, **kwargs: Any) -> None:
        target.execute("CREATE TABLE half (x)")
        target.commit()
        raise sqlite3.OperationalError("database or disk is full")


def test_a_copy_cut_short_is_never_taken_for_the_kept_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = shape_1(tmp_path / "matinee.sqlite")
    whole = upgrade._connect

    def cut_short(at: Path) -> sqlite3.Connection:
        db = sqlite3.connect(at, timeout=10, isolation_level=None, factory=CutShort)
        db.execute("PRAGMA foreign_keys = OFF")
        return db

    monkeypatch.setattr(upgrade, "_connect", cut_short)
    with pytest.raises(ShapeError, match="disk is full"):
        Store(path)
    assert copies(path) == [] and rows(path, "PRAGMA user_version") == [(1,)]
    monkeypatch.setattr(upgrade, "_connect", whole)
    Store(path)  # the next start copies afresh over the leftover working file
    [kept] = copies(path)
    assert rows(kept, "SELECT * FROM notes ORDER BY id") == SHAPE_1_NOTES
    assert not path.with_name(f"{path.name}.copying").exists()


def test_a_shape_1_store_with_notes_filed_by_older_code_is_refused_unchanged(tmp_path: Path) -> None:
    path = shape_1(tmp_path / "matinee.sqlite")
    with sqlite3.connect(path) as db:
        db.executescript(SHAPE_0.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS").replace("CREATE INDEX", "--"))
        db.execute("INSERT INTO feedback VALUES (50, 2, 1, 'west', 'kind', '[]', 0, 'filed during a rollback', 'x')")
    before = path.read_bytes()
    with pytest.raises(ShapeError, match="1 notes in its old feedback table"):
        Store(path)
    assert path.read_bytes() == before and copies(path) == []


@pytest.mark.parametrize("damage", ["newer", "not_sqlite", "unknown_shape", "missing_table"])
def test_a_store_the_code_cannot_read_stops_the_start_and_is_unchanged(tmp_path: Path, damage: str) -> None:
    path = tmp_path / "matinee.sqlite"
    if damage == "not_sqlite":
        path.write_bytes(b"this is not a database, just some bytes" * 100)
    else:
        shape_0(path)
        with sqlite3.connect(path) as db:
            if damage == "newer":
                db.execute(f"PRAGMA user_version = {SHAPE + 1}")
            if damage == "unknown_shape":
                db.execute("PRAGMA user_version = -3")
            if damage == "missing_table":
                db.execute("DROP TABLE feedback")
    before = path.read_bytes()
    with pytest.raises(ShapeError):
        Store(path)
    assert path.read_bytes() == before


def test_an_upgrade_that_would_lose_a_note_is_undone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = shape_0(tmp_path / "matinee.sqlite")
    losing = tuple(s.replace("FROM feedback", "FROM feedback WHERE id > 4") for s in upgrade.FROM_SHAPE_0)
    monkeypatch.setattr(upgrade, "FROM_SHAPE_0", losing)
    before = path.read_bytes()
    with pytest.raises(ShapeError, match="profiles, tokens and notes"):
        Store(path)
    assert path.read_bytes() == before


def test_after_the_upgrade_deleting_a_profile_keeps_its_notes(tmp_path: Path) -> None:
    path = shape_0(tmp_path / "matinee.sqlite")
    store = Store(path)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("DELETE FROM profiles WHERE id = 1")
    assert [(n.id, n.profile) for n in store.notes()] == [(4, None), (9, "Bo"), (11, None), (12, "Bo"), (13, None)]


def test_notes_older_code_files_after_the_upgrade_stop_the_next_start(tmp_path: Path) -> None:
    path = shape_0(tmp_path / "matinee.sqlite")
    Store(path)
    with sqlite3.connect(path) as db:  # what the code from before shapes does on a rollback: recreate, then file
        db.executescript(
            SHAPE_0.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS").replace(
                "CREATE INDEX", "CREATE INDEX IF NOT EXISTS"
            )
        )
        db.execute("INSERT INTO feedback VALUES (50, 2, 1, 'west', 'kind', '[]', 0, 'filed during a rollback', 'x')")
    before = path.read_bytes()
    with pytest.raises(ShapeError, match="1 notes in its old feedback table"):
        Store(path)
    assert path.read_bytes() == before


def test_a_rollback_that_filed_nothing_does_not_stop_the_start(tmp_path: Path) -> None:
    path = shape_0(tmp_path / "matinee.sqlite")
    Store(path)
    with sqlite3.connect(path) as db:
        db.executescript(
            SHAPE_0.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS").replace(
                "CREATE INDEX", "CREATE INDEX IF NOT EXISTS"
            )
        )
    assert [n.id for n in Store(path).notes()] == [n[0] for n in NOTES]


def test_a_start_that_keeps_failing_keeps_one_copy(tmp_path: Path) -> None:
    path = shape_0(tmp_path / "matinee.sqlite")
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE feedback")
    for _ in range(3):
        with pytest.raises(ShapeError):
            Store(path)
    assert len(copies(path)) == 1
