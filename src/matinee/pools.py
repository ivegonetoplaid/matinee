"""Which films each tree and mode holds before any question is asked.

The labels file (`matinee.labels`) alone places a film behind a genre door: a
door's pool is the library's films the labels list under it, plus the films the
house pins there. Nothing here reads genre tags or genome scores to place a film
behind a genre door. Documentaries keep their own rule (every film tagged
Documentary, less the standup specials), the standup specials join the comedy
door, where only its stand-up answer offers them. House pins add single films to a tree or a kids band, or count a
film as a standup special.

The waiting room is the one place genres are read: a library film the labels file
does not list at all appears behind the doors its TMDB genres name (`WAITING_ROOM`),
where it holds no kind, so only "anything" and `Just pick one!` reach it, until a
labelling pass places it. A documentary or a standup special does not wait: its own
rule gives it a home.

For the kids holds the films the labels list under it whose certificate passes,
each in the older of its labelled age band and its certificate's band (`kids_band`);
the gate fails closed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from matinee.labels import BANDS, Labels, TreeLabels
from matinee.reference import DATA
from matinee.table import FilmTable

Mask = pd.Series

STANDUP_KEYWORD = "stand-up comedy"
CONCERT_KEYWORDS = {"concert", "concert film"}
CERTIFICATE_BANDS = {  # the youngest kids band a certificate allows; any other certificate never passes
    **dict.fromkeys(("G", "TV-Y", "TV-Y7", "TV-G", "E"), "little"),
    **dict.fromkeys(("PG", "TV-PG"), "family"),
    **dict.fromkeys(("PG-13", "TV-14"), "older"),
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
    scale_pins: Mapping[tuple[str, str, str], frozenset[int]]
    flavour_pins: Mapping[tuple[str, str], Mapping[int, bool]] = field(default_factory=dict)
    specials: frozenset[int] = frozenset()  # films counted as standup specials whatever the rule says

    def without(self, films: frozenset[int]) -> House:
        """The pins less every placement of `films` (kids, tree, flavour and specials pins): the household file
        places them. Scale pins stay, since a gore pail is neither a door nor a kind."""
        return House(
            kids_pins={t: b for t, b in self.kids_pins.items() if t not in films},
            tree_pins={tree: ids - films for tree, ids in self.tree_pins.items()},
            scale_pins=self.scale_pins,
            flavour_pins={
                k: {t: m for t, m in pins.items() if t not in films} for k, pins in self.flavour_pins.items()
            },
            specials=self.specials - films,
        )


def load_house(path: Path = DATA / "house_overrides.json") -> House:
    doc = json.loads(path.read_text(encoding="utf-8"))
    tree_pins: dict[str, set[int]] = {}
    for pin in doc.get("trees", []):
        tree_pins.setdefault(pin["tree"], set()).add(int(pin["tmdb"]))
    scales: dict[tuple[str, str, str], set[int]] = {}
    for pin in doc.get("scales", []):
        scales.setdefault((pin["tree"], pin["scale"], pin["band"]), set()).add(int(pin["tmdb"]))
    flavours: dict[tuple[str, str], dict[int, bool]] = {}
    for pin in doc.get("flavours", []):
        flavours.setdefault((pin["tree"], pin["flavour"]), {})[int(pin["tmdb"])] = bool(pin["member"])
    return House(
        kids_pins={int(p["tmdb"]): p["band"] for p in doc.get("kids", [])},
        tree_pins={t: frozenset(ids) for t, ids in tree_pins.items()},
        scale_pins={k: frozenset(ids) for k, ids in scales.items()},
        flavour_pins=flavours,
        specials=frozenset(int(p["tmdb"]) for p in doc.get("specials", [])),
    )


def _genre(table: FilmTable, name: str) -> Mask:
    return table.films.genres.apply(lambda g: name in g)


def _ids(table: FilmTable, ids: frozenset[int]) -> Mask:
    return pd.Series(table.films.index.isin(list(ids)), index=table.films.index)


def kids_band(labelled: str | None, certificate: str | None, spooky: bool = False) -> str | None:
    """The older of a film's labelled kids band and its certificate's band; None when either fails.

    A film labelled for the whole family whose certificate allows the little ones (G-class) is offered to
    the little ones too, unless it is spooky. A film with no labelled band, or a certificate outside
    `CERTIFICATE_BANDS` (R, NC-17, TV-MA, none, unrated), never passes: the kids gate fails closed.
    """
    ceiling = CERTIFICATE_BANDS.get(certificate or "")
    if labelled is None or ceiling is None:
        return None
    if labelled == "family" and ceiling == "little" and not spooky:
        return "little"
    return max(labelled, ceiling, key=BANDS.index)


def kids_bands(table: FilmTable, labels: TreeLabels, pins: Mapping[int, str]) -> dict[str, Mask]:
    """The kids pool split into little, family and older bands; family includes little, older includes both.

    A film's band is `kids_band` of its label, certificate and spooky kind. A house pin sets the band outright for a
    film the library holds; for one it does not hold, the pin applies only when the film's certificate passes the
    gate, so a pin never carries an unrated film the household has not vetted into the pool.
    """
    films = table.films
    held = films.held if "held" in films else pd.Series(True, index=films.index)

    def pinned(t: int, certificate: str, is_held: bool) -> str | None:
        pin = pins.get(t)
        return pin if pin is not None and (is_held or certificate in CERTIFICATE_BANDS) else None

    band = pd.Series(
        [
            pinned(int(t), c, bool(h))
            or kids_band(labels.bands.get(int(t)), c, "spooky" in labels.kinds.get(int(t), ()))
            for t, c, h in zip(films.index, films.certificate, held, strict=True)
        ],
        index=films.index,
        dtype=object,
    )
    return {"little": band.eq("little"), "family": band.isin(["little", "family"]), "older": band.notna()}


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
    """Every tree's and mode's pool, plus the kids bands as `kids:little` and `kids:family`.

    A genre door holds the films the labels list under it, the waiting films whose genres name it, and the
    films the house pins there.
    """
    bands = kids_bands(table, labels.of("kids"), house.kids_pins)
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
        "nonfiction": _genre(table, "Documentary") & ~standup,
    }
    for tree, ids in house.tree_pins.items():
        pools[tree] = pools[tree] | _ids(table, ids)
    return pools
