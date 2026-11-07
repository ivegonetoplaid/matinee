"""Client-neutral selections over Matinee's tree engine, with explicit release-year refinement.

Constraints travel with each request. No conversation or selection state is retained.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, model_validator

from matinee.engine import Answer, Catalog, EngineError, Source, Step, Viewer, first_question, opening_pool, walk
from matinee.trees import Option, Question


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChoiceIn(ClosedModel):
    question: str = Field(min_length=1, max_length=40)
    option: str = Field(min_length=1, max_length=80)


class SelectionIn(ClosedModel):
    source: Source = "held"
    tree: str | None = Field(default=None, min_length=1, max_length=40)
    answers: list[ChoiceIn] = Field(default_factory=list, max_length=12)
    year_min: int | None = Field(default=None, ge=1800, le=3000)
    year_max: int | None = Field(default=None, ge=1800, le=3000)
    seen: list[int] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def valid_range(self) -> SelectionIn:
        if self.year_min is not None and self.year_max is not None and self.year_min > self.year_max:
            raise ValueError("year_min exceeds year_max")
        if any(t <= 0 for t in self.seen):
            raise ValueError("seen identifiers must be positive")
        return self


class ChoiceOut(ClosedModel):
    id: str
    label: str
    count: int


class QuestionOut(ClosedModel):
    id: str
    options: list[ChoiceOut]


@dataclass(frozen=True)
class Selection:
    pool: tuple[int, ...]
    prefer: str | None
    doors: list[ChoiceOut]
    question: QuestionOut | None


def option_id(question: Question, index: int) -> str:
    """A unique flavour name when available, otherwise the tree's stable option index."""
    flavour = question.options[index].filter.flavour
    if flavour and sum(o.filter.flavour == flavour for o in question.options) == 1:
        return flavour
    return f"option_{index}"


def option_label(option: Option) -> str:
    """Use engine filter terms rather than theatrical browser copy."""
    f = option.filter
    if f.flavour:
        return f.flavour
    if f.flavour_none:
        return f"excluding {f.flavour_none}"
    if f.bands:
        return f"{f.bands.scale}: {', '.join(sorted(f.bands.bands))}"
    parts = []
    for field in ("year_min", "year_max", "runtime_min", "runtime_max", "rating_min", "kids_band", "prefer"):
        value = getattr(f, field)
        if value is not None:
            parts.append(f"{field}: {value}")
    # Other filters have no single canonical term; their authored answer remains the label.
    return "; ".join(parts) or option.say.rstrip(".*")


def refine(cat: Catalog, pool: tuple[int, ...], body: SelectionIn) -> tuple[int, ...]:
    """Explicit release bounds exclude unknown years rather than claiming an unknown film is newer."""
    if body.year_min is None and body.year_max is None:
        return pool
    years = cat.table.films.year
    known = years.notna()
    if body.year_min is not None:
        known &= years >= body.year_min
    if body.year_max is not None:
        known &= years <= body.year_max
    kept = {int(t) for t in years.index[known]}
    return tuple(t for t in pool if t in kept)


def translated(cat: Catalog, viewer: Viewer, body: SelectionIn) -> tuple[list[Answer], Step]:
    """Validate each canonical choice against the engine's current next question."""
    if body.tree is None:
        raise EngineError("answers require a tree")
    answers: list[Answer] = []
    step = walk(cat, body.tree, viewer, answers)
    questions = {q.id: q for q in cat.trees[body.tree].questions}
    for choice in body.answers:
        shown = step.question
        if shown is None or shown.id != choice.question:
            raise EngineError("choice does not match the current question")
        q = questions[shown.id]
        indices = [o.index for o in shown.options if option_id(q, o.index) == choice.option]
        if len(indices) != 1:
            raise EngineError("choice is not currently available")
        answers.append(Answer(q.id, indices[0]))
        step = walk(cat, body.tree, viewer, answers)
    return answers, step


def next_question(
    cat: Catalog, viewer: Viewer, body: SelectionIn, answers: list[Answer], step: Step
) -> QuestionOut | None:
    if step.question is None or body.tree is None:
        return None
    q = next(q for q in cat.trees[body.tree].questions if q.id == step.question.id)
    options = []
    for o in step.question.options:
        following = walk(cat, body.tree, viewer, [*answers, Answer(q.id, o.index)])
        count = len(refine(cat, following.pool, body))
        if count:
            options.append(ChoiceOut(id=option_id(q, o.index), label=option_label(q.options[o.index]), count=count))
    return QuestionOut(id=q.id, options=options)


def select(cat: Catalog, viewer: Viewer, body: SelectionIn) -> Selection:
    doors = []
    entire: set[int] = set()
    for door in first_question(cat, viewer):
        pool = refine(cat, tuple(int(t) for t in cat.ids[opening_pool(cat, door.tree, viewer)]), body)
        entire.update(pool)
        if pool:
            doors.append(ChoiceOut(id=door.tree, label=door.label, count=len(pool)))
    if body.tree is None:
        if body.answers:
            raise EngineError("answers require a tree")
        return Selection(tuple(sorted(entire)), None, doors, None)
    answers, step = translated(cat, viewer, body)
    pool = refine(cat, step.pool, body)
    return Selection(pool, step.prefer, doors, next_question(cat, viewer, body, answers, step))
