"""Matinee's own store: profiles, the device tokens that remember them, and what each profile saved.

A profile holds a display name, an optional four-digit PIN, the viewer's
exclusions and their corrections. A correction is one override written as
structured rows sharing an override id, one per tree and direction, each with
the film's TMDB id and a timestamp, so it can later be exported or pooled. Matinee never writes any of
this to a media server.

Device tokens are random, issued here, and stored only as SHA-256 digests, so a
copy of the store cannot be replayed as a cookie. A PIN is stored as a salted
scrypt digest, never as typed. Five wrong PINs lock that profile against PIN
entry for fifteen minutes; the lockout is keyed on the profile, never on a
client address, because every request arrives through the same tunnel. The
store holds at most `MAX_PROFILES` profiles.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import unicodedata
from collections.abc import Iterable, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

MAX_PROFILES = 50
MAX_NAME = 40
PIN_TRIES = 5
LOCKOUT_S = 15 * 60
SUGGEST_AFTER = 3
SUGGEST_AT_MOST = 3
MAX_EDITS = 2
SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
TOKEN_LIFE_S = 400 * 24 * 3600  # the cookie's own lifetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
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
CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY,
    override_id TEXT NOT NULL,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    tmdb INTEGER NOT NULL,
    tree TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('remove', 'add')),
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS corrections_by_profile ON corrections (profile_id);
CREATE TABLE IF NOT EXISTS tokens (
    token_hash TEXT PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
"""


class StoreError(ValueError):
    """A request the store refuses; `code` says which rule refused it, for the page to phrase."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class Locked(StoreError):
    def __init__(self, until: float) -> None:
        super().__init__("locked", "this profile is locked against PIN entry")
        self.until = until


@dataclass(frozen=True)
class SavedCorrection:
    tmdb: int
    tree: str
    direction: Literal["remove", "add"]


@dataclass(frozen=True)
class Profile:
    id: int
    name: str
    has_pin: bool
    topics: frozenset[int]
    exclusions: frozenset[str]


def name_key(name: str) -> str:
    return unicodedata.normalize("NFKC", name).strip().casefold()


def clean_name(raw: str) -> str:
    """The display name as stored: trimmed, one to MAX_NAME characters, no control characters."""
    name = " ".join(unicodedata.normalize("NFKC", raw).split())
    if not name or len(name) > MAX_NAME or any(unicodedata.category(c).startswith("C") for c in name):
        raise StoreError("bad_name", f"a name is 1 to {MAX_NAME} printable characters")
    return name


def clean_pin(pin: str | None) -> str | None:
    if pin is None or pin == "":
        return None
    if len(pin) != 4 or not pin.isascii() or not pin.isdigit():
        raise StoreError("bad_pin", "a PIN is four digits")
    return pin


def edits(a: str, b: str) -> int:
    """Levenshtein distance: single-character insertions, deletions and substitutions."""
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def names_match(typed: str, name: str) -> bool:
    """One name, ignoring case, starts with the other, or the two differ by at most MAX_EDITS edits."""
    a, b = name_key(typed), name_key(name)
    return a.startswith(b) or b.startswith(a) or edits(a, b) <= MAX_EDITS


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _pin_digest(pin: str, salt: bytes) -> bytes:
    return hashlib.scrypt(pin.encode(), salt=salt, **SCRYPT)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path: Path) -> None:
        if not path.parent.is_dir():
            raise StoreError("no_store", f"the store's directory {path.parent} does not exist")
        self._path = path
        with closing(self._connect()) as db, db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self._path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    @staticmethod
    def _profile(row: sqlite3.Row) -> Profile:
        return Profile(
            id=int(row["id"]),
            name=str(row["name"]),
            has_pin=row["pin_hash"] is not None,
            topics=frozenset(int(t) for t in json.loads(row["topics"])),
            exclusions=frozenset(str(e) for e in json.loads(row["exclusions"])),
        )

    def _issue(self, db: sqlite3.Connection, profile_id: int) -> str:
        """A new device token; tokens older than any cookie can live are pruned on the way."""
        cutoff = datetime.fromtimestamp(datetime.now(UTC).timestamp() - TOKEN_LIFE_S, UTC).isoformat()
        db.execute("DELETE FROM tokens WHERE created_at < ?", (cutoff,))
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO tokens VALUES (?, ?, ?)", (_digest(token), profile_id, _now()))
        return token

    def create(
        self, name: str, pin: str | None, topics: Iterable[int], exclusions: Iterable[str]
    ) -> tuple[Profile, str]:
        """A new profile and a device token for it; refuses a taken name, a bad PIN, or a full store."""
        display, pin = clean_name(name), clean_pin(pin)
        salt = secrets.token_bytes(16) if pin else None
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] >= MAX_PROFILES:
                raise StoreError("full", f"Matinee holds at most {MAX_PROFILES} profiles")
            try:
                cur = db.execute(
                    "INSERT INTO profiles (name, name_key, pin_salt, pin_hash, topics, exclusions, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        display,
                        name_key(display),
                        salt,
                        _pin_digest(pin, salt) if pin and salt else None,
                        json.dumps(sorted(set(topics))),
                        json.dumps(sorted(set(exclusions))),
                        _now(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise StoreError("name_taken", "that name is already a profile") from exc
            profile_id = int(cur.lastrowid or 0)
            token = self._issue(db, profile_id)
            row = db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        return self._profile(row), token

    def holding(self, tokens: Sequence[str]) -> dict[str, Profile]:
        """The profiles these device tokens remember, by token; a token for no profile is left out."""
        found: dict[str, Profile] = {}
        with closing(self._connect()) as db:
            for token in tokens:
                row = db.execute(
                    "SELECT p.* FROM tokens t JOIN profiles p ON p.id = t.profile_id WHERE t.token_hash = ?",
                    (_digest(token),),
                ).fetchone()
                if row is not None:
                    found[token] = self._profile(row)
        return found

    def suggest(self, typed: str) -> list[Profile]:
        """At most three profiles matching a typed name, closest first, and none until three characters are typed.

        Prefix matches rank before edit-distance matches, then fewer edits, then the name.
        """
        key = name_key(typed)
        if len(key) < SUGGEST_AFTER:
            return []
        with closing(self._connect()) as db:
            rows = db.execute("SELECT * FROM profiles").fetchall()
        found = [self._profile(r) for r in rows if names_match(typed, str(r["name"]))]

        def rank(p: Profile) -> tuple[bool, int, str]:
            other = name_key(p.name)
            return (not (other.startswith(key) or key.startswith(other)), edits(key, other), other)

        return sorted(found, key=rank)[:SUGGEST_AT_MOST]

    def set_exclusions(self, profile_id: int, topics: Iterable[int], exclusions: Iterable[str]) -> Profile:
        """Replace a profile's saved exclusions."""
        with closing(self._connect()) as db, db:
            db.execute(
                "UPDATE profiles SET topics = ?, exclusions = ? WHERE id = ?",
                (json.dumps(sorted(set(topics))), json.dumps(sorted(set(exclusions))), profile_id),
            )
            row = db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if row is None:
            raise StoreError("no_profile", "no such profile")
        return self._profile(row)

    def correct(self, profile_id: int, tmdb: int, remove_from: str, add_to: Iterable[str]) -> None:
        """Record one correction: the film leaves one tree and joins others, for this profile only."""
        override = secrets.token_hex(8)
        at = _now()
        rows = [(override, profile_id, tmdb, remove_from, "remove", at)]
        rows += [(override, profile_id, tmdb, tree, "add", at) for tree in sorted(set(add_to) - {remove_from})]
        with closing(self._connect()) as db, db:
            if db.execute("SELECT 1 FROM profiles WHERE id = ?", (profile_id,)).fetchone() is None:
                raise StoreError("no_profile", "no such profile")
            db.executemany(
                "INSERT INTO corrections (override_id, profile_id, tmdb, tree, direction, at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )

    def corrections(self, profile_id: int) -> list[SavedCorrection]:
        """This profile's corrections, oldest first, so a later one wins."""
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT tmdb, tree, direction FROM corrections WHERE profile_id = ? ORDER BY id", (profile_id,)
            ).fetchall()
        out = []
        for r in rows:
            direction = str(r["direction"])
            if direction not in ("remove", "add"):
                raise StoreError("bad_row", f"a stored correction has direction {direction!r}")
            out.append(SavedCorrection(int(r["tmdb"]), str(r["tree"]), "add" if direction == "add" else "remove"))
        return out

    def open(self, profile_id: int, pin: str | None, now: float) -> tuple[Profile, str]:
        """A device token for a profile found by name: needs its PIN when it has one."""
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
            if row is None:
                raise StoreError("no_profile", "no such profile")
            if row["pin_hash"] is not None:
                self._check_pin(db, row, pin, now)
            token = self._issue(db, profile_id)
        return self._profile(row), token

    def _check_pin(self, db: sqlite3.Connection, row: sqlite3.Row, pin: str | None, now: float) -> None:
        if row["locked_until"] > now:
            raise Locked(float(row["locked_until"]))
        if pin and hmac.compare_digest(_pin_digest(pin, row["pin_salt"]), row["pin_hash"]):
            db.execute("UPDATE profiles SET failed = 0 WHERE id = ?", (row["id"],))
            return
        failed = int(row["failed"]) + 1
        if failed >= PIN_TRIES:
            db.execute("UPDATE profiles SET failed = 0, locked_until = ? WHERE id = ?", (now + LOCKOUT_S, row["id"]))
            db.commit()
            raise Locked(now + LOCKOUT_S)
        db.execute("UPDATE profiles SET failed = ? WHERE id = ?", (failed, row["id"]))
        db.commit()
        raise StoreError("wrong_pin", "that PIN is not right")
