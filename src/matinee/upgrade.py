"""The store file's shape, and the steps that carry an older store file to it.

A store file records its shape in SQLite's `user_version`. A file from before
shapes were recorded reads 0 and holds the tables `profiles`, `corrections`,
`feedback` and `tokens`. Shape 1 holds profiles, notes and tokens. Shape 2 adds
each profile's tailoring settings and welcome mark, and the tables `ratings`,
`hidden`, `runs` and `run_films`, whose rows go with their profile.

`prepare` creates a missing or empty file at the current shape and leaves a
current file alone. It carries an older file to the current shape in one
transaction, after copying the file as it stood to a new file beside it, which
nothing ever overwrites; a start that finds such a copy already there makes no
other. From shape 0 it keeps where each "Not <genre> at all" note said its film
belongs from the correction saved with it, gives every note the status `open`
and every profile no avatar. From shape 1 every profile arrives unmarked, with
every setting at its default. It refuses, and changes nothing in the store file,
a file in which older code has since filed notes into its old `feedback` table,
a file newer than this code, a file that is not a SQLite database, and an
upgrade that fails or would lose a profile, a token or a note.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

SHAPE = 2

# What a profile keeps of its own, from shape 2. A rating is 1 ("Hated it") to 5 ("Loved it!") with when and where it
# was made, the outside service's own value for an imported one, and an optional short review. A hidden film's `until`
# is empty when it is hidden for good. A run keeps when it began and the films it showed, each with the walk that
# reached it (its door and answers as a note takes them, what each said, whether "Just pick one!" ended them) and what
# the viewer did with it there; `before` holds the mark a hide replaced, which its "Undo" restores. A film shown again
# in the same run moves to the end and keeps its mark (its row's `seq` and walk are rewritten).
RECORDS = (
    """CREATE TABLE ratings (
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    tmdb INTEGER NOT NULL,
    score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
    at TEXT NOT NULL,
    source TEXT NOT NULL,
    outside TEXT,
    review TEXT CHECK (review IS NULL OR length(review) BETWEEN 1 AND 140),
    PRIMARY KEY (profile_id, tmdb)
)""",
    "CREATE INDEX ratings_by_film ON ratings (tmdb)",
    """CREATE TABLE hidden (
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    tmdb INTEGER NOT NULL,
    length TEXT NOT NULL CHECK (length IN ('3m', '6m', '1y', 'good')),
    at TEXT NOT NULL,
    until TEXT,
    CHECK ((length = 'good') = (until IS NULL)),
    PRIMARY KEY (profile_id, tmdb)
)""",
    """CREATE TABLE runs (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    run_key TEXT NOT NULL,
    began TEXT NOT NULL,
    UNIQUE (profile_id, run_key)
)""",
    """CREATE TABLE run_films (
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    tmdb INTEGER NOT NULL,
    mark TEXT CHECK (mark IS NULL OR mark IN ('rated', 'hid', 'reported')),
    before TEXT CHECK (before IS NULL OR before IN ('rated', 'reported')),
    tree TEXT,
    answers TEXT NOT NULL DEFAULT '[]',
    says TEXT NOT NULL DEFAULT '[]',
    rushed INTEGER NOT NULL DEFAULT 0 CHECK (rushed IN (0, 1)),
    PRIMARY KEY (run_id, tmdb)
)""",
)

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
    created_at TEXT NOT NULL,
    avatar TEXT,
    floor TEXT NOT NULL DEFAULT 'anything'
        CHECK (floor IN ('anything', 'above_bottom', 'middle', 'above_middle', 'well_liked')),
    languages TEXT NOT NULL DEFAULT '[]',
    rated_out INTEGER NOT NULL DEFAULT 1 CHECK (rated_out BETWEEN 0 AND 5),
    sharing INTEGER NOT NULL DEFAULT 0 CHECK (sharing IN (0, 1)),
    welcomed INTEGER NOT NULL DEFAULT 0 CHECK (welcomed IN (0, 1))
)""",
    """CREATE TABLE notes (
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
)""",
    """CREATE TABLE tokens (
    token_hash TEXT PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
)""",
    *RECORDS,
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

# Shape 0 to shape 1. Each note keeps its id, so a note named before the upgrade is the same note after,
# and outlives the profile that filed it: deleting the profile leaves the note with no profile.
FROM_SHAPE_0 = (
    TABLES[1],
    "INSERT INTO notes (id, profile_id, tmdb, tree, kind, path, rushed, comment, at)"
    " SELECT id, profile_id, tmdb, tree, kind, path, rushed, comment, at FROM feedback",
    BELONGS_FROM_CORRECTIONS,
    "DROP TABLE feedback",
    "DROP INDEX IF EXISTS corrections_by_profile",
    "DROP TABLE corrections",
    "ALTER TABLE profiles ADD COLUMN avatar TEXT",
)

# Shape 1 to shape 2: the settings and welcome mark take their defaults, so every profile arrives unmarked.
FROM_SHAPE_1 = (
    "ALTER TABLE profiles ADD COLUMN floor TEXT NOT NULL DEFAULT 'anything'"
    " CHECK (floor IN ('anything', 'above_bottom', 'middle', 'above_middle', 'well_liked'))",
    "ALTER TABLE profiles ADD COLUMN languages TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE profiles ADD COLUMN rated_out INTEGER NOT NULL DEFAULT 1 CHECK (rated_out BETWEEN 0 AND 5)",
    "ALTER TABLE profiles ADD COLUMN sharing INTEGER NOT NULL DEFAULT 0 CHECK (sharing IN (0, 1))",
    "ALTER TABLE profiles ADD COLUMN welcomed INTEGER NOT NULL DEFAULT 0 CHECK (welcomed IN (0, 1))",
    *RECORDS,
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


def _stranded(db: sqlite3.Connection) -> int:
    """Notes that code from before shapes were recorded filed into its own `feedback` table after the upgrade."""
    if db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'feedback'").fetchone() is None:
        return 0
    return int(db.execute(COUNTS["feedback"]).fetchone()[0])


def _keep_copy(db: sqlite3.Connection, path: Path) -> Path | None:
    """A copy of the store as it stands, in a new file beside it whose name says what it was kept before.

    The copy is written under a working name and takes its kept name only once whole, so a copy cut short by a
    crash or a full disk never passes for one. None when a kept copy is already there: a refused upgrade leaves
    the store unchanged, so the first copy still holds it, and a start that keeps failing must not fill the disk
    with copies.
    """
    if next(path.parent.glob(f"{path.name}.before-shape-{SHAPE}-*"), None) is not None:
        return None
    working = path.with_name(f"{path.name}.copying")
    working.unlink(missing_ok=True)
    with closing(sqlite3.connect(working)) as dest:
        db.backup(dest)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    copy = path.with_name(f"{path.name}.before-shape-{SHAPE}-{stamp}")
    os.replace(working, copy)
    return copy


def _create(db: sqlite3.Connection) -> None:
    db.execute("BEGIN IMMEDIATE")
    for statement in TABLES:
        db.execute(statement)
    db.execute(f"PRAGMA user_version = {SHAPE}")
    db.execute("COMMIT")


def _upgrade(db: sqlite3.Connection, start: int) -> None:
    """Every step from shape `start` to the current shape in one transaction, kept only when no profile, token or
    note is lost."""
    steps = (FROM_SHAPE_0, FROM_SHAPE_1)[start:]  # read at call time, so a test can stand a step in
    db.execute("BEGIN IMMEDIATE")
    try:
        if _shape(db) != start:  # another process upgraded it first
            db.execute("ROLLBACK")
            return
        before = _counts(db, "feedback" if start == 0 else "notes")
        for step in steps:
            for statement in step:
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


def _refuse_stranded(db: sqlite3.Connection) -> None:
    """Code from before shapes were recorded still opens a current file and files notes where no queue reads them."""
    stranded = _stranded(db)
    if stranded:
        raise ShapeError(
            f"the store file holds {stranded} notes in its old feedback table, filed by older code after the upgrade;"
            " move them into notes by hand before starting"
        )


def prepare(path: Path) -> None:
    """Bring the store file at `path` to the current shape, or raise ShapeError having changed nothing in it."""
    with closing(_connect(path)) as db:
        try:
            shape = _shape(db)
            if shape > SHAPE:
                raise ShapeError(f"the store file has shape {shape}, newer than this code's {SHAPE}")
            if shape < 0:
                raise ShapeError(f"the store file has shape {shape}, which no upgrade starts from")
            if shape > 0:
                _refuse_stranded(db)
            if shape == SHAPE:
                return
            if shape == 0 and _empty(db):
                _create(db)
                return
            _keep_copy(db, path)
            _upgrade(db, shape)
        except sqlite3.Error as exc:
            raise ShapeError(f"the store file cannot be upgraded: {exc}") from exc
