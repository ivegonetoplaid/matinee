"""The tree checker's own rules, on a constructed table."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from check_trees import Report, _check_gore, check_gore, check_pins_in_key
from matinee.pools import House
from matinee.table import FilmTable

BANDS = ["spotless", "some", "messy", "rip"]


def _table() -> FilmTable:
    films = pd.DataFrame(
        {"name": ["Known", "Unknown", "Pinned"], "year": [2000, 2001, 2002], "tmdb_known": [True] * 3},
        index=[1, 2, 3],
    )
    matrix = np.array([[0.5], [np.nan], [np.nan]], dtype=np.float32)
    return FilmTable(films, ("gore",), matrix, datetime.now(UTC), None, "test")


def _house(scale_pins: dict[tuple[str, str, str], frozenset[int]]) -> House:
    return House(kids_pins={}, tree_pins={}, payoff_pins={}, scale_pins=scale_pins)


def _gore(rows: dict[int, list[str]]) -> pd.DataFrame:
    return pd.DataFrame({b: [b in rows[i] for i in rows] for b in BANDS}, index=list(rows))


def test_unknown_unpinned_film_may_not_promise_spotless_or_rip() -> None:
    table = _table()
    pools = {"horror": pd.Series(True, index=table.films.index)}
    house = _house({("horror", "gore", "rip"): frozenset({3})})
    ok = _gore({1: ["rip"], 2: ["some", "messy"], 3: ["rip"]})
    report = Report()
    check_gore(table, pools, house, ok, report)
    assert report.failures == []
    for bad_band in ("spotless", "rip"):
        report = Report()
        check_gore(table, pools, house, _gore({1: ["rip"], 2: ["some", bad_band], 3: ["rip"]}), report)
        assert report.failures == [f"gore: Unknown (2001) has no genome entry and no pin but is in {bad_band}"]


def test_fixture_gore_band_and_gore_not() -> None:
    gore = _gore({1: ["some"], 2: ["some", "messy"]})
    report = Report()
    _check_gore({"tmdb": 1, "title": "A", "gore_band": "some", "gore_not": ["rip"]}, gore, report)
    assert report.failures == []
    _check_gore({"tmdb": 2, "title": "B", "gore_band": "some"}, gore, report)
    _check_gore({"tmdb": 1, "title": "A", "gore_not": ["some"]}, gore, report)
    assert len(report.failures) == 2


def test_every_pin_needs_a_fixture_asserting_its_placement() -> None:
    house = House(
        kids_pins={10: "older"},
        tree_pins={"action": frozenset({11})},
        payoff_pins={("western", "showdown"): frozenset({12})},
        scale_pins={("horror", "gore", "rip"): frozenset({13})},
    )
    good = [
        {"tmdb": 10, "kids_band": "older"},
        {"tmdb": 11, "must_reach": ["action"]},
        {"tmdb": 12, "must_reach": ["western"]},
        {"tmdb": 13, "gore_band": "rip"},
    ]
    report = Report()
    check_pins_in_key(house, {"films": good}, report)
    assert report.failures == []
    weak = [{"tmdb": 10}, {"tmdb": 11, "must_reach": ["drama"]}, {"tmdb": 12}, {"tmdb": 13, "gore_band": "some"}]
    check_pins_in_key(house, {"films": weak}, report)
    assert len(report.failures) == 4
