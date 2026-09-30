"""Which films each tree and mode holds before any question is asked.

The inclusive rule: a tree takes every film carrying its genre tag. A film
leaves a tree only when it barely reaches for that tree's own effect (its score
is under the tree's floor) and it has another home to land in: the Comedy tag
for horror, action and drama, the kids tree for family films, and the stray
route below for the thriller tree. A film with no genome score is never removed
for a missing score. A film tagged Adventure, Thriller, Crime, Mystery, Science
Fiction or War joins the action tree when its excitement reaches the Adventure
bar. A film no tree claims joins every tree holding another film of its TMDB
collection (the franchise rule for strays); the films still unclaimed fall to
the drama tree. The crime tree takes every film tagged Crime and claims no stray,
so a Crime film the drama or action tree holds keeps that home. Standup specials
join the comedy tree, where only its stand-up answer offers them, and are held out of the non-fiction tree. House
pins add single films to a tree or a kids band, or count a film as a standup
special.

The kids tree is gated and fails closed: a film enters only with a passing
certificate, and sorts into three age bands. A film in the same TMDB collection
as a kids film joins when its certificate and adult signal allow. A kids film
stays in the adult trees too, except that one with no genome entry is kids-only,
and one offered to little ones or the whole family never counts as adult horror,
thriller or crime (`FOR_GROWN_UPS`), whatever its labels say.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from matinee.reference import DATA
from matinee.table import FilmTable

Mask = pd.Series

EFFECT_FLOOR = {"fear": 0.20, "excite": 0.30, "weight": 0.13, "thrill": 0.20}
ACTION_EXCITEMENT = 0.60
ACTION_BY_EXCITEMENT = {"Adventure", "Thriller", "Crime", "Mystery", "Science Fiction", "War"}
THRILLER_GENRES = {"Thriller", "Mystery"}
STANDUP_KEYWORD = "stand-up comedy"
CONCERT_KEYWORDS = {"concert", "concert film"}
ADULT_TREES = ("horror", "comedy", "action", "fantasy", "thriller")
FOR_GROWN_UPS = ("horror", "thriller", "crime")  # trees no film for little ones or the whole family joins
SLEEP_ENCHANTMENT, SLEEP_EDGE = 0.55, 0.40
KIDS_GENRES = {"Animation", "Family"}
LITTLE_CERTS = {"G", "TV-Y", "TV-Y7", "TV-G", "E"}
FAMILY_CERTS = LITTLE_CERTS | {"PG", "TV-PG"}
TEEN_CERTS = {"PG-13", "TV-14"}
KIDS_UNTAGGED_YOUNG = 0.50
KIDS_ADULT_CEILING = 0.40
LITTLE_FRIGHT, LITTLE_ADULT = 0.30, 0.25
ROUGH_FRIGHT = 0.45
WONDER_BAR = EXPLORE_BAR = 0.45
DRAMA_STRAYS = {
    "Crime",
    "Mystery",
    "Thriller",
    "Romance",
    "War",
    "History",
    "Music",
    "Science Fiction",
    "Fantasy",
    "Adventure",
}
SCORES = {
    "fear": ["scary", "frightening", "creepy", "horror"],
    "excite": ["action", "action packed", "good action"],
    "thrill": ["tense", "suspense", "suspenseful", "intense"],
    "weight": ["drama", "dramatic", "emotional", "moving", "touching", "harsh"],
    "ench": ["fairy tale", "childhood", "fantasy", "whimsical", "magic", "fantasy world", "fairy tales"],
    "edge": ["violent", "gore", "disturbing", "tense", "brutal"],
    "young": ["kids", "children", "cute", "cute!", "talking animals"],
    "fright": ["scary", "creepy", "dark fantasy"],
    "language": ["foul language"],
    "sex": ["sex", "sexual", "sex comedy", "nudity", "nudity (topless)", "notable nudity"],
    "crude": ["crude humor", "gross-out"],
    "drugs": ["drugs"],
    "wonder": ["fantasy world", "magic", "fantasy", "mythology", "fairy tale", "imagination", "dragons", "wizards"],
    "explore": ["treasure", "treasure hunt", "pirates", "archaeology", "jungle", "island"],
}
TREES = (
    "horror",
    "comedy",
    "action",
    "kids",
    "western",
    "nonfiction",
    "fantasy",
    "thriller",
    "crime",
    "drama",
    "sleep",
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


def leaves_for_comedy(table: FilmTable, s: pd.DataFrame, effect: str) -> Mask:
    """True where `effect` is under its floor and a Comedy tag gives the film a landing."""
    below = s[effect].lt(EFFECT_FLOOR[effect]).fillna(False).astype(bool)
    return below & _genre(table, "Comedy")


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


def _strays_follow_franchise(table: FilmTable, pools: dict[str, Mask], strays: Mask) -> None:
    """Add each stray to every tree holding another film of its TMDB collection; membership never chains."""
    coll = table.films.collection_id
    held = {name: set(coll[pool & ~strays].dropna().astype(int)) for name, pool in pools.items()}
    for name, colls in held.items():
        pools[name] = pools[name] | (strays & coll.isin(colls).fillna(False).astype(bool))


def _claimed(pools: Mapping[str, Mask]) -> Mask:
    return pd.concat([pools[name] for name in ADULT_TREES], axis=1).any(axis=1)


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


def build_pools(table: FilmTable, house: House) -> dict[str, Mask]:
    """Every tree's and mode's pool, plus the kids bands as `kids:little`, `kids:family`, `kids:franchise`.

    `kids:only` marks the kids-only films, which no other tree takes, and `kids:young` the films for little
    ones or the whole family, which no `FOR_GROWN_UPS` tree takes.
    """
    s = scores(table)
    tag = {name: _genre(table, name) for name in ("Horror", "Comedy", "Action", "Adventure", "Fantasy", "Drama")}
    tag |= {name: _genre(table, name) for name in ("Western", "Documentary")}
    has_genome = table.has_genome()
    bands = kids_bands(table, s, house.kids_pins)
    young_kids = bands["tagged"] & (bands["little"] | bands["family"])
    kids_only = young_kids & ~has_genome
    standup = specials(table, house)
    exciting = (tag["Adventure"] & s["excite"].isna()) | (
        _any_genre(table, ACTION_BY_EXCITEMENT) & over(s["excite"], ACTION_EXCITEMENT)
    )
    pools = {
        "horror": tag["Horror"] & ~young_kids & ~leaves_for_comedy(table, s, "fear"),
        "comedy": (tag["Comedy"] | standup) & ~kids_only,
        "action": (tag["Action"] | exciting) & ~kids_only & ~leaves_for_comedy(table, s, "excite"),
        "kids": bands["older"],
        "kids:little": bands["little"],
        "kids:family": bands["family"],
        "western": tag["Western"] & ~kids_only,
        "nonfiction": tag["Documentary"] & ~standup & ~kids_only,
    }
    pools["fantasy"] = (
        ((tag["Fantasy"] | tag["Adventure"]) & (over(s["wonder"], WONDER_BAR) | over(s["explore"], EXPLORE_BAR)))
        | (tag["Fantasy"] & s["wonder"].isna())
    ) & ~kids_only
    tense = ~s["thrill"].lt(EFFECT_FLOOR["thrill"]).fillna(False).astype(bool)
    pools["thriller"] = _any_genre(table, THRILLER_GENRES) & tense & ~young_kids & ~kids_only
    pools["crime"] = _genre(table, "Crime") & ~young_kids  # not in ADULT_TREES: it claims no stray
    pools["kids:franchise"] = bands["franchise"]
    pools["kids:only"] = kids_only  # films only the kids tree may hold; not a home of its own
    pools["kids:young"] = young_kids  # films for little ones or the whole family; no FOR_GROWN_UPS tree holds one
    pinned = _ids(table, frozenset().union(*house.tree_pins.values()))
    strays = _any_genre(table, DRAMA_STRAYS) & ~_claimed(pools) & ~pinned & ~kids_only
    adult = {name: pools[name] for name in ADULT_TREES}
    _strays_follow_franchise(table, adult, strays)
    pools.update(adult)
    strays &= ~_claimed(pools)
    pools["drama"] = (tag["Drama"] | strays) & ~kids_only & ~leaves_for_comedy(table, s, "weight")
    for tree, ids in house.tree_pins.items():
        pools[tree] = pools[tree] | _ids(table, ids)
    pools["sleep"] = (s["ench"].ge(SLEEP_ENCHANTMENT) & s["edge"].lt(SLEEP_EDGE)).fillna(False).astype(bool)
    return pools
