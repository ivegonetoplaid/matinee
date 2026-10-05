"""The MovieLens ml-latest tag genome as a dense film-by-tag matrix, and the scores Matinee keeps from it.

The full genome is read from a local copy of the ml-latest release by the
maintainer's tools and is never committed or shipped. A film there is a MovieLens
movie; `tmdb_by_movie` joins it to TMDB through the release's own links.csv,
never by title. `Scores` is the slice of it Matinee reads at run time: the tags
any reader names, for every genome film with a TMDB id, keyed by that id
(`matinee.genome_file` ships it as `data/genome.json`).
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd

Matrix = npt.NDArray[np.float32]
Mask = npt.NDArray[np.bool_]
GENERATED = re.compile(r"This dataset was generated on ([A-Z][a-z]+ \d{1,2}, \d{4})\.")


class GenomeError(ValueError):
    """The dataset is not the shape this module reads, or a tag it was asked for is not in it."""


@dataclass(frozen=True)
class Genome:
    """Relevance of every genome tag for every genome film, with each film's TMDB id and MovieLens genres."""

    release: str
    movie_ids: npt.NDArray[np.int64]
    tags: tuple[str, ...]
    relevance: Matrix
    tmdb_by_movie: Mapping[int, int]
    genres_by_movie: Mapping[int, frozenset[str]]

    def columns(self, tags: Sequence[str]) -> list[int]:
        """Column indexes of `tags`; raises GenomeError naming every tag the genome does not carry."""
        index = {t: i for i, t in enumerate(self.tags)}
        missing = [t for t in tags if t not in index]
        if missing:
            raise GenomeError(f"tags not in the genome: {', '.join(missing)}")
        return [index[t] for t in tags]

    def mean_of(self, tags: Sequence[str]) -> Matrix:
        """Mean relevance of `tags` for every film, in `movie_ids` order."""
        if not tags:
            raise GenomeError("a score needs at least one tag")
        return self.relevance[:, self.columns(tags)].mean(axis=1)

    def scores(self, tags: Sequence[str]) -> Scores:
        """The relevance of `tags` for every genome film with a TMDB id; where two films share one, the first wins."""
        rows: dict[int, int] = {}
        for row, movie in enumerate(self.movie_ids):
            tmdb = self.tmdb_by_movie.get(int(movie))
            if tmdb is not None:
                rows.setdefault(tmdb, row)
        kept = list(rows.values())
        relevance = self.relevance[np.ix_(kept, self.columns(tags))]
        return Scores(self.release, tuple(tags), {t: i for i, t in enumerate(rows)}, relevance)

    def with_genres(self, names: Iterable[str]) -> Mask:
        """True for films carrying any of the MovieLens genres `names`."""
        wanted = frozenset(names)
        return np.array([bool(wanted & self.genres_by_movie.get(int(m), frozenset())) for m in self.movie_ids])


@dataclass(frozen=True)
class Scores:
    """Genome relevance of a fixed set of tags, one row per TMDB id: what the film table joins on."""

    release: str
    tags: tuple[str, ...]
    rows: Mapping[int, int]  # TMDB id -> row of `relevance`
    relevance: Matrix


def release_of(ml: Path) -> str:
    """The release name and generation date, read from the dataset's own README."""
    match = GENERATED.search((ml / "README.txt").read_text(encoding="utf-8"))
    if match is None:
        raise GenomeError(f"{ml / 'README.txt'} does not state when the dataset was generated")
    return f"MovieLens ml-latest, generated {match.group(1)}"


def _dense(ml: Path) -> tuple[npt.NDArray[np.int64], Matrix]:
    """Movie ids and the relevance matrix from genome-scores.csv, which is dense and sorted by movie then tag."""
    frame = pd.read_csv(
        ml / "genome-scores.csv", dtype={"movieId": np.int64, "tagId": np.int32, "relevance": np.float32}
    )
    n_tags = int(frame.tagId.max())
    if len(frame) % n_tags:
        raise GenomeError(f"genome-scores.csv has {len(frame)} rows, not a multiple of its {n_tags} tags")
    movies = frame.movieId.to_numpy()[::n_tags]
    tag_ids = frame.tagId.to_numpy().reshape(-1, n_tags)
    if not (tag_ids == np.arange(1, n_tags + 1)).all():
        raise GenomeError("genome-scores.csv is not sorted by movie and then by tag")
    return movies, frame.relevance.to_numpy().reshape(-1, n_tags)


def _stamp(source: Path) -> npt.NDArray[np.int64]:
    stat = source.stat()
    return np.array([stat.st_size, stat.st_mtime_ns], dtype=np.int64)


def _cached(cache: Path, stamp: npt.NDArray[np.int64]) -> tuple[npt.NDArray[np.int64], Matrix] | None:
    """The cached matrix when it was made from a source with this size and modification time, else None."""
    if not cache.exists():
        return None
    with np.load(cache) as saved:
        if "stamp" not in saved.files or not np.array_equal(saved["stamp"], stamp):
            return None
        return saved["movies"], saved["relevance"]


def load_genome(ml: Path, cache: Path | None = None) -> Genome:
    """Read the genome from the ml-latest directory `ml`.

    Parsing genome-scores.csv takes seconds to a minute. When `cache` is given
    the matrix is read from it if it was made from a genome-scores.csv of the
    same size and modification time, and rebuilt and rewritten otherwise; an
    unzipped newer release therefore never reuses an older matrix. The cache is
    a derived file beside the dataset, never in the repository.
    """
    source = ml / "genome-scores.csv"
    stamp = _stamp(source)
    hit = _cached(cache, stamp) if cache is not None else None
    if hit is not None:
        movies, relevance = hit
    else:
        movies, relevance = _dense(ml)
        if cache is not None:
            partial = cache.with_name(cache.name + ".partial.npz")
            np.savez(partial, movies=movies, relevance=relevance, stamp=stamp)
            os.replace(partial, cache)
    tags = pd.read_csv(ml / "genome-tags.csv").sort_values("tagId")
    if len(tags) != relevance.shape[1]:
        raise GenomeError(f"genome-tags.csv names {len(tags)} tags; the scores carry {relevance.shape[1]}")
    links = pd.read_csv(ml / "links.csv").dropna(subset=["tmdbId"])
    movies_csv = pd.read_csv(ml / "movies.csv")
    return Genome(
        release=release_of(ml),
        movie_ids=movies,
        tags=tuple(str(t) for t in tags.tag),
        relevance=relevance,
        tmdb_by_movie=dict(zip(links.movieId.astype(int), links.tmdbId.astype(int), strict=True)),
        genres_by_movie={
            int(m): frozenset(str(g).split("|")) for m, g in zip(movies_csv.movieId, movies_csv.genres, strict=True)
        },
    )
