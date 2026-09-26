"""The offline film table: for every library film, the facts and scores the trees filter on.

Built nightly from the media server's film list, the MovieLens genome and the
TMDB cache, and written as one SQLite file in Matinee's own storage, never in
the repository. The app reads it and never queries the genome or TMDB.

A film the genome does not cover carries no genome scores (NaN), never zeros.
A film whose TMDB record is missing or older than six months carries no TMDB
facts (`tmdb_known` is False, keywords None rather than empty). The table refuses to be served once its oldest
TMDB fact is older than six months, because TMDB's terms cap caching there.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from matinee.genome import Genome, Matrix
from matinee.library import LibraryFilm
from matinee.tmdb import MAX_AGE, TmdbFilm

FORMAT = 1
COLUMNS = (
    "item_id",
    "name",
    "year",
    "genres",
    "certificate",
    "runtime_min",
    "rating",
    "tmdb_known",
    "language",
    "collection_id",
    "keywords",
)


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


@dataclass
class BuildReport:
    """What the nightly pass saw that the operator should know about. It changes nothing on the server."""

    library_items: int = 0
    no_tmdb_id: list[str] = field(default_factory=list)
    path_mismatches: list[str] = field(default_factory=list)
    tmdb_missing: list[str] = field(default_factory=list)
    tmdb_too_old: list[str] = field(default_factory=list)
    with_genome: int = 0

    def lines(self) -> list[str]:
        out = [
            f"{self.library_items} library items; {self.with_genome} films with genome scores",
            f"{len(self.no_tmdb_id)} items with no TMDB id (not in the table)",
            f"{len(self.path_mismatches)} files whose {{tmdb-N}} folder tag differs from the server's TMDB id",
            f"{len(self.tmdb_missing)} films with no TMDB record; {len(self.tmdb_too_old)} over six months old",
        ]
        out += [f"  path tag differs: {m}" for m in self.path_mismatches]
        out += [f"  no TMDB record: {m}" for m in self.tmdb_missing]
        out += [f"  TMDB record too old: {m}" for m in self.tmdb_too_old]
        return out


def _label(f: LibraryFilm) -> str:
    return f"{f.name} ({f.year})"


def _genome_rows(genome: Genome) -> dict[int, int]:
    """TMDB id -> genome row, first MovieLens movie wins where two share a TMDB id."""
    rows: dict[int, int] = {}
    for row, movie in enumerate(genome.movie_ids):
        tmdb = genome.tmdb_by_movie.get(int(movie))
        if tmdb is not None:
            rows.setdefault(tmdb, row)
    return rows


def _tmdb_fields(rec: TmdbFilm | None, usable: bool) -> dict[str, object]:
    if rec is None or not usable:
        return {"tmdb_known": False, "language": None, "collection_id": None, "keywords": None}
    return {
        "tmdb_known": True,
        "language": rec.original_language or None,
        "collection_id": rec.collection_id,
        "keywords": frozenset(rec.keywords),
    }


def _rows(
    films: Sequence[LibraryFilm], tmdb: Mapping[int, TmdbFilm], now: datetime, report: BuildReport
) -> dict[int, dict[str, object]]:
    """One row per distinct TMDB id; the first file of a film supplies its media-server item."""
    seen: dict[int, dict[str, object]] = {}
    for f in films:
        if f.tmdb is None:
            report.no_tmdb_id.append(_label(f))
            continue
        if f.path_tmdb is not None and f.path_tmdb != f.tmdb:
            report.path_mismatches.append(f"{_label(f)}: folder says {f.path_tmdb}, server says {f.tmdb}")
        if f.tmdb in seen:
            continue
        rec = tmdb.get(f.tmdb)
        usable = rec is not None and now - rec.fetched < MAX_AGE
        if rec is None:
            report.tmdb_missing.append(_label(f))
        elif not usable:
            report.tmdb_too_old.append(_label(f))
        seen[f.tmdb] = {
            "item_id": f.item_id,
            "name": f.name,
            "year": f.year,
            "genres": f.genres,
            "certificate": f.certificate,
            "runtime_min": f.runtime_min,
            "rating": f.rating,
            **_tmdb_fields(rec, usable),
        }
    return seen


def build_table(
    films: Sequence[LibraryFilm], genome: Genome, tmdb: Mapping[int, TmdbFilm], now: datetime
) -> tuple[FilmTable, BuildReport]:
    """The table for `films`, and what the pass saw. Films with no TMDB id are left out and reported."""
    report = BuildReport(library_items=len(films))
    rows_of = _genome_rows(genome)
    frame = pd.DataFrame.from_dict(_rows(films, tmdb, now, report), orient="index", columns=list(COLUMNS))
    frame.index.name = "tmdb"
    matrix = np.full((len(frame), len(genome.tags)), np.nan, dtype=np.float32)
    for i, t in enumerate(frame.index):
        row = rows_of.get(int(t))
        if row is not None:
            matrix[i] = genome.relevance[row]
    report.with_genome = int((~np.isnan(matrix).any(axis=1)).sum())
    known = [tmdb[int(t)].fetched for t in frame.index[frame.tmdb_known.astype(bool)]]
    table = FilmTable(frame, genome.tags, matrix, now, min(known) if known else None, genome.release)
    return table, report


SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE films (
    tmdb INTEGER PRIMARY KEY, item_id TEXT NOT NULL, name TEXT NOT NULL, year INTEGER,
    genres TEXT NOT NULL, certificate TEXT NOT NULL, runtime_min REAL, rating REAL,
    tmdb_known INTEGER NOT NULL, language TEXT, collection_id INTEGER, keywords TEXT
);
CREATE TABLE genome (tmdb INTEGER PRIMARY KEY REFERENCES films(tmdb), relevance BLOB NOT NULL);
"""
SELECT_FILMS = (
    "SELECT tmdb, item_id, name, year, genres, certificate, runtime_min, rating,"
    " tmdb_known, language, collection_id, keywords FROM films ORDER BY tmdb"
)


def _optional(value: object) -> object:
    """None for pandas' missing markers, the value otherwise."""
    return None if value is None or (isinstance(value, float) and np.isnan(value)) else value


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
            db.execute(
                "INSERT INTO films VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    int(str(tmdb)),
                    f.item_id,
                    f["name"],
                    _optional(f.year),
                    json.dumps(sorted(f.genres)),
                    f.certificate,
                    _optional(f.runtime_min),
                    _optional(f.rating),
                    int(bool(f.tmdb_known)),
                    _optional(f.language),
                    _optional(f.collection_id),
                    None if f.keywords is None else json.dumps(sorted(f.keywords)),
                ),
            )
            if not np.isnan(table.genome[i]).any():
                db.execute("INSERT INTO genome VALUES (?, ?)", (int(str(tmdb)), table.genome[i].tobytes()))
    db.close()
    os.replace(partial, path)


def _check_age(oldest: datetime | None, now: datetime, path: Path) -> None:
    if oldest is not None and now - oldest >= MAX_AGE:
        raise TableError(
            f"the film table at {path} holds TMDB data fetched {oldest:%Y-%m-%d}, over six months ago; "
            "TMDB's terms forbid serving it. Run the nightly rebuild."
        )


def load_table(path: Path, now: datetime | None = None) -> FilmTable:
    """Read the table; raises TableError when it is absent, in another format, or too old to serve."""
    if not path.exists():
        raise TableError(f"no film table at {path}; run tools/rebuild_table.py")
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        meta = dict(db.execute("SELECT key, value FROM meta").fetchall())
        rows = db.execute(SELECT_FILMS).fetchall()
        blobs = dict(db.execute("SELECT tmdb, relevance FROM genome").fetchall())
    db.close()
    if meta.get("format") != str(FORMAT):
        raise TableError(f"the film table at {path} is format {meta.get('format')}; this Matinee reads {FORMAT}")
    oldest = datetime.fromisoformat(meta["oldest_tmdb"]) if meta["oldest_tmdb"] else None
    _check_age(oldest, now or datetime.now(UTC), path)
    tags = tuple(json.loads(meta["tags"]))
    frame = pd.DataFrame(rows, columns=["tmdb", *COLUMNS]).set_index("tmdb")
    frame["genres"] = frame.genres.map(lambda g: frozenset(json.loads(g)))
    frame["keywords"] = frame.keywords.map(lambda k: frozenset(json.loads(k)) if isinstance(k, str) else None)
    frame["tmdb_known"] = frame.tmdb_known.astype(bool)
    frame["year"] = frame.year.astype("Int64")
    frame["collection_id"] = frame.collection_id.astype("Int64")
    matrix = np.full((len(frame), len(tags)), np.nan, dtype=np.float32)
    for i, t in enumerate(frame.index):
        blob = blobs.get(int(t))
        if blob is not None:
            matrix[i] = np.frombuffer(blob, dtype=np.float32)
    return FilmTable(frame, tags, matrix, datetime.fromisoformat(meta["built_at"]), oldest, meta["release"])
