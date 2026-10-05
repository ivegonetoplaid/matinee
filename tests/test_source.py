"""The source question: which films a walk draws from, asked first while the library can be used."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from matinee.engine import KIND_MIN_FILMS, Answer, Catalog, Viewer, first_question, load_catalog, walk
from matinee.labels import Labels, TreeLabels
from matinee.store import Store
from matinee.table import write_table
from matinee.web.app import create_app
from matinee.web.config import Config
from matinee.web.theatre import LIVE_TTL, Theatre
from test_engine import TREE, make_table, reference, write_data
from test_web_library import SERVER, Clock, FakeLibrary, film_table, seat_for

HELD = range(1, 21)  # the library holds films 1-20 of the table's 40


def catalog(tmp_path: Path, tree: dict[str, Any] | None = None, labels: Labels | None = None) -> Catalog:
    data = write_data(tmp_path / "data", tree)
    table = make_table()
    table.films["held"] = [t in HELD for t in table.films.index]
    return load_catalog(table, data, reference(), labels)


def test_each_source_bounds_the_walk_from_its_first_question(tmp_path: Path) -> None:
    cat = catalog(tmp_path)
    pools = {s: set(walk(cat, "west", Viewer(source=s), []).pool) for s in ("held", "new", "all")}
    assert pools["held"] and pools["held"] <= set(HELD)
    assert pools["new"] and not pools["new"] & set(HELD)
    assert pools["all"] == pools["held"] | pools["new"]  # a film in both appears once
    deeper = walk(cat, "west", Viewer(source="new"), [Answer("era", 1)])
    assert set(deeper.pool) <= pools["new"]
    assert [o.tree for o in first_question(cat, Viewer(source="held"))] == ["west"]


def test_a_kind_shows_or_hides_by_its_count_in_the_chosen_source(tmp_path: Path) -> None:
    tree = json.loads(json.dumps(TREE))
    tree["questions"].insert(
        0,
        {
            "id": "who",
            "ask": "heroes?",
            "options": [
                {"say": "heroes.", "reply": "", "filter": {"flavour": "heroic"}},
                {"say": "anyone.", "reply": "", "filter": {}},
            ],
        },
    )
    heroes = range(1, KIND_MIN_FILMS + 6)  # 35 heroic films: 20 held, 15 not
    labels = Labels({"west": TreeLabels({t: frozenset({"heroic"}) for t in heroes})})
    cat = catalog(tmp_path, tree, labels)

    def says(source: str) -> list[str]:
        step = walk(cat, "west", Viewer(source=source), [])  # type: ignore[arg-type]
        assert step.question is not None
        return [o.say for o in step.question.options]

    assert says("all") == ["heroes.", "anyone."]
    assert says("held") == ["anyone."] and says("new") == ["anyone."]  # under the bar in either alone


WEST = Labels({"west": TreeLabels({t: frozenset() for t in range(1, 41)})})  # every film behind the one door


def site(tmp_path: Path, library: FakeLibrary | None) -> tuple[TestClient, Clock]:
    """A site whose library holds `library.held`, and whose labels name film 40 beside the library's films."""
    data = write_data(tmp_path / "data")
    stored = film_table()
    stored.films["tmdb_title"] = [f"TMDB {t}" for t in stored.films.index]
    write_table(stored, tmp_path / "films.sqlite")
    clock = Clock()
    listed = frozenset({40}) if library is not None else frozenset(range(1, 41))
    theatre = Theatre(
        library,
        tmp_path / "films.sqlite",
        clock=clock,
        catalog_of=lambda t: load_catalog(t, data, reference(), WEST),
        listed=listed,
    )
    config = Config(None if library is None else SERVER, tmp_path, None, None)
    app = create_app(config, theatre, Store(tmp_path / "s.sqlite"), None)
    return TestClient(app, base_url="https://testserver"), clock


def test_the_source_question_is_asked_first_in_its_order_and_bounds_every_later_answer(tmp_path: Path) -> None:
    client, _ = site(tmp_path, FakeLibrary(held=list(HELD)))
    viewer = seat_for(client)
    first = client.post("/api/first", json={"viewer": viewer}).json()
    assert first["source"]["ask"] == "from where?"
    assert [o["source"] for o in first["source"]["options"]] == ["held", "new", "all"]
    assert first["pool"] and set(first["pool"]) <= set(HELD)  # the wall behind the question shows the library
    new = client.post("/api/first", json={"viewer": viewer, "source": "new"}).json()
    assert new["source"] is None and set(new["pool"]) == {40}
    walked = client.post("/api/walk", json={"tree": "west", "viewer": viewer, "source": "held"}).json()
    assert walked["pool"] and set(walked["pool"]) <= set(HELD)
    picked = client.post("/api/pick", json={"viewer": viewer, "source": "new"}).json()
    assert picked["film"]["tmdb"] == 40  # "Just pick one!" draws from the chosen source too
    front = client.post("/api/first", json={"viewer": {}}).json()
    assert set(front["pool"]) <= set(HELD)  # the front door's wall shows the library too


def test_while_the_library_cannot_be_used_no_source_is_asked_or_obeyed(tmp_path: Path) -> None:
    library = FakeLibrary(held=list(HELD))
    client, clock = site(tmp_path, library)
    viewer = seat_for(client)
    library.down = True
    clock.now += LIVE_TTL + 1
    first = client.post("/api/first", json={"viewer": viewer}).json()
    assert first["source"] is None and set(first["pool"]) == {40}  # the films the labels name
    walked = client.post("/api/walk", json={"tree": "west", "viewer": viewer, "source": "held"})
    assert walked.status_code == 200 and set(walked.json()["pool"]) == {40}  # "held" would leave nothing


def test_with_no_library_the_source_question_is_never_asked(tmp_path: Path) -> None:
    client, _ = site(tmp_path, None)
    first = client.post("/api/first", json={"viewer": seat_for(client)}).json()
    assert first["source"] is None and len(first["pool"]) == 40


@pytest.mark.parametrize(("held", "asked"), [([], False), (list(range(1, 41)), False), (list(range(1, 40)), True)])
def test_the_question_is_asked_only_when_both_pools_hold_a_film(tmp_path: Path, held: list[int], asked: bool) -> None:
    client, _ = site(tmp_path, FakeLibrary(held=held))
    viewer = seat_for(client)
    first = client.post("/api/first", json={"viewer": viewer}).json()
    assert (first["source"] is not None) == asked and first["pool"]
    if asked:
        new = client.post("/api/first", json={"viewer": viewer, "source": "new"}).json()
        assert new["options"] and new["pool"]
    else:  # a sent source is not obeyed: the walk draws from every film offered
        walked = client.post("/api/walk", json={"tree": "west", "viewer": viewer, "source": "held"}).json()
        assert walked["pool"]


def test_the_shipped_source_question_reads_as_decided_and_maps_each_answer_to_its_pool() -> None:
    from matinee.reference import DATA

    shipped = json.loads((DATA / "first_question.json").read_text(encoding="utf-8"))["source"]
    assert shipped["ask"] == "what are we choosing from tonight?"
    assert [(o["say"], o["source"]) for o in shipped["options"]] == [
        ("only what we can watch right now.", "held"),
        ("something we don't have yet. something new!", "new"),
        ("anything at all. ours or not.", "all"),
    ]
    assert all(o["reply"] for o in shipped["options"])


def test_a_source_answer_naming_no_pool_is_refused(tmp_path: Path) -> None:
    from matinee.engine import EngineError

    data = write_data(tmp_path / "data")
    first = json.loads((data / "first_question.json").read_text())
    first["source"]["options"][0]["source"] = "ours"
    (data / "first_question.json").write_text(json.dumps(first))
    with pytest.raises(EngineError, match="names no source"):
        load_catalog(make_table(), data, reference())
