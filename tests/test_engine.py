"""The engine, on a constructed library and a constructed data directory."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from matinee.engine import (
    Answer,
    Catalog,
    Correction,
    EngineError,
    Viewer,
    first_question,
    gentlest,
    load_catalog,
    option_mask,
    payoff_members,
    reachable,
    walk,
)
from matinee.pools import SCORES
from matinee.reference import Cuts, Reference, Stat, TreeReference
from matinee.table import FilmTable
from matinee.trees import Bands, Filter, Option

EXTRA = ("p_fast", "p_slow", "gore_a", "spook", "hero")
TAGS = tuple(sorted({t for tags in SCORES.values() for t in tags} | set(EXTRA)))
N = 40  # films 1..40, all Western; enough to stay over the stop-under-12 line


def genres_of(t: int) -> frozenset[str]:
    extra = {1: {"Animation"}, 2: {"Animation"}, 4: {"Musical"}}.get(t, set())
    return frozenset({"Western", "Comedy" if t % 2 else "Horror", *extra})


def certificate_of(t: int) -> str:
    return {1: "G", 6: ""}.get(t, "PG" if t <= 20 else "R")


def film_rows() -> list[dict[str, Any]]:
    rows = []
    for t in range(1, N + 1):
        rows.append(
            {
                "tmdb": t,
                "name": f"Film {t}",
                "year": 1970 + t,
                "genres": genres_of(t),
                "certificate": certificate_of(t),
                "runtime_min": None if t == 40 else 80.0 + t,
                "rating": 5.0 + t / 10,
                "tmdb_known": True,
                "language": {8: "fr", 9: None}.get(t, "en"),
                "collection_id": 5 if t <= 3 else None,
                "keywords": frozenset({"superhero"}) if t == 7 else frozenset(),
            }
        )
    return rows


def relevance(t: int) -> dict[str, float] | None:
    """Films 1-30 have genome rows; 31-40 do not."""
    if t > 30:
        return None
    rel = {"p_fast": 0.9 if t <= 10 else 0.1, "p_slow": 0.8 if t > 10 else 0.2, "spook": 0.5 if t == 12 else 0.0}
    rel |= {13: {"p_fast": 0.6, "p_slow": 0.5}, 14: {"p_fast": 0.9, "p_slow": 0.55}}.get(t, {})
    rel["gore_a"] = 0.8 if t <= 5 else 0.0
    rel["hero"] = 0.7 if t == 3 else 0.0
    return rel


def make_table() -> FilmTable:
    frame = pd.DataFrame(film_rows()).set_index("tmdb")
    frame["year"] = frame["year"].astype("Int64")
    frame["collection_id"] = frame["collection_id"].astype("Int64")
    matrix = np.full((N, len(TAGS)), np.nan, dtype=np.float32)
    for i, t in enumerate(frame.index):
        rel = relevance(int(t))
        if rel is not None:
            matrix[i] = 0.0
            for tag, v in rel.items():
                matrix[i, TAGS.index(tag)] = v
    return FilmTable(frame, TAGS, matrix, datetime.now(UTC), None, "test")


TREE: dict[str, Any] = {
    "pool": "western",
    "opening": "howdy.",
    "scores": {"fast": ["p_fast"], "slow": ["p_slow"], "spook": ["spook"], "gore": ["gore_a"]},
    "reference": {"movielens_genres": ["Western"], "floor_any": {}},
    "scales": {
        "gore": {"score": "gore", "percentiles": [50], "bands": ["clean", "messy"], "unscored_bands": ["messy"]}
    },
    "flavours": {"heroic": {"keywords_any": ["superhero"], "genome_any": ["hero"], "genres_any": ["Musical"]}},
    "genome": {"threshold": 0.6},
    "registers": {
        "dimensions": {"a": ["p_fast"], "b": ["p_slow"]},
        "rules": {
            "both": {"all": [["a", ">=", 0.5], ["b", ">=", 0.5]]},
            "either": {"any": [["a", ">=", 0.85], ["b", ">=", 0.85]]},
        },
    },
    "payoffs": {"fast": ["p_fast"], "slow": ["p_slow"]},
    "payoff_rule": {
        "overlap": 1.0,
        "thresholds": {"spooky": {"score": "spook", "min": 0.3}},
        "no_genome": {"by_genre": [["Horror", "spooky"]], "default": "all"},
    },
    "questions": [
        {
            "id": "era",
            "ask": "when?",
            "options": [
                {"say": "old.", "reply": "old it is.", "filter": {"year_max": 1990}},
                {"say": "any.", "reply": "", "filter": {}},
                {"say": "future.", "reply": "", "filter": {"year_min": 3000}},
                {"say": "late.", "reply": "", "filter": {"year_min": 1991, "year_max": 2009}},
            ],
        },
        {
            "id": "gore",
            "ask": "blood?",
            "skip_if_topics": [188],
            "treat_as": 0,
            "options": [
                {"say": "short.", "reply": "short.", "filter": {"runtime_max": 100}},
                {"say": "long.", "reply": "long.", "filter": {"runtime_min": 100, "sort": "rating"}},
            ],
        },
        {
            "id": "payoff",
            "ask": "what?",
            "only_if_pool_over": 15,
            "options": [
                {"say": "fast.", "reply": "zoom.", "filter": {"payoff": "fast"}},
                {"say": "slow.", "reply": "ahh.", "filter": {"payoff": "slow"}},
                {"say": "spooky.", "reply": "boo.", "filter": {"payoff": "spooky"}, "not_after": {"era": [0]}},
            ],
        },
    ],
}


def write_data(root: Path, tree: dict[str, Any] | None = None) -> Path:
    (root / "trees").mkdir(parents=True)
    (root / "modes").mkdir()
    (root / "trees" / "west.json").write_text(json.dumps(tree or TREE))
    (root / "first_question.json").write_text(
        json.dumps(
            {
                "lines": ["Right this way."],
                "options": [
                    {"say": "Cowboys.", "tree": "west", "label": "Western"},
                    {"say": "No.", "tree": "none", "label": "None"},
                ],
            }
        )
    )
    (root / "exclusions.json").write_text(
        json.dumps(
            {
                "exclusions": {
                    "superheroes": {"say": "Superheroes", "any": [{"keywords_any": ["superhero"]}]},
                    "heroes": {"any": [{"tags": ["hero"], "min": 0.6}]},
                }
            }
        )
    )
    (root / "house_overrides.json").write_text(
        json.dumps(
            {
                "kids": [],
                "trees": [],
                "payoffs": [{"tmdb": 5, "tree": "west", "payoff": "slow"}],
                "scales": [{"tmdb": 2, "tree": "west", "scale": "gore", "band": "clean"}],
            }
        )
    )
    return root


def reference() -> Reference:
    return Reference(
        "test",
        {
            "west": TreeReference(
                genres=("Western",),
                floor_any=(),
                films=30,
                payoffs={"fast": Stat(("p_fast",), 0.5, 0.2), "slow": Stat(("p_slow",), 0.3, 0.2)},
                scales={"gore": Cuts(("gore_a",), (50.0,), (0.5,))},
            )
        },
    )


@pytest.fixture
def cat(tmp_path: Path) -> Catalog:
    return load_catalog(make_table(), write_data(tmp_path), reference())


def test_first_step_asks_with_non_empty_answers_only(cat: Catalog) -> None:
    step = walk(cat, "west", Viewer(), [])
    assert step.line == "howdy."
    assert step.question is not None and step.question.id == "era"
    assert [o.index for o in step.question.options] == [0, 1, 3]
    assert len(step.pool) == N


def test_answers_narrow_reply_and_prefer(cat: Catalog) -> None:
    step = walk(cat, "west", Viewer(), [Answer("era", 1), Answer("gore", 1)])
    assert step.line == "long."
    assert step.prefer == "rating"
    assert step.pool == tuple(range(20, N + 1))  # runtime 100+ and the film with no runtime
    assert step.question is not None and step.question.id == "payoff"


def test_asks_while_twelve_or_more_remain_and_stops_under(cat: Catalog) -> None:
    short = walk(cat, "west", Viewer(), [Answer("era", 0), Answer("gore", 0)])  # films 1-20: over 15
    assert short.question is not None and short.question.id == "payoff"
    assert [o.index for o in short.question.options] == [0, 1]  # spooky hidden after "old."
    fewer = Viewer(corrections=tuple(Correction(t, "west", "remove") for t in range(1, 10)))
    stopped = walk(cat, "west", fewer, [Answer("era", 0)])  # films 10-20: eleven left
    assert stopped.question is None and stopped.pool == tuple(range(10, 21))
    twelve = Viewer(corrections=tuple(Correction(t, "west", "remove") for t in range(1, 9)))
    assert walk(cat, "west", twelve, [Answer("era", 0)]).question is not None


def test_only_if_pool_over(cat: Catalog, tmp_path: Path) -> None:
    tree = json.loads(json.dumps(TREE))
    tree["questions"][2]["only_if_pool_over"] = 25
    other = load_catalog(make_table(), write_data(tmp_path / "b", tree), reference())
    step = walk(other, "west", Viewer(), [Answer("era", 0), Answer("gore", 0)])
    assert step.question is None and len(step.pool) == 20


def test_topic_skip_narrows_the_starting_pool(cat: Catalog) -> None:
    squeamish = Viewer(topics=frozenset({188}))
    start = walk(cat, "west", squeamish, [])
    assert start.pool == (*range(1, 21), 40)  # runtime at most 100, and film 40 whose runtime is unknown
    assert start.question is not None
    assert [o.index for o in start.question.options] == [0, 1]  # "late." holds only long films: hidden
    step = walk(cat, "west", squeamish, [Answer("era", 1)])
    assert step.question is not None and step.question.id == "payoff"
    with pytest.raises(EngineError):
        walk(cat, "west", squeamish, [Answer("era", 1), Answer("gore", 0)])


def test_topic_skip_applies_even_when_the_walk_stops_first(cat: Catalog) -> None:
    few = tuple(Correction(t, "west", "remove") for t in range(1, 30))  # 30-40 remain: all long or unknown
    squeamish = Viewer(topics=frozenset({188}), corrections=few)
    step = walk(cat, "west", squeamish, [])
    assert step.question is None and step.pool == (40,)


def test_misfit_and_leftover_answers_are_refused(cat: Catalog) -> None:
    with pytest.raises(EngineError):
        walk(cat, "west", Viewer(), [Answer("gore", 0)])
    with pytest.raises(EngineError):
        walk(cat, "west", Viewer(), [Answer("era", 2)])  # an empty answer is not shown
    with pytest.raises(EngineError):
        walk(cat, "west", Viewer(), [Answer("era", 1), Answer("gore", 1), Answer("payoff", 0), Answer("x", 0)])
    with pytest.raises(EngineError):
        walk(cat, "nope", Viewer(), [])


def test_exclusions_and_corrections(cat: Catalog) -> None:
    pool = walk(cat, "west", Viewer(exclusions=frozenset({"superheroes"})), []).pool
    assert 7 not in pool and len(pool) == N - 1
    assert walk(cat, "west", Viewer(exclusions=frozenset({"heroes"})), []).pool == tuple(
        t for t in range(1, N + 1) if t != 3
    )
    readd = Viewer(exclusions=frozenset({"superheroes"}), corrections=(Correction(7, "west", "add"),))
    assert 7 not in walk(cat, "west", readd, []).pool
    fixes = (Correction(3, "west", "remove"), Correction(3, "elsewhere", "add"))
    assert 3 not in walk(cat, "west", Viewer(corrections=fixes), []).pool
    with pytest.raises(EngineError):
        walk(cat, "west", Viewer(exclusions=frozenset({"nope"})), [])


def test_payoff_placement(cat: Catalog) -> None:
    m = payoff_members(cat, cat.trees["west"])
    assert m.loc[1, "fast"] and not m.loc[1, "slow"]  # z 2.0 against -0.5
    assert m.loc[11, "slow"] and not m.loc[11, "fast"]
    assert m.loc[13, "slow"] and not m.loc[13, "fast"]  # raw fast 0.6 beats slow 0.5; standardised, slow wins
    assert m.loc[14, "fast"] and m.loc[14, "slow"]  # weaker payoff z 1.25 reaches the overlap of 1.0
    assert m.loc[5, "slow"] and not m.loc[5, "fast"]  # a house pin moves the film to its answer
    assert m.loc[12, "spooky"] and not m.loc[11, "spooky"]  # raw threshold, never strongest
    assert m.loc[32, "spooky"] and not m.loc[32, "fast"] and not m.loc[32, "slow"]  # no genome, Horror


def test_no_genome_default_all(cat: Catalog) -> None:
    m = payoff_members(cat, cat.trees["west"])
    odd = 31  # Comedy, no genome, matches no by_genre rule: every standardised payoff
    assert m.loc[odd, "fast"] and m.loc[odd, "slow"] and not m.loc[odd, "spooky"]


def test_not_after_hides_an_option(cat: Catalog) -> None:
    step = walk(cat, "west", Viewer(), [Answer("era", 0), Answer("gore", 0)])
    assert step.question is not None and step.question.id == "payoff"
    assert 2 not in [o.index for o in step.question.options]
    wide = walk(cat, "west", Viewer(), [Answer("era", 1), Answer("gore", 1)])
    assert wide.question is not None and 2 in [o.index for o in wide.question.options]


def test_first_question_hides_missing_and_empty_trees(cat: Catalog) -> None:
    assert [o.tree for o in first_question(cat, Viewer())] == ["west"]
    everyone = tuple(Correction(t, "west", "remove") for t in range(1, N + 1))
    assert first_question(cat, Viewer(corrections=everyone)) == ()


def test_stale_reference_refuses_to_load(tmp_path: Path) -> None:
    stale = Reference("test", {"west": TreeReference(("Western",), (), 30, {}, reference().trees["west"].scales)})
    with pytest.raises(EngineError, match="reference"):
        load_catalog(make_table(), write_data(tmp_path), stale)


def test_misspelt_filter_refuses_to_load(tmp_path: Path) -> None:
    tree = json.loads(json.dumps(TREE))
    tree["questions"][0]["options"][0]["filter"] = {"year_maximum": 1990}
    with pytest.raises(ValueError, match="year_maximum"):
        load_catalog(make_table(), write_data(tmp_path, tree), reference())


def mask_of(cat: Catalog, **kw: Any) -> list[int]:
    films = option_mask(cat, cat.trees["west"], Option("x", "", Filter(**kw)))
    return [int(t) for t in cat.ids[films]]


def test_register_rules(cat: Catalog) -> None:
    assert mask_of(cat, register="both") == [13, 14]
    either = mask_of(cat, register="either")
    assert 1 in either and 14 in either and 13 not in either and 11 not in either


def test_metadata_filters(cat: Catalog) -> None:
    everyone = set(range(1, N + 1))
    assert set(mask_of(cat, genres_none=frozenset({"Horror"}))) == {t for t in everyone if t % 2}
    assert mask_of(cat, certificate_in=frozenset({""})) == [6]
    assert set(mask_of(cat, certificate_in=frozenset({"G", "PG"}))) == set(range(1, 21)) - {6}
    assert set(mask_of(cat, spoken_english=True)) == everyone - {8}  # film 9's language is unknown: kept
    assert set(mask_of(cat, standalone=True)) == everyone - {1, 2, 3}
    assert mask_of(cat, flavour="heroic") == [3, 4, 7]  # genome, genre, keyword
    assert mask_of(cat, kids_band="little") == [1]
    assert mask_of(cat, kids_band="family") == [1, 2, 3]  # film 3 shares film 1's collection (franchise rule)


def test_scale_bands_with_pin_and_unscored(cat: Catalog) -> None:
    clean = mask_of(cat, bands=Bands("gore", frozenset({"clean"})))
    messy = mask_of(cat, bands=Bands("gore", frozenset({"messy"})))
    assert 2 in clean and 2 not in messy  # pinned clean although it scores 0.8
    assert 1 in messy and 1 not in clean
    assert 31 in messy and 31 not in clean  # no genome: the unscored band only


def test_score_limits_at_the_edge(cat: Catalog, tmp_path: Path) -> None:
    at_most = mask_of(cat, score_at_most={"fast": 0.6})
    above = mask_of(cat, score_above={"fast": 0.6})
    assert 13 in at_most and 13 not in above  # exactly 0.6
    assert 31 in at_most and 31 in above  # unknown passes both


def test_only_if_pool_over_is_strictly_over(cat: Catalog, tmp_path: Path) -> None:
    tree = json.loads(json.dumps(TREE))
    tree["questions"][2]["only_if_pool_over"] = 20
    other = load_catalog(make_table(), write_data(tmp_path / "c", tree), reference())
    assert walk(other, "west", Viewer(), [Answer("era", 0), Answer("gore", 0)]).question is None  # 20 films
    tree["questions"][2]["only_if_pool_over"] = 19
    again = load_catalog(make_table(), write_data(tmp_path / "d", tree), reference())
    assert walk(again, "west", Viewer(), [Answer("era", 0), Answer("gore", 0)]).question is not None


@pytest.mark.parametrize(
    "path,value",
    [
        (("questions", 0, "options", 0, "fliter"), {}),
        (("questions", 0, "skip_if"), [1]),
        (("flavours", "heroic", "keyword_any"), ["x"]),
    ],
)
def test_misspelt_keys_refuse_to_load(tmp_path: Path, path: tuple[Any, ...], value: Any) -> None:
    tree = json.loads(json.dumps(TREE))
    node = tree
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    with pytest.raises(ValueError, match=str(path[-1])):
        load_catalog(make_table(), write_data(tmp_path, tree), reference())


def test_reachable_is_the_union_of_walk_ends(cat: Catalog, tmp_path: Path) -> None:
    assert {int(t) for t in cat.ids[reachable(cat, "west")]} == set(range(1, N + 1))
    tree = json.loads(json.dumps(TREE))
    tree["questions"][0]["options"] = [{"say": "old.", "reply": "", "filter": {"year_max": 2000}}]
    narrow = load_catalog(make_table(), write_data(tmp_path / "e", tree), reference())
    assert {int(t) for t in narrow.ids[reachable(narrow, "west")]} == set(range(1, 31))
    few = Viewer(corrections=tuple(Correction(t, "west", "remove") for t in range(1, 30)))
    assert {int(t) for t in narrow.ids[reachable(narrow, "west", few)]} == set(range(30, N + 1))


def test_a_first_answer_without_a_label_refuses_to_load(tmp_path: Path) -> None:
    data = write_data(tmp_path / "data")
    first = json.loads((data / "first_question.json").read_text())
    del first["options"][0]["label"]
    (data / "first_question.json").write_text(json.dumps(first))
    with pytest.raises(EngineError, match="no label"):
        load_catalog(make_table(), data, reference())


def gore_cut_tree() -> dict[str, Any]:
    """TREE with its gore question cutting the gore scale, as horror's pails do; skipping it keeps both bands."""
    tree: dict[str, Any] = json.loads(json.dumps(TREE))
    tree["questions"][1]["treat_as"] = 1
    tree["questions"][1]["options"] = [
        {"say": "clean.", "reply": "", "filter": {"bands": {"scale": "gore", "in": ["clean"]}}},
        {"say": "any.", "reply": "", "filter": {"bands": {"scale": "gore", "in": ["clean", "messy"]}}},
    ]
    return tree


def test_gentlest_is_the_least_gory_third_for_a_viewer_whose_topics_skip_the_gore_question(tmp_path: Path) -> None:
    cat = load_catalog(make_table(), write_data(tmp_path, gore_cut_tree()), reference())
    squeamish = Viewer(topics=frozenset({188}))  # 188 skips the gore question
    assert gentlest(cat, squeamish, [1, 2, 3, 6, 7, 8]) == {6, 7}  # films 1-5 score 0.8, the rest 0.0
    assert gentlest(cat, squeamish, [31, 1, 6]) == {6}  # 31 has no genome entry, so it ranks last
    assert gentlest(cat, Viewer(topics=frozenset({153})), [1, 6]) == frozenset()
    assert gentlest(cat, squeamish, []) == frozenset()


def test_gentlest_needs_a_skipped_question_that_cuts_a_scale(cat: Catalog) -> None:
    assert gentlest(cat, Viewer(topics=frozenset({188})), [1, 6]) == frozenset()  # TREE's gore question cuts runtime


def comedy_gate_tree() -> dict[str, Any]:
    """TREE with a flavour of Comedy films that must also score 'fast' at 0.5, and an answer leaving it out."""
    tree: dict[str, Any] = json.loads(json.dumps(TREE))
    tree["flavours"]["laughs"] = {"genres_any": ["Comedy"], "score_at_least": {"fast": 0.5}}
    tree["questions"][0]["options"] = [
        {"say": "laughs.", "reply": "", "filter": {"flavour": "laughs"}},
        {"say": "no laughs.", "reply": "", "filter": {"flavour_none": "laughs"}},
    ]
    return tree


def test_a_flavour_floor_keeps_only_films_reaching_it_and_films_with_no_score(tmp_path: Path) -> None:
    cat = load_catalog(make_table(), write_data(tmp_path, comedy_gate_tree()), reference())
    laughs = set(walk(cat, "west", Viewer(), [Answer("era", 0)]).pool)
    # odd films are Comedy; 'fast' is 0.9 up to film 10, 0.6 for 13, 0.1 otherwise; 31-40 have no genome entry
    assert laughs == {1, 3, 5, 7, 9, 13, 31, 33, 35, 37, 39}
    rest = set(walk(cat, "west", Viewer(), [Answer("era", 1)]).pool)
    assert rest == set(range(1, 41)) - laughs  # leaving the flavour out is its exact complement


def pin_flavours(root: Path, pins: list[dict[str, Any]]) -> Path:
    house = json.loads((root / "house_overrides.json").read_text())
    (root / "house_overrides.json").write_text(json.dumps({**house, "flavours": pins}))
    return root


def test_flavour_pins_move_a_film_in_or_out_and_a_film_pinned_elsewhere_survives_leaving_one_out(
    tmp_path: Path,
) -> None:
    pins = [
        {"tmdb": 3, "tree": "west", "flavour": "laughs", "member": False},
        {"tmdb": 2, "tree": "west", "flavour": "laughs", "member": True},
        {"tmdb": 5, "tree": "west", "flavour": "heroic", "member": True},
    ]
    cat = load_catalog(make_table(), pin_flavours(write_data(tmp_path, comedy_gate_tree()), pins), reference())
    laughs = set(walk(cat, "west", Viewer(), [Answer("era", 0)]).pool)
    rest = set(walk(cat, "west", Viewer(), [Answer("era", 1)]).pool)
    assert 3 in rest and 3 not in laughs
    assert 2 in laughs and 2 not in rest
    assert 5 in laughs and 5 in rest  # a funny film pinned into another flavour is offered both ways


def test_a_flavour_pin_naming_an_unknown_flavour_refuses_to_load(tmp_path: Path) -> None:
    pins = [{"tmdb": 3, "tree": "west", "flavour": "nope", "member": True}]
    with pytest.raises(ValueError):
        load_catalog(make_table(), pin_flavours(write_data(tmp_path, comedy_gate_tree()), pins), reference())


@pytest.mark.parametrize(
    "change",
    [
        lambda t: t["flavours"]["heroic"].update({"score_at_least": {"fast": "high"}}),
        lambda t: t["flavours"]["heroic"].update({"score_at_least": {"nope": 0.5}}),
        lambda t: t["questions"][0]["options"][0]["filter"].update({"flavour_none": "nope"}),
    ],
)
def test_a_bad_flavour_floor_or_unknown_flavour_none_refuses_to_load(tmp_path: Path, change: Any) -> None:
    tree: dict[str, Any] = json.loads(json.dumps(TREE))
    change(tree)
    with pytest.raises(ValueError):  # TreeError and EngineError are both ValueErrors
        load_catalog(make_table(), write_data(tmp_path, tree), reference())
