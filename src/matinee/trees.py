"""Tree and mode files, read into typed models.

A tree file carries the content: its opening line, its questions and their
answers in the viewer's voice, and the rule each answer filters or scores on. The
engine carries the behaviour. Question, option and filter keys are checked
strictly, so a misspelt key fails at load rather than silently widening a pool.
Top-level documentation keys (notes, measurements) are left alone.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from matinee.reference import DATA


class TreeError(ValueError):
    """A tree or mode file is malformed."""


@dataclass(frozen=True)
class Bands:
    scale: str
    bands: frozenset[str]


@dataclass(frozen=True)
class Filter:
    """What one answer keeps. Every field left at its default keeps everything."""

    runtime_min: float | None = None
    runtime_max: float | None = None
    rating_min: float | None = None
    year_min: int | None = None
    year_max: int | None = None
    spoken_english: bool = False
    standalone: bool = False
    certificate_in: frozenset[str] | None = None
    genres_any: frozenset[str] | None = None
    genres_none: frozenset[str] | None = None
    flavour: str | None = None
    flavour_none: str | None = None
    payoff: str | None = None
    bands: Bands | None = None
    score_at_most: Mapping[str, float] = field(default_factory=dict)
    score_above: Mapping[str, float] = field(default_factory=dict)
    kids_band: str | None = None
    prefer: str | None = None


@dataclass(frozen=True)
class Option:
    say: str
    reply: str
    filter: Filter
    not_after: Mapping[str, frozenset[int]] = field(default_factory=dict)
    image: str | None = None


@dataclass(frozen=True)
class Question:
    id: str
    ask: str
    options: tuple[Option, ...]
    only_if_pool_over: int | None = None
    skip_if_topics: frozenset[int] = frozenset()
    treat_as: int | None = None
    presentation: str | None = None


@dataclass(frozen=True)
class Payoffs:
    """How films are placed on a tree's payoff answers.

    `standardised` payoffs are scored against the reference; a film belongs to its
    strongest one and to any other reaching `overlap` (None: strongest only).
    `thresholds` payoffs are raw scores that must reach a minimum and never count
    as strongest. A film with no genome score is placed under every `by_genre`
    payoff whose genre it carries; a film matching none of them is placed by
    `default`: a payoff name, or "all" for every standardised payoff.
    """

    standardised: Mapping[str, tuple[str, ...]]
    overlap: float | None
    thresholds: Mapping[str, tuple[tuple[str, ...], float]]
    by_genre: tuple[tuple[str, str], ...]
    default: str


@dataclass(frozen=True)
class Tree:
    id: str
    pool: str
    opening: str
    questions: tuple[Question, ...]
    scores: Mapping[str, tuple[str, ...]]
    flavours: Mapping[str, Mapping[str, Any]]
    genome_threshold: float
    payoffs: Payoffs | None
    scales: Mapping[str, Mapping[str, Any]]


FILTER_KEYS = {
    "runtime_min",
    "runtime_max",
    "rating_min",
    "year_min",
    "year_max",
    "spoken_english",
    "sequel",
    "certificate_in",
    "genres_any",
    "genre_also",
    "genres_none",
    "flavour",
    "flavour_none",
    "payoff",
    "bands",
    "score_at_most",
    "score_above",
    "kids_band",
    "sort",
}
OPTION_KEYS = {"say", "reply", "filter", "note", "pail", "image", "not_after"}
QUESTION_KEYS = {"id", "ask", "options", "only_if_pool_over", "presentation", "note", "skip_if_topics", "treat_as"}
KIDS_BANDS = {"little", "family", "older"}
FLAVOUR_SIGNALS = {"keywords_any", "genome_any", "genres_any"}


def _check_keys(block: Mapping[str, Any], allowed: set[str], what: str) -> None:
    extra = set(block) - allowed
    if extra:
        raise TreeError(f"{what} has keys this engine does not read: {sorted(extra)}")


def _opt_float(raw: Mapping[str, Any], key: str) -> float | None:
    return None if key not in raw else float(raw[key])


def _opt_int(raw: Mapping[str, Any], key: str) -> int | None:
    return None if key not in raw else int(raw[key])


def _opt_set(raw: Mapping[str, Any], key: str) -> frozenset[str] | None:
    return None if key not in raw else frozenset(raw[key])


def _genres_any(raw: Mapping[str, Any]) -> frozenset[str] | None:
    genres = _opt_set(raw, "genres_any")
    if "genre_also" in raw:
        genres = (genres or frozenset()) | {raw["genre_also"]}
    return genres


def parse_filter(raw: Mapping[str, Any], what: str) -> Filter:
    _check_keys(raw, FILTER_KEYS, what)
    if raw.get("sequel", False) is not False:
        raise TreeError(f"{what}: 'sequel' may only be false (standalone films only)")
    if raw.get("sort", "rating") != "rating":
        raise TreeError(f"{what}: 'sort' may only be 'rating'")
    if raw.get("kids_band", "little") not in KIDS_BANDS:
        raise TreeError(f"{what}: 'kids_band' must be one of {sorted(KIDS_BANDS)}")
    bands = raw.get("bands")
    return Filter(
        runtime_min=_opt_float(raw, "runtime_min"),
        runtime_max=_opt_float(raw, "runtime_max"),
        rating_min=_opt_float(raw, "rating_min"),
        year_min=_opt_int(raw, "year_min"),
        year_max=_opt_int(raw, "year_max"),
        spoken_english=bool(raw.get("spoken_english", False)),
        standalone="sequel" in raw,
        certificate_in=_opt_set(raw, "certificate_in"),
        genres_any=_genres_any(raw),
        genres_none=_opt_set(raw, "genres_none"),
        flavour=raw.get("flavour"),
        flavour_none=raw.get("flavour_none"),
        payoff=raw.get("payoff"),
        bands=None if bands is None else Bands(str(bands["scale"]), frozenset(bands["in"])),
        score_at_most={k: float(v) for k, v in raw.get("score_at_most", {}).items()},
        score_above={k: float(v) for k, v in raw.get("score_above", {}).items()},
        kids_band=raw.get("kids_band"),
        prefer=raw.get("sort"),
    )


def parse_question(raw: Mapping[str, Any], tree: str) -> Question:
    what = f"tree '{tree}' question '{raw.get('id')}'"
    _check_keys(raw, QUESTION_KEYS, what)
    options = []
    for i, o in enumerate(raw["options"]):
        _check_keys(o, OPTION_KEYS, f"{what} option {i}")
        options.append(
            Option(
                say=str(o["say"]),
                reply=str(o.get("reply", "")),
                filter=parse_filter(o.get("filter", {}), f"{what} option {i}"),
                not_after={q: frozenset(ix) for q, ix in o.get("not_after", {}).items()},
                image=o.get("image"),
            )
        )
    treat_as = raw.get("treat_as")
    if treat_as is not None and not 0 <= int(treat_as) < len(options):
        raise TreeError(f"{what}: treat_as {treat_as} names no option")
    return Question(
        id=str(raw["id"]),
        ask=str(raw["ask"]),
        options=tuple(options),
        only_if_pool_over=raw.get("only_if_pool_over"),
        skip_if_topics=frozenset(int(t) for t in raw.get("skip_if_topics", [])),
        treat_as=None if treat_as is None else int(treat_as),
        presentation=raw.get("presentation"),
    )


def _payoffs(doc: Mapping[str, Any], tree: str) -> Payoffs | None:
    if "payoffs" not in doc:
        return None
    rule = doc.get("payoff_rule", {})
    _check_keys(rule, {"overlap", "thresholds", "no_genome", "note"}, f"tree '{tree}' payoff_rule")
    no_genome = rule.get("no_genome", {})
    _check_keys(no_genome, {"by_genre", "default"}, f"tree '{tree}' payoff_rule.no_genome")
    scores = doc.get("scores", {})
    thresholds = {name: (tuple(scores[t["score"]]), float(t["min"])) for name, t in rule.get("thresholds", {}).items()}
    names = set(doc["payoffs"]) | set(thresholds)
    by_genre = tuple((str(g), str(p)) for g, p in no_genome.get("by_genre", []))
    default = str(no_genome.get("default", "all"))
    unknown = {p for _, p in by_genre} | ({default} - {"all"})
    if unknown - names:
        raise TreeError(f"tree '{tree}': no-genome placement names unknown payoffs {sorted(unknown - names)}")
    overlap = rule.get("overlap")
    return Payoffs(
        standardised={name: tuple(tags) for name, tags in doc["payoffs"].items()},
        overlap=None if overlap is None else float(overlap),
        thresholds=thresholds,
        by_genre=by_genre,
        default=default,
    )


def _check_flavours(tree: str, flavours: Mapping[str, Any], scores: Mapping[str, Any]) -> None:
    for name, spec in flavours.items():
        _check_keys(spec, FLAVOUR_SIGNALS | {"note", "score_at_least", "labelled"}, f"tree '{tree}' flavour '{name}'")
        if spec.get("labelled") is True:
            if set(spec) - {"labelled", "note"}:
                raise TreeError(f"tree '{tree}' flavour '{name}' is labelled, so it takes no signals or floors")
            continue
        floors = spec.get("score_at_least", {})
        if not isinstance(floors, dict) or not all(isinstance(v, int | float) for v in floors.values()):
            raise TreeError(f"tree '{tree}' flavour '{name}' score_at_least must map score names to numbers")
        unknown = set(floors) - set(scores)
        if unknown:
            raise TreeError(f"tree '{tree}' flavour '{name}' score_at_least names undefined scores {sorted(unknown)}")
        if not FLAVOUR_SIGNALS & set(spec):
            raise TreeError(
                f"tree '{tree}' flavour '{name}' names no keywords, genome tags or genres, and is not labelled"
            )


def parse_tree(tree: str, doc: Mapping[str, Any]) -> Tree:
    for key in ("pool", "opening"):
        if key not in doc:
            raise TreeError(f"tree '{tree}' has no '{key}'")
    _check_flavours(tree, doc.get("flavours", {}), doc.get("scores", {}))
    return Tree(
        id=tree,
        pool=str(doc["pool"]),
        opening=str(doc["opening"]),
        questions=tuple(parse_question(q, tree) for q in doc.get("questions", [])),
        scores={name: tuple(tags) for name, tags in doc.get("scores", {}).items()},
        flavours=doc.get("flavours", {}),
        genome_threshold=float(doc.get("genome", {}).get("threshold", 0.6)),
        payoffs=_payoffs(doc, tree),
        scales=doc.get("scales", {}),
    )


def load_trees(dirs: Sequence[Path] = (DATA / "trees", DATA / "modes")) -> dict[str, Tree]:
    """Every tree and mode file, keyed by file name without extension."""
    trees = {}
    for d in dirs:
        for path in sorted(d.glob("*.json")):
            if path.stem in trees:
                raise TreeError(f"two tree or mode files are named '{path.stem}'")
            trees[path.stem] = parse_tree(path.stem, json.loads(path.read_text(encoding="utf-8")))
    return trees
