"""What a profile keeps of its own: its ratings and their short reviews, and the films it has hidden.

Everything here is private to the profile. Only a device holding one of its
tokens reads or writes it, and every write checks that in the same store
transaction as the write (`Store.writing`). The store's shape and its tables
live in `matinee.upgrade`.

A rating is one of the five answers, stored as 1 ("Hated it") to 5 ("Loved
it!"), with the time it was made, its source (`matinee` for every rating made
here) and an outside value that only an import from another service fills.
Saving the answer a film already has records nothing and keeps the first time,
so a later sync never sends a rating that did not change. A rating may carry a
short review: one line of plain text, at most `MAX_REVIEW` characters. A longer
one is refused, never cut. Changing only the short review does not change the
rating's time. A rating does not, by itself, keep a film out of any pick.

A hidden film is one the profile asked Matinee not to pick, for a length the
viewer chose each time: three months, six months, a year (calendar months from
the moment it was hidden, the day clamped to the month's last) or for good.
Hiding a film already hidden replaces its length. A hide whose end has passed
no longer hides the film, and the film drops off the profile's list.
"""

from __future__ import annotations

import calendar
import sqlite3
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from matinee.store import Store, StoreError, now

SOURCE = "matinee"
MAX_REVIEW = 140
SCORES = range(1, 6)
# A short review is one line: control characters (tab, newline, carriage return, next line) and the line and
# paragraph separators are refused. Format characters stay, since every joined emoji carries one.
LINE_BREAKING = frozenset({"Cc", "Zl", "Zp"})


# Each hide length, as the store keeps it, and how many months it lasts; None lasts for good.
LENGTHS: dict[str, int | None] = {"3m": 3, "6m": 6, "1y": 12, "good": None}


@dataclass(frozen=True)
class Hidden:
    """A film the profile has hidden: the length chosen, when, and when it comes back (None for good)."""

    tmdb: int
    length: str
    at: str
    until: str | None


@dataclass(frozen=True)
class Rating:
    """One profile's answer about one film, and the short review it carries (None when it has none)."""

    tmdb: int
    score: int
    at: str
    source: str
    outside: str | None
    review: str | None


def clean_score(score: int) -> int:
    if score not in SCORES:
        raise StoreError("bad_score", "a rating is a whole number from 1 to 5")
    return score


def clean_review(raw: str | None) -> str | None:
    """The short review as stored: trimmed, one line of at most MAX_REVIEW characters; None for an empty one."""
    text = (raw or "").strip()
    if not text:
        return None
    if len(text) > MAX_REVIEW or any(unicodedata.category(c) in LINE_BREAKING for c in text):
        raise StoreError("bad_review", f"a short review is one line of at most {MAX_REVIEW} characters")
    return text


def months_on(at: datetime, months: int) -> datetime:
    """The same moment `months` calendar months later; a day the later month lacks becomes its last day."""
    total = at.month - 1 + months
    year, month = at.year + total // 12, total % 12 + 1
    return at.replace(year=year, month=month, day=min(at.day, calendar.monthrange(year, month)[1]))


def hide_until(at: str, length: str) -> str | None:
    """When a hide of `length` made at `at` ends, in the store's time format; None for good. Refuses an unknown
    length, so a hide always names one."""
    if length not in LENGTHS:
        raise StoreError("bad_length", "a hide lasts 3 months, 6 months, 1 year or for good")
    months = LENGTHS[length]
    return None if months is None else months_on(datetime.fromisoformat(at), months).isoformat()


def _hidden(row: sqlite3.Row) -> Hidden:
    return Hidden(tmdb=int(row["tmdb"]), length=str(row["length"]), at=str(row["at"]), until=row["until"])


def _rating(row: sqlite3.Row) -> Rating:
    return Rating(
        tmdb=int(row["tmdb"]),
        score=int(row["score"]),
        at=str(row["at"]),
        source=str(row["source"]),
        outside=row["outside"],
        review=row["review"],
    )


RATING = "SELECT * FROM ratings WHERE profile_id = ? AND tmdb = ?"


class Records:
    """A profile's own records, read and written through the store's ownership checks."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def rate(self, profile_id: int, tmdb: int, score: int, by: Sequence[str]) -> Rating:
        """Save or change the profile's answer for a film; the same answer again changes nothing."""
        score = clean_score(score)
        with self._store.writing(profile_id, by) as db:
            db.execute(
                "INSERT INTO ratings (profile_id, tmdb, score, at, source) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (profile_id, tmdb) DO UPDATE"
                " SET score = excluded.score, at = excluded.at, source = excluded.source, outside = NULL"
                " WHERE ratings.score != excluded.score",
                (profile_id, tmdb, score, now(), SOURCE),
            )
            row = db.execute(RATING, (profile_id, tmdb)).fetchone()
        return _rating(row)

    def unrate(self, profile_id: int, tmdb: int, by: Sequence[str]) -> bool:
        """Clear the profile's rating of a film, and its short review with it; False when there was none."""
        with self._store.writing(profile_id, by) as db:
            gone = db.execute("DELETE FROM ratings WHERE profile_id = ? AND tmdb = ?", (profile_id, tmdb)).rowcount
        return gone > 0

    def review(self, profile_id: int, tmdb: int, text: str | None, by: Sequence[str]) -> Rating:
        """Save, change or clear (empty or None) the short review of a film the profile has rated; refuses a film it
        has not rated, since a short review belongs to a rating."""
        kept = clean_review(text)
        with self._store.writing(profile_id, by) as db:
            changed = db.execute(
                "UPDATE ratings SET review = ? WHERE profile_id = ? AND tmdb = ?", (kept, profile_id, tmdb)
            ).rowcount
            if not changed:
                raise StoreError("not_rated", "a short review needs a rating of the film first")
            row = db.execute(RATING, (profile_id, tmdb)).fetchone()
        return _rating(row)

    def ratings(self, profile_id: int, by: Sequence[str]) -> list[Rating]:
        """Every rating the profile has made, newest first."""
        with self._store.reading(profile_id, by) as db:
            rows = db.execute(
                "SELECT * FROM ratings WHERE profile_id = ? ORDER BY at DESC, tmdb", (profile_id,)
            ).fetchall()
        return [_rating(r) for r in rows]

    def hide(self, profile_id: int, tmdb: int, length: str, by: Sequence[str]) -> Hidden:
        """Hide a film from the profile's picks for `length`, replacing any hide it already has."""
        at = now()
        until = hide_until(at, length)
        with self._store.writing(profile_id, by) as db:
            db.execute(
                "INSERT INTO hidden (profile_id, tmdb, length, at, until) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (profile_id, tmdb) DO UPDATE"
                " SET length = excluded.length, at = excluded.at, until = excluded.until",
                (profile_id, tmdb, length, at, until),
            )
        return Hidden(tmdb=tmdb, length=length, at=at, until=until)

    def unhide(self, profile_id: int, tmdb: int, by: Sequence[str]) -> bool:
        """Bring a hidden film back to the profile's picks; False when it was not hidden."""
        with self._store.writing(profile_id, by) as db:
            gone = db.execute("DELETE FROM hidden WHERE profile_id = ? AND tmdb = ?", (profile_id, tmdb)).rowcount
        return gone > 0

    def hidden(self, profile_id: int, by: Sequence[str]) -> list[Hidden]:
        """The films the profile has hidden whose hide has not ended, newest hide first."""
        with self._store.reading(profile_id, by) as db:
            rows = db.execute(
                "SELECT * FROM hidden WHERE profile_id = ? AND (until IS NULL OR until > ?) ORDER BY at DESC, tmdb",
                (profile_id, now()),
            ).fetchall()
        return [_hidden(r) for r in rows]
