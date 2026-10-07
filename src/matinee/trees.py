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
    self_destruct: int | None = None  # seconds the reply counts down before it burns away


@dataclass(frozen=True)
class Question:
    id: str
    ask: str
    options: tuple[Option, ...]
    only_if_pool_over: int | None = None
    skip_if_topics: frozenset[int] = frozenset()
    treat_as: int | None = None
    presentation: str | None = None
    footnote: str | None = None  # a line the viewer sees beneath the answers


@dataclass(frozen=True)
class Tree:
    id: str
    pool: str
    opening: str
    questions: tuple[Question, ...]
    scores: Mapping[str, tuple[str, ...]]
    flavours: Mapping[str, Mapping[str, Any]]
    scales: Mapping[str, Mapping[str, Any]]
    apart: str | None = None  # a flavour whose films only the answer naming it offers


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
    "bands",
    "score_at_most",
    "score_above",
    "kids_band",
    "sort",
}
OPTION_KEYS = {"say", "reply", "filter", "note", "pail", "image", "not_after", "self_destruct"}
QUESTION_KEYS = {
    "id",
    "ask",
    "options",
    "only_if_pool_over",
    "presentation",
    "note",
    "footnote",
    "skip_if_topics",
    "treat_as",
}
KIDS_BANDS = {"little", "family", "older"}


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
        bands=None if bands is None else Bands(str(bands["scale"]), frozenset(bands["in"])),
        score_at_most={k: float(v) for k, v in raw.get("score_at_most", {}).items()},
        score_above={k: float(v) for k, v in raw.get("score_above", {}).items()},
        kids_band=raw.get("kids_band"),
        prefer=raw.get("sort"),
    )


def _self_destruct(value: Any, what: str) -> int | None:
    """A countdown of whole seconds, 1 to 9, or None."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 9:
        raise TreeError(f"{what}: self_destruct must be a whole number of seconds from 1 to 9, got {value!r}")
    return value


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
                self_destruct=_self_destruct(o.get("self_destruct"), f"{what} option {i}"),
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
        footnote=raw.get("footnote"),
    )


SOLE_SIGNALS = ("labelled", "specials")  # a flavour takes its films from the labels or the standup specials


def _check_flavours(tree: str, flavours: Mapping[str, Any]) -> None:
    """Each flavour is labelled or the standup specials, never both, and only a labelled one may be always shown."""
    for name, spec in flavours.items():
        what = f"tree '{tree}' flavour '{name}'"
        _check_keys(spec, {"note", "always_shown", *SOLE_SIGNALS}, what)
        sole = [key for key in SOLE_SIGNALS if spec.get(key) is True]
        if len(sole) != 1:
            raise TreeError(f"{what} must be either labelled or the standup specials")
        if "always_shown" in spec and (sole != ["labelled"] or spec["always_shown"] is not True):
            raise TreeError(f"{what}: only a labelled flavour may be always_shown, and only as true")


def parse_tree(tree: str, doc: Mapping[str, Any]) -> Tree:
    for key in ("pool", "opening"):
        if key not in doc:
            raise TreeError(f"tree '{tree}' has no '{key}'")
    _check_flavours(tree, doc.get("flavours", {}))
    apart = doc.get("apart")
    if apart is not None and apart not in doc.get("flavours", {}):
        raise TreeError(f"tree '{tree}' holds apart flavour '{apart}', which it does not define")
    return Tree(
        id=tree,
        pool=str(doc["pool"]),
        opening=str(doc["opening"]),
        questions=tuple(parse_question(q, tree) for q in doc.get("questions", [])),
        scores={name: tuple(tags) for name, tags in doc.get("scores", {}).items()},
        flavours=doc.get("flavours", {}),
        scales=doc.get("scales", {}),
        apart=apart,
    )


def load_trees(dirs: Sequence[Path] = (DATA / "trees",)) -> dict[str, Tree]:
    """Every tree file, keyed by file name without extension."""
    trees = {}
    for d in dirs:
        for path in sorted(d.glob("*.json")):
            if path.stem in trees:
                raise TreeError(f"two tree files are named '{path.stem}'")
            trees[path.stem] = parse_tree(path.stem, json.loads(path.read_text(encoding="utf-8")))
    _one_self_destruct(trees)
    return trees


def _one_self_destruct(trees: Mapping[str, Tree]) -> None:
    """The self-destructing reply is one joke: every answer across the trees that carries it speaks the
    same reply, so it may sit behind each door offering that answer and nowhere else."""
    replies = {
        o.reply: f"{t.id}/{q.id}/{i}"
        for t in trees.values()
        for q in t.questions
        for i, o in enumerate(q.options)
        if o.self_destruct
    }
    if len(replies) > 1:
        raise TreeError(f"only one reply may self-destruct; found {len(replies)}: {', '.join(replies.values())}")
