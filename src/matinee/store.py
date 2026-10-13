"""Matinee's own store: profiles, the device tokens that remember them, and the notes viewers file.

A profile holds a display name, an optional four-digit PIN, an optional avatar
(one of `AVATARS`; two profiles may share one) and the DoesTheDogDie topics the
viewer steers around, its tailoring settings and whether it has seen the welcome,
and it keeps ratings, hidden films and its last runs, all of which go with it.
The store's `exclusions` column is no longer read or
written; a new row takes its empty default. An
avatar Matinee does not offer is refused when set and reads as none when found
in the store. A note is a viewer's complaint about a pick, kept for whoever runs
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
from collections.abc import Iterable, Iterator, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from matinee.upgrade import prepare

MAX_PROFILES = 50
MAX_NAME = 40
PIN_TRIES = 5
LOCKOUT_S = 15 * 60
SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
TOKEN_LIFE_S = 400 * 24 * 3600  # the cookie's own lifetime
MAX_REASON = 300
AVATARS = (
    "3d-glasses",
    "camera",
    "candy",
    "chair",
    "clapperboard",
    "comedy-tragedy",
    "director-megaphone",
    "film-reel",
    "hotdog",
    "nachos",
    "popcorn",
    "soda",
    "theater-seat",
    "ticket",
    "vhs",
)
Status = Literal["open", "accepted", "rejected"]
# The rating floor's choices, loosest first: every film; above the bottom 10%; the bottom 40% kept out; only the top
# 40%; only the top 25% (`matinee.ranks` bands).
FLOORS = ("anything", "above_bottom", "middle", "above_middle", "well_liked")
# The rated-films setting: films rated this or lower stay out of the profile's picks; 0 keeps every rated film in.
RATED_OUT = range(0, 6)
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


@dataclass(frozen=True, kw_only=True)
class Profile:
    """A profile and its tailoring settings: the rating floor (one of FLOORS), the languages it watches in (none
    ticked: any language), the rated-films setting (RATED_OUT), whether it shares its ratings with the household, and
    whether it has seen this feature's welcome."""

    id: int
    name: str
    has_pin: bool
    topics: frozenset[int]
    avatar: str | None = None
    floor: str
    languages: frozenset[str]
    rated_out: int
    sharing: bool
    welcomed: bool


@dataclass(frozen=True)
class Settings:
    """A change to a profile's settings; None leaves that setting as it is."""

    floor: str | None = None
    languages: frozenset[str] | None = None
    rated_out: int | None = None
    sharing: bool | None = None


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


def clean_avatar(avatar: str | None) -> str | None:
    if avatar is not None and avatar not in AVATARS:
        raise StoreError("bad_avatar", "that avatar is not one Matinee offers")
    return avatar


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _pin_digest(pin: str, salt: bytes) -> bytes:
    return hashlib.scrypt(pin.encode(), salt=salt, **SCRYPT)


def now() -> str:
    """The time as the store keeps it: ISO 8601 in UTC."""
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
            avatar=row["avatar"] if row["avatar"] in AVATARS else None,
            floor=str(row["floor"]),
            languages=frozenset(str(code) for code in json.loads(row["languages"])),
            rated_out=int(row["rated_out"]),
            sharing=bool(row["sharing"]),
            welcomed=bool(row["welcomed"]),
        )

    def _issue(self, db: sqlite3.Connection, profile_id: int) -> str:
        """A new device token; tokens older than any cookie can live are pruned on the way."""
        cutoff = datetime.fromtimestamp(datetime.now(UTC).timestamp() - TOKEN_LIFE_S, UTC).isoformat()
        db.execute("DELETE FROM tokens WHERE created_at < ?", (cutoff,))
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO tokens VALUES (?, ?, ?)", (_digest(token), profile_id, now()))
        return token

    def create(
        self, name: str, pin: str | None, topics: Iterable[int], avatar: str | None = None
    ) -> tuple[Profile, str]:
        """A new profile and a device token for it; refuses a taken name, a bad PIN or avatar, or a full store.

        A profile made now is marked as having seen the welcome: making it already offers the tailoring steps."""
        display, pin, avatar = clean_name(name), clean_pin(pin), clean_avatar(avatar)
        salt = secrets.token_bytes(16) if pin else None
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] >= MAX_PROFILES:
                raise StoreError("full", f"Matinee holds at most {MAX_PROFILES} profiles")
            try:
                cur = db.execute(
                    "INSERT INTO profiles (name, name_key, pin_salt, pin_hash, topics, created_at, avatar, welcomed)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                    (
                        display,
                        name_key(display),
                        salt,
                        _pin_digest(pin, salt) if pin and salt else None,
                        json.dumps(sorted(set(topics))),
                        now(),
                        avatar,
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

    def everyone(self) -> list[Profile]:
        """Every profile, sorted by name ignoring case."""
        with closing(self._connect()) as db:
            rows = db.execute("SELECT * FROM profiles ORDER BY name_key, id").fetchall()
        return [self._profile(r) for r in rows]

    @staticmethod
    def _issued(db: sqlite3.Connection, profile_id: int, tokens: Sequence[str]) -> sqlite3.Row | None:
        """The profile, when one of these device tokens is issued for it; None otherwise."""
        issued = {str(r[0]) for r in db.execute("SELECT token_hash FROM tokens WHERE profile_id = ?", (profile_id,))}
        held: sqlite3.Row | None = db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if held is None or not issued & {_digest(t) for t in tokens}:
            return None
        return held

    @classmethod
    def _held(cls, db: sqlite3.Connection, profile_id: int, tokens: Sequence[str]) -> sqlite3.Row:
        """The profile, inside the caller's write transaction, when one of these device tokens is issued for it.

        Checking and writing in one transaction means a profile deleted, and its id reused by a new profile,
        between a device's check and its write can never receive that write: the new profile holds none of the
        device's tokens.
        """
        db.execute("BEGIN IMMEDIATE")
        held = cls._issued(db, profile_id, tokens)
        if held is None:
            raise StoreError("not_held", "this device holds no token for that profile")
        return held

    @contextmanager
    def writing(self, profile_id: int, by: Sequence[str]) -> Iterator[sqlite3.Connection]:
        """One write transaction on what a profile keeps, opened only for a profile one of the tokens `by` is issued
        for, and committed when the block ends without an error."""
        with closing(self._connect()) as db, db:
            self._held(db, profile_id, by)
            yield db

    @contextmanager
    def reading(self, profile_id: int, by: Sequence[str]) -> Iterator[sqlite3.Connection]:
        """A connection that reads what a profile keeps, opened only for a profile one of the tokens `by` is issued
        for."""
        with closing(self._connect()) as db:
            if self._issued(db, profile_id, by) is None:
                raise StoreError("not_held", "this device holds no token for that profile")
            yield db

    def set_topics(self, profile_id: int, topics: Iterable[int], by: Sequence[str]) -> Profile:
        """Replace the saved DoesTheDogDie topics of a profile one of the device tokens `by` is issued for."""
        with closing(self._connect()) as db, db:
            self._held(db, profile_id, by)
            db.execute("UPDATE profiles SET topics = ? WHERE id = ?", (json.dumps(sorted(set(topics))), profile_id))
            row = db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        return self._profile(row)

    def clear_topics(self) -> int:
        """Clear every profile's DoesTheDogDie topics; returns how many profiles held any."""
        with closing(self._connect()) as db, db:
            return db.execute("UPDATE profiles SET topics = '[]' WHERE topics != '[]'").rowcount

    def rename(self, profile_id: int, name: str, by: Sequence[str]) -> Profile:
        """Rename a profile `by` holds, under the rules a new profile's name follows; its own name in another case is
        allowed, and another profile's is refused as name_taken."""
        display = clean_name(name)
        with closing(self._connect()) as db, db:
            self._held(db, profile_id, by)
            try:
                db.execute(
                    "UPDATE profiles SET name = ?, name_key = ? WHERE id = ?", (display, name_key(display), profile_id)
                )
            except sqlite3.IntegrityError as exc:
                raise StoreError("name_taken", "that name is already a profile") from exc
            row = db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        return self._profile(row)

    def set_avatar(self, profile_id: int, avatar: str | None, by: Sequence[str]) -> Profile:
        """Set the avatar of a profile `by` holds, or clear it for initials; refuses an avatar not offered."""
        avatar = clean_avatar(avatar)
        with closing(self._connect()) as db, db:
            self._held(db, profile_id, by)
            db.execute("UPDATE profiles SET avatar = ? WHERE id = ?", (avatar, profile_id))
            row = db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        return self._profile(row)

    def profile(self, profile_id: int, by: Sequence[str]) -> Profile:
        """The profile with its settings, when one of the tokens `by` is issued for it; not_held otherwise."""
        with closing(self._connect()) as db:
            row = self._issued(db, profile_id, by)
        if row is None:
            raise StoreError("not_held", "this device holds no token for that profile")
        return self._profile(row)

    def set_settings(self, profile_id: int, change: Settings, known: frozenset[str], by: Sequence[str]) -> Profile:
        """Change the settings of a profile `by` holds. Refuses a floor or rated-films choice that is not offered, and a
        newly ticked language that is not in `known` (the languages the film table holds); a language already ticked
        stays kept whether or not the table still holds it."""
        if change.floor is not None and change.floor not in FLOORS:
            raise StoreError("bad_setting", f"the rating floor is one of {', '.join(FLOORS)}")
        if change.rated_out is not None and change.rated_out not in RATED_OUT:
            raise StoreError("bad_setting", "the rated-films setting is a rating from 0 to 5")
        with closing(self._connect()) as db, db:
            row = self._held(db, profile_id, by)
            kept = frozenset(str(code) for code in json.loads(row["languages"]))
            if change.languages is not None and change.languages - known - kept:
                raise StoreError("bad_language", "that language is not one the film table holds")
            languages = kept if change.languages is None else change.languages
            db.execute(
                "UPDATE profiles SET floor = ?, languages = ?, rated_out = ?, sharing = ? WHERE id = ?",
                (
                    row["floor"] if change.floor is None else change.floor,
                    json.dumps(sorted(languages)),
                    row["rated_out"] if change.rated_out is None else change.rated_out,
                    row["sharing"] if change.sharing is None else int(change.sharing),
                    profile_id,
                ),
            )
            row = db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        return self._profile(row)

    def welcome(self, profile_id: int, by: Sequence[str]) -> Profile:
        """Mark a profile `by` holds as having seen this feature's welcome; it never shows again."""
        with closing(self._connect()) as db, db:
            self._held(db, profile_id, by)
            db.execute("UPDATE profiles SET welcomed = 1 WHERE id = ?", (profile_id,))
            row = db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        return self._profile(row)

    def note(self, n: Note, by: Sequence[str]) -> None:
        """Keep one viewer's note on a pick for review, filed by a profile `by` holds: what was wrong and why."""
        with closing(self._connect()) as db, db:
            self._held(db, n.profile_id, by)
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
                    now(),
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
                (status, reason, kept, now(), note_id),
            )
        return _filed(row)

    def delete(self, profile_id: int, by: Sequence[str]) -> Profile:
        """Delete a profile `by` holds with everything it keeps: its settings, every device token issued for it, its
        ratings, hidden films and runs. Its notes stay."""
        with closing(self._connect()) as db, db:
            row = self._held(db, profile_id, by)
            db.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        return self._profile(row)

    def clear_pin(self, name: str) -> Profile:
        """Clear the PIN and any lockout of the profile with this name, ignoring case; refuses an unknown name."""
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT id FROM profiles WHERE name_key = ?", (name_key(clean_name(name)),)).fetchone()
            if row is None:
                raise StoreError("no_profile", f"no profile is named {name.strip()!r}")
            db.execute(
                "UPDATE profiles SET pin_salt = NULL, pin_hash = NULL, failed = 0, locked_until = 0 WHERE id = ?",
                (row["id"],),
            )
            cleared = db.execute("SELECT * FROM profiles WHERE id = ?", (row["id"],)).fetchone()
        return self._profile(cleared)

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
