"""Kinds read from the labels file: loading it, and how the engine offers labelled films."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from matinee.engine import Answer, EngineError, Viewer, load_catalog, walk
from matinee.labels import Labels, LabelsError, TreeLabels, load_labels
from matinee.trees import TreeError, load_trees
from test_engine import TREE, make_table, reference, write_data


def labelled_tree() -> dict[str, Any]:
    """TREE whose first question offers two labelled kinds and an answer leaving `laughs` out."""
    tree: dict[str, Any] = json.loads(json.dumps(TREE))
    tree["flavours"] = {"ghost": {"labelled": True}, "laughs": {"labelled": True}}
    tree["questions"][0]["options"] = [
        {"say": "ghosts.", "reply": "", "filter": {"flavour": "ghost"}},
        {"say": "laughs.", "reply": "", "filter": {"flavour": "laughs"}},
        {"say": "anything but laughs.", "reply": "", "filter": {"flavour_none": "laughs"}},
    ]
    return tree


def labels(kinds: dict[int, list[str]], out: tuple[int, ...] = ()) -> Labels:
    return Labels({"west": TreeLabels({t: frozenset(k) for t, k in kinds.items()}, frozenset(out))})


def pool_after(cat: Any, option: int) -> set[int]:
    return set(walk(cat, "west", Viewer(), [Answer("era", option)]).pool)


def test_a_labelled_kind_holds_the_films_labelled_with_it_and_a_film_may_sit_in_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("matinee.engine.KIND_MIN_FILMS", 1)  # which films a kind holds, not whether it shows
    lab = labels({1: ["ghost"], 2: ["ghost", "laughs"], 3: ["laughs"], 4: []})
    cat = load_catalog(make_table(), write_data(tmp_path, labelled_tree()), reference(), lab)
    assert pool_after(cat, 0) == {1, 2}
    assert pool_after(cat, 1) == {2, 3}


def test_leaving_a_kind_out_keeps_films_in_another_kind_and_films_in_none(tmp_path: Path) -> None:
    lab = labels({1: ["ghost"], 2: ["ghost", "laughs"], 3: ["laughs"], 4: []})
    cat = load_catalog(make_table(), write_data(tmp_path, labelled_tree()), reference(), lab)
    rest = pool_after(cat, 2)
    assert 3 not in rest  # laughs and nothing else
    assert {1, 2, 4, 5} <= rest  # another kind, labelled with no kind, unlabelled


def test_a_labelled_film_joins_the_pool_the_rules_left_it_out_of(tmp_path: Path) -> None:
    root = write_data(tmp_path, labelled_tree())
    (root / "trees" / "west.json").write_text(json.dumps({**labelled_tree(), "pool": "horror"}))
    cat = load_catalog(make_table(), root, reference(), labels({3: ["laughs"]}))
    ids = list(cat.ids)
    assert cat.pools["horror"][ids.index(3)]  # film 3 is tagged Comedy, not Horror


def test_a_label_never_brings_a_kids_only_film_into_another_tree(tmp_path: Path) -> None:
    table = make_table()
    genres, certificate = table.films.genres.copy(), table.films.certificate.copy()
    genres[31], certificate[31] = frozenset({"Animation", "Comedy", "Western"}), "G"  # no genome: kids-only
    table.films["genres"], table.films["certificate"] = genres, certificate
    root = write_data(tmp_path, labelled_tree())
    (root / "trees" / "west.json").write_text(json.dumps({**labelled_tree(), "pool": "horror"}))
    cat = load_catalog(table, root, reference(), labels({31: ["ghost"], 3: ["ghost"]}))
    ids = list(cat.ids)
    assert cat.pools["kids:only"][ids.index(31)] and cat.pools["kids"][ids.index(31)]
    assert not cat.pools["horror"][ids.index(31)]  # only the kids tree holds a kids-only film
    assert cat.pools["horror"][ids.index(3)]  # any other labelled film still joins


def test_a_film_labelled_out_leaves_only_when_another_tree_holds_it(tmp_path: Path) -> None:
    root = write_data(tmp_path, labelled_tree())
    (root / "trees" / "laughs.json").write_text(json.dumps({"pool": "comedy", "opening": "ha."}))
    cat = load_catalog(make_table(), root, reference(), labels({}, out=(2, 3)))
    ids = list(cat.ids)
    assert not cat.pools["western"][ids.index(3)]  # a Comedy film: the comedy tree holds it
    assert cat.pools["western"][ids.index(2)]  # a Horror film: no other tree holds it, so it stays


@pytest.mark.parametrize("order", [("west", "scary"), ("scary", "west")])
def test_labels_settle_the_same_whatever_order_the_file_lists_them(tmp_path: Path, order: tuple[str, str]) -> None:
    root = write_data(tmp_path, labelled_tree())
    scary = {"pool": "horror", "opening": "boo.", "flavours": {"ghost": {"labelled": True}}}
    (root / "trees" / "scary.json").write_text(json.dumps(scary))
    entries = {
        "west": TreeLabels({1: frozenset()}, frozenset({3, 4})),  # 3 is labelled into scary; 4 is out of both
        "scary": TreeLabels({3: frozenset()}, frozenset({4})),
    }
    pools = load_catalog(make_table(), root, reference(), Labels({t: entries[t] for t in order})).pools
    ids = list(make_table().films.index)
    assert pools["horror"][ids.index(3)] and not pools["western"][ids.index(3)]  # its labels place it in scary
    assert pools["western"][ids.index(4)] and pools["horror"][ids.index(4)]  # every door holding it labels it out


def test_a_film_the_house_pins_to_a_tree_stays_there_whatever_its_labels_say(tmp_path: Path) -> None:
    root = write_data(tmp_path, labelled_tree())
    (root / "trees" / "laughs.json").write_text(json.dumps({"pool": "comedy", "opening": "ha."}))
    house = json.loads((root / "house_overrides.json").read_text())
    (root / "house_overrides.json").write_text(json.dumps({**house, "trees": [{"tmdb": 3, "tree": "western"}]}))
    cat = load_catalog(make_table(), root, reference(), labels({}, out=(3, 5)))
    ids = list(cat.ids)
    assert cat.pools["western"][ids.index(3)]  # pinned: the comedy tree holds it too, and it stays
    assert not cat.pools["western"][ids.index(5)]  # unpinned, held by comedy: it leaves


def test_the_shipped_thriller_door_offers_its_kinds_in_order_and_only_spies_self_destructs() -> None:
    thriller = load_trees()["thriller"]
    (question,) = thriller.questions
    flavours = [o.filter.flavour for o in question.options]
    assert flavours == ["keep_guessing", "trapped", "mind_games", "spies", "serial_killers", "erotic", None]
    assert [o.self_destruct for o in question.options] == [None, None, None, 5, None, None, None]
    assert all(thriller.flavours[f]["labelled"] for f in flavours if f)


@pytest.mark.parametrize(
    "lab",
    [labels({1: ["nope"]}), Labels({"nowhere": TreeLabels()})],
)
def test_labels_naming_an_unknown_kind_or_tree_refuse_to_load(tmp_path: Path, lab: Labels) -> None:
    with pytest.raises(EngineError):
        load_catalog(make_table(), write_data(tmp_path, labelled_tree()), reference(), lab)


def test_a_labelled_kind_takes_no_signals(tmp_path: Path) -> None:
    tree = labelled_tree()
    tree["flavours"]["ghost"]["keywords_any"] = ["ghost"]
    with pytest.raises(TreeError):
        load_catalog(make_table(), write_data(tmp_path, tree), reference())


def test_the_labels_file_reads_kinds_and_out_and_is_empty_when_absent(tmp_path: Path) -> None:
    path = tmp_path / "labels.json"
    assert load_labels(path) == Labels()
    path.write_text(json.dumps({"format": 1, "trees": {"horror": {"kinds": {"238": ["a", "b"], "9": []}, "out": [7]}}}))
    horror = load_labels(path).of("horror")
    assert horror.kinds == {238: frozenset({"a", "b"}), 9: frozenset()}
    assert horror.out == frozenset({7})
    assert load_labels(path).of("comedy") == TreeLabels()


@pytest.mark.parametrize(
    "doc",
    [
        {"format": 2, "trees": {}},
        {"format": 1, "trees": {"horror": {"kinds": {"238": "a"}}}},
        {"format": 1, "trees": {"horror": {"kinds": {"x": ["a"]}}}},
        {"format": 1, "trees": {"horror": {"extra": []}}},
    ],
)
def test_a_malformed_labels_file_refuses_to_load(tmp_path: Path, doc: dict[str, Any]) -> None:
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(doc))
    with pytest.raises(LabelsError):
        load_labels(path)


def shown_says(cat: Any) -> list[str]:
    step = walk(cat, "west", Viewer(), [])
    return [o.say for o in step.question.options] if step.question else []


def bar_tree() -> dict[str, Any]:
    tree = labelled_tree()
    tree["questions"][0]["options"].append({"say": "anything.", "reply": "", "filter": {}})
    tree["flavours"]["heroic"] = {"keywords_any": ["superhero"]}
    tree["questions"][0]["options"].append({"say": "heroes.", "reply": "", "filter": {"flavour": "heroic"}})
    return tree


@pytest.mark.parametrize(("ghosts", "shown"), [(29, False), (30, True)])
def test_a_labelled_kind_shows_from_thirty_films_and_a_hidden_one_keeps_its_films(
    tmp_path: Path, ghosts: int, shown: bool
) -> None:
    lab = labels({t: ["ghost", "laughs"] if t <= ghosts else ["laughs"] for t in range(1, 31)})
    cat = load_catalog(make_table(), write_data(tmp_path, bar_tree()), reference(), lab)
    says = shown_says(cat)
    assert ("ghosts." in says) is shown  # ghost has no answer leaving it out, so the bar alone decides
    assert "anything but laughs." in says
    assert "heroes." in says  # a kind found by signals is not held to the bar
    assert int(cat.masks[("west", "era", 0)].sum()) == ghosts  # the bar never changes which films it holds
    anything = set(walk(cat, "west", Viewer(), [Answer("era", 3)]).pool)
    assert set(range(1, ghosts + 1)) <= anything


def test_an_always_shown_kind_shows_under_thirty_films(tmp_path: Path) -> None:
    tree = bar_tree()
    tree["flavours"]["ghost"]["always_shown"] = True
    cat = load_catalog(make_table(), write_data(tmp_path, tree), reference(), labels({1: ["ghost"], 2: ["ghost"]}))
    assert "ghosts." in shown_says(cat)


@pytest.mark.parametrize(
    "change",
    [
        lambda t: t["flavours"]["heroic"].update({"always_shown": True}),
        lambda t: t["flavours"]["laughs"].update({"always_shown": "yes"}),
    ],
)
def test_always_shown_is_only_for_a_labelled_kind_and_only_true(tmp_path: Path, change: Any) -> None:
    tree = bar_tree()
    change(tree)
    with pytest.raises(TreeError):
        load_catalog(make_table(), write_data(tmp_path, tree), reference())


def test_a_small_kind_another_answer_leaves_out_still_shows(tmp_path: Path) -> None:
    lab = labels({t: ["laughs"] for t in range(1, 5)})  # laughs 4; "anything but laughs." leaves them out
    tree = bar_tree()
    tree["questions"][0]["options"] = [o for o in tree["questions"][0]["options"] if o["say"] != "anything."]
    cat = load_catalog(make_table(), write_data(tmp_path, tree), reference(), lab)
    assert "laughs." in shown_says(cat)  # hiding it would leave films 1-4 no answer
