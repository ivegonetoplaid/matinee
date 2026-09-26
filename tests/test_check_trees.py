"""The tree checker's own rules, on a constructed table."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from check_trees import (
    SAMPLES,
    Report,
    _check_gore,
    check_answer_coverage,
    check_gore,
    check_pins_in_key,
    check_same_answers,
    check_sample,
)
from matinee.engine import load_catalog
from matinee.pools import House
from matinee.reference import Reference, Stat
from matinee.table import FilmTable
from test_engine import TREE, make_table, reference, write_data

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


def test_a_sample_keeps_every_answer(tmp_path: Path) -> None:
    full = load_catalog(make_table(), write_data(tmp_path), reference())
    report = Report()
    check_sample(full, "a half", 0.5, 1, report, tmp_path)
    assert not [f for f in report.failures if "library's size" in f]
    assert any("a half of the library: 20 films, seed 1" in line for line in report.lines)
    assert any("west" in line and "asks 1-2 questions over 4 paths" in line for line in report.lines)


def test_sample_draws_its_share_by_its_seed_and_counts_its_failures(tmp_path: Path) -> None:
    tree = json.loads(json.dumps(TREE))
    tree["questions"][0]["options"] = [{"say": "old.", "reply": "", "filter": {"year_max": 2000}}]
    full = load_catalog(make_table(), write_data(tmp_path, tree), reference())
    runs: dict[int, list[Report]] = {}
    for seed in (1, 2, 1):
        report = Report()
        check_sample(full, "a half", 0.5, seed, report, tmp_path)
        assert any("a half of the library: 20 films" in line for line in report.lines)
        runs.setdefault(seed, []).append(report)
    stranded = [f for f in runs[1][0].failures if f.startswith("[a half] answers:")]
    assert stranded and all("no answer path reaches it" in f for f in stranded)  # films after 2000 only
    assert [r.failures for r in runs[1]][0] == runs[1][1].failures
    assert runs[1][0].lines != runs[2][0].lines
    assert all(f.startswith("[a half] ") for r in (runs[1][0], runs[2][0]) for f in r.failures)
    whole = Report()
    check_sample(full, "all", 1.0, 1, whole, tmp_path)
    reached = [f for f in whole.failures if "no answer path reaches it" in f]
    assert len(reached) == 10  # films 31-40, the years after 2000


def test_an_answer_that_depends_on_the_library_fails(tmp_path: Path) -> None:
    full = load_catalog(make_table(), write_data(tmp_path), reference())
    west = reference().trees["west"]
    moved = replace(west, payoffs={**west.payoffs, "slow": Stat(("p_slow",), 0.45, 0.2)})
    other = load_catalog(make_table().subset(list(range(1, 31))), tmp_path, Reference("test", {"west": moved}))
    report = Report()
    check_same_answers(full, other, report)
    assert sorted(report.failures) == [
        "answers: Film 13 (1983) changes its west 'payoff' answer 0 with the library's size",
        "answers: Film 13 (1983) changes its west 'payoff' answer 1 with the library's size",
        "answers: Film 14 (1984) changes its west 'payoff' answer 1 with the library's size",
    ]


def test_a_path_ending_on_no_film_fails(tmp_path: Path) -> None:
    tree = json.loads(json.dumps(TREE))
    tree["pool"] = "standup"
    cat = load_catalog(make_table(), write_data(tmp_path, tree), reference())
    pools = {n: pd.Series(m, index=cat.table.films.index) for n, m in cat.pools.items()}
    report = Report()
    check_answer_coverage(cat, pools, report)
    assert report.failures == ["answers: a west path ends on no film: []"]
    assert any("west" in line and "asks 0-0 questions over 1 paths" in line for line in report.lines)


def test_subset_keeps_rows_and_genome_aligned() -> None:
    table = make_table()
    part = table.subset([31, 2, 13])
    assert list(part.films.index) == [2, 13, 31]
    assert part.tag("p_fast").tolist()[:2] == pytest.approx([0.9, 0.6])
    assert np.isnan(part.tag("p_fast")[31])


def test_samples_are_a_third_and_a_tenth_with_fixed_seeds() -> None:
    assert [(name, share) for name, share, _ in SAMPLES] == [("a third", 1 / 3), ("a tenth", 1 / 10)]
    assert len({seed for _, _, seed in SAMPLES}) == 2


def test_a_sample_runs_reachability_and_expected_homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    full = load_catalog(make_table(), write_data(tmp_path), reference())
    mine = Report()
    seen: list[tuple[str, int, bool]] = []

    def record(name: str) -> Callable[[FilmTable, object, Report], None]:
        return lambda table, pools, report: seen.append((name, len(table.films), report is mine))

    monkeypatch.setattr("check_trees.check_reachability", record("reach"))
    monkeypatch.setattr("check_trees.check_expected", record("expect"))
    check_sample(full, "a half", 0.5, 1, mine, tmp_path)
    assert sorted(seen) == [("expect", 20, True), ("reach", 20, True)]
