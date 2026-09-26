"""The one engine that walks every tree: a tree, a viewer and their answers in, a pool and the next question out.

It imports no web framework and reads no request state; the web page and the
tree checker are two callers of the same module, so they cannot disagree about a
pool.

A viewer's pool for a tree starts from the tree's pool (house pins already
applied), applies the viewer's personal corrections, then drops films the
viewer's own exclusions match, so a correction never brings back an excluded
film. Each answer narrows it. Questioning stops when
the tree has no more questions, or fewer than `STOP_UNDER` films remain. A
question marked `only_if_pool_over` is skipped unless the pool is larger; one
marked `skip_if_topics` is skipped for a viewer excluding any of those
DoesTheDogDie topics, and its `treat_as` answer is applied instead. An answer
that would leave the pool empty is not shown. Pool counts do not include
DoesTheDogDie exclusions, which are checked at the pick.

Unknown values are inclusive: a film with no runtime, rating, year, language,
collection or score passes a filter on it, because a wrongly included film costs
one `Not that one` and a wrongly excluded one is invisible.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
import pandas as pd

from matinee.pools import House, build_pools, load_house
from matinee.reference import DATA, Reference, load_reference, load_specs, problems
from matinee.scales import membership, offered, scale_of
from matinee.table import FilmTable
from matinee.trees import Filter, Option, Question, Tree, TreeError, load_trees

STOP_UNDER = 12
Mask = npt.NDArray[np.bool_]


class EngineError(ValueError):
    """The answers do not fit the tree, or the data the engine was given is inconsistent."""


@dataclass(frozen=True)
class Correction:
    """One personal correction: a film removed from, or added to, one tree for one viewer."""

    tmdb: int
    tree: str
    direction: Literal["remove", "add"]


@dataclass(frozen=True)
class Viewer:
    exclusions: frozenset[str] = frozenset()
    topics: frozenset[int] = frozenset()
    corrections: tuple[Correction, ...] = ()


@dataclass(frozen=True)
class Answer:
    question: str
    option: int


@dataclass(frozen=True)
class Shown:
    index: int
    say: str
    image: str | None = None


@dataclass(frozen=True)
class Asked:
    id: str
    ask: str
    options: tuple[Shown, ...]
    presentation: str | None


@dataclass(frozen=True)
class Step:
    """Where a walk stands: the line acknowledging the last answer, the next question or None, and the pool."""

    tree: str
    line: str
    question: Asked | None
    pool: tuple[int, ...]
    prefer: str | None = None


@dataclass(frozen=True)
class FirstOption:
    say: str
    tree: str
    label: str


@dataclass
class Catalog:
    """Everything the engine needs, prepared once per film table."""

    table: FilmTable
    reference: Reference
    trees: Mapping[str, Tree]
    house: House
    exclusions: Mapping[str, Mask]
    exclusion_names: Mapping[str, str]
    first_lines: tuple[str, ...]
    first_options: tuple[FirstOption, ...]
    pools: dict[str, Mask] = field(default_factory=dict)
    masks: dict[tuple[str, str, int], Mask] = field(default_factory=dict)

    @property
    def ids(self) -> npt.NDArray[np.int64]:
        return self.table.films.index.to_numpy()


def _bool(series: pd.Series) -> Mask:
    """A writable boolean array; pandas may hand back a read-only view otherwise."""
    return np.array(series.fillna(False).astype(bool), dtype=bool)


def _passes(values: pd.Series, test: pd.Series) -> Mask:
    """True where the value is unknown or the test holds."""
    return _bool(values.isna() | test)


def _keywords(table: FilmTable) -> pd.Series:
    return table.films.keywords.map(lambda k: k or frozenset())


def _any_genre(table: FilmTable, names: frozenset[str]) -> Mask:
    return np.array(table.films.genres.map(lambda g: bool(names & g)), dtype=bool)


def _flavour(table: FilmTable, tree: Tree, name: str) -> Mask:
    spec = tree.flavours.get(name)
    if spec is None:
        raise TreeError(f"tree '{tree.id}' has no flavour '{name}'")
    words = frozenset(spec.get("keywords_any", []))
    hit = np.array(_keywords(table).map(lambda k: bool(words & k)), dtype=bool)
    for tag in spec.get("genome_any", []):
        hit |= _bool(table.tag(tag) >= tree.genome_threshold)
    return hit | _any_genre(table, frozenset(spec.get("genres_any", [])))


OPS = {">=": np.greater_equal, ">": np.greater, "<": np.less, "<=": np.less_equal}


def _rule(rule: Any, dims: Mapping[str, npt.NDArray[np.float32]]) -> Mask:
    """A register rule: ["dim", op, value], {"all": [...]} or {"any": [...]}. An unknown score matches nothing."""
    if isinstance(rule, list):
        name, op, value = rule
        return np.asarray(OPS[op](dims[name], float(value)), dtype=bool)
    if "all" in rule:
        return np.array(np.logical_and.reduce([_rule(r, dims) for r in rule["all"]]), dtype=bool)
    return np.array(np.logical_or.reduce([_rule(r, dims) for r in rule["any"]]), dtype=bool)


def _register(table: FilmTable, tree: Tree, name: str) -> Mask:
    if name not in tree.registers:
        raise TreeError(f"tree '{tree.id}' has no register '{name}'")
    dims = {d: table.mean_of(tags).to_numpy() for d, tags in tree.register_dimensions.items()}
    return _rule(tree.registers[name], dims)


def payoff_members(cat: Catalog, tree: Tree) -> pd.DataFrame:
    """One boolean column per payoff answer of `tree`: whether each film belongs to it."""
    spec = tree.payoffs
    if spec is None:
        raise TreeError(f"tree '{tree.id}' has no payoffs")
    table = cat.table
    z = pd.DataFrame(
        {
            name: (table.mean_of(tags) - cat.reference.payoff(tree.id, name).mean)
            / cat.reference.payoff(tree.id, name).sd
            for name, tags in spec.standardised.items()
        }
    )
    strongest = z.eq(z.max(axis=1), axis=0)
    members = strongest if spec.overlap is None else strongest | z.ge(spec.overlap)
    for name, (tags, minimum) in spec.thresholds.items():
        members[name] = table.mean_of(tags).ge(minimum)
    members = members.fillna(False).astype(bool)
    unscored = ~table.has_genome()
    placed = pd.Series(False, index=table.films.index)
    for genre, payoff in spec.by_genre:
        hit = unscored & table.films.genres.map(lambda g, n=genre: n in g)
        members[payoff] |= hit
        placed |= hit
    rest = unscored & ~placed
    for name in spec.standardised if spec.default == "all" else [spec.default]:
        members[name] |= rest
    pins = {payoff: ids for (pin_tree, payoff), ids in cat.house.payoff_pins.items() if pin_tree == tree.id}
    for ids in pins.values():
        members.loc[table.films.index.isin(list(ids))] = False
    for payoff, ids in pins.items():
        members[payoff] |= table.films.index.isin(list(ids))
    return members


def scale_members(cat: Catalog, tree: Tree, name: str) -> pd.DataFrame:
    """One boolean column per band of `tree`'s scale `name`: whether each film belongs to it."""
    if name not in tree.scales:
        raise TreeError(f"tree '{tree.id}' has no scale '{name}'")
    scale = scale_of(tree.id, name, tree.scales[name], tree.scores)
    pins = {band: ids for (t, s, band), ids in cat.house.scale_pins.items() if (t, s) == (tree.id, name)}
    return membership(cat.table, scale, cat.reference.scale(tree.id, name), pins)


def _score(table: FilmTable, tree: Tree, name: str) -> pd.Series:
    if name not in tree.scores:
        raise TreeError(f"tree '{tree.id}' filters on score '{name}' but defines no such score")
    return table.mean_of(tree.scores[name])


RANGES = (
    ("runtime_min", "runtime_min", np.greater_equal),
    ("runtime_max", "runtime_min", np.less_equal),
    ("rating_min", "rating", np.greater_equal),
    ("year_min", "year", np.greater_equal),
    ("year_max", "year", np.less_equal),
)


def _range_mask(table: FilmTable, f: Filter) -> Mask:
    """Runtime, rating and year limits; a film with the value unknown passes."""
    mask = np.ones(len(table.films), dtype=bool)
    for attr, column, op in RANGES:
        limit = getattr(f, attr)
        if limit is not None:
            values = table.films[column].astype("Float64")
            mask &= _passes(values, pd.Series(op(values, limit), index=values.index))
    return mask


def _plain_mask(table: FilmTable, f: Filter) -> Mask:
    films = table.films
    mask = _range_mask(table, f)
    if f.spoken_english:
        mask &= _passes(films.language, films.language == "en")
    if f.standalone:
        mask &= films.collection_id.isna().to_numpy()
    if f.certificate_in is not None:
        mask &= films.certificate.isin(f.certificate_in).to_numpy()
    if f.genres_any is not None:
        mask &= _any_genre(table, f.genres_any)
    if f.genres_none is not None:
        mask &= ~_any_genre(table, f.genres_none)
    return mask


def _scored_mask(cat: Catalog, tree: Tree, f: Filter) -> Mask:
    table = cat.table
    mask = np.ones(len(table.films), dtype=bool)
    if f.flavour is not None:
        mask &= _flavour(table, tree, f.flavour)
    if f.register is not None:
        mask &= _register(table, tree, f.register)
    if f.payoff is not None:
        members = payoff_members(cat, tree)
        if f.payoff not in members.columns:
            raise TreeError(f"tree '{tree.id}' has no payoff '{f.payoff}'")
        mask &= members[f.payoff].to_numpy()
    if f.bands is not None:
        mask &= offered(scale_members(cat, tree, f.bands.scale), f.bands.bands).to_numpy()
    for name, limit in f.score_at_most.items():
        score = _score(table, tree, name)
        mask &= _passes(score, score <= limit)
    for name, limit in f.score_above.items():
        score = _score(table, tree, name)
        mask &= _passes(score, score > limit)
    if f.kids_band is not None:
        mask &= cat.pools["kids" if f.kids_band == "older" else f"kids:{f.kids_band}"]
    return mask


def option_mask(cat: Catalog, tree: Tree, option: Option) -> Mask:
    return _plain_mask(cat.table, option.filter) & _scored_mask(cat, tree, option.filter)


def _exclusion(table: FilmTable, spec: Mapping[str, Any]) -> Mask:
    """A viewer exclusion matches when any of its tests holds; unknown data never matches."""
    hit = np.zeros(len(table.films), dtype=bool)
    for test in spec["any"]:
        if "keywords_any" in test:
            words = frozenset(test["keywords_any"])
            hit |= np.array(_keywords(table).map(lambda k, w=words: bool(w & k)), dtype=bool)
        else:
            hit |= _bool(table.mean_of(test["tags"]) >= float(test["min"]))
    return hit


def _first_option(o: dict[str, str]) -> FirstOption:
    if not o.get("label"):
        raise EngineError(f"first question: '{o.get('say')}' has no label naming its tree")
    return FirstOption(o["say"], o["tree"], o["label"])


def load_catalog(table: FilmTable, data: Path = DATA, reference: Reference | None = None) -> Catalog:
    """Prepare the engine for one film table; raises when the shipped statistics do not cover the trees."""
    ref = reference or load_reference(data / "reference.json")
    stale = problems(ref, load_specs(data / "trees"))
    if stale:
        raise EngineError("the reference statistics do not cover the tree files: " + "; ".join(stale))
    first = json.loads((data / "first_question.json").read_text(encoding="utf-8"))
    excl = json.loads((data / "exclusions.json").read_text(encoding="utf-8"))
    cat = Catalog(
        table=table,
        reference=ref,
        trees=load_trees((data / "trees", data / "modes")),
        house=load_house(data / "house_overrides.json"),
        exclusions={name: _exclusion(table, spec) for name, spec in excl["exclusions"].items()},
        exclusion_names={name: str(spec.get("say", name)) for name, spec in excl["exclusions"].items()},
        first_lines=tuple(first["lines"]),
        first_options=tuple(_first_option(o) for o in first["options"]),
    )
    cat.pools = {name: np.array(pool, dtype=bool) for name, pool in build_pools(table, cat.house).items()}
    for tree in cat.trees.values():
        if tree.pool not in cat.pools:
            raise EngineError(f"tree '{tree.id}' names pool '{tree.pool}', which no pool rule builds")
        for q in tree.questions:
            for i, option in enumerate(q.options):
                cat.masks[(tree.id, q.id, i)] = option_mask(cat, tree, option)
    return cat


def base_pool(cat: Catalog, tree_id: str, viewer: Viewer) -> Mask:
    """The tree's pool for this viewer before any answer.

    Personal corrections apply first, then the viewer's exclusions, so a
    correction can never bring back a film an exclusion removes. A question the
    viewer's DoesTheDogDie topics skip applies its `treat_as` answer here, to the
    whole starting pool, so every answer shown and every stop count already sees it.
    """
    tree = cat.trees.get(tree_id)
    if tree is None:
        raise EngineError(f"no tree '{tree_id}'")
    pool = cat.pools[tree.pool].copy()
    ids = cat.ids
    for c in viewer.corrections:
        if c.tree == tree_id:
            pool[ids == c.tmdb] = c.direction == "add"
    for name in viewer.exclusions:
        if name not in cat.exclusions:
            raise EngineError(f"no exclusion '{name}'")
        pool &= ~cat.exclusions[name]
    for q in tree.questions:
        if q.treat_as is not None and q.skip_if_topics & viewer.topics:
            pool &= cat.masks[(tree.id, q.id, q.treat_as)]
    return pool


def _visible(option: Option, history: Mapping[str, int]) -> bool:
    return not any(history.get(q) in picked for q, picked in option.not_after.items())


def _shown(cat: Catalog, tree: Tree, q: Question, pool: Mask, history: Mapping[str, int]) -> list[int]:
    return [
        i
        for i, o in enumerate(q.options)
        if _visible(o, history) and bool((pool & cat.masks[(tree.id, q.id, i)]).any())
    ]


def _asked(q: Question, shown: Sequence[int]) -> Asked:
    return Asked(q.id, q.ask, tuple(Shown(i, q.options[i].say, q.options[i].image) for i in shown), q.presentation)


def _gate(
    cat: Catalog, tree: Tree, q: Question, pool: Mask, viewer: Viewer, history: Mapping[str, int]
) -> tuple[Mask, list[int]]:
    """The pool after a question is skipped or not, and the options to show; none shown means it is not asked."""
    if q.only_if_pool_over is not None and pool.sum() <= q.only_if_pool_over:
        return pool, []
    if q.treat_as is not None and q.skip_if_topics & viewer.topics:
        return pool, []
    return pool, _shown(cat, tree, q, pool, history)


def _answer(cat: Catalog, tree: Tree, q: Question, shown: Sequence[int], answer: Answer, pool: Mask) -> Mask:
    if answer.question != q.id or answer.option not in shown:
        raise EngineError(f"answer {answer} does not fit question '{q.id}' (shown options {list(shown)})")
    return pool & cat.masks[(tree.id, q.id, answer.option)]


def walk(cat: Catalog, tree_id: str, viewer: Viewer, answers: Sequence[Answer]) -> Step:
    """Apply `answers` in order and return where the walk stands; raises EngineError when one does not fit."""
    pool = base_pool(cat, tree_id, viewer)
    tree = cat.trees[tree_id]
    line, prefer = tree.opening, None
    history: dict[str, int] = {}
    pending = list(answers)
    for q in tree.questions:
        if pool.sum() < STOP_UNDER:
            break
        pool, shown = _gate(cat, tree, q, pool, viewer, history)
        if not shown:
            continue
        if not pending:
            return Step(tree_id, line, _asked(q, shown), tuple(int(t) for t in cat.ids[pool]), prefer)
        answer = pending.pop(0)
        pool = _answer(cat, tree, q, shown, answer, pool)
        option = q.options[answer.option]
        line, prefer = option.reply, option.filter.prefer or prefer
        history[q.id] = answer.option
    if pending:
        raise EngineError(f"{len(pending)} answers left over after the last question of '{tree_id}'")
    return Step(tree_id, line, None, tuple(int(t) for t in cat.ids[pool]), prefer)


def walk_ends(cat: Catalog, tree_id: str, viewer: Viewer | None = None) -> list[tuple[tuple[Answer, ...], Step]]:
    """Every complete path of answers through the tree for this viewer, with the step it ends on."""
    who = viewer or Viewer()
    ends = []
    stack: list[tuple[Answer, ...]] = [()]
    while stack:
        answers = stack.pop()
        step = walk(cat, tree_id, who, answers)
        if step.question is None:
            ends.append((answers, step))
            continue
        stack.extend((*answers, Answer(step.question.id, o.index)) for o in step.question.options)
    return ends


def reachable(cat: Catalog, tree_id: str, viewer: Viewer | None = None) -> Mask:
    """Films some complete path of answers ends on for this viewer: the union of every walk's final pool.

    A film in the tree's pool but not here can only be reached by `Just pick one!`.
    """
    reached = np.zeros(len(cat.ids), dtype=bool)
    for _, step in walk_ends(cat, tree_id, viewer):
        reached[np.isin(cat.ids, step.pool)] = True
    return reached


def first_question(cat: Catalog, viewer: Viewer) -> tuple[FirstOption, ...]:
    """The first question's answers whose tree or mode holds a film for this viewer."""
    return tuple(o for o in cat.first_options if o.tree in cat.trees and base_pool(cat, o.tree, viewer).any())
