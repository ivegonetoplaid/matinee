"""Authenticated, stateless HTTP choices and picks for clients other than the website.

An existing profile token authorizes these routes after normal door admission.
The API never changes profiles or substitutes another source when a library fails.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from matinee.engine import Viewer, gentlest
from matinee.pick import Pick, Picker, candidates
from matinee.recommendations import ChoiceOut, ClosedModel, QuestionOut, Selection, SelectionIn, select
from matinee.records import Records
from matinee.store import Profile, Store
from matinee.web.common import problem
from matinee.web.theatre import Theatre
from matinee.web.viewing import DTDD_CREDIT, DTDD_LINK, FilmRef, Seating, film_ref, pick_out


class ProfileOut(ClosedModel):
    id: int
    name: str
    floor: str


class SelectionOut(SelectionIn):
    profile: ProfileOut
    pool_count: int
    available_count: int
    doors: list[ChoiceOut]
    question: QuestionOut | None


class Credit(ClosedModel):
    text: str
    url: str


class PickOut(SelectionOut):
    film: FilmRef | None
    warnings: list[str]
    excluded: list[int]
    credits: list[Credit]


@dataclass(frozen=True)
class ClientContext:
    profile: Profile
    token: str = field(repr=False)


def authenticated(request: Request, store: Store) -> ClientContext | None:
    value = request.headers.get("Authorization", "")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not 16 <= len(token) <= 128:
        return None
    profile = store.holding([token]).get(token)
    if profile is None:
        return None
    return ClientContext(profile, token)


def viewer_for(ctx: ClientContext, seating: Seating, body: SelectionIn, topics_on: bool) -> Viewer:
    p = ctx.profile
    return Viewer(
        source=body.source,
        topics=p.topics if topics_on else frozenset(),
        allowed=seating.allowed(p, [ctx.token]),
        floor=p.floor,
        languages=p.languages,
    )


def output(body: SelectionIn, ctx: ClientContext, selection: Selection) -> SelectionOut:
    return SelectionOut(
        **body.model_dump(),
        profile=ProfileOut(id=ctx.profile.id, name=ctx.profile.name, floor=ctx.profile.floor),
        pool_count=len(selection.pool),
        available_count=len(set(selection.pool) - set(body.seen)),
        doors=selection.doors,
        question=selection.question,
    )


@dataclass(frozen=True)
class ClientService:
    theatre: Theatre
    store: Store
    records: Records
    picker: Picker
    topics_on: bool

    def serve(self, body: SelectionIn, request: Request, picking: bool) -> SelectionOut | PickOut | JSONResponse:
        ctx = authenticated(request, self.store)
        if ctx is None:
            return problem(401, "unauthorized", "A valid Matinee profile token is required.")
        showing = self.theatre.showing()
        if body.source in ("held", "new") and showing.library != "usable":
            return problem(503, "library_unavailable", "The library cannot be verified. No film was selected.")
        cat = showing.catalog
        viewer = viewer_for(ctx, Seating(self.store, self.records, cat), body, self.topics_on)
        selection = select(cat, viewer, body)
        result = output(body, ctx, selection)
        if not picking:
            return result
        films = cat.table.films
        ratings = dict(zip(films.index.tolist(), films.rating.fillna(0.0).tolist(), strict=True))
        pool = candidates(selection.pool, body.seen, ratings, selection.prefer)
        device = hashlib.sha256(ctx.token.encode()).hexdigest()
        drawn = Pick(None, used_up=True)
        if pool:
            drawn = self.picker.pick(pool, viewer.topics, device, gentlest(cat, viewer, pool))
        rendered = pick_out(films, drawn, ticked=viewer.languages)
        warnings = [s for s in (rendered.unchecked, rendered.exhausted, rendered.tired) if s]
        if drawn.film is None and not warnings:
            warnings.append("No unoffered film matches these constraints.")
        if self.theatre.stale:
            warnings.append("The film table is stale and needs rebuilding.")
        film = None
        if drawn.film is not None:
            film = film_ref(films, drawn.film)
        credits = []
        if viewer.topics and pool:
            credits.append(Credit(text=DTDD_CREDIT, url=DTDD_LINK))
        return PickOut(
            **result.model_dump(),
            film=film,
            warnings=warnings,
            excluded=list(drawn.turned),
            credits=credits,
        )


def add_client_routes(app: FastAPI, service: ClientService) -> None:
    @app.post("/api/client/choices", response_model=None)
    def choices(body: SelectionIn, request: Request) -> SelectionOut | PickOut | JSONResponse:
        return service.serve(body, request, picking=False)

    @app.post("/api/client/pick", response_model=None)
    def pick(body: SelectionIn, request: Request) -> SelectionOut | PickOut | JSONResponse:
        return service.serve(body, request, picking=True)
