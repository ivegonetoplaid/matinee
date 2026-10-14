"""A viewer's settings and hidden films narrowing every pool: the rating floor by door place, the language check,
hidden and rated films, and the doors offered before any door."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from matinee.engine import (
    FLOOR_EDGES,
    VOTE_FLOOR,
    Answer,
    Catalog,
    EngineError,
    Viewer,
    allowed_films,
    base_pool,
    first_question,
    load_catalog,
    places,
    walk,
    walk_ends,
    walk_kept,
)
from matinee.ranks import BANDS, band, rank_among
from matinee.reference import Reference
from matinee.store import FLOORS
from matinee.table import FilmTable
from matinee.web.viewing import USED_UP, AnswerIn, PickIn, everything, pick_pool
from test_engine import TREE, make_table, reference, write_data
from test_web_library import make_world


def ranked_table(seed: int = 7) -> FilmTable:
    """The engine's films with TMDB scores; every fifth film under the vote floor and every seventh unscored."""
    table = make_table()
    rng = np.random.default_rng(seed)
    n = len(table.films)
    scores = np.round(rng.uniform(4, 9, n), 1)  # rounded, so films tie
    table.films["tmdb_rating"] = [np.nan if i % 7 == 6 else s for i, s in enumerate(scores)]
    table.films["vote_count"] = pd.array(
        [VOTE_FLOOR - 1 if i % 5 == 4 else VOTE_FLOOR for i in range(n)], dtype="Int64"
    )
    return table


@pytest.fixture
def cat(tmp_path: Path) -> Catalog:
    return load_catalog(ranked_table(), write_data(tmp_path), reference())


@pytest.fixture
def apart(tmp_path: Path) -> Catalog:
    """The ranked films with the ten best-scored ones moved out of the west door, so its door holds fewer films than
    the table and a film's place in the door differs from its place among every film."""
    table = ranked_table()
    best = table.films.tmdb_rating.sort_values(ascending=False).index[:10]
    table.films.loc[best, "genres"] = pd.Series([frozenset({"Comedy"})] * 10, index=best)
    return load_catalog(table, write_data(tmp_path), reference())


def test_a_films_door_place_reads_as_the_band_the_pick_shows(apart: Catalog) -> None:
    cat = apart
    films = cat.table.films
    among = cat.pools[cat.trees["west"].pool]
    assert (~among).any()  # the door holds fewer films than the table
    place = places(films, among)
    for i, tmdb in enumerate(cat.ids):
        shown = rank_among(films, among, int(tmdb), None) if among[i] else None
        assert (band(place[i], None) if not np.isnan(place[i]) else None) == shown, tmdb
    assert np.isnan(place[~among]).all()


def test_each_floor_ends_at_a_rank_band_edge() -> None:
    edges = [edge for edge, _, _ in BANDS]
    assert {
        "anything": 1.0,
        "above_bottom": edges[5],  # keeps out "Bringing up the rear"
        "middle": edges[4],  # keeps out the bottom 40%
        "above_middle": edges[3],  # keeps only the top 40%
        "well_liked": edges[2],  # keeps only the top 25%
    } == FLOOR_EDGES


def test_the_floor_ranks_a_film_among_its_own_doors_films(apart: Catalog) -> None:
    among = apart.pools[apart.trees["west"].pool]
    door, table = places(apart.table.films, among), places(apart.table.films, np.ones(len(among), dtype=bool))
    kept = base_pool(apart, "west", Viewer(floor="well_liked"))
    assert (kept == (among & (np.isnan(door) | (door <= 0.25)))).all()
    assert (kept != (among & (np.isnan(table) | (table <= 0.25)))).any()  # ranked among every film, fewer would stay


def test_the_floor_names_are_the_ones_the_store_keeps() -> None:
    assert tuple(FLOOR_EDGES) == FLOORS


def test_the_floor_keeps_out_films_below_its_edge_and_never_one_with_no_place(cat: Catalog) -> None:
    place = places(cat.table.films, cat.pools[cat.trees["west"].pool])
    every = base_pool(cat, "west", Viewer())
    for floor, edge in FLOOR_EDGES.items():
        kept = base_pool(cat, "west", Viewer(floor=floor))
        expected = every & (np.isnan(place) | (place <= edge))
        assert (kept == expected).all(), floor
    unplaced = every & np.isnan(place)
    assert unplaced.any() and (base_pool(cat, "west", Viewer(floor="well_liked")) & unplaced).sum() == unplaced.sum()
    on_edge = cat.places["west"].copy()
    on_edge[np.flatnonzero(every)[0]] = 0.25  # exactly on the edge: kept
    cat.places["west"] = on_edge
    assert base_pool(cat, "west", Viewer(floor="well_liked"))[np.flatnonzero(every)[0]]


def two_doors(tmp_path: Path) -> Catalog:
    """West and east, two doors onto the same films."""
    root = write_data(tmp_path)
    (root / "trees" / "east.json").write_text(json.dumps(TREE))
    first = json.loads((root / "first_question.json").read_text())
    first["options"] = [
        {"say": "Cowboys.", "tree": "west", "label": "Western"},
        {"say": "East.", "tree": "east", "label": "East"},
    ]
    (root / "first_question.json").write_text(json.dumps(first))
    west = reference().trees["west"]
    return load_catalog(ranked_table(), root, Reference("test", {"west": west, "east": west}))


def test_a_film_passing_the_floor_in_one_of_its_doors_stays_before_any_door(tmp_path: Path) -> None:
    cat = two_doors(tmp_path)
    pool = base_pool(cat, "west", Viewer())
    film = np.flatnonzero(pool)[0]
    low, high = np.full(len(cat.ids), 0.1), np.full(len(cat.ids), 0.1)
    low[film], high[film] = 0.95, 0.05  # bottom of the west door, top of the east one
    cat.places.update(west=low, east=high)
    viewer = Viewer(floor="well_liked")
    assert not base_pool(cat, "west", viewer)[film] and base_pool(cat, "east", viewer)[film]
    assert int(cat.ids[film]) in everything(cat, viewer)
    cat.places.update(west=high, east=low)  # the other way round: the first door keeps it
    assert int(cat.ids[film]) in everything(cat, viewer)
    cat.places.update(west=low, east=np.full(len(cat.ids), 0.9))  # nothing behind east passes: east is not offered
    assert [o.tree for o in first_question(cat, viewer)] == ["west"]
    assert int(cat.ids[film]) not in everything(cat, viewer)


def film_frame(rows: list[tuple[int, str | None, frozenset[str] | None]]) -> FilmTable:
    frame = pd.DataFrame(rows, columns=["tmdb", "language", "audio"]).set_index("tmdb")
    return FilmTable(frame, (), np.zeros((len(rows), 0), dtype=np.float32), pd.Timestamp.now(tz="UTC"), None, "")


def test_a_ticked_language_keeps_a_film_by_its_copys_tagged_tracks_else_by_its_original_language() -> None:
    table = film_frame(
        [
            (1, "en", frozenset({"fr"})),  # an English film with a French dub only
            (2, "fr", None),  # no copy, or untagged: its original language decides
            (3, "en", frozenset({"en", "fr"})),
            (4, None, None),  # no known language: matches nothing
            (5, "ja", frozenset({"en"})),
        ]
    )

    def kept(languages: set[str], out: set[int] = set()) -> list[int]:  # noqa: B006
        mask = allowed_films(table, frozenset(out), frozenset(languages))
        return list(table.films.index) if mask is None else [int(t) for t in table.films.index[mask]]

    assert kept({"fr"}) == [1, 2, 3]
    assert kept({"en"}) == [3, 5]
    assert kept({"ja"}) == []
    assert kept({"en"}, out={3}) == [5]
    assert kept(set(), out={1, 4}) == [2, 3, 5]
    assert allowed_films(table, frozenset(), frozenset()) is None  # nothing narrows: the pools Matinee shows today


def test_narrowing_one_viewer_never_changes_the_shared_masks(cat: Catalog) -> None:
    masks, small = copy.deepcopy(cat.masks), copy.deepcopy(cat.small)
    allowed = np.zeros(len(cat.ids), dtype=bool)
    allowed[:20] = True
    narrowed = Viewer(allowed=allowed, floor="middle")
    walk(cat, "west", narrowed, [])
    everything(cat, narrowed)
    assert cat.masks.keys() == masks.keys() and all((cat.masks[k] == masks[k]).all() for k in masks)
    assert cat.small == small


@pytest.fixture
def world(tmp_path: Path) -> tuple[TestClient, Any]:
    """The web fixture with films 1 to 20 ranked (film 1 lowest), and a held profile."""
    client, _, _, theatre = make_world(tmp_path, scores={t: 4.0 + t / 4 for t in range(1, 21)})
    return client, theatre


def first_pool(client: TestClient, viewer: dict[str, Any]) -> set[int]:
    return set(client.post("/api/first", json={"viewer": viewer, "source": "all"}).json()["pool"])


def walk_pool(client: TestClient, viewer: dict[str, Any]) -> set[int]:
    return set(client.post("/api/walk", json={"tree": "west", "viewer": viewer, "source": "all"}).json()["pool"])


def test_a_viewer_at_every_default_sees_exactly_the_pools_matinee_shows_today(world: Any) -> None:
    client, _ = world
    pid = client.post("/api/profiles", json={"name": "Ada"}).json()["id"]
    assert first_pool(client, {"profile_id": pid}) == first_pool(client, {})


def test_a_hide_a_rating_and_each_setting_narrow_the_next_request(world: Any) -> None:
    client, theatre = world
    pid = client.post("/api/profiles", json={"name": "Ada"}).json()["id"]
    me = {"profile_id": pid}
    every = first_pool(client, me)
    assert {5, 6, 7} <= every
    client.put(f"/api/profiles/{pid}/hidden/5", json={"length": "3m"})
    client.put(f"/api/profiles/{pid}/ratings/6", json={"score": 1})  # "Hated it" stays out by default
    client.put(f"/api/profiles/{pid}/ratings/7", json={"score": 2})
    assert first_pool(client, me) == every - {5, 6}
    assert 5 not in walk_pool(client, me) and 6 not in walk_pool(client, me)
    client.put(f"/api/profiles/{pid}/settings", json={"rated_out": 0})
    assert first_pool(client, me) == every - {5}
    client.put(f"/api/profiles/{pid}/settings", json={"rated_out": 5})
    assert first_pool(client, me) == every - {5, 6, 7}
    client.delete(f"/api/profiles/{pid}/hidden/5")
    client.put(f"/api/profiles/{pid}/settings", json={"rated_out": 1})
    assert first_pool(client, me) == every - {6}
    films = theatre.showing().catalog.table.films
    client.put(f"/api/profiles/{pid}/settings", json={"languages": ["fr"]})
    french = {int(t) for t in films.index[films.language == "fr"]}
    assert first_pool(client, me) == (every - {6}) & french
    client.put(f"/api/profiles/{pid}/settings", json={"languages": [], "floor": "well_liked"})
    narrowed = first_pool(client, me)
    unranked = {t for t in every if t > 20}
    assert unranked - {6} <= narrowed < every - {6}  # every film with no rank stays; low ranks go
    assert not {1, 2, 3} & narrowed and {20, 19} <= narrowed


def test_one_viewers_settings_never_reach_another(world: Any) -> None:
    client, _ = world
    ada = client.post("/api/profiles", json={"name": "Ada"}).json()["id"]
    bo = client.post("/api/profiles", json={"name": "Bo"}).json()["id"]
    before = first_pool(client, {"profile_id": bo})
    client.put(f"/api/profiles/{ada}/hidden/20", json={"length": "good"})
    client.put(f"/api/profiles/{ada}/settings", json={"floor": "middle", "languages": ["fr"]})
    first_pool(client, {"profile_id": ada})  # her narrowed pool is drawn first, and the door ranks with it
    assert first_pool(client, {"profile_id": bo}) == before
    client.put(f"/api/profiles/{bo}/settings", json={"floor": "middle"})
    after = first_pool(client, {"profile_id": bo})
    assert not set(range(1, 9)) & after and set(range(9, 21)) <= after  # his bands rank every film of the door


def test_the_pick_draws_from_the_narrowed_pool(world: Any) -> None:
    client, _ = world
    pid = client.post("/api/profiles", json={"name": "Ada"}).json()["id"]
    me = {"profile_id": pid}
    for t in sorted(first_pool(client, me) - {10}):
        client.put(f"/api/profiles/{pid}/hidden/{t}", json={"length": "good"})
    for tree in (None, "west"):
        picked = client.post("/api/pick", json={"tree": tree, "viewer": me, "source": "all"}).json()
        assert picked["film"]["tmdb"] == 10, tree


def test_settings_that_leave_nothing_offer_no_door_and_count_what_they_left_out(world: Any) -> None:
    client, _ = world
    pid = client.post("/api/profiles", json={"name": "Ada"}).json()["id"]
    every = first_pool(client, {"profile_id": pid})
    client.put(f"/api/profiles/{pid}/settings", json={"floor": "well_liked"})
    for t in sorted(every)[:-1]:
        client.put(f"/api/profiles/{pid}/hidden/{t}", json={"length": "good"})
    one_left = client.post("/api/first", json={"viewer": {"profile_id": pid}, "source": "all"}).json()
    assert one_left["options"] and one_left["unsettled"] is None  # a pool holding any film never says it
    client.put(f"/api/profiles/{pid}/hidden/{max(every)}", json={"length": "good"})
    first = client.post("/api/first", json={"viewer": {"profile_id": pid}, "source": "all"}).json()
    assert first["options"] == [] and first["pool"] == []
    assert first["unsettled"] == len(every)  # counted with no setting applied and nothing hidden
    picked = client.post("/api/pick", json={"viewer": {"profile_id": pid}, "source": "all"}).json()
    assert picked["film"] is None and picked["exhausted"] == USED_UP  # never "trips something on your list"


def test_the_narrowing_only_ever_narrows_the_doors_own_pool(cat: Catalog) -> None:
    everyone = np.ones(len(cat.ids), dtype=bool)
    none_held = Viewer(source="held", allowed=everyone, floor="well_liked")  # the fixture's library holds no film
    assert not base_pool(cat, "west", none_held).any()
    assert (base_pool(cat, "west", Viewer(allowed=everyone)) == base_pool(cat, "west", Viewer())).all()


def test_a_pick_after_a_hide_never_refuses_answers_the_narrowing_no_longer_asks(cat: Catalog) -> None:
    """A hide can bring a pool under a question's stop, so the answers given no longer fit the narrowed walk; the
    pick still draws from them, and only from films the viewer's narrowing allows."""
    found = 0
    for answers, step in walk_ends(cat, "west"):
        if len(answers) < 2:
            continue
        for tmdb in step.pool:
            allowed = cat.ids != tmdb
            viewer = Viewer(allowed=allowed)
            try:
                walk(cat, "west", viewer, answers)
            except EngineError:
                kept = walk_kept(cat, "west", viewer, answers)
                assert tmdb not in kept.pool and set(kept.pool) <= set(step.pool)
                found += 1
    assert found  # the fixture holds such a walk
    with pytest.raises(EngineError):  # with no narrowing, answers that do not fit are still refused
        walk_kept(cat, "west", Viewer(), [Answer("era", 99)])


def test_after_a_hide_the_pick_draws_from_the_answers_given_and_the_rest_of_the_narrowed_pool(cat: Catalog) -> None:
    answers = [Answer("era", 3), Answer("gore", 1), Answer("kind", 2)]
    viewer = Viewer(allowed=cat.ids != 21, floor="above_bottom")  # film 21 just hidden
    with pytest.raises(EngineError):  # one film fewer changes which questions the narrowed walk asks
        walk(cat, "west", viewer, answers)
    plain = walk(cat, "west", Viewer(), answers)
    allowed = {int(t) for t in cat.ids[base_pool(cat, "west", viewer)]}
    kept = walk_kept(cat, "west", viewer, answers)
    assert kept.pool == tuple(t for t in plain.pool if t in allowed)
    assert len(kept.pool) == 15 and 21 not in kept.pool  # a pool to pick from, not an empty one
    body = PickIn(tree="west", answers=[AnswerIn(question=a.question, option=a.option) for a in answers])
    assert pick_pool(cat, viewer, body)[0] == list(kept.pool)  # the pick route draws from it
