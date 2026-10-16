"""Routes for what a profile keeps of its own: its ratings and their short reviews, its hidden films, its runs, and
its tailoring settings and welcome mark; and the languages the film table holds.

Every route here answers only a device holding the profile, checked by the
store in the same transaction as any write; any other device is refused as
`not_held` (403). No reply carries another profile's records.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from matinee.languages import held
from matinee.records import Hidden, Mark, Rating, Records, Run, Shared, Walk
from matinee.store import Profile, Settings, Store
from matinee.web.common import device_tokens
from matinee.web.theatre import Theatre
from matinee.web.viewing import AnswerIn, FilmRef, answer_says, film_ref

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


class HiddenListedOut(HiddenOut):
    """A hidden film as My profile lists it: with the film's title and year from the film table."""

    title: str
    year: int | None


class RatingOut(BaseModel):
    """One of the viewer's own ratings: the answer (1 to 5), when it was made, and its short review, if any."""

    tmdb: int
    score: int
    at: str
    review: str | None


class RatedOut(RatingOut):
    """A rating as My profile lists it: with the film's title and year from the film table."""

    title: str
    year: int | None


class SharedOut(BaseModel):
    """Another profile's shared rating of a film: its name, avatar (null for initials), answer and short review."""

    name: str
    avatar: str | None
    score: int
    review: str | None


def shared_out(r: Shared) -> SharedOut:
    return SharedOut(name=r.name, avatar=r.avatar, score=r.score, review=r.review)


class Cleared(BaseModel):
    tmdb: int
    cleared: bool  # False when there was nothing to clear


def rating_out(r: Rating) -> RatingOut:
    return RatingOut(tmdb=r.tmdb, score=r.score, at=r.at, review=r.review)


def rated_out(r: Rating, film: FilmRef) -> RatedOut:
    return RatedOut(tmdb=r.tmdb, score=r.score, at=r.at, review=r.review, title=film.title, year=film.year)


def offered(theatre: Theatre, tmdb: int) -> int:
    """The film when it is in the current film list; 404 otherwise, as for every other route naming a film."""
    if tmdb not in theatre.showing().catalog.table.films.index:
        raise HTTPException(status_code=404, detail="not_found")
    return tmdb


def add_rating_routes(app: FastAPI, theatre: Theatre, records: Records) -> None:
    @app.get("/api/profiles/{profile_id}/ratings")
    def ratings(profile_id: int, request: Request) -> list[RatedOut]:
        """Every rating the held profile has made of a film in the current film list, newest first. A rating of a
        film that has left the list stays stored, and is neither shown nor counted."""
        films = theatre.showing().catalog.table.films
        listed = [r for r in records.ratings(profile_id, device_tokens(request)) if r.tmdb in films.index]
        return [rated_out(r, film_ref(films, r.tmdb)) for r in listed]

    @app.get("/api/profiles/{profile_id}/shared/{tmdb}")
    def shared(profile_id: int, tmdb: int, request: Request) -> list[SharedOut]:
        """The household's shared ratings of a film, newest first, for a device holding the asking profile; never
        that profile's own, and nothing of a profile whose sharing is off."""
        return [shared_out(r) for r in records.shared(profile_id, tmdb, device_tokens(request))]

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


def hidden_listed(h: Hidden, film: FilmRef) -> HiddenListedOut:
    return HiddenListedOut(tmdb=h.tmdb, length=h.length, at=h.at, until=h.until, title=film.title, year=film.year)


def add_hide_routes(app: FastAPI, theatre: Theatre, records: Records) -> None:
    @app.get("/api/profiles/{profile_id}/hidden")
    def hidden(profile_id: int, request: Request) -> list[HiddenListedOut]:
        """The held profile's hidden films in the current film list whose hide has not ended, newest first. A hide of
        a film that has left the list stays stored, and is neither shown nor counted."""
        films = theatre.showing().catalog.table.films
        listed = [h for h in records.hidden(profile_id, device_tokens(request)) if h.tmdb in films.index]
        return [hidden_listed(h, film_ref(films, h.tmdb)) for h in listed]

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
    title: str
    year: int | None
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


def run_out(run: Run, table_films: Any) -> RunOut | None:
    """A kept run with each film's title and year; a film that has left the film table stays stored and is not
    shown, and a run left with no film is not shown either."""
    films = [
        ShownOut(**film_ref(table_films, f.tmdb).model_dump(), mark=f.mark, walk=walk_out(f.walk))
        for f in run.films
        if f.tmdb in table_films.index
    ]
    return RunOut(began=run.began, walk=walk_out(run.walk), films=films) if films else None


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
        films = theatre.showing().catalog.table.films
        kept = (run_out(r, films) for r in records.history(profile_id, device_tokens(request)))
        return [r for r in kept if r is not None]


class SettingsIn(BaseModel):
    """A change to the viewer's settings; a field left out (or null) stays as it is. "Any language" is
    `languages: []`, which clears every tick."""

    model_config = ConfigDict(extra="forbid")
    floor: str | None = Field(default=None, max_length=20)
    languages: list[str] | None = Field(default=None, max_length=200)
    rated_out: int | None = None
    sharing: bool | None = None


class SettingsOut(BaseModel):
    """The viewer's tailoring settings and whether they have seen this feature's welcome. `languages` empty means
    any language; `rated_out` 0 keeps every rated film in the picks; `topics` are the DoesTheDogDie topics steered
    around."""

    topics: list[int]
    floor: str
    languages: list[str]
    rated_out: int
    sharing: bool
    welcomed: bool


class LanguageOut(BaseModel):
    code: str  # the two-letter code TMDB gives a film's original language
    films: int


def settings_out(p: Profile) -> SettingsOut:
    return SettingsOut(
        topics=sorted(p.topics),
        floor=p.floor,
        languages=sorted(p.languages),
        rated_out=p.rated_out,
        sharing=p.sharing,
        welcomed=p.welcomed,
    )


def add_settings_routes(app: FastAPI, theatre: Theatre, store: Store) -> None:
    def known() -> frozenset[str]:
        return frozenset(code for code, _ in held(theatre.showing().catalog.table.films))

    @app.get("/api/languages")
    def languages() -> list[LanguageOut]:
        """Every language the film table holds, with its count of films, most first. The page names each one and
        puts the browser's own language first."""
        return [LanguageOut(code=code, films=n) for code, n in held(theatre.showing().catalog.table.films)]

    @app.get("/api/profiles/{profile_id}/settings")
    def settings(profile_id: int, request: Request) -> SettingsOut:
        """The held profile's settings and welcome mark."""
        return settings_out(store.profile(profile_id, device_tokens(request)))

    @app.put("/api/profiles/{profile_id}/settings")
    def change(profile_id: int, body: SettingsIn, request: Request) -> SettingsOut:
        """Change the held profile's settings; each takes effect on its next request."""
        languages = None if body.languages is None else frozenset(body.languages)
        wanted = Settings(floor=body.floor, languages=languages, rated_out=body.rated_out, sharing=body.sharing)
        offered = frozenset() if languages is None else known()  # the catalogue is read only for a language change
        return settings_out(store.set_settings(profile_id, wanted, offered, device_tokens(request)))

    @app.post("/api/profiles/{profile_id}/welcomed")
    def welcomed(profile_id: int, request: Request) -> SettingsOut:
        """Mark the held profile as having seen this feature's welcome."""
        return settings_out(store.welcome(profile_id, device_tokens(request)))
