"""Standup specials as a kind held apart in a tree: offered only by the answer naming them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from matinee.engine import Answer, Catalog, Viewer, load_catalog, opening_pool, walk, walk_ends
from matinee.labels import Labels, TreeLabels
from matinee.table import FilmTable
from matinee.trees import TreeError, parse_tree
from matinee.web.viewing import everything
from test_engine import TREE, make_table, reference, write_data

SPECIALS = {31, 33, 35}  # 31 and 33 carry the stand-up keyword; 35 is pinned by the house. All are rated R.


def table() -> FilmTable:
    t = make_table()
    keywords = t.films.keywords.copy()
    for tmdb in (31, 33):
        keywords[tmdb] = frozenset({"stand-up comedy"})
    t.films["keywords"] = keywords
    return t


def standup_tree() -> dict[str, Any]:
    tree: dict[str, Any] = json.loads(json.dumps(TREE))
    tree["flavours"] = {"ghost": {"labelled": True}, "standup": {"specials": True}}
    tree["apart"] = "standup"
    tree["questions"] = [
        {
            "id": "room",
            "ask": "who's watching?",
            "options": [
                {"say": "kids.", "reply": "", "filter": {"certificate_in": ["G", "PG"]}},
                {"say": "adults.", "reply": "", "filter": {}},
            ],
        },
        {
            "id": "kind",
            "ask": "what kind?",
            "footnote": "*specials have their own answer.",
            "options": [
                {"say": "ghosts.", "reply": "", "filter": {"flavour": "ghost"}},
                {"say": "a mic.", "reply": "one mic.", "filter": {"flavour": "standup"}},
                {"say": "anything.*", "reply": "", "filter": {}},
            ],
        },
    ]
    return tree


def catalog(
    root: Path,
    labels: Labels | None = None,
    tree: dict[str, Any] | None = None,
    pins: tuple[Any, ...] = (),
    also: dict[str, Any] | None = None,
) -> Catalog:
    """The standup tree over `table()`, 35 pinned as a special, plus `pins` and any `also` tree files by name."""
    data = write_data(root, tree or standup_tree())
    for name, doc in (also or {}).items():
        (data / "trees" / f"{name}.json").write_text(json.dumps(doc))
    house = json.loads((data / "house_overrides.json").read_text())
    house["trees"] = list(pins)
    house["specials"] = [{"tmdb": 35}]
    (data / "house_overrides.json").write_text(json.dumps(house))
    return load_catalog(table(), data, reference(), labels)


def ends(cat: Catalog) -> dict[tuple[int, ...], set[int]]:
    return {tuple(a.option for a in answers): set(step.pool) for answers, step in walk_ends(cat, "west")}


def test_only_the_standup_answer_offers_a_special_and_it_offers_nothing_else(tmp_path: Path) -> None:
    paths = ends(catalog(tmp_path, Labels({"west": TreeLabels({31: frozenset({"ghost"}), 2: frozenset({"ghost"})})})))
    assert paths[(1, 1)] == SPECIALS
    for path, pool in paths.items():
        if path != (1, 1):
            assert not pool & SPECIALS, path  # a special labelled into ghost is still not offered there
    assert 2 in paths[(1, 0)] and 31 not in paths[(1, 0)]


def test_no_pool_before_the_standup_answer_holds_a_special(tmp_path: Path) -> None:
    cat = catalog(tmp_path)
    before = walk(cat, "west", Viewer(), [])
    after_room = walk(cat, "west", Viewer(), [Answer("room", 1)])
    assert before.question is not None and after_room.question is not None
    assert not set(before.pool) & SPECIALS  # "Just pick one!" draws from these pools
    assert not set(after_room.pool) & SPECIALS
    assert not {int(t) for t in cat.ids[opening_pool(cat, "west", Viewer())]} & SPECIALS
    assert "a mic." in [o.say for o in after_room.question.options]
    assert not set(everything(cat, Viewer())) & SPECIALS  # "Just pick one!" at the first question


def test_the_certificate_ceiling_keeps_specials_and_their_answer_from_the_kids_path(tmp_path: Path) -> None:
    cat = catalog(tmp_path)
    kids = walk(cat, "west", Viewer(), [Answer("room", 0)])
    assert kids.question is not None
    assert "a mic." not in [o.say for o in kids.question.options]
    for path, pool in ends(cat).items():
        if path[0] == 0:
            assert not pool & SPECIALS


def test_a_special_labelled_out_of_the_tree_stays_reachable_through_its_answer(tmp_path: Path) -> None:
    # A second tree holds special 31 and film 4, so labelling them out of west removes them unless held apart.
    cat = catalog(
        tmp_path,
        Labels({"west": TreeLabels({}, frozenset({*SPECIALS, 4}))}),
        pins=({"tmdb": 31, "tree": "horror"},),
        also={"scary": {"pool": "horror", "opening": "boo."}},
    )
    paths = ends(cat)
    assert paths[(1, 1)] == SPECIALS
    assert not any(4 in pool for pool in paths.values())  # only the apart flavour is kept against its labels


def test_the_footnote_shows_only_beside_the_answer_it_points_at(tmp_path: Path) -> None:
    cat = catalog(tmp_path)
    adults = walk(cat, "west", Viewer(), [Answer("room", 1)]).question
    kids = walk(cat, "west", Viewer(), [Answer("room", 0)]).question
    assert adults is not None and kids is not None
    assert adults.footnote == "*specials have their own answer."
    assert "anything.*" in [o.say for o in adults.options]
    assert kids.footnote is None  # the stand-up answer is hidden, so nothing points at it
    assert "anything." in [o.say for o in kids.options]


@pytest.mark.parametrize(
    "change",
    [
        lambda t: t.update({"apart": "nope"}),
        lambda t: t["flavours"]["standup"].update({"keywords_any": ["comedian"]}),
    ],
)
def test_an_unknown_apart_flavour_or_a_specials_flavour_with_signals_refuses_to_load(change: Any) -> None:
    tree = standup_tree()
    change(tree)
    with pytest.raises(TreeError):
        parse_tree("west", tree)
