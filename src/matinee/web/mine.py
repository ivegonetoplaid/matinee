"""Routes for what a profile keeps of its own: its ratings and their short reviews, its hidden films and its runs.

Every route here answers only a device holding the profile, checked by the
store in the same transaction as any write; any other device is refused as
`not_held` (403). No reply carries another profile's records.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from matinee.records import Hidden, Mark, Rating, Records, Run, Walk
from matinee.web.common import device_tokens
from matinee.web.theatre import Theatre
from matinee.web.viewing import AnswerIn, answer_says

# The request's own cap; a short review between this and the store's limit is refused by the store, in words.
REVIEW_CAP = 1000


# A run's key as the page sends it; the store refuses any but 8 to 64 letters, digits, - or _.
RunKey = Field(default=None, max_length=64)


class ScoreIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int
    run: str | None = RunKey  # the run a rating made on the pick names, where the film is marked rated


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review: str | None = Field(default=None, max_length=REVIEW_CAP)


class HideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    length: str = Field(max_length=8)  # 3m, 6m, 1y or good; the store refuses any other, and a missing one is 422
    run: str | None = RunKey  # the run a hide made on the pick names, where the film is marked hid


class HiddenOut(BaseModel):
    """A film the viewer has hidden: the length chosen, when, and when it comes back (null when hidden for good)."""

    tmdb: int
    length: str
    at: str
    until: str | None


class RatingOut(BaseModel):
    """One of the viewer's own ratings: the answer (1 to 5), when it was made, and its short review, if any."""

    tmdb: int
    score: int
    at: str
    review: str | None


class Cleared(BaseModel):
    tmdb: int
    cleared: bool  # False when there was nothing to clear


def rating_out(r: Rating) -> RatingOut:
    return RatingOut(tmdb=r.tmdb, score=r.score, at=r.at, review=r.review)


def offered(theatre: Theatre, tmdb: int) -> int:
    """The film when it is in the current film list; 404 otherwise, as for every other route naming a film."""
    if tmdb not in theatre.showing().catalog.table.films.index:
        raise HTTPException(status_code=404, detail="not_found")
    return tmdb


def add_rating_routes(app: FastAPI, theatre: Theatre, records: Records) -> None:
    @app.get("/api/profiles/{profile_id}/ratings")
    def ratings(profile_id: int, request: Request) -> list[RatingOut]:
        """Every rating the held profile has made, newest first."""
        return [rating_out(r) for r in records.ratings(profile_id, device_tokens(request))]

    @app.put("/api/profiles/{profile_id}/ratings/{tmdb}")
    def rate(profile_id: int, tmdb: int, body: ScoreIn, request: Request) -> RatingOut:
        """Save or change the held profile's answer for a film Matinee offers now."""
        film = offered(theatre, tmdb)
        return rating_out(records.rate(profile_id, film, body.score, device_tokens(request), body.run))

    @app.delete("/api/profiles/{profile_id}/ratings/{tmdb}")
    def unrate(profile_id: int, tmdb: int, request: Request) -> Cleared:
        """Clear the held profile's rating of a film, with its short review."""
        return Cleared(tmdb=tmdb, cleared=records.unrate(profile_id, tmdb, device_tokens(request)))

    @app.put("/api/profiles/{profile_id}/ratings/{tmdb}/review")
    def review(profile_id: int, tmdb: int, body: ReviewIn, request: Request) -> RatingOut:
        """Save, change or clear the short review of a film the held profile has rated."""
        return rating_out(records.review(profile_id, tmdb, body.review, device_tokens(request)))


def hidden_out(h: Hidden) -> HiddenOut:
    return HiddenOut(tmdb=h.tmdb, length=h.length, at=h.at, until=h.until)


def add_hide_routes(app: FastAPI, theatre: Theatre, records: Records) -> None:
    @app.get("/api/profiles/{profile_id}/hidden")
    def hidden(profile_id: int, request: Request) -> list[HiddenOut]:
        """The held profile's hidden films whose hide has not ended, newest first."""
        return [hidden_out(h) for h in records.hidden(profile_id, device_tokens(request))]

    @app.put("/api/profiles/{profile_id}/hidden/{tmdb}")
    def hide(profile_id: int, tmdb: int, body: HideIn, request: Request) -> HiddenOut:
        """Hide a film Matinee offers now from the held profile's picks, for the length chosen."""
        return hidden_out(
            records.hide(profile_id, offered(theatre, tmdb), body.length, device_tokens(request), body.run)
        )

    @app.delete("/api/profiles/{profile_id}/hidden/{tmdb}")
    def unhide(profile_id: int, tmdb: int, request: Request, run: str | None = None) -> Cleared:
        """Bring a hidden film back to the held profile's picks; "Undo" on the pick names its `run`, where the film's
        mark is cleared."""
        return Cleared(tmdb=tmdb, cleared=records.unhide(profile_id, tmdb, device_tokens(request), run))


class ShownIn(BaseModel):
    """A film a run showed, and the walk that reached it: the door (null before one), the answers, and whether
    "Just pick one!" ended them."""

    model_config = ConfigDict(extra="forbid")
    tmdb: int
    tree: str | None = Field(default=None, max_length=40)
    answers: list[AnswerIn] = Field(default=[], max_length=12)
    rushed: bool = False


class KeptOut(BaseModel):
    tmdb: int
    run: str


class AnswerOut(BaseModel):
    question: str
    option: int


class WalkOut(BaseModel):
    """How a film was reached: its door (null before one), the answers as a note takes them, what the door and each
    answer said, and whether "Just pick one!" ended them."""

    tree: str | None
    answers: list[AnswerOut]
    says: list[str]
    rushed: bool


class ShownOut(BaseModel):
    tmdb: int
    mark: Mark | None  # rated, hid or reported on the pick; null when the viewer did none of those
    walk: WalkOut


class RunOut(BaseModel):
    """One kept run: when it began (UTC), its films in the order shown, and its walk, which is its latest film's."""

    began: str
    walk: WalkOut
    films: list[ShownOut]


def walk_of(theatre: Theatre, body: ShownIn) -> Walk:
    """The walk as the run keeps it, with the words the door and each answer said; refuses a door or an answer the
    catalogue does not hold, and answers with no door."""
    cat = theatre.showing().catalog
    pairs = tuple((a.question, a.option) for a in body.answers)
    if body.tree is None:
        if body.answers:
            raise HTTPException(status_code=400, detail="refused")
        return Walk(None, (), (), body.rushed)
    tree = cat.trees.get(body.tree)
    door = next((o.say for o in cat.first_options if o.tree == body.tree), None)
    if tree is None or door is None:
        raise HTTPException(status_code=400, detail="refused")
    return Walk(body.tree, pairs, (door, *answer_says(tree, body.answers)), body.rushed)


def walk_out(walk: Walk) -> WalkOut:
    answers = [AnswerOut(question=q, option=o) for q, o in walk.answers]
    return WalkOut(tree=walk.tree, answers=answers, says=list(walk.says), rushed=walk.rushed)


def run_out(run: Run) -> RunOut:
    films = [ShownOut(tmdb=f.tmdb, mark=f.mark, walk=walk_out(f.walk)) for f in run.films]
    return RunOut(began=run.began, walk=walk_out(run.walk), films=films)


def add_run_routes(app: FastAPI, theatre: Theatre, records: Records) -> None:
    @app.post("/api/profiles/{profile_id}/runs/{run}/films")
    def shown(profile_id: int, run: str, body: ShownIn, request: Request) -> KeptOut:
        """Keep a film the held profile's run showed on screen, with the walk that reached it."""
        film = offered(theatre, body.tmdb)
        records.show(profile_id, run, film, walk_of(theatre, body), device_tokens(request))
        return KeptOut(tmdb=film, run=run)

    @app.get("/api/profiles/{profile_id}/runs")
    def runs(profile_id: int, request: Request) -> list[RunOut]:
        """The held profile's kept runs, newest first."""
        return [run_out(r) for r in records.history(profile_id, device_tokens(request))]
