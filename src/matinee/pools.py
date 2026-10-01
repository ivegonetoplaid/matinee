"""Which films each tree and mode holds before any question is asked.

The labels file (`matinee.labels`) alone places a film behind a genre door: a
door's pool is the library's films the labels list under it, plus the films the
house pins there. Nothing here reads genre tags or genome scores to place a film
behind a genre door. Documentaries keep their own rule (every film tagged
Documentary, less the standup specials), the standup specials join the comedy
door, where only its stand-up answer offers them, and the fall-asleep mode keeps
its genome rule. House pins add single films to a tree or a kids band, or count a
film as a standup special.

The waiting room is the one place genres are read: a library film the labels file
does not list at all appears behind the doors its TMDB genres name (`WAITING_ROOM`),
where it holds no kind, so only "anything" and `Just pick one!` reach it, until a
labelling pass places it. A documentary or a standup special does not wait: its own
rule gives it a home.

The kids tree is gated and fails closed: a film enters only with a passing
certificate, and sorts into three age bands.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from matinee.labels import Labels
from matinee.reference import DATA
from matinee.table import FilmTable

Mask = pd.Series

STANDUP_KEYWORD = "stand-up comedy"
CONCERT_KEYWORDS = {"concert", "concert film"}
SLEEP_ENCHANTMENT, SLEEP_EDGE = 0.55, 0.40
KIDS_GENRES = {"Animation", "Family"}
LITTLE_CERTS = {"G", "TV-Y", "TV-Y7", "TV-G", "E"}
FAMILY_CERTS = LITTLE_CERTS | {"PG", "TV-PG"}
TEEN_CERTS = {"PG-13", "TV-14"}
KIDS_UNTAGGED_YOUNG = 0.50
KIDS_ADULT_CEILING = 0.40
LITTLE_FRIGHT, LITTLE_ADULT = 0.30, 0.25
ROUGH_FRIGHT = 0.45
SCORES = {
    "ench": ["fairy tale", "childhood", "fantasy", "whimsical", "magic", "fantasy world", "fairy tales"],
    "edge": ["violent", "gore", "disturbing", "tense", "brutal"],
    "young": ["kids", "children", "cute", "cute!", "talking animals"],
    "fright": ["scary", "creepy", "dark fantasy"],
    "language": ["foul language"],
    "sex": ["sex", "sexual", "sex comedy", "nudity", "nudity (topless)", "notable nudity"],
    "crude": ["crude humor", "gross-out"],
    "drugs": ["drugs"],
}
WAITING_ROOM = {
    "Action": "action",
    "Adventure": "action",
    "Comedy": "comedy",
    "Drama": "drama",
    "Horror": "horror",
    "Thriller": "thriller",
    "Mystery": "thriller",
    "Crime": "crime",
    "Science Fiction": "scifi",
    "Fantasy": "fantasy",
    "Romance": "romance",
    "Animation": "animation",
    "War": "war",
    "Western": "western",
}
GENRE_DOORS = (
    "comedy",
    "action",
    "drama",
    "thriller",
    "crime",
    "horror",
    "scifi",
    "fantasy",
    "romance",
    "animation",
    "western",
    "war",
)


@dataclass(frozen=True)
class House:
    """This installation's hand-set placements, from data/house_overrides.json."""

    kids_pins: Mapping[int, str]
    tree_pins: Mapping[str, frozenset[int]]
    payoff_pins: Mapping[tuple[str, str], frozenset[int]]
    scale_pins: Mapping[tuple[str, str, str], frozenset[int]]
    flavour_pins: Mapping[tuple[str, str], Mapping[int, bool]] = field(default_factory=dict)
    specials: frozenset[int] = frozenset()  # films counted as standup specials whatever the rule says


def load_house(path: Path = DATA / "house_overrides.json") -> House:
    doc = json.loads(path.read_text(encoding="utf-8"))
    tree_pins: dict[str, set[int]] = {}
    for pin in doc.get("trees", []):
        tree_pins.setdefault(pin["tree"], set()).add(int(pin["tmdb"]))
    payoffs: dict[tuple[str, str], set[int]] = {}
    for pin in doc.get("payoffs", []):
        payoffs.setdefault((pin["tree"], pin["payoff"]), set()).add(int(pin["tmdb"]))
    scales: dict[tuple[str, str, str], set[int]] = {}
    for pin in doc.get("scales", []):
        scales.setdefault((pin["tree"], pin["scale"], pin["band"]), set()).add(int(pin["tmdb"]))
    flavours: dict[tuple[str, str], dict[int, bool]] = {}
    for pin in doc.get("flavours", []):
        flavours.setdefault((pin["tree"], pin["flavour"]), {})[int(pin["tmdb"])] = bool(pin["member"])
    return House(
        kids_pins={int(p["tmdb"]): p["band"] for p in doc.get("kids", [])},
        tree_pins={t: frozenset(ids) for t, ids in tree_pins.items()},
        payoff_pins={k: frozenset(ids) for k, ids in payoffs.items()},
        scale_pins={k: frozenset(ids) for k, ids in scales.items()},
        flavour_pins=flavours,
        specials=frozenset(int(p["tmdb"]) for p in doc.get("specials", [])),
    )


def scores(table: FilmTable) -> pd.DataFrame:
    """The scores the pool rules read, NaN where the genome does not cover a film."""
    return pd.DataFrame({name: table.mean_of(tags) for name, tags in SCORES.items()})


def _genre(table: FilmTable, name: str) -> Mask:
    return table.films.genres.apply(lambda g: name in g)


def _any_genre(table: FilmTable, names: set[str]) -> Mask:
    return table.films.genres.apply(lambda g: bool(names & g))


def _ids(table: FilmTable, ids: frozenset[int]) -> Mask:
    return pd.Series(table.films.index.isin(list(ids)), index=table.films.index)


def under(x: pd.Series, limit: float) -> Mask:
    """True where x is below limit or unknown: a missing score is not evidence of a problem."""
    return x.isna() | x.lt(limit)


def over(x: pd.Series, limit: float) -> Mask:
    """True where x is at or above limit; unknown counts as not over."""
    return x.ge(limit).fillna(False).astype(bool)


def _franchise(table: FilmTable, entered: Mask) -> Mask:
    coll = table.films.collection_id
    kid_colls = set(coll[entered].dropna().astype(int))
    return coll.isin(kid_colls).fillna(False).astype(bool)


def kids_bands(table: FilmTable, s: pd.DataFrame, pins: Mapping[int, str]) -> dict[str, Mask]:
    """The gated kids pool split into little, family and older bands (older includes family)."""
    cert = table.films.certificate
    tagged = _any_genre(table, KIDS_GENRES)
    adult = s[["language", "sex", "crude", "drugs"]].max(axis=1)
    family_cert = cert.isin(FAMILY_CERTS)
    teen_ok = (
        cert.isin(TEEN_CERTS)
        & tagged
        & ((_genre(table, "Animation") & ~_genre(table, "Comedy")) | _genre(table, "Family"))
        & under(adult, KIDS_ADULT_CEILING)
    )
    untagged = ~tagged & family_cert & over(s["young"], KIDS_UNTAGGED_YOUNG)
    entered = (tagged & family_cert) | teen_ok | untagged
    franchise = (
        _franchise(table, entered) & ~entered & cert.isin(FAMILY_CERTS | TEEN_CERTS) & under(adult, KIDS_ADULT_CEILING)
    )
    pool = entered | franchise | _ids(table, frozenset(pins))
    pinned_older = _ids(table, frozenset(t for t, b in pins.items() if b == "older"))
    rough = over(s["fright"], ROUGH_FRIGHT) | cert.isin(TEEN_CERTS) | pinned_older
    little = (
        pool & cert.isin(LITTLE_CERTS) & under(s["fright"], LITTLE_FRIGHT) & under(adult, LITTLE_ADULT) & ~pinned_older
    )
    return {"little": little, "family": pool & ~rough, "older": pool, "tagged": tagged, "franchise": franchise}


def standup_specials(table: FilmTable) -> Mask:
    """Standup and comedy concert specials, which are not films.

    A feature film with a concert scene carries the concert keyword without the comedian one.
    Unknown TMDB facts (keywords None) never mark a film as standup.
    """

    def special(kw: frozenset[str] | None, genres: frozenset[str]) -> bool:
        kw = kw or frozenset()
        concert, comedian = bool(CONCERT_KEYWORDS & kw), "comedian" in kw
        tv_special = "TV Movie" in genres and (concert or comedian)
        return STANDUP_KEYWORD in kw or ("Comedy" in genres and (tv_special or (concert and comedian)))

    films = table.films
    return pd.Series([special(k, g) for k, g in zip(films.keywords, films.genres, strict=True)], index=films.index)


def specials(table: FilmTable, house: House) -> Mask:
    """Standup specials: the films the rule finds, plus the films the house counts as specials."""
    return standup_specials(table) | _ids(table, house.specials)


def waiting(table: FilmTable, house: House, labels: Labels) -> Mask:
    """The films in the waiting room: in the library, listed nowhere in the labels file, and no
    documentary or standup special."""
    unlisted = ~_ids(table, labels.films())
    return unlisted & ~_genre(table, "Documentary") & ~specials(table, house)


def build_pools(table: FilmTable, house: House, labels: Labels) -> dict[str, Mask]:
    """Every tree's and mode's pool, plus the kids bands as `kids:little`, `kids:family`, `kids:franchise`.

    A genre door holds the films the labels list under it, the waiting films whose genres name it, and the
    films the house pins there.
    """
    s = scores(table)
    bands = kids_bands(table, s, house.kids_pins)
    standup = specials(table, house)
    pools = {door: _ids(table, frozenset(labels.of(door).kinds)) for door in GENRE_DOORS}
    unplaced = waiting(table, house, labels)
    for genre, door in WAITING_ROOM.items():
        pools[door] |= unplaced & _genre(table, genre)
    pools["comedy"] |= standup
    pools |= {
        "kids": bands["older"],
        "kids:little": bands["little"],
        "kids:family": bands["family"],
        "kids:franchise": bands["franchise"],
        "nonfiction": _genre(table, "Documentary") & ~standup,
    }
    for tree, ids in house.tree_pins.items():
        pools[tree] = pools[tree] | _ids(table, ids)
    pools["sleep"] = (s["ench"].ge(SLEEP_ENCHANTMENT) & s["edge"].lt(SLEEP_EDGE)).fillna(False).astype(bool)
    return pools
