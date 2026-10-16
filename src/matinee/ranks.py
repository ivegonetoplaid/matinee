"""How well audiences regard a film, as the pick says it: the film's place among its door's films by TMDB's
vote average (`tmdb_rating`), in words with the share of films its band stands for, never as a score.

A door's films are its whole pool over the film table, whatever source the viewer draws from. Before any door, a
film ranks behind the door it ranks best in, the door a rating floor lets it in by; a film no door ranks counts
among every film behind any door. Only films with at least `VOTE_FLOOR` TMDB votes are counted, and a film under the
floor, or with no TMDB score, has no clear rank. A film's place is its position from the top, as a share of the
counted films and itself; tied films share the better position, so films with the same score share a band. A
place exactly on a band's edge reads as the higher band. The media server's `rating` column is never read here.

A film under the floor still has a line, so the pick's room for the rank never empties: why its rank is not clear
(too new, released this year or last, or else too little-known), and where its few votes would place it among the
counted films, or that it has no votes yet.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NamedTuple

import numpy as np
import pandas as pd

from matinee.engine import VOTE_FLOOR, Catalog, Mask

NEW_YEARS = 1  # a film released this many years before this one, or later, reads as too new rather than little-known

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


def _band(place: float) -> tuple[str, str]:
    return next((words, share) for edge, words, share in BANDS if place <= edge)


def band(place: float, door: str | None) -> Rank:
    """The pick's rank for `place`, a share of the door's films (0 to 1), behind `door` or before any door."""
    where = f"in {DOOR_WORDS[door]}" if door is not None else "overall"
    words, share = _band(place)
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
    place = _place(films, among, tmdb)
    return None if place is None else band(place, door)


def _place(films: pd.DataFrame, among: Mask, tmdb: int) -> float | None:
    """Film `tmdb`'s place among the counted films `among` marks; None when it is not in `films` or not counted."""
    if tmdb not in films.index:
        return None
    scores, counted = _counted(films)
    at = films.index.get_loc(tmdb)
    if not counted[at]:
        return None
    others = scores[counted & among & (np.arange(len(films)) != at)]
    better = int((others > scores[at]).sum())
    return (better + 1) / (len(others) + 1)


def best_door(cat: Catalog, tmdb: int) -> str | None:
    """The door film `tmdb` ranks best behind, among the doors the first question offers: the door a rating floor,
    which ranks each door apart, lets it in by. None when no door holds it or it has no clear rank."""
    films = cat.table.films
    at = films.index.get_loc(tmdb)
    placed = []
    for option in cat.first_options:
        tree = cat.trees.get(option.tree)
        if tree is None or option.tree not in DOOR_WORDS or not cat.pools[tree.pool][at]:
            continue
        place = _place(films, cat.pools[tree.pool], tmdb)
        if place is not None:
            placed.append((place, option.tree))
    return min(placed)[1] if placed else None


def _counted(films: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    scores = films.tmdb_rating.to_numpy(dtype=float, na_value=np.nan)
    return scores, (films.vote_count.fillna(0) >= VOTE_FLOOR).to_numpy(dtype=bool) & ~np.isnan(scores)


def thin_rank(films: pd.DataFrame, among: Mask, tmdb: int, this_year: int) -> Rank:
    """The line for film `tmdb`, in `films` and under VOTE_FLOOR or with no score: "Too new for clear ratings" (or
    "Too little-known"), over where its few votes would place it among the counted films `among` marks, such as
    "Only 19 votes, which place it in the top 40% by TMDB audience rating", or "No votes on TMDB yet"."""
    year = films.year.get(tmdb) if "year" in films else None
    new = year is not None and not pd.isna(year) and int(year) >= this_year - NEW_YEARS
    words = f"{'Too new' if new else 'Too little-known'} for clear ratings"
    scores, counted = _counted(films)
    at = films.index.get_loc(tmdb)
    votes = int(films.vote_count.fillna(0).loc[tmdb])
    if np.isnan(scores[at]) or votes == 0:
        return Rank(words, "No votes on TMDB yet")
    others = scores[counted & among]
    _, share = _band((int((others > scores[at]).sum()) + 1) / (len(others) + 1))
    said = "1 vote, which places" if votes == 1 else f"{votes} votes, which place"
    return Rank(words, f"Only {said} it in the {share[0].lower()}{share[1:]} {BASIS}")


def rank(cat: Catalog, tmdb: int, door: str | None, this_year: int | None = None) -> Rank | None:
    """The rank for film `tmdb` among `door`'s films, or before a door among the films of the door it ranks best
    behind (`best_door`; every door's when none ranks it), or its line under the vote floor
    (`thin_rank`); None for a film the table does not hold, or a door with no word in DOOR_WORDS, which the shipped
    doors never are (a test holds them to it)."""
    films = cat.table.films
    if (door is not None and door not in DOOR_WORDS) or tmdb not in films.index:
        return None
    door = door or best_door(cat, tmdb)
    among = door_films(cat, door)
    year = this_year or datetime.now(UTC).year
    return rank_among(films, among, tmdb, door) or thin_rank(films, among, tmdb, year)
