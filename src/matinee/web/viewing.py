"""Routes that walk the trees for a viewer, and the exclusions that shape every walk.

A viewer is either a profile this device holds a token for, whose saved
exclusions apply, or a visitor whose exclusions arrive with each request from the
page and end with the visit. Matinee's own exclusions remove matching films from
every tree and mode through the engine. DoesTheDogDie topics are checked at the
pick; here they only decide whether the gore question is asked.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from matinee.dtdd import Dtdd, DtddError
from matinee.engine import Answer, Viewer, first_question, walk
from matinee.pick import Pick, Picker, candidates
from matinee.store import Profile, Store
from matinee.web.common import COOKIE_AGE_S, Seat, device_tokens, optional_int, problem, seat
from matinee.web.theatre import Theatre

log = logging.getLogger("matinee.web")
DTDD_CREDIT = "Powered by DoesTheDogDie.com"
DTDD_LINK = "https://www.doesthedogdie.com"
TOPICS_UNAVAILABLE = "I can't load the list of topics right now."


class ViewerIn(BaseModel):
    profile_id: int | None = None
    topics: list[int] = Field(default=[], max_length=400)
    exclusions: list[str] = Field(default=[], max_length=20)


class AnswerIn(BaseModel):
    question: str = Field(max_length=40)
    option: int = Field(ge=0, le=50)


class WalkIn(BaseModel):
    tree: str = Field(max_length=40)
    answers: list[AnswerIn] = Field(default=[], max_length=12)
    viewer: ViewerIn = ViewerIn()


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


class StepOut(BaseModel):
    tree: str
    line: str
    question: QuestionOut | None
    pool: list[int]
    prefer: str | None


class FirstOptionOut(BaseModel):
    say: str
    tree: str


class FirstOut(BaseModel):
    lines: list[str]
    name: str | None
    options: list[FirstOptionOut]


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


class ExclusionOut(BaseModel):
    id: str
    say: str


class PickIn(WalkIn):
    seen: list[int] = Field(default=[], max_length=200)


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
    credit: str
    link: str


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
    """The engine's viewer: a held profile's saved exclusions, or this visit's."""
    if v.profile_id is not None:
        profile = held_profile(request, store, v.profile_id)
        return Viewer(exclusions=profile.exclusions, topics=profile.topics), profile
    return Viewer(exclusions=frozenset(v.exclusions), topics=frozenset(v.topics)), None


DEVICE_COOKIE = "matinee_device"
SWAP_LINE = "Oh, I almost recommended a film where {topic}. Let's find you an alternative."
REVEAL = "What were you going to show me?"
UNCHECKED_LINES = {
    "slow": "I couldn't check this one against your list, so have a look before you press play.",
    "no_record": "I couldn't check this one against your list, so have a look before you press play.",
    "cap": "I've checked a lot of films for you this hour, so this one is unchecked. Have a look before you play.",
}
EXHAUSTED = "Every film left here trips something on your list. Want to start over?"


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
        exhausted=EXHAUSTED if result.exhausted else None,
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
        options = [FirstOptionOut(say=o.say, tree=o.tree) for o in first_question(cat, viewer)]
        return FirstOut(lines=list(cat.first_lines), name=profile.name if profile else None, options=options)

    @app.post("/api/walk")
    def walk_tree(body: WalkIn, request: Request) -> StepOut:
        cat = theatre.showing().catalog
        viewer, _ = resolve(request, store, body.viewer)
        step = walk(cat, body.tree, viewer, [Answer(a.question, a.option) for a in body.answers])
        question = None
        if step.question is not None:
            q = step.question
            options = [OptionOut(index=o.index, say=o.say, image=o.image) for o in q.options]
            question = QuestionOut(id=q.id, ask=q.ask, options=options, presentation=q.presentation)
        return StepOut(tree=step.tree, line=step.line, question=question, pool=list(step.pool), prefer=step.prefer)


def add_pick_routes(app: FastAPI, theatre: Theatre, store: Store, picker: Picker) -> None:
    @app.post("/api/pick")
    def pick(body: PickIn, request: Request, response: Response) -> PickOut:
        """One film from the pool the answers leave, checked against the viewer's topics before it is shown."""
        cat = theatre.showing().catalog
        viewer, _ = resolve(request, store, body.viewer)
        step = walk(cat, body.tree, viewer, [Answer(a.question, a.option) for a in body.answers])
        films = cat.table.films
        ratings = dict(zip(films.index.tolist(), films.rating.fillna(0.0).tolist(), strict=True))
        pool = candidates(step.pool, body.seen, ratings, step.prefer)
        device = device_id(request, response) if viewer.topics else ""
        return pick_out(films, picker.pick(pool, viewer.topics, device))
