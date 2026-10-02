"""Routes that walk the trees for a viewer, and the exclusions that shape every walk.

A viewer is a profile this device holds a token for, and its saved exclusions
apply. Walks and picks run only under a held profile. The first question's pool
may be asked for without one, for the wall behind the front door, and then no
exclusion applies. Matinee's own exclusions remove matching films from every
tree and mode through the engine. DoesTheDogDie topics are checked at the pick;
here they only decide whether the gore question is asked.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Literal

import numpy as np
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from matinee.dtdd import Dtdd, DtddError
from matinee.engine import Answer, Catalog, Correction, Viewer, first_question, gentlest, opening_pool, walk
from matinee.pick import Pick, Picker, candidates
from matinee.store import Note, Profile, Store
from matinee.trees import Tree
from matinee.web.common import COOKIE_AGE_S, Seat, device_tokens, optional_int, problem, seat
from matinee.web.theatre import Theatre

log = logging.getLogger("matinee.web")
DTDD_CREDIT = "Powered by DoesTheDogDie.com"
DTDD_LINK = "https://www.doesthedogdie.com"
TOPICS_UNAVAILABLE = "I can't load the list of topics right now."


class ViewerIn(BaseModel):
    profile_id: int | None = None


class AnswerIn(BaseModel):
    question: str = Field(max_length=40)
    option: int = Field(ge=0, le=50)


class WalkIn(BaseModel):
    tree: str = Field(max_length=40)
    answers: list[AnswerIn] = Field(default=[], max_length=12)
    viewer: ViewerIn = ViewerIn()


class PickIn(BaseModel):
    tree: str | None = Field(default=None, max_length=40)
    answers: list[AnswerIn] = Field(default=[], max_length=12)
    viewer: ViewerIn = ViewerIn()
    seen: list[int] = Field(default=[], max_length=200)
    risk: bool = False  # "Just pick one" after a tired pick: nothing is checked or turned away


class FirstIn(BaseModel):
    viewer: ViewerIn = ViewerIn()


class ExclusionsIn(BaseModel):
    topics: list[int] = Field(default=[], max_length=400)
    exclusions: list[str] = Field(default=[], max_length=20)


class OptionOut(BaseModel):
    index: int
    say: str
    image: str | None


class QuestionOut(BaseModel):
    id: str
    ask: str
    options: list[OptionOut]
    presentation: str | None
    footnote: str | None = None


class StepOut(BaseModel):
    tree: str
    line: str
    question: QuestionOut | None
    pool: list[int]
    prefer: str | None
    self_destruct: int | None = None


class FirstOptionOut(BaseModel):
    say: str
    tree: str
    label: str
    correctable: bool


class FirstOut(BaseModel):
    lines: list[str]
    name: str | None
    options: list[FirstOptionOut]
    pool: list[int]


class TopicOut(BaseModel):
    id: int
    name: str
    short: str
    keywords: str
    category: int


class TopicsOut(BaseModel):
    topics: list[TopicOut]
    credit: str
    link: str


class CorrectionIn(BaseModel):
    profile_id: int
    tmdb: int
    remove_from: str = Field(max_length=40)
    add_to: list[str] = Field(default=[], max_length=12)


class CorrectionOut(BaseModel):
    line: str


class NoteIn(BaseModel):
    profile_id: int
    tmdb: int
    tree: str = Field(max_length=40)
    kind: Literal["genre", "kind", "quality"]
    answers: list[AnswerIn] = Field(default=[], max_length=12)
    rushed: bool = False
    comment: str = Field(default="", max_length=500)


class ExclusionOut(BaseModel):
    id: str
    say: str


class FilmRef(BaseModel):
    tmdb: int
    title: str
    year: int | None


class SwapOut(BaseModel):
    film: FilmRef
    topics: list[str]
    line: str
    reveal: str


class PickOut(BaseModel):
    film: FilmRef | None
    swapped: SwapOut | None
    unchecked: str | None
    exhausted: str | None
    tired: str | None
    turned_away: list[int]
    credit: str
    link: str


def everything(cat: Catalog, viewer: Viewer) -> list[int]:
    """Every film some first-question answer offers this viewer before anything is chosen.

    A flavour a tree holds apart (the standup specials) is not among them: only its own answer offers it.
    """
    every = np.zeros(len(cat.ids), dtype=bool)
    for option in first_question(cat, viewer):
        every |= opening_pool(cat, option.tree, viewer)
    return [int(t) for t in cat.ids[every]]


def held_profile(request: Request, store: Store, profile_id: int) -> Profile:
    """The profile if this device holds a token for it; 403 otherwise."""
    for profile in store.holding(device_tokens(request)).values():
        if profile.id == profile_id:
            return profile
    raise HTTPException(status_code=403, detail="refused")


def check_exclusions(theatre: Theatre, names: Sequence[str]) -> None:
    """Refuse an exclusion name Matinee does not define, before it is saved or walked with."""
    if set(names) - set(theatre.showing().catalog.exclusion_names):
        raise HTTPException(status_code=400, detail="refused")


def resolve(request: Request, store: Store, v: ViewerIn) -> tuple[Viewer, Profile | None]:
    """The engine's viewer: a held profile's saved exclusions, or none when no profile is named."""
    if v.profile_id is None:
        return Viewer(), None
    profile = held_profile(request, store, v.profile_id)
    fixes = tuple(Correction(c.tmdb, c.tree, c.direction) for c in store.corrections(profile.id))
    return Viewer(exclusions=profile.exclusions, topics=profile.topics, corrections=fixes), profile


def resolve_held(request: Request, store: Store, v: ViewerIn) -> Viewer:
    """The engine's viewer for a walk or a pick, which runs only under a profile this device holds; 403 otherwise."""
    viewer, profile = resolve(request, store, v)
    if profile is None:
        raise HTTPException(status_code=403, detail="refused")
    return viewer


DEVICE_COOKIE = "matinee_device"
SWAP_LINE = "Oh, I almost recommended a film where {topic}. Let's find you an alternative."
REVEAL = "What were you going to show me?"
UNCHECKED_LINES = {
    "slow": "I couldn't check this one against your list, so have a look before you press play.",
    "no_record": "I couldn't check this one against your list, so have a look before you press play.",
    "cap": "I've checked a lot of films for you this hour, so this one is unchecked. Have a look before you play.",
    "waived": "I didn't check this one against your list, as you asked. Have a look before you press play.",
    "house": (
        "I've checked a lot of films for everyone here this hour, so this one is unchecked. "
        "Have a look before you play."
    ),
}
EXHAUSTED = "Every film left here trips something on your list. Want to start over?"
USED_UP = "That's every film I've got for those answers. Step back along the trail, or start over."
TIRED = (
    "Three in a row trip your list, starting with one where {topic}. Roll again, or I can just pick one "
    "without turning any away. It might have some of what you'd rather skip."
)


def film_ref(table_films: Any, tmdb: int) -> FilmRef:
    row = table_films.loc[tmdb]
    return FilmRef(tmdb=tmdb, title=str(row["name"]), year=optional_int(row.year))


def device_id(request: Request, response: Response) -> str:
    """This device's anonymous id, for the hourly lookup cap only; issued when absent."""
    existing = request.cookies.get(DEVICE_COOKIE, "")
    if 16 <= len(existing) <= 64 and existing.replace("-", "").replace("_", "").isalnum():
        return existing
    fresh = secrets.token_urlsafe(16)
    response.set_cookie(
        DEVICE_COOKIE, fresh, max_age=COOKIE_AGE_S, path="/", secure=True, httponly=True, samesite="lax"
    )
    return fresh


def _no_film_line(result: Pick) -> str | None:
    if result.used_up:
        return USED_UP
    return EXHAUSTED if result.exhausted else None


def pick_out(films: Any, result: Pick) -> PickOut:
    swapped = None
    if result.swapped is not None:
        names = [h.name for h in result.swapped_hits]
        swapped = SwapOut(
            film=film_ref(films, result.swapped), topics=names, line=SWAP_LINE.format(topic=names[0]), reveal=REVEAL
        )
    return PickOut(
        film=None if result.film is None else film_ref(films, result.film),
        swapped=swapped,
        unchecked=None if result.unchecked is None else UNCHECKED_LINES[result.unchecked],
        exhausted=_no_film_line(result),
        tired=TIRED.format(topic=result.swapped_hits[0].name) if result.tired else None,
        turned_away=list(result.turned),
        credit=DTDD_CREDIT,
        link=DTDD_LINK,
    )


def add_viewing_routes(app: FastAPI, theatre: Theatre, store: Store, dtdd: Dtdd) -> None:

    @app.get("/api/topics", response_model=None)
    def topics() -> TopicsOut | JSONResponse:
        """DoesTheDogDie's topics, fetched as the page that offers them opens, never stored."""
        try:
            found = dtdd.topics()
        except DtddError as exc:
            log.warning("topic list: %s", exc)
            return problem(503, "topics_unavailable", TOPICS_UNAVAILABLE)
        return TopicsOut(
            topics=[
                TopicOut(id=t.id, name=t.name, short=t.short, keywords=t.keywords, category=t.category) for t in found
            ],
            credit=DTDD_CREDIT,
            link=DTDD_LINK,
        )

    @app.get("/api/exclusions")
    def exclusions() -> list[ExclusionOut]:
        names = theatre.showing().catalog.exclusion_names
        return [ExclusionOut(id=k, say=v) for k, v in names.items()]

    @app.put("/api/profiles/{profile_id}/exclusions")
    def save_exclusions(profile_id: int, body: ExclusionsIn, request: Request) -> Seat:
        held_profile(request, store, profile_id)
        check_exclusions(theatre, body.exclusions)
        return seat(store.set_exclusions(profile_id, body.topics, body.exclusions))

    @app.post("/api/first")
    def first(body: FirstIn, request: Request) -> FirstOut:
        cat = theatre.showing().catalog
        viewer, profile = resolve(request, store, body.viewer)
        options = [
            FirstOptionOut(say=o.say, tree=o.tree, label=o.label, correctable=not banded(cat.trees[o.tree]))
            for o in first_question(cat, viewer)
        ]
        return FirstOut(
            lines=list(cat.first_lines),
            name=profile.name if profile else None,
            options=options,
            pool=everything(cat, viewer),
        )

    @app.post("/api/walk")
    def walk_tree(body: WalkIn, request: Request) -> StepOut:
        cat = theatre.showing().catalog
        viewer = resolve_held(request, store, body.viewer)
        step = walk(cat, body.tree, viewer, [Answer(a.question, a.option) for a in body.answers])
        question = None
        if step.question is not None:
            q = step.question
            options = [OptionOut(index=o.index, say=o.say, image=o.image) for o in q.options]
            question = QuestionOut(
                id=q.id, ask=q.ask, options=options, presentation=q.presentation, footnote=q.footnote
            )
        return StepOut(
            tree=step.tree,
            line=step.line,
            question=question,
            pool=list(step.pool),
            prefer=step.prefer,
            self_destruct=step.self_destruct,
        )


CORRECTED = "Got it. I'll remember that for you."


def banded(tree: Tree) -> bool:
    """A tree whose answers re-apply a gated age band: a correction cannot add a film to it, so it is refused."""
    return any(o.filter.kids_band is not None for q in tree.questions for o in q.options)


def add_correction_routes(app: FastAPI, theatre: Theatre, store: Store) -> None:
    @app.post("/api/corrections")
    def correct(body: CorrectionIn, request: Request) -> CorrectionOut:
        """One correction for a profile this device holds; a visitor is asked for a name first, by the page."""
        held_profile(request, store, body.profile_id)
        cat = theatre.showing().catalog
        trees = {body.remove_from, *body.add_to}
        if body.tmdb not in cat.table.films.index or trees - set(cat.trees):
            raise HTTPException(status_code=400, detail="refused")
        if any(banded(cat.trees[t]) for t in body.add_to):
            raise HTTPException(status_code=400, detail="refused")
        store.correct(body.profile_id, body.tmdb, body.remove_from, body.add_to)
        return CorrectionOut(line=CORRECTED)


NOTED = "Thanks. I've kept that for whoever tunes Matinee."


def answer_says(tree: Tree, answers: Sequence[AnswerIn]) -> list[str]:
    """What each answer said, in order; an answer the tree does not have is refused."""
    questions = {q.id: q for q in tree.questions}
    says = []
    for a in answers:
        q = questions.get(a.question)
        if q is None or a.option >= len(q.options):
            raise HTTPException(status_code=400, detail="refused")
        says.append(q.options[a.option].say)
    return says


def add_note_routes(app: FastAPI, theatre: Theatre, store: Store) -> None:
    @app.post("/api/notes")
    def note(body: NoteIn, request: Request) -> CorrectionOut:
        """Keep a viewer's note on a pick for review; it changes nothing the viewer is shown."""
        held_profile(request, store, body.profile_id)
        cat = theatre.showing().catalog
        tree = cat.trees.get(body.tree)
        if tree is None or body.tmdb not in cat.table.films.index:
            raise HTTPException(status_code=400, detail="refused")
        path = tuple(answer_says(tree, body.answers))
        store.note(Note(body.profile_id, body.tmdb, body.tree, body.kind, path, body.rushed, body.comment.strip()))
        return CorrectionOut(line=NOTED)


def pick_pool(cat: Catalog, viewer: Viewer, body: PickIn) -> tuple[list[int], str | None]:
    """The pool a pick draws from and its preference: the walk's end, or before any answer the whole pool."""
    if body.tree is None:
        if body.answers:
            raise HTTPException(status_code=400, detail="refused")
        return everything(cat, viewer), None
    step = walk(cat, body.tree, viewer, [Answer(a.question, a.option) for a in body.answers])
    return list(step.pool), step.prefer


def add_pick_routes(app: FastAPI, theatre: Theatre, store: Store, picker: Picker) -> None:
    @app.post("/api/pick")
    def pick(body: PickIn, request: Request, response: Response) -> PickOut:
        """One film from the pool the answers leave, checked against the viewer's topics before it is shown."""
        cat = theatre.showing().catalog
        viewer = resolve_held(request, store, body.viewer)
        left, prefer = pick_pool(cat, viewer, body)
        films = cat.table.films
        ratings = dict(zip(films.index.tolist(), films.rating.fillna(0.0).tolist(), strict=True))
        pool = candidates(left, body.seen, ratings, prefer)
        if left and not pool:
            return pick_out(films, Pick(None, used_up=True))
        topics = frozenset() if body.risk else viewer.topics
        device = device_id(request, response) if topics else ""
        result = picker.pick(pool, topics, device, gentlest(cat, viewer, pool))
        if body.risk and viewer.topics and result.film is not None:
            result = replace(result, unchecked="waived")
        return pick_out(films, result)
