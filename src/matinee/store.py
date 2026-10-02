"""Matinee's own store: profiles, the device tokens that remember them, and the notes viewers file.

A profile holds a display name, an optional four-digit PIN and the viewer's
exclusions. A note is a viewer's complaint about a pick, kept for whoever runs
Matinee; it changes nothing any viewer is shown. A note outlives the profile
that filed it, and then names no profile. Every note has a review status:
`open` when filed, then `accepted` with a one-line reason and the label ruling
that fixed it, or `rejected` with a one-line reason. A later ruling replaces an
earlier one. The file's shape and its
upgrade live in `matinee.upgrade`. Matinee never writes any of this to a media
server.

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

from matinee.upgrade import prepare

MAX_PROFILES = 50
MAX_NAME = 40
PIN_TRIES = 5
LOCKOUT_S = 15 * 60
SUGGEST_AFTER = 3
SUGGEST_AT_MOST = 3
MAX_EDITS = 2
SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
TOKEN_LIFE_S = 400 * 24 * 3600  # the cookie's own lifetime
MAX_REASON = 300
Status = Literal["open", "accepted", "rejected"]
NOTE_SELECT = "SELECT n.*, p.name AS profile FROM notes AS n LEFT JOIN profiles AS p ON p.id = n.profile_id"


@dataclass(frozen=True)
class Note:
    """A viewer's note on one pick: what was wrong with it, the answers that led there, and why."""

    profile_id: int
    tmdb: int
    tree: str
    kind: Literal["genre", "kind", "quality"]
    path: tuple[str, ...]
    rushed: bool
    comment: str
    belongs: tuple[str, ...] = ()  # where a "Not <genre> at all" note says the film belongs


@dataclass(frozen=True)
class FiledNote:
    """A note as the store holds it, with the profile's name (None when the profile is gone) and its review."""

    id: int
    profile: str | None
    tmdb: int
    tree: str
    kind: str
    path: tuple[str, ...]
    rushed: bool
    comment: str
    at: str
    belongs: tuple[str, ...]
    status: Status
    reason: str | None
    ruling: str | None
    ruled_at: str | None


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


def one_line(raw: str, what: str) -> str:
    """A reason or a ruling as stored: trimmed, one to MAX_REASON characters, on one line, no control characters."""
    text = raw.strip()
    if not text or len(text) > MAX_REASON or any(unicodedata.category(c).startswith("C") for c in text):
        raise StoreError("bad_reason", f"a {what} is one line of 1 to {MAX_REASON} characters")
    return text


def _status(raw: str) -> Status:
    if raw == "open":
        return "open"
    if raw == "accepted":
        return "accepted"
    if raw == "rejected":
        return "rejected"
    raise StoreError("bad_row", f"a stored note has status {raw!r}")


def _filed(row: sqlite3.Row) -> FiledNote:
    return FiledNote(
        id=int(row["id"]),
        profile=None if row["profile"] is None else str(row["profile"]),
        tmdb=int(row["tmdb"]),
        tree=str(row["tree"]),
        kind=str(row["kind"]),
        path=tuple(str(p) for p in json.loads(row["path"])),
        rushed=bool(row["rushed"]),
        comment=str(row["comment"]),
        at=str(row["at"]),
        belongs=tuple(str(t) for t in json.loads(row["belongs"])),
        status=_status(str(row["status"])),
        reason=row["reason"],
        ruling=row["ruling"],
        ruled_at=row["ruled_at"],
    )


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
        prepare(path)

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

    def note(self, n: Note) -> None:
        """Keep one viewer's note on a pick for review: what was wrong, the answers that led to it, and why."""
        with closing(self._connect()) as db, db:
            if db.execute("SELECT 1 FROM profiles WHERE id = ?", (n.profile_id,)).fetchone() is None:
                raise StoreError("no_profile", "no such profile")
            db.execute(
                "INSERT INTO notes (profile_id, tmdb, tree, kind, path, rushed, comment, at, belongs)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    n.profile_id,
                    n.tmdb,
                    n.tree,
                    n.kind,
                    json.dumps(list(n.path)),
                    int(n.rushed),
                    n.comment,
                    _now(),
                    json.dumps(sorted(set(n.belongs))),
                ),
            )

    def notes(self, status: Status = "open") -> list[FiledNote]:
        """Every note with this status, oldest first."""
        with closing(self._connect()) as db:
            rows = db.execute(f"{NOTE_SELECT} WHERE n.status = ? ORDER BY n.id", (status,)).fetchall()
        return [_filed(r) for r in rows]

    def filed(self, note_id: int) -> FiledNote:
        """One note by its id; refuses an id no note has."""
        with closing(self._connect()) as db:
            row = db.execute(f"{NOTE_SELECT} WHERE n.id = ?", (note_id,)).fetchone()
        if row is None:
            raise StoreError("no_note", f"no note {note_id}")
        return _filed(row)

    def rule(
        self, note_id: int, status: Literal["accepted", "rejected"], reason: str, ruling: str | None = None
    ) -> FiledNote:
        """Record a ruling on one note, replacing any earlier one, and return the note as it stood before.

        An accepted note needs the label ruling that fixed it; a rejected one takes none. A ruling changes no
        film's placement.
        """
        reason = one_line(reason, "reason")
        if (status == "accepted") != (ruling is not None):
            raise StoreError("bad_ruling", "an accepted note names its label ruling, and a rejected one names none")
        kept = None if ruling is None else one_line(ruling, "ruling")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(f"{NOTE_SELECT} WHERE n.id = ?", (note_id,)).fetchone()
            if row is None:
                raise StoreError("no_note", f"no note {note_id}")
            db.execute(
                "UPDATE notes SET status = ?, reason = ?, ruling = ?, ruled_at = ? WHERE id = ?",
                (status, reason, kept, _now(), note_id),
            )
        return _filed(row)

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
