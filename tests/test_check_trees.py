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
    check_apart,
    check_first_question,
    check_gore,
    check_hidden,
    check_homes,
    check_kinds,
    check_pins_in_key,
    check_reachability,
    check_same_answers,
    check_sample,
    check_shared_kinds,
    door_pools,
    report_waiting,
)
from matinee.engine import load_catalog
from matinee.labels import LABELS, Labels, LabelsError, TreeLabels
from matinee.pools import House
from matinee.reference import Cuts, Reference
from matinee.table import FilmTable
from test_engine import TREE, gore_cut_tree, make_table, reference, write_data

BANDS = ["spotless", "some", "messy", "rip"]


def _table() -> FilmTable:
    films = pd.DataFrame(
        {"name": ["Known", "Unknown", "Pinned"], "year": [2000, 2001, 2002], "tmdb_known": [True] * 3},
        index=[1, 2, 3],
    )
    matrix = np.array([[0.5], [np.nan], [np.nan]], dtype=np.float32)
    return FilmTable(films, ("gore",), matrix, datetime.now(UTC), None, "test")


def _house(scale_pins: dict[tuple[str, str, str], frozenset[int]]) -> House:
    return House(kids_pins={}, tree_pins={}, scale_pins=scale_pins)


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
        scale_pins={("horror", "gore", "rip"): frozenset({13})},
        specials=frozenset({14}),
    )
    good = [
        {"tmdb": 10, "kids_band": "older"},
        {"tmdb": 11, "must_reach": ["action"]},
        {"tmdb": 13, "gore_band": "rip"},
        {"tmdb": 14, "flavour_in": {"comedy": ["standup"]}},
    ]
    report = Report()
    check_pins_in_key(house, {"films": good}, report)
    assert report.failures == []
    weak = [
        {"tmdb": 10},
        {"tmdb": 11, "must_reach": ["drama"]},
        {"tmdb": 13, "gore_band": "some"},
        {"tmdb": 14, "must_reach": ["comedy"]},
    ]
    report = Report()
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
    data = write_data(tmp_path, gore_cut_tree())
    full = load_catalog(make_table(), data, reference())
    moved = replace(reference().trees["west"], scales={"gore": Cuts(("gore_a",), (50.0,), (0.9,))})
    other = load_catalog(make_table().subset(list(range(1, 31))), data, Reference("test", {"west": moved}))
    report = Report()
    check_same_answers(full, other, report)
    assert sorted(report.failures) == [
        f"answers: Film {t} ({1970 + t}) changes its west 'gore' answer 0 with the library's size" for t in (1, 3, 4, 5)
    ]


def test_a_path_ending_on_no_film_fails(tmp_path: Path) -> None:
    tree = json.loads(json.dumps(TREE))
    tree["pool"] = "nonfiction"  # no film in the constructed table is a documentary
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


def test_a_sample_runs_reachability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    full = load_catalog(make_table(), write_data(tmp_path), reference())
    mine = Report()
    seen: list[tuple[str, int, bool]] = []

    def record(name: str) -> Callable[[FilmTable, object, Report], None]:
        return lambda table, pools, report: seen.append((name, len(table.films), report is mine))

    monkeypatch.setattr("check_trees.check_reachability", record("reach"))
    check_sample(full, "a half", 0.5, 1, mine, tmp_path)
    assert seen == [("reach", 20, True)]


def test_a_labelled_film_holding_none_of_its_doors_kinds_is_named_not_failed(tmp_path: Path) -> None:
    lab = Labels({"west": TreeLabels({1: frozenset({"heroic"}), 2: frozenset()})})
    cat = load_catalog(make_table(), write_data(tmp_path), reference(), lab)
    report = Report()
    check_kinds(cat, report)
    report_waiting(cat, report)
    assert report.failures == []
    assert "  west: 1 labelled films no kind fits: Film 2 (1972)" in report.lines
    assert any(line.startswith("  west: 38 films there by pin") for line in report.lines)
    assert "  waiting: Film 3 (1973) -> comedy, western" in report.lines


def test_first_question_answers_must_name_a_tree(tmp_path: Path) -> None:
    cat = load_catalog(make_table(), write_data(tmp_path), reference())
    report = Report()
    check_first_question(cat, report)
    assert report.failures == ["first question: 'No.' leads to 'none', which names no tree file"]


def test_a_film_held_only_by_a_tree_no_door_leads_to_has_no_home(tmp_path: Path) -> None:
    data = write_data(tmp_path)
    (data / "trees" / "orphan.json").write_text(json.dumps({"pool": "horror", "opening": "boo."}))
    cat = load_catalog(make_table(), data, reference())
    index = cat.table.films.index
    pools = {"western": pd.Series(index != 2, index=index), "horror": pd.Series(index == 2, index=index)}
    pools["kids:little"] = pd.Series(False, index=index)
    doors = door_pools(cat, pools)
    assert set(doors) == {"western", "kids:little"}  # only "Cowboys." leads anywhere
    report = Report()
    check_reachability(cat.table, doors, report)
    assert report.failures == ["unreachable: Film 2 (1972) genres=Animation/Horror/Western"]


def test_a_film_held_apart_fails_when_another_door_holds_it(tmp_path: Path) -> None:
    tree = json.loads(json.dumps(TREE))
    tree["flavours"]["standup"] = {"specials": True}
    tree["apart"] = "standup"
    cat = load_catalog(make_table(), write_data(tmp_path, tree), reference())
    cat.apart["west"][:] = cat.table.films.index == 5
    index = cat.table.films.index
    pools = {"western": pd.Series(True, index=index), "horror": pd.Series(index == 5, index=index)}
    report = Report()
    check_apart(cat, pools, report)
    assert report.failures == ["held apart: Film 5 (1975) is held apart in west but horror holds it"]
    report = Report()
    check_apart(cat, {**pools, "horror": pd.Series(False, index=index)}, report)
    assert report.failures == []


def test_a_sample_counts_only_the_doors_pools_as_homes(tmp_path: Path) -> None:
    tree = json.loads(json.dumps(TREE))
    tree["pool"] = "horror"  # the door ("Cowboys.") now holds only the even, Horror-tagged films
    data = write_data(tmp_path, tree)
    (data / "trees" / "orphan.json").write_text(json.dumps({"pool": "western", "opening": "howdy."}))
    full = load_catalog(make_table(), data, reference())
    report = Report()
    check_sample(full, "all", 1.0, 1, report, data)
    assert "[all] unreachable: Film 3 (1973) genres=Comedy/Western" in report.failures  # held only by the orphan
    pools = {n: pd.Series(m, index=full.table.films.index) for n, m in full.pools.items()}
    homes = check_homes(full, pools, Report())
    assert "western" not in homes and "horror" in homes and "kids:little" in homes


def test_the_homes_check_fails_a_special_another_door_holds(tmp_path: Path) -> None:
    tree = json.loads(json.dumps(TREE))
    tree["flavours"]["standup"] = {"specials": True}
    tree["apart"] = "standup"
    data = write_data(tmp_path, tree)
    (data / "trees" / "scary.json").write_text(json.dumps({"pool": "horror", "opening": "boo."}))
    first = json.loads((data / "first_question.json").read_text())
    first["options"].append({"say": "Scary.", "tree": "scary", "label": "Scary"})
    (data / "first_question.json").write_text(json.dumps(first))
    house = json.loads((data / "house_overrides.json").read_text())
    (data / "house_overrides.json").write_text(json.dumps({**house, "specials": [{"tmdb": 5}]}))
    cat = load_catalog(make_table(), data, reference())  # film 5 is Comedy-tagged; pinned a special
    index = cat.table.films.index
    pools = {n: pd.Series(m, index=index) for n, m in cat.pools.items()}
    report = Report()
    check_homes(cat, pools, report)
    assert not [f for f in report.failures if f.startswith("held apart")]
    pools["horror"] = pools["horror"] | pd.Series(index == 5, index=index)
    cat.pools["horror"] = pools["horror"].to_numpy()
    report = Report()
    check_homes(cat, pools, report)
    assert "held apart: Film 5 (1975) is held apart in west but horror holds it" in report.failures


def test_a_shared_kind_must_hold_the_same_film_at_every_door_that_lists_it(tmp_path: Path) -> None:
    data = write_data(tmp_path)
    (data / "trees" / "east.json").write_text(
        json.dumps({"pool": "comedy", "opening": "ha.", "flavours": {"heroic": {"labelled": True}}})
    )
    lab = Labels(
        {
            "west": TreeLabels({1: frozenset({"heroic"}), 2: frozenset({"heroic"})}),
            "east": TreeLabels({1: frozenset(), 2: frozenset({"heroic"})}),
        }
    )
    cat = load_catalog(make_table(), data, reference(), lab)
    report = Report()
    check_shared_kinds(cat, report)
    assert report.failures == ["shared kinds: Film 1 (1971) holds 'heroic' at ['west'] but not at ['east']"]


def test_the_hidden_kinds_must_be_the_ones_the_key_expects(tmp_path: Path) -> None:
    tree = json.loads(json.dumps(TREE))
    tree["flavours"]["ghost"] = {"labelled": True}
    tree["questions"][0]["options"].append({"say": "ghosts.", "reply": "", "filter": {"flavour": "ghost"}})
    lab = Labels({"west": TreeLabels({1: frozenset({"ghost"})})})
    cat = load_catalog(make_table(), write_data(tmp_path, tree), reference(), lab)  # ghost holds 1 film
    report = Report()
    check_hidden(cat, {"hidden": [["west", "ghost"]]}, report)
    assert report.failures == []
    check_hidden(cat, {"hidden": []}, report)
    assert report.failures == ["hidden: west kind ghost is hidden, and the answer key does not expect it to be"]
    report = Report()
    check_hidden(cat, {"hidden": [["west", "ghost"], ["west", "heroic"]]}, report)
    assert report.failures == ["hidden: west kind heroic shows, and the answer key expects it hidden"]


def test_the_checker_reads_the_shipped_labels_unless_told_otherwise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import check_trees

    read: list[Path] = []

    def labels_at(path: Path) -> Labels:
        read.append(path)
        raise LabelsError("stop here")

    monkeypatch.setattr(check_trees, "load_table", lambda _path: _table())
    monkeypatch.setattr(check_trees, "load_labels", labels_at)
    monkeypatch.setattr("sys.argv", ["check_trees.py", "--table", str(tmp_path / "films.sqlite")])
    assert check_trees.main() == 1
    assert read == [LABELS]
