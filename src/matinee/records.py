"""What a profile keeps of its own: its ratings and their short reviews, the films it has hidden, and its last runs.

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
rating's time. A rating does not, by itself, keep a film out of any pick. While
a profile's sharing is on, its every rating and short review reach the other
profiles of the household (`Records.shared`); while it is off, none does.

A hidden film is one the profile asked Matinee not to pick, for a length the
viewer chose each time: three months, six months, a year (calendar months from
the moment it was hidden, the day clamped to the month's last) or for good.
Hiding a film already hidden replaces its length. A hide whose end has passed
no longer hides the film, and the film drops off the profile's list.

A run is everything from the first question to "Start over"; the page names
each run with a key of its own. A run is kept once its first film is shown,
with its door and answers as a note takes them, what each said, whether "Just
pick one!" ended them, and every film shown in it, in order. A film shown again
in the same run moves to the end and keeps its mark. A rating, hide or note
made on the pick names its run, and marks the film there as rated, hid or
reported; "Undo" of a hide clears its mark. A profile keeps its `MAX_RUNS`
newest runs: keeping one more drops the oldest. Nothing of DoesTheDogDie is
kept here: the page never names a film the check turned away.
"""

from __future__ import annotations

import calendar
import json
import re
import sqlite3
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast, get_args

from matinee.store import Store, StoreError, now, shown_avatar

SOURCE = "matinee"
MAX_RUNS = 50
RUN_KEY = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
Mark = Literal["rated", "hid", "reported"]
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
class Shared:
    """Another profile's rating of a film, as the household sees it: who, their avatar, the answer and the short
    review."""

    name: str
    avatar: str | None
    score: int
    review: str | None


@dataclass(frozen=True)
class Walk:
    """How a run reached a film: the door (None before one), the answers as a note takes them, what the door and
    each answer said, and whether "Just pick one!" ended the questions."""

    tree: str | None
    answers: tuple[tuple[str, int], ...]
    says: tuple[str, ...]
    rushed: bool


@dataclass(frozen=True)
class Shown:
    """A film a run showed, what the viewer did with it there (None: nothing yet), and the walk that reached it."""

    tmdb: int
    mark: Mark | None
    walk: Walk


@dataclass(frozen=True)
class Run:
    """One kept run: when it began, and its films in the order shown. Its walk is its latest film's."""

    began: str
    films: tuple[Shown, ...]

    @property
    def walk(self) -> Walk:
        return self.films[-1].walk


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


def clean_run(run_key: str) -> str:
    if not RUN_KEY.match(run_key):
        raise StoreError("bad_run", "a run's key is 8 to 64 letters, digits, - or _")
    return run_key


MARKS: tuple[str, ...] = get_args(Mark)


def _mark(value: object) -> Mark | None:
    return cast(Mark, value) if value in MARKS else None


# What each action on the pick does to its film's row in the run. A hide keeps the mark it replaces in `before`, and
# its "Undo" puts that mark back; a second hide keeps the first one's `before`.
MARKING = {
    "rated": "UPDATE run_films SET mark = 'rated', before = NULL"
    " WHERE tmdb = ? AND run_id = (SELECT id FROM runs WHERE profile_id = ? AND run_key = ?)",
    "reported": "UPDATE run_films SET mark = 'reported', before = NULL"
    " WHERE tmdb = ? AND run_id = (SELECT id FROM runs WHERE profile_id = ? AND run_key = ?)",
    "hid": "UPDATE run_films SET before = CASE WHEN mark = 'hid' THEN before ELSE mark END, mark = 'hid'"
    " WHERE tmdb = ? AND run_id = (SELECT id FROM runs WHERE profile_id = ? AND run_key = ?)",
    "undo": "UPDATE run_films SET mark = before, before = NULL"
    " WHERE mark = 'hid' AND tmdb = ? AND run_id = (SELECT id FROM runs WHERE profile_id = ? AND run_key = ?)",
}


def mark_in_run(
    db: sqlite3.Connection,
    profile_id: int,
    run_key: str | None,
    tmdb: int,
    action: Literal["rated", "reported", "hid", "undo"],
) -> None:
    """Inside the caller's write, record `action` on a film the profile's run `run_key` showed; no run named, or a
    film that run did not show, changes nothing."""
    if run_key is None:
        return
    db.execute(MARKING[action], (tmdb, profile_id, clean_run(run_key)))


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

    def rate(self, profile_id: int, tmdb: int, score: int, by: Sequence[str], run: str | None = None) -> Rating:
        """Save or change the profile's answer for a film; the same answer again changes nothing. Made on the pick,
        it names its `run`, where the film is marked rated."""
        score = clean_score(score)
        with self._store.writing(profile_id, by) as db:
            db.execute(
                "INSERT INTO ratings (profile_id, tmdb, score, at, source) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (profile_id, tmdb) DO UPDATE"
                " SET score = excluded.score, at = excluded.at, source = excluded.source, outside = NULL"
                " WHERE ratings.score != excluded.score",
                (profile_id, tmdb, score, now(), SOURCE),
            )
            mark_in_run(db, profile_id, run, tmdb, "rated")
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

    def shared(self, profile_id: int, tmdb: int, by: Sequence[str]) -> list[Shared]:
        """The ratings of a film by every other profile whose sharing is on, newest first, for a device holding
        `profile_id`; never that profile's own rating, and nothing of a profile whose sharing is off."""
        with self._store.reading(profile_id, by) as db:
            rows = db.execute(
                "SELECT p.name, p.avatar, r.score, r.review"
                " FROM ratings AS r JOIN profiles AS p ON p.id = r.profile_id"
                " WHERE r.tmdb = ? AND p.sharing = 1 AND p.id != ? ORDER BY r.at DESC, p.name_key",
                (tmdb, profile_id),
            ).fetchall()
        return [
            Shared(
                name=str(r["name"]),
                avatar=shown_avatar(r["avatar"]),
                score=int(r["score"]),
                review=r["review"],
            )
            for r in rows
        ]

    def ratings(self, profile_id: int, by: Sequence[str]) -> list[Rating]:
        """Every rating the profile has made, newest first."""
        with self._store.reading(profile_id, by) as db:
            rows = db.execute(
                "SELECT * FROM ratings WHERE profile_id = ? ORDER BY at DESC, tmdb", (profile_id,)
            ).fetchall()
        return [_rating(r) for r in rows]

    def hide(self, profile_id: int, tmdb: int, length: str, by: Sequence[str], run: str | None = None) -> Hidden:
        """Hide a film from the profile's picks for `length`, replacing any hide it already has. Made on the pick, it
        names its `run`, where the film is marked hid."""
        at = now()
        until = hide_until(at, length)
        with self._store.writing(profile_id, by) as db:
            db.execute(
                "INSERT INTO hidden (profile_id, tmdb, length, at, until) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (profile_id, tmdb) DO UPDATE"
                " SET length = excluded.length, at = excluded.at, until = excluded.until",
                (profile_id, tmdb, length, at, until),
            )
            mark_in_run(db, profile_id, run, tmdb, "hid")
        return Hidden(tmdb=tmdb, length=length, at=at, until=until)

    def unhide(self, profile_id: int, tmdb: int, by: Sequence[str], run: str | None = None) -> bool:
        """Bring a hidden film back to the profile's picks; False when it was not hidden. "Undo" on the pick names
        its `run`, where the film gets back the mark the hide replaced."""
        with self._store.writing(profile_id, by) as db:
            gone = db.execute("DELETE FROM hidden WHERE profile_id = ? AND tmdb = ?", (profile_id, tmdb)).rowcount
            mark_in_run(db, profile_id, run, tmdb, "undo")
        return gone > 0

    def hidden(self, profile_id: int, by: Sequence[str]) -> list[Hidden]:
        """The films the profile has hidden whose hide has not ended, newest hide first."""
        with self._store.reading(profile_id, by) as db:
            rows = db.execute(
                "SELECT * FROM hidden WHERE profile_id = ? AND (until IS NULL OR until > ?) ORDER BY at DESC, tmdb",
                (profile_id, now()),
            ).fetchall()
        return [_hidden(r) for r in rows]

    def show(self, profile_id: int, run_key: str, tmdb: int, walk: Walk, by: Sequence[str]) -> None:
        """Keep a film the profile's run showed, with the walk that reached it. The first film keeps the run, which
        may drop the profile's oldest; a film shown again moves to the end with its new walk and keeps its mark."""
        key, way = clean_run(run_key), _walk_columns(walk)
        with self._store.writing(profile_id, by) as db:
            found = db.execute("SELECT id FROM runs WHERE profile_id = ? AND run_key = ?", (profile_id, key)).fetchone()
            if found is None:
                added = db.execute(
                    "INSERT INTO runs (profile_id, run_key, began) VALUES (?, ?, ?)", (profile_id, key, now())
                )
                run_id = int(added.lastrowid or 0)
                _drop_oldest(db, profile_id)
            else:
                run_id = int(found["id"])
            db.execute(
                "INSERT INTO run_films (run_id, seq, tmdb, tree, answers, says, rushed) VALUES"
                " (?, (SELECT COALESCE(MAX(seq), -1) + 1 FROM run_films WHERE run_id = ?), ?, ?, ?, ?, ?)"
                " ON CONFLICT (run_id, tmdb) DO UPDATE SET seq = excluded.seq, tree = excluded.tree,"
                " answers = excluded.answers, says = excluded.says, rushed = excluded.rushed",
                (run_id, run_id, tmdb, *way),
            )

    def report(self, profile_id: int, run_key: str | None, tmdb: int, by: Sequence[str]) -> None:
        """Mark a film the profile's run showed as reported, once its note is kept."""
        with self._store.writing(profile_id, by) as db:
            mark_in_run(db, profile_id, run_key, tmdb, "reported")

    def history(self, profile_id: int, by: Sequence[str]) -> list[Run]:
        """The profile's kept runs, newest first, each with its films in the order shown."""
        with self._store.reading(profile_id, by) as db:
            runs = db.execute(
                "SELECT * FROM runs WHERE profile_id = ? ORDER BY began DESC, id DESC", (profile_id,)
            ).fetchall()
            films = db.execute(
                "SELECT f.* FROM run_films AS f JOIN runs AS r ON r.id = f.run_id"
                " WHERE r.profile_id = ? ORDER BY f.run_id, f.seq",
                (profile_id,),
            ).fetchall()
        shown: dict[int, list[Shown]] = {}
        for f in films:
            shown.setdefault(int(f["run_id"]), []).append(Shown(int(f["tmdb"]), _mark(f["mark"]), _walk(f)))
        return [Run(str(r["began"]), tuple(shown[int(r["id"])])) for r in runs if int(r["id"]) in shown]


def _walk_columns(walk: Walk) -> tuple[str | None, str, str, int]:
    answers = [{"question": q, "option": o} for q, o in walk.answers]
    return walk.tree, json.dumps(answers), json.dumps(list(walk.says)), int(walk.rushed)


def _walk(row: sqlite3.Row) -> Walk:
    answers = tuple((str(a["question"]), int(a["option"])) for a in json.loads(row["answers"]))
    says = tuple(str(x) for x in json.loads(row["says"]))
    return Walk(row["tree"], answers, says, bool(row["rushed"]))


def _drop_oldest(db: sqlite3.Connection, profile_id: int) -> None:
    """Keep only the profile's MAX_RUNS newest runs; their films go with them."""
    db.execute(
        "DELETE FROM runs WHERE profile_id = ? AND id NOT IN"
        " (SELECT id FROM runs WHERE profile_id = ? ORDER BY began DESC, id DESC LIMIT ?)",
        (profile_id, profile_id, MAX_RUNS),
    )
