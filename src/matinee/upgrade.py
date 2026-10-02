"""The store file's shape, and the one step that carries an older store file to it.

A store file records its shape in SQLite's `user_version`. A file from before
shapes were recorded reads 0 and holds the tables `profiles`, `corrections`,
`feedback` and `tokens`. `prepare` creates a missing or empty file at the current
shape and leaves a current file alone. It carries a shape-0 file to the current
shape in one transaction, keeping where each "Not <genre> at all" note said its
film belongs from the correction saved with it and giving every note the status
`open`, after copying the file as it stood to a new file beside
it, which nothing ever overwrites. It refuses, and changes nothing in the store
file, a file newer than this code, a file that is not a SQLite database, and an
upgrade that fails or would lose a profile, a token or a note.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

SHAPE = 1

TABLES = (
    """CREATE TABLE profiles (
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
)""",
    """CREATE TABLE notes (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
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
)""",
    """CREATE TABLE tokens (
    token_hash TEXT PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
)""",
)

# Where a "Not <genre> at all" note says its film belongs was kept only in the correction saved with it: the
# override whose removal names the note's profile, film and tree, saved at or before the note, latest first.
BELONGS_FROM_CORRECTIONS = """UPDATE notes SET belongs = (
    SELECT json_group_array(tree) FROM (
        SELECT added.tree FROM corrections AS added
        WHERE added.direction = 'add' AND added.override_id = (
            SELECT removed.override_id FROM corrections AS removed
            WHERE removed.direction = 'remove' AND removed.profile_id = notes.profile_id
              AND removed.tmdb = notes.tmdb AND removed.tree = notes.tree AND removed.at <= notes.at
            ORDER BY removed.at DESC, removed.id DESC LIMIT 1)
        ORDER BY added.tree))
WHERE kind = 'genre'"""

# Shape 0 to the current shape. Each note keeps its id, so a note named before the upgrade is the same note after.
FROM_SHAPE_0 = (
    TABLES[1],
    "INSERT INTO notes (id, profile_id, tmdb, tree, kind, path, rushed, comment, at)"
    " SELECT id, profile_id, tmdb, tree, kind, path, rushed, comment, at FROM feedback",
    BELONGS_FROM_CORRECTIONS,
    "DROP TABLE feedback",
    "DROP INDEX IF EXISTS corrections_by_profile",
    "DROP TABLE corrections",
)


class ShapeError(RuntimeError):
    """The store file cannot be brought to the current shape; the file was not changed."""


def _connect(path: Path) -> sqlite3.Connection:
    """A connection that runs statements exactly as given: no implicit transactions, foreign keys off."""
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.execute("PRAGMA foreign_keys = OFF")
    return db


def _shape(db: sqlite3.Connection) -> int:
    return int(db.execute("PRAGMA user_version").fetchone()[0])


def _empty(db: sqlite3.Connection) -> bool:
    return int(db.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]) == 0


COUNTS = {
    "profiles": "SELECT COUNT(*) FROM profiles",
    "tokens": "SELECT COUNT(*) FROM tokens",
    "feedback": "SELECT COUNT(*) FROM feedback",
    "notes": "SELECT COUNT(*) FROM notes",
}


def _counts(db: sqlite3.Connection, notes: str) -> tuple[int, int, int]:
    """Profiles, tokens and notes, the rows an upgrade must keep; `notes` names the table holding the notes."""

    def count(table: str) -> int:
        return int(db.execute(COUNTS[table]).fetchone()[0])

    return count("profiles"), count("tokens"), count(notes)


def _keep_copy(db: sqlite3.Connection, path: Path) -> Path:
    """A copy of the store as it stands, in a new file beside it whose name says what it was kept before."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    copy = path.with_name(f"{path.name}.before-shape-{SHAPE}-{stamp}")
    with closing(sqlite3.connect(copy)) as dest:
        db.backup(dest)
    return copy


def _create(db: sqlite3.Connection) -> None:
    db.execute("BEGIN IMMEDIATE")
    for statement in TABLES:
        db.execute(statement)
    db.execute(f"PRAGMA user_version = {SHAPE}")
    db.execute("COMMIT")


def _upgrade_from_0(db: sqlite3.Connection) -> None:
    """Every statement of the upgrade in one transaction, kept only when no profile, token or note is lost."""
    db.execute("BEGIN IMMEDIATE")
    try:
        if _shape(db) != 0:  # another process upgraded it first
            db.execute("ROLLBACK")
            return
        before = _counts(db, "feedback")
        for statement in FROM_SHAPE_0:
            db.execute(statement)
        db.execute(f"PRAGMA user_version = {SHAPE}")
        after = _counts(db, "notes")
        if after != before:
            raise ShapeError(f"the upgrade would change the profiles, tokens and notes from {before} to {after}")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ShapeError("the upgrade would leave a row pointing at nothing")
        db.execute("COMMIT")
    except (sqlite3.Error, ShapeError):
        db.execute("ROLLBACK")
        raise


def prepare(path: Path) -> None:
    """Bring the store file at `path` to the current shape, or raise ShapeError having changed nothing in it."""
    with closing(_connect(path)) as db:
        try:
            shape = _shape(db)
            if shape == SHAPE:
                return
            if shape > SHAPE:
                raise ShapeError(f"the store file has shape {shape}, newer than this code's {SHAPE}")
            if shape != 0:
                raise ShapeError(f"the store file has shape {shape}, which no upgrade starts from")
            if _empty(db):
                _create(db)
                return
            _keep_copy(db, path)
            _upgrade_from_0(db)
        except sqlite3.Error as exc:
            raise ShapeError(f"the store file cannot be upgraded: {exc}") from exc
