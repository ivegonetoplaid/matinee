"""The household override file: laid over the shipped labels and pins, read only, set aside when unusable."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from matinee.engine import load_catalog
from matinee.labels import OVERRIDES, Labels, TreeLabels, load_overrides, with_overrides
from matinee.pools import House
from matinee.web.main import OVERRIDES_BROKEN, household
from test_engine import make_table, reference, write_data

SHIPPED = Labels(
    {
        "comedy": TreeLabels({1: frozenset({"slapstick"}), 2: frozenset({"feelgood"})}),
        "kids": TreeLabels({3: frozenset({"silly"})}, {3: "family"}),
    }
)


def test_a_film_the_household_names_takes_its_whole_placement_from_the_file() -> None:
    theirs = Labels(
        {
            "horror": TreeLabels({1: frozenset({"monsters"}), 9: frozenset()}),  # 1 moves; 9 is new
            "kids": TreeLabels({3: frozenset({"adventure"})}, {3: "older"}),  # a kids film: its kinds and its band
        }
    )
    merged = with_overrides(SHIPPED, theirs)
    assert merged.overridden == frozenset({1, 3, 9})
    assert 1 not in merged.of("comedy").kinds and merged.of("horror").kinds[1] == frozenset({"monsters"})
    assert merged.of("comedy").kinds[2] == frozenset({"feelgood"})  # untouched
    assert merged.of("kids").kinds[3] == frozenset({"adventure"}) and merged.of("kids").bands[3] == "older"
    out = with_overrides(SHIPPED, Labels({"comedy": TreeLabels({3: frozenset({"slapstick"})})}))
    assert 3 not in out.of("kids").kinds and 3 not in out.of("kids").bands  # moved out of kids altogether
    assert 9 in merged.films()


def test_the_pins_of_a_film_the_household_places_give_way_except_its_gore_pail() -> None:
    house = House(
        kids_pins={1: "little", 2: "family"},
        tree_pins={"comedy": frozenset({1, 2})},
        scale_pins={("horror", "gore", "rip"): frozenset({1})},
        flavour_pins={("comedy", "slapstick"): {1: True, 2: False}},
        specials=frozenset({1, 2}),
    )
    left = house.without(frozenset({1}))
    assert left.kids_pins == {2: "family"} and left.tree_pins == {"comedy": frozenset({2})}
    assert left.flavour_pins == {("comedy", "slapstick"): {2: False}} and left.specials == frozenset({2})
    assert left.scale_pins == house.scale_pins


def test_a_pinned_film_can_be_moved_out_of_where_its_pin_puts_it(tmp_path: Path) -> None:
    data = write_data(tmp_path / "data")
    scary = {"pool": "horror", "opening": "boo.", "flavours": {"ghost": {"labelled": True}}}
    (data / "trees" / "scary.json").write_text(json.dumps(scary))
    pins = json.loads((data / "house_overrides.json").read_text())
    pins["trees"] = [{"tmdb": 1, "tree": "horror", "title": "Film 1", "note": "pinned in"}]
    (data / "house_overrides.json").write_text(json.dumps(pins))
    table = make_table()
    at = list(table.films.index).index(1)
    shipped = load_catalog(table, data, reference(), Labels())
    assert shipped.pools["horror"][at]  # the pin puts it behind the scary door
    theirs = with_overrides(Labels(), Labels({"west": TreeLabels({1: frozenset()})}))
    moved = load_catalog(table, data, reference(), theirs)
    assert not moved.pools["horror"][at] and moved.pools["western"][at]


def write(data_dir: Path, doc: object) -> Path:
    path = data_dir / OVERRIDES
    path.write_text(json.dumps(doc) if not isinstance(doc, str) else doc)
    return path


@pytest.mark.parametrize(
    ("doc", "problem"),
    [
        ("{not json", "not valid JSON"),
        ({"format": 1, "trees": {}}, "format"),
        ({"format": 2, "trees": {"musicals": {"kinds": {"1": []}}}}, "musicals"),
        ({"format": 2, "trees": {"comedy": {"kinds": {"1": ["tap dancing"]}}}}, "tap dancing"),
        ({"format": 2, "trees": {"kids": {"bands": {"3": "older"}}}}, "both its kinds and its band"),
        ({"format": 2, "trees": {"kids": {"kinds": {"3": ["silly"]}}}}, "both its kinds and its band"),
        ({"format": 2, "trees": {"comedy": {"kinds": {"3": []}, "bands": {"3": "little"}}}}, "only kids carries"),
    ],
)
def test_a_file_that_cannot_be_used_leaves_the_shipped_placements_and_says_so(
    tmp_path: Path, doc: object, problem: str
) -> None:
    path = write(tmp_path, doc)
    before = path.read_bytes()
    faults: list[str] = []
    assert household(SHIPPED, tmp_path, faults) is SHIPPED
    assert len(faults) == 1 and faults[0].startswith(OVERRIDES_BROKEN.split("{")[0]) and problem in faults[0]
    assert path.read_bytes() == before  # never written


def test_a_good_file_is_laid_over_and_removing_it_restores_the_shipped(tmp_path: Path) -> None:
    path = write(tmp_path, {"format": 2, "trees": {"comedy": {"kinds": {"2": ["slapstick"]}}}})
    before = path.read_bytes()
    faults: list[str] = []
    merged = household(SHIPPED, tmp_path, faults)
    assert faults == [] and merged.of("comedy").kinds[2] == frozenset({"slapstick"})
    assert path.read_bytes() == before
    path.unlink()
    assert household(SHIPPED, tmp_path, []) is SHIPPED
    assert load_overrides(tmp_path) is None


def test_the_rebuild_fetches_the_films_the_household_names(tmp_path: Path) -> None:
    import rebuild_table

    write(tmp_path, {"format": 2, "trees": {"comedy": {"kinds": {"999999999": []}}}})
    assert rebuild_table.household_films(tmp_path) == frozenset({999_999_999})
    write(tmp_path, "{broken")
    assert rebuild_table.household_films(tmp_path) == frozenset()


def test_the_documented_name_and_the_shipped_labels_pass_the_household_rules() -> None:
    from matinee.engine import household_problems
    from matinee.labels import load_labels
    from matinee.trees import load_trees

    assert OVERRIDES == "overrides.json"
    assert household_problems(load_labels(), load_trees()) == []


def test_a_broken_tree_file_with_an_override_file_still_starts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from matinee.trees import TreeError

    def broken() -> object:
        raise TreeError("tree 'comedy' is malformed")

    write(tmp_path, {"format": 2, "trees": {"comedy": {"kinds": {"5": []}}}})
    monkeypatch.setattr("matinee.web.main.load_trees", broken)
    faults: list[str] = []
    assert household(SHIPPED, tmp_path, faults) is SHIPPED and faults == []
    write(tmp_path, {"format": 1, "trees": {}})
    assert household(SHIPPED, tmp_path, faults) is SHIPPED and len(faults) == 1
