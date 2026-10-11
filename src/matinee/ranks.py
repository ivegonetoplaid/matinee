"""How well audiences regard a film, as the pick says it: the film's place among its door's films by TMDB's
vote average (`tmdb_rating`), in words with the share of films its band stands for, never as a score.

A door's films are its whole pool over the film table, whatever source the viewer draws from; before any door,
every film behind any door. Only films with at least `VOTE_FLOOR` TMDB votes are counted, and a film under the
floor, or with no TMDB score, has no rank. A film's place is its position from the top, as a share of the
counted films and itself; tied films share the better position, so films with the same score share a band. A
place exactly on a band's edge reads as the higher band. The media server's `rating` column is never read here.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
import pandas as pd

from matinee.engine import Catalog, Mask

VOTE_FLOOR = 200  # TMDB votes a film needs before its average is ranked or counted

# The word each door's rank names, by tree id; "overall" stands in before any door.
DOOR_WORDS = {
    "comedy": "comedy",
    "action": "action and adventure",
    "drama": "drama",
    "thriller": "thrillers",
    "crime": "crime",
    "horror": "horror",
    "scifi": "sci-fi",
    "fantasy": "fantasy",
    "romance": "romance",
    "animation": "animation",
    "western": "westerns",
    "war": "war films",
    "kids": "kids' films",
    "nonfiction": "documentaries",
}

# The highest share of the door's films a place may reach for each band, best band first, with the band's words
# and the share it stands for. A place is never over 1, so the last band takes every place the others leave.
BANDS = (
    (0.05, "A crowd favourite", "Top 5%"),
    (0.10, "Very well received", "Top 10%"),
    (0.25, "Well liked", "Top 25%"),
    (0.40, "Above the middle", "Top 40%"),
    (0.60, "Middle of the pack", "Middle 20%"),
    (0.90, "A tougher sell", "Bottom 40%"),
    (1.00, "Bringing up the rear", "Bottom 10%"),
)
BASIS = "by TMDB audience rating"


class Rank(NamedTuple):
    """The rank as the pick says it: its words, such as "A tougher sell in horror", and its standing, such as
    "Bottom 40% by TMDB audience rating"."""

    words: str
    standing: str


def band(place: float, door: str | None) -> Rank:
    """The pick's rank for `place`, a share of the door's films (0 to 1), behind `door` or before any door."""
    where = f"in {DOOR_WORDS[door]}" if door is not None else "overall"
    words, share = next((words, share) for edge, words, share in BANDS if place <= edge)
    return Rank(f"{words} {where}", f"{share} {BASIS}")


def door_films(cat: Catalog, door: str | None) -> Mask:
    """The films a rank counts among, aligned with the film table: `door`'s pool, or every door's before one."""
    if door is not None:
        return cat.pools[cat.trees[door].pool]
    every = np.zeros(len(cat.table.films), dtype=bool)
    for option in cat.first_options:
        if option.tree in cat.trees:
            every |= cat.pools[cat.trees[option.tree].pool]
    return every


def rank_among(films: pd.DataFrame, among: Mask, tmdb: int, door: str | None) -> Rank | None:
    """The rank for film `tmdb` among the films `among` marks, named for `door`; None when the film is not in
    `films`, has fewer than VOTE_FLOOR votes or has no TMDB score. `among` is aligned with `films`."""
    if tmdb not in films.index:
        return None
    scores = films.tmdb_rating.to_numpy(dtype=float, na_value=np.nan)
    counted = (films.vote_count.fillna(0) >= VOTE_FLOOR).to_numpy(dtype=bool) & ~np.isnan(scores)
    at = films.index.get_loc(tmdb)
    if not counted[at]:
        return None
    others = scores[counted & among & (np.arange(len(films)) != at)]
    better = int((others > scores[at]).sum())
    return band((better + 1) / (len(others) + 1), door)


def rank(cat: Catalog, tmdb: int, door: str | None) -> Rank | None:
    """The rank for film `tmdb` among `door`'s films, or every door's before one; None for a door with no
    word in DOOR_WORDS, which the shipped doors never are (a test holds them to it)."""
    if door is not None and door not in DOOR_WORDS:
        return None
    return rank_among(cat.table.films, door_films(cat, door), tmdb, door)
