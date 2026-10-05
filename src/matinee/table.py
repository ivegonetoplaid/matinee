"""The offline film table: for every film Matinee can offer, the facts and scores the trees filter on.

Built nightly from the media server's film list, the films the labels name, the
shipped genome scores (`data/genome.json`) and the TMDB cache, and written as one
SQLite file in Matinee's own storage, never in the repository. The app reads it
and never queries the genome or TMDB.

A row is a library film (with its media-server item and facts) or a film the labels
name that the library did not hold at the rebuild (with TMDB's title, year,
runtime, rating, genres and US age rating in the same columns, and no item). Every
row also keeps the film's TMDB facts in their own columns, so a film can change
sides between rebuilds: the server reads which films the library holds from the
media server's live list (`with_live`), never from the table.

A film the genome does not cover carries no genome scores (NaN), never zeros.
A film whose TMDB record is missing or older than six months carries no TMDB
facts (`tmdb_known` is False, keywords None rather than empty); a film the library
does not hold needs those facts to be offered at all. A table whose oldest TMDB
fact is six months old or more is still read and served, flagged (`is_stale`):
TMDB's terms cap caching there, and the server warns on every screen until a
rebuild refreshes it.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from matinee.genome import Matrix, Scores
from matinee.library import LibraryFilm
from matinee.tmdb import MAX_AGE, TmdbFilm

FORMAT = 2
SHOWN = ("name", "year", "genres", "certificate", "runtime_min", "rating")  # the facts the trees and the page read
TMDB_COLUMNS = (
    "tmdb_known",
    "language",
    "collection_id",
    "keywords",
    "poster_path",
    "backdrop_path",
    "tmdb_title",
    "tmdb_year",
    "tmdb_genres",
    "tmdb_certificate",
    "tmdb_runtime",
    "tmdb_rating",
    "synopsis",
    "vote_count",
)
COLUMNS = ("item_id", *SHOWN, *TMDB_COLUMNS)
SET_COLUMNS = ("genres", "keywords", "tmdb_genres")  # stored as JSON lists, read as frozensets (None stays None)


class TableError(RuntimeError):
    """The film table is absent, in another format, or too old to serve."""


@dataclass(frozen=True)
class FilmTable:
    """Films indexed by TMDB id, with a genome matrix aligned to that index (NaN rows where uncovered)."""

    films: pd.DataFrame
    tags: tuple[str, ...]
    genome: Matrix
    built_at: datetime
    oldest_tmdb: datetime | None
    release: str

    def mean_of(self, tags: Sequence[str]) -> pd.Series:
        """Mean genome relevance of `tags` per film; NaN where the genome does not cover the film."""
        if not tags:
            raise TableError("a score needs at least one tag")
        index = {t: i for i, t in enumerate(self.tags)}
        missing = [t for t in tags if t not in index]
        if missing:
            raise TableError(f"tags not in the film table's genome: {', '.join(missing)}")
        return pd.Series(self.genome[:, [index[t] for t in tags]].mean(axis=1), index=self.films.index)

    def tag(self, name: str) -> pd.Series:
        return self.mean_of([name])

    def has_genome(self) -> pd.Series:
        return pd.Series(~np.isnan(self.genome).any(axis=1), index=self.films.index)

    def subset(self, ids: Sequence[int]) -> FilmTable:
        """The same table holding only the films `ids`, in table order: a smaller library for the checker."""
        keep = self.films.index.isin(list(ids))
        return FilmTable(self.films[keep], self.tags, self.genome[keep], self.built_at, self.oldest_tmdb, self.release)


@dataclass
class BuildReport:
    """What the nightly pass saw that the operator should know about. It changes nothing on the server."""

    library_items: int = 0
    no_tmdb_id: list[str] = field(default_factory=list)
    path_mismatches: list[str] = field(default_factory=list)
    tmdb_missing: list[str] = field(default_factory=list)
    tmdb_too_old: list[str] = field(default_factory=list)
    with_genome: int = 0
    not_held: int = 0  # films the labels name that the library did not hold, each with a usable TMDB record
    listed_without_record: int = 0  # films the labels name that the library did not hold, left out for want of one

    def lines(self) -> list[str]:
        out = [
            f"{self.library_items} library items; {self.with_genome} films with genome scores",
            f"{len(self.no_tmdb_id)} items with no TMDB id (not in the table)",
            f"{len(self.path_mismatches)} files whose {{tmdb-N}} folder tag differs from the server's TMDB id",
            f"{len(self.tmdb_missing)} films with no TMDB record; {len(self.tmdb_too_old)} over six months old",
            f"{self.not_held} films the labels name that the library does not hold; "
            f"{self.listed_without_record} more left out for want of a usable TMDB record",
        ]
        out += [f"  path tag differs: {m}" for m in self.path_mismatches]
        out += [f"  no TMDB record: {m}" for m in self.tmdb_missing]
        out += [f"  TMDB record too old: {m}" for m in self.tmdb_too_old]
        return out


def _label(f: LibraryFilm) -> str:
    return f"{f.name} ({f.year})"


def _tmdb_fields(rec: TmdbFilm | None, usable: bool) -> dict[str, object]:
    """The TMDB columns of a row; all unknown when the film has no usable record."""
    if rec is None or not usable:
        return {"tmdb_known": False, **dict.fromkeys(TMDB_COLUMNS[1:])}
    return {
        "tmdb_known": True,
        "language": rec.original_language or None,
        "collection_id": rec.collection_id,
        "keywords": frozenset(rec.keywords),
        "poster_path": rec.poster_path or None,
        "backdrop_path": rec.backdrop_path or None,
        "tmdb_title": rec.title or None,
        "tmdb_year": rec.year,
        "tmdb_genres": None if rec.genres is None else frozenset(rec.genres),
        "tmdb_certificate": rec.certification or "",
        "tmdb_runtime": rec.runtime_min,
        "tmdb_rating": rec.rating,
        "synopsis": rec.synopsis or None,
        "vote_count": rec.vote_count,
    }


def _text(value: object) -> str | None:
    """A non-empty string, or None for anything else (None, NaN or pandas' NA read from the table included)."""
    return value if isinstance(value, str) and value else None


def _from_tmdb(tmdb: dict[str, object]) -> dict[str, object]:
    """The shown facts of a film the library does not hold: TMDB's, with no item."""
    genres = tmdb["tmdb_genres"]
    return {
        "item_id": None,
        "name": tmdb["tmdb_title"],
        "year": tmdb["tmdb_year"],
        "genres": genres if genres is not None else frozenset(),
        "certificate": tmdb["tmdb_certificate"] or "",
        "runtime_min": tmdb["tmdb_runtime"],
        "rating": tmdb["tmdb_rating"],
    }


def _from_library(f: LibraryFilm, tmdb: Mapping[str, object]) -> dict[str, object]:
    """The shown facts of a film the library holds: the media server's, with three exceptions.

    Its genres are TMDB's when it has a usable record, because the rules read TMDB's genre names and a Plex
    library writes its own. An empty title is TMDB's. A rating another country's system wrote (a prefix such
    as `gb/`) is TMDB's US one, which the kids pool reads.
    """
    genres = tmdb.get("tmdb_genres")
    certificate = f.certificate
    if "/" in certificate and tmdb.get("tmdb_known"):
        certificate = str(tmdb.get("tmdb_certificate") or "")
    return {
        "item_id": f.item_id,
        "name": f.name or _text(tmdb.get("tmdb_title")) or "",
        "year": f.year,
        "genres": genres if tmdb.get("tmdb_known") and genres else f.genres,
        "certificate": certificate,
        "runtime_min": f.runtime_min,
        "rating": f.rating,
    }


def _record(tmdb: Mapping[int, TmdbFilm], t: int, now: datetime) -> tuple[TmdbFilm | None, bool]:
    rec = tmdb.get(t)
    return rec, rec is not None and now - rec.fetched < MAX_AGE


def _library_rows(
    films: Sequence[LibraryFilm], tmdb: Mapping[int, TmdbFilm], now: datetime, report: BuildReport
) -> dict[int, dict[str, object]]:
    """One row per distinct TMDB id the library holds; the first file of a film supplies its media-server item."""
    seen: dict[int, dict[str, object]] = {}
    for f in films:
        if f.tmdb is None:
            report.no_tmdb_id.append(_label(f))
            continue
        if f.path_tmdb is not None and f.path_tmdb != f.tmdb:
            report.path_mismatches.append(f"{_label(f)}: folder says {f.path_tmdb}, server says {f.tmdb}")
        if f.tmdb in seen:
            continue
        rec, usable = _record(tmdb, f.tmdb, now)
        if rec is None:
            report.tmdb_missing.append(_label(f))
        elif not usable:
            report.tmdb_too_old.append(_label(f))
        fields = _tmdb_fields(rec, usable)
        seen[f.tmdb] = {**_from_library(f, fields), **fields}
    return seen


def _listed_rows(
    listed: Iterable[int], held: Mapping[int, object], tmdb: Mapping[int, TmdbFilm], now: datetime, report: BuildReport
) -> dict[int, dict[str, object]]:
    """A row for each film the labels name that the library does not hold and that has a usable TMDB record."""
    rows: dict[int, dict[str, object]] = {}
    for t in sorted(set(listed) - set(held)):
        rec, usable = _record(tmdb, t, now)
        if not usable or rec is None or not rec.title:  # a record with no title cannot name the film
            report.listed_without_record += 1
            continue
        fields = _tmdb_fields(rec, usable)
        rows[t] = {**_from_tmdb(fields), **fields}
    return rows


def _frame(rows: Mapping[int, Mapping[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame.from_dict(dict(rows), orient="index", columns=list(COLUMNS))
    frame.index.name = "tmdb"
    for column in ("year", "collection_id", "tmdb_year", "vote_count"):
        frame[column] = frame[column].astype("Int64")
    frame["tmdb_known"] = frame.tmdb_known.astype(bool)
    return frame


def build_table(
    films: Sequence[LibraryFilm],
    genome: Scores,
    tmdb: Mapping[int, TmdbFilm],
    now: datetime,
    listed: Iterable[int] = (),
) -> tuple[FilmTable, BuildReport]:
    """The table for the library `films` and the films the labels name (`listed`), and what the pass saw.

    Library films with no TMDB id are left out and reported. A listed film the library does not hold joins only
    with a usable TMDB record, since its title and facts come from it.
    """
    report = BuildReport(library_items=len(films))
    held = _library_rows(films, tmdb, now, report)
    frame = _frame({**held, **_listed_rows(listed, held, tmdb, now, report)}).sort_index()
    matrix = np.full((len(frame), len(genome.tags)), np.nan, dtype=np.float32)
    for i, t in enumerate(frame.index):
        row = genome.rows.get(int(t))
        if row is not None:
            matrix[i] = genome.relevance[row]
    report.with_genome = int((~np.isnan(matrix).any(axis=1)).sum())
    report.not_held = int(frame.item_id.isna().sum())
    known = [tmdb[int(t)].fetched for t in frame.index[frame.tmdb_known]]
    table = FilmTable(frame, genome.tags, matrix, now, min(known) if known else None, genome.release)
    return table, report


SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE films (
    tmdb INTEGER PRIMARY KEY, item_id TEXT, name TEXT NOT NULL, year INTEGER,
    genres TEXT NOT NULL, certificate TEXT NOT NULL, runtime_min REAL, rating REAL,
    tmdb_known INTEGER NOT NULL, language TEXT, collection_id INTEGER, keywords TEXT,
    poster_path TEXT, backdrop_path TEXT, tmdb_title TEXT, tmdb_year INTEGER, tmdb_genres TEXT,
    tmdb_certificate TEXT, tmdb_runtime REAL, tmdb_rating REAL, synopsis TEXT, vote_count INTEGER
);
CREATE TABLE genome (tmdb INTEGER PRIMARY KEY REFERENCES films(tmdb), relevance BLOB NOT NULL);
"""
INSERT_FILM = (
    "INSERT INTO films VALUES ("
    "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?"
    ")"
)  # one placeholder per column of SCHEMA's films table, tmdb first


def empty_table(tags: Sequence[str]) -> FilmTable:
    """A table with no films: what the server shows before the first rebuild writes one."""
    frame = _frame({})
    return FilmTable(frame, tuple(tags), np.zeros((0, len(tags)), dtype=np.float32), datetime.now(UTC), None, "")


def library_films(table: FilmTable) -> list[LibraryFilm]:
    """The library the table was built from: its rows with a media-server item, as the table holds them."""
    if "item_id" not in table.films:
        return []
    rows = table.films[table.films.item_id.notna()]
    return [
        LibraryFilm(
            str(r.item_id),
            int(str(t)),
            str(r["name"]),
            None if pd.isna(r.year) else int(r.year),
            frozenset(r.genres),
            str(r.certificate),
            None if pd.isna(r.runtime_min) else float(r.runtime_min),
            None if pd.isna(r.rating) else float(r.rating),
            None,
        )
        for t, r in rows.iterrows()
    ]


def _offered(tmdb_id: int, r: pd.Series, live: Mapping[int, LibraryFilm], names: set[int]) -> dict[str, object] | None:
    """The row `with_live` offers for one table row, or None when the film is not offered."""
    fields = {c: r[c] for c in TMDB_COLUMNS}
    if tmdb_id in live and pd.notna(r.item_id):
        shown = {c: r[c] for c in SHOWN}  # the media server's facts as the rebuild read them
        return {"item_id": live[tmdb_id].item_id, **shown, **fields, "held": True}
    if tmdb_id in live:  # the library has taken it in since the rebuild, which read TMDB's facts
        return {**_from_library(live[tmdb_id], fields), **fields, "held": True}
    if tmdb_id in names and fields["tmdb_known"] and _text(fields["tmdb_title"]):
        return {**_from_tmdb(fields), **fields, "held": False}
    return None


def _aligned(table: FilmTable, index: pd.Index) -> Matrix:
    """The table's genome rows in the order of `index`; NaN for a film the table does not hold."""
    order = {int(str(t)): i for i, t in enumerate(table.films.index)}
    genome = np.full((len(index), len(table.tags)), np.nan, dtype=np.float32)
    for i, t in enumerate(index):
        at = order.get(int(str(t)))
        if at is not None:
            genome[i] = table.genome[at]
    return genome


def with_live(
    table: FilmTable, films: Sequence[LibraryFilm] | None, listed: Iterable[int] = ()
) -> tuple[FilmTable, list[str]]:
    """What the server offers: the films the library holds now, and the films the labels name it does not.

    `films` is the media server's live list, or None while the library cannot be used. A held film shows the
    media server's facts now (`_from_library`) and is marked `held`. A film the labels name (`listed`) that the
    library does not hold shows its TMDB facts, and only with a usable record. A film gone from the library and
    named by no label is never offered. A held film the table does not know yet (added since the last rebuild) is
    offered by its media-server facts alone: no genome scores and no TMDB facts. Returns the names of those films.
    """
    live: dict[int, LibraryFilm] = {}
    for f in films or ():
        if f.tmdb is not None:
            live.setdefault(f.tmdb, f)
    names = set(listed)
    rows: dict[int, dict[str, object]] = {}
    for t, r in table.films.iterrows():
        row = _offered(int(str(t)), r, live, names)
        if row is not None:
            rows[int(str(t))] = row
    new = [f for t, f in live.items() if t not in table.films.index]
    for f in new:
        fields = _tmdb_fields(None, False)
        rows[int(str(f.tmdb))] = {**_from_library(f, fields), **fields, "held": True}
    frame = _frame(rows)
    frame["held"] = pd.Series({t: r["held"] for t, r in rows.items()}, dtype=bool)
    merged = FilmTable(
        frame, table.tags, _aligned(table, frame.index), table.built_at, table.oldest_tmdb, table.release
    )
    return merged, [_label(f) for f in new]


def _optional(value: object) -> object:
    """None for any missing marker (None, NaN, pandas' NA), the value otherwise, as SQLite can bind it."""
    if value is None or value is pd.NA or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def _cell(column: str, value: object) -> object:
    """A value as SQLite stores it: a set as a sorted JSON list, a flag as 0 or 1, a missing value as NULL."""
    if column in SET_COLUMNS:
        return None if value is None or not isinstance(value, frozenset | set) else json.dumps(sorted(value))
    if column == "tmdb_known":
        return int(bool(value))
    return _optional(value)


def write_table(table: FilmTable, path: Path) -> None:
    """Write the table to `path`, replacing any previous table only once the new one is complete."""
    partial = path.with_name(path.name + ".partial")
    partial.unlink(missing_ok=True)
    partial.with_name(partial.name + "-journal").unlink(missing_ok=True)
    with sqlite3.connect(partial) as db:
        db.executescript(SCHEMA)
        meta = {
            "format": str(FORMAT),
            "built_at": table.built_at.isoformat(),
            "oldest_tmdb": table.oldest_tmdb.isoformat() if table.oldest_tmdb else "",
            "release": table.release,
            "tags": json.dumps(list(table.tags)),
        }
        db.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
        for i, (tmdb, f) in enumerate(table.films.iterrows()):
            db.execute(INSERT_FILM, (int(str(tmdb)), *(_cell(c, f[c]) for c in COLUMNS)))
            if not np.isnan(table.genome[i]).any():
                db.execute("INSERT INTO genome VALUES (?, ?)", (int(str(tmdb)), table.genome[i].tobytes()))
    db.close()
    os.replace(partial, path)


def is_stale(table: FilmTable, now: datetime | None = None) -> bool:
    """Whether the table's oldest TMDB fact is six months old or more, which TMDB's terms forbid keeping."""
    return table.oldest_tmdb is not None and (now or datetime.now(UTC)) - table.oldest_tmdb >= MAX_AGE


def _read(path: Path) -> tuple[dict[str, str], list[str], list[tuple[object, ...]], dict[int, bytes]]:
    """The table file's meta, column names, film rows and genome blobs, read only."""
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        meta = dict(db.execute("SELECT key, value FROM meta").fetchall())
        films = db.execute("SELECT * FROM films ORDER BY tmdb")
        names = [column[0] for column in films.description]
        rows = films.fetchall()
        blobs = dict(db.execute("SELECT tmdb, relevance FROM genome").fetchall())
    db.close()
    return meta, names, rows, blobs


def load_table(path: Path) -> FilmTable:
    """Read the table; raises TableError when it is absent or in another format. A table too old for TMDB's terms
    is still read (`is_stale`)."""
    if not path.exists():
        raise TableError(f"no film table at {path}; run tools/rebuild_table.py")
    meta, names, rows, blobs = _read(path)
    if meta.get("format") != str(FORMAT):
        raise TableError(f"the film table at {path} is format {meta.get('format')}; this Matinee reads {FORMAT}")
    lacking = set(COLUMNS) - set(names)
    if lacking:
        raise TableError(f"the film table at {path} has no {', '.join(sorted(lacking))} column")
    oldest = datetime.fromisoformat(meta["oldest_tmdb"]) if meta["oldest_tmdb"] else None
    tags = tuple(json.loads(meta["tags"]))
    at = names.index("tmdb")
    frame = _frame({int(str(row[at])): dict(zip(names, row, strict=True)) for row in rows})
    for column in SET_COLUMNS:
        frame[column] = frame[column].map(lambda v: frozenset(json.loads(v)) if isinstance(v, str) else None)
    frame["genres"] = frame.genres.map(lambda g: g if g is not None else frozenset())
    matrix = np.full((len(frame), len(tags)), np.nan, dtype=np.float32)
    for i, t in enumerate(frame.index):
        blob = blobs.get(int(t))
        if blob is not None:
            matrix[i] = np.frombuffer(blob, dtype=np.float32)
    return FilmTable(frame, tags, matrix, datetime.fromisoformat(meta["built_at"]), oldest, meta["release"])
