"""Routes that walk the trees for a viewer, and the DoesTheDogDie topics a viewer steers around.

A viewer is a profile this device holds a token for. Walks and picks run only
under a held profile. The first question's pool may be asked for without one, for
the wall behind the front door. DoesTheDogDie topics are checked at the pick; here
they only decide whether the gore question is asked.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Sequence
from typing import Any, Literal

import numpy as np
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from matinee.dtdd import Dtdd, DtddError
from matinee.engine import Answer, Catalog, Source, Viewer, first_question, gentlest, opening_pool, walk
from matinee.pick import Pick, Picker, candidates
from matinee.store import Note, Profile, Store
from matinee.trees import Tree
from matinee.web.common import COOKIE_AGE_S, Seat, device_tokens, optional_int, problem, seat
from matinee.web.setup import fallback_line
from matinee.web.theatre import UNUSABLE, Showing, Theatre

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
    source: Source | None = None  # the source question's answer; None before one


class PickIn(BaseModel):
    tree: str | None = Field(default=None, max_length=40)
    answers: list[AnswerIn] = Field(default=[], max_length=12)
    viewer: ViewerIn = ViewerIn()
    seen: list[int] = Field(default=[], max_length=200)
    source: Source | None = None


class FirstIn(BaseModel):
    viewer: ViewerIn = ViewerIn()
    source: Source | None = None


class TopicsIn(BaseModel):
    topics: list[int] = Field(default=[], max_length=400)


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
    fallback: str | None = None  # the walk's source answer cannot be kept: the library stopped answering


class FirstOptionOut(BaseModel):
    say: str
    tree: str
    label: str


class SourceOptionOut(BaseModel):
    say: str
    source: Source
    reply: str


class SourceQuestionOut(BaseModel):
    ask: str
    options: list[SourceOptionOut]


class FirstOut(BaseModel):
    lines: list[str]
    name: str | None
    options: list[FirstOptionOut]
    pool: list[int]
    checked: bool  # this viewer's picks are checked against DoesTheDogDie: a key is set and they hold topics
    source: SourceQuestionOut | None = None  # asked first, before the doors; None when it is not asked
    fallback: str | None = None


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


class NoteOut(BaseModel):
    """What the viewer is told once a note is saved: a gold line, then a cream one."""

    lines: list[str]


class NoteIn(BaseModel):
    profile_id: int
    tmdb: int
    tree: str = Field(max_length=40)
    kind: Literal["genre", "kind", "quality"]
    answers: list[AnswerIn] = Field(default=[], max_length=12)
    rushed: bool = False
    comment: str = Field(default="", max_length=500)
    belongs: list[str] = Field(default=[], max_length=32)  # "Not <genre> at all": where the film belongs


class FilmRef(BaseModel):
    tmdb: int
    title: str
    year: int | None


class SwapOut(BaseModel):
    film: FilmRef
    topics: list[str]
    line: str
    reveal: str


class LastOut(BaseModel):
    """A tired pick's last film turned away, the topics it trips, and the two lines that show it."""

    film: FilmRef
    topics: list[str]
    lines: list[str]


class PickOut(BaseModel):
    film: FilmRef | None
    swapped: SwapOut | None
    last: LastOut | None
    unchecked: str | None
    dtdd_item: int | None  # an unchecked film's DoesTheDogDie item, when one is held: its page is /media/<id>
    exhausted: str | None
    tired: str | None
    turned_away: list[int]
    credit: str
    link: str
    fallback: str | None = None


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


def asks_source(showing: Showing) -> bool:
    """The source question is asked while the library can be used, it holds a film, and a film it lacks is offered:
    with either pool empty, every answer would draw from the same films or from none."""
    sources = showing.catalog.sources
    return showing.library == "usable" and bool(sources["held"].any()) and bool(sources["new"].any())


def source_for(answer: Source | None, showing: Showing) -> Source:
    """The films a walk draws from. While the source question is asked: its answer, or before one the library's
    films (the wall behind the front door and the source question). Otherwise every film offered."""
    if not asks_source(showing):
        return "all"
    return answer or "held"


def fallback_for(answer: Source | None, showing: Showing, server: str | None) -> str | None:
    """What the page says when a walk's answer of "held" or "new" cannot be kept because the media server stopped
    answering or turned down the key mid-walk, so the walk goes on among every film offered; None otherwise. An
    answer of "all" loses nothing, and a walk that never asked the source question was told by the setup note."""
    if answer not in ("held", "new") or server is None or showing.library not in UNUSABLE:
        return None
    return fallback_line(server, showing.library == "refused")


def resolve(
    request: Request, store: Store, v: ViewerIn, topics_on: bool, source: Source = "all"
) -> tuple[Viewer, Profile | None]:
    """The engine's viewer within `source`: a held profile's saved topics, or none when no profile is named.

    Without a DoesTheDogDie key (`topics_on` false) a profile's stored topics stay in the store and have no effect.
    """
    if v.profile_id is None:
        return Viewer(source=source), None
    profile = held_profile(request, store, v.profile_id)
    return Viewer(topics=profile.topics if topics_on else frozenset(), source=source), profile


def resolve_held(request: Request, store: Store, v: ViewerIn, topics_on: bool, source: Source = "all") -> Viewer:
    """The engine's viewer for a walk or a pick, which runs only under a profile this device holds; 403 otherwise."""
    viewer, profile = resolve(request, store, v, topics_on, source)
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
    "house": (
        "I've checked a lot of films for everyone here this hour, so this one is unchecked. "
        "Have a look before you play."
    ),
}
EXHAUSTED = "Every film left here trips something on your list. Want to start over?"
USED_UP = "That's every film I've got for those answers. Step back along the trail, or start over."
TIRED = "Three in a row trip your list, starting with one where {topic}. Roll again, or I can show you what I picked."
PICKED = ("Here's what I picked.", "Heads up: it's one where {topic}.")


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


def _swap_out(films: Any, result: Pick) -> SwapOut | None:
    if result.swapped is None:
        return None
    names = [h.name for h in result.swapped_hits]
    return SwapOut(
        film=film_ref(films, result.swapped), topics=names, line=SWAP_LINE.format(topic=names[0]), reveal=REVEAL
    )


def _last_out(films: Any, result: Pick) -> LastOut | None:
    if result.last is None:
        return None
    names = [h.name for h in result.last_hits]
    gold, cream = PICKED
    return LastOut(film=film_ref(films, result.last), topics=names, lines=[gold, cream.format(topic=names[0])])


def pick_out(films: Any, result: Pick, fallback: str | None = None) -> PickOut:
    return PickOut(
        film=None if result.film is None else film_ref(films, result.film),
        swapped=_swap_out(films, result),
        last=_last_out(films, result),
        unchecked=None if result.unchecked is None else UNCHECKED_LINES[result.unchecked],
        dtdd_item=result.item,
        exhausted=_no_film_line(result),
        tired=TIRED.format(topic=result.swapped_hits[0].name) if result.last is not None else None,
        turned_away=list(result.turned),
        credit=DTDD_CREDIT,
        link=DTDD_LINK,
        fallback=fallback,
    )


def add_topic_routes(app: FastAPI, store: Store, dtdd: Dtdd) -> None:
    """DoesTheDogDie's topic list and a profile's saved topics; an installation with no key has neither route."""

    @app.get("/api/topics", response_model=None)
    def topics() -> TopicsOut | JSONResponse:
        """DoesTheDogDie's topics, fetched as the page that offers them opens, never stored."""
        try:
            found = dtdd.topics()
        except DtddError as exc:
            log.warning(
                "DoesTheDogDie's topic list could not be fetched: %s. Meanwhile the list cannot be edited and picks"
                " are still checked against saved topics; check DTDD_API_KEY and that DoesTheDogDie answers.",
                exc,
            )
            return problem(503, "topics_unavailable", TOPICS_UNAVAILABLE)
        return TopicsOut(
            topics=[
                TopicOut(id=t.id, name=t.name, short=t.short, keywords=t.keywords, category=t.category) for t in found
            ],
            credit=DTDD_CREDIT,
            link=DTDD_LINK,
        )

    @app.put("/api/profiles/{profile_id}/topics")
    def save_topics(profile_id: int, body: TopicsIn, request: Request) -> Seat:
        held_profile(request, store, profile_id)
        return seat(store.set_topics(profile_id, body.topics, device_tokens(request)))


def add_viewing_routes(app: FastAPI, theatre: Theatre, store: Store, topics_on: bool, server: str | None) -> None:
    @app.post("/api/first")
    def first(body: FirstIn, request: Request) -> FirstOut:
        """The first screen of a walk: the source question until it is answered (while it is asked), then the doors
        within its answer, and the films the wall shows behind them."""
        showing = theatre.showing()
        cat = showing.catalog
        viewer, profile = resolve(request, store, body.viewer, topics_on, source_for(body.source, showing))
        options = [FirstOptionOut(say=o.say, tree=o.tree, label=o.label) for o in first_question(cat, viewer)]
        question = None
        if body.source is None and asks_source(showing):
            question = SourceQuestionOut(
                ask=cat.source_ask,
                options=[SourceOptionOut(say=o.say, source=o.source, reply=o.reply) for o in cat.source_options],
            )
        return FirstOut(
            lines=list(cat.first_lines),
            name=profile.name if profile else None,
            options=options,
            pool=everything(cat, viewer),
            checked=bool(viewer.topics),
            source=question,
            fallback=fallback_for(body.source, showing, server),
        )

    @app.post("/api/walk")
    def walk_tree(body: WalkIn, request: Request) -> StepOut:
        showing = theatre.showing()
        cat = showing.catalog
        viewer = resolve_held(request, store, body.viewer, topics_on, source_for(body.source, showing))
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
            fallback=fallback_for(body.source, showing, server),
        )


NOTED = ["Thanks. That's gone to whoever runs Matinee.", "If they agree, it moves for everyone."]


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


def check_belongs(cat: Catalog, body: NoteIn) -> None:
    """Where a film belongs is named only on "Not <genre> at all", and only as other trees the catalogue holds."""
    if body.belongs and body.kind != "genre":
        raise HTTPException(status_code=400, detail="refused")
    if set(body.belongs) - set(cat.trees) or body.tree in body.belongs:
        raise HTTPException(status_code=400, detail="refused")


def add_note_routes(app: FastAPI, theatre: Theatre, store: Store) -> None:
    @app.post("/api/notes")
    def note(body: NoteIn, request: Request) -> NoteOut:
        """Keep a viewer's note on a pick for whoever runs Matinee; it changes nothing any viewer is shown."""
        held_profile(request, store, body.profile_id)
        cat = theatre.showing().catalog
        tree = cat.trees.get(body.tree)
        if tree is None or body.tmdb not in cat.table.films.index:
            raise HTTPException(status_code=400, detail="refused")
        check_belongs(cat, body)
        path = tuple(answer_says(tree, body.answers))
        comment, belongs = body.comment.strip(), tuple(body.belongs)
        note = Note(body.profile_id, body.tmdb, body.tree, body.kind, path, body.rushed, comment, belongs)
        store.note(note, device_tokens(request))
        return NoteOut(lines=NOTED)


def pick_pool(cat: Catalog, viewer: Viewer, body: PickIn) -> tuple[list[int], str | None]:
    """The pool a pick draws from and its preference: the walk's end, or before any answer the whole pool."""
    if body.tree is None:
        if body.answers:
            raise HTTPException(status_code=400, detail="refused")
        return everything(cat, viewer), None
    step = walk(cat, body.tree, viewer, [Answer(a.question, a.option) for a in body.answers])
    return list(step.pool), step.prefer


def add_pick_routes(
    app: FastAPI, theatre: Theatre, store: Store, picker: Picker, topics_on: bool, server: str | None
) -> None:
    @app.post("/api/pick")
    def pick(body: PickIn, request: Request, response: Response) -> PickOut:
        """One film from the pool the answers leave, checked against the viewer's topics before it is shown."""
        showing = theatre.showing()
        cat = showing.catalog
        viewer = resolve_held(request, store, body.viewer, topics_on, source_for(body.source, showing))
        left, prefer = pick_pool(cat, viewer, body)
        films = cat.table.films
        ratings = dict(zip(films.index.tolist(), films.rating.fillna(0.0).tolist(), strict=True))
        pool = candidates(left, body.seen, ratings, prefer)
        note = fallback_for(body.source, showing, server)
        if left and not pool:
            return pick_out(films, Pick(None, used_up=True), note)
        device = device_id(request, response) if viewer.topics else ""
        return pick_out(films, picker.pick(pool, viewer.topics, device, gentlest(cat, viewer, pool)), note)
