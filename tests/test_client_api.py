"""Client picks use existing profile, admission, library and tree contracts without browser delays."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from matinee.store import Settings, Store
from matinee.web.theatre import LIVE_TTL
from test_admission import WORD, client_of, make_app
from test_web_library import make_world


@pytest.fixture
def client_world(tmp_path: Path) -> tuple[TestClient, Any, Any, Store, str, int]:
    client, library, clock, _ = make_world(tmp_path)
    store = Store(tmp_path / "store.sqlite")
    profile, token = store.create("Household", None, [])
    client.headers["Authorization"] = f"Bearer {token}"
    return client, library, clock, store, token, profile.id


@pytest.mark.parametrize("operation", ["choices", "pick"])
def test_requires_profile_token_even_without_door_word(client_world: Any, operation: str) -> None:
    client, library, _, _, token, _ = client_world
    library.calls.clear()
    for authorization in ("", "Bearer " + "x" * 43, "Basic " + token):
        response = client.post(f"/api/client/{operation}", json={}, headers={"Authorization": authorization})
        assert response.status_code == 401
        assert response.json()["error"] == "unauthorized"
    assert library.calls == []


def test_profile_token_never_bypasses_door_admission(tmp_path: Path) -> None:
    client = client_of(make_app(tmp_path))
    store = Store(tmp_path / "matinee.sqlite")
    _, token = store.create("Household", None, [])
    client.headers["Authorization"] = f"Bearer {token}"
    for operation in ("choices", "pick"):
        assert client.post(f"/api/client/{operation}", json={}).json()["error"] == "not_admitted"
    client.post("/api/admission", json={"word": WORD})
    assert client.post("/api/client/choices", json={}).status_code == 200
    assert client.post("/api/client/pick", json={}).status_code == 200
    # Admission alone does not confer profile access.
    del client.headers["Authorization"]
    assert client.post("/api/client/choices", json={}).json()["error"] == "unauthorized"


def test_choices_early_pick_another_and_year_refinement(client_world: Any) -> None:
    client, _, _, _, token, profile_id = client_world
    initial = client.post("/api/client/choices", json={}).json()
    assert initial["source"] == "held" and initial["profile"]["id"] == profile_id
    assert initial["doors"] == [{"id": "west", "label": "Western", "count": 40}]
    assert initial["pool_count"] == 40
    choices = client.post("/api/client/choices", json={"tree": "west"}).json()
    assert choices["question"]["id"] == "era"
    assert [(o["id"], o["count"]) for o in choices["question"]["options"]] == [
        ("option_0", 20),
        ("option_1", 40),
        ("option_3", 20),
    ]
    body = {"tree": "west", "answers": [{"question": "era", "option": "option_0"}]}
    picked = client.post("/api/client/pick", json=body).json()
    assert picked["film"]["tmdb"] in range(1, 21)
    assert picked["pool_count"] == 20 and picked["answers"] == body["answers"]
    again = client.post("/api/client/pick", json={**body, "seen": [picked["film"]["tmdb"]]}).json()
    assert again["film"]["tmdb"] != picked["film"]["tmdb"]
    assert again["available_count"] == 19
    refined = client.post("/api/client/pick", json={**body, "year_min": 1985}).json()
    assert 1985 <= refined["film"]["year"] <= 1990
    assert refined["pool_count"] == 6 and refined["source"] == "held"
    changed = client.post("/api/client/pick", json={"tree": "west", "year_min": 2005}).json()
    assert changed["film"]["year"] >= 2005 and changed["answers"] == []
    assert token not in str(picked)


@pytest.mark.parametrize(
    "body",
    [
        {"tree": "missing"},
        {"answers": [{"question": "era", "option": "option_0"}]},
        {"tree": "west", "answers": [{"question": "era", "option": "option_2"}]},
        {"tree": "west", "answers": [{"question": "gore", "option": "option_0"}]},
        {"tree": "west", "answers": [{"question": "era", "option": "made_up"}]},
    ],
)
def test_invalid_choices_never_widen(client_world: Any, body: dict[str, Any]) -> None:
    client = client_world[0]
    for operation in ("choices", "pick"):
        response = client.post(f"/api/client/{operation}", json=body)
        assert response.status_code == 400
        assert "film" not in response.json()


@pytest.mark.parametrize(
    "body", [{"rating_min": 6}, {"source": "invented"}, {"year_min": 2000, "year_max": 1990}, {"seen": [-1]}]
)
def test_schema_rejects_unknown_or_invalid_constraints(client_world: Any, body: dict[str, Any]) -> None:
    assert client_world[0].post("/api/client/pick", json=body).status_code == 422


def test_held_failure_is_explicit_after_success(client_world: Any) -> None:
    client, library, clock, _, _, _ = client_world
    assert client.post("/api/client/pick", json={}).status_code == 200
    library.down = True
    clock.now += LIVE_TTL + 1
    for source in ("held", "new"):
        for operation in ("choices", "pick"):
            response = client.post(f"/api/client/{operation}", json={"source": source})
            assert response.status_code == 503
            assert response.json()["error"] == "library_unavailable"
            assert "film" not in response.json()


def test_no_match_and_exhaustion_do_not_restart_pool(client_world: Any) -> None:
    client = client_world[0]
    for body in ({"year_min": 2500}, {"seen": [*range(1, 40), 99]}):
        result = client.post("/api/client/pick", json=body).json()
        assert result["film"] is None and result["available_count"] == 0
        assert result["warnings"]


def test_profile_preferences_are_read_fresh(client_world: Any) -> None:
    client, _, _, store, token, profile_id = client_world
    store.set_settings(profile_id, Settings(languages=frozenset({"fr"})), frozenset({"fr"}), [token])
    result = client.post("/api/client/pick", json={}).json()
    assert result["film"]["tmdb"] == 8
    assert result["pool_count"] == 1


def test_canonical_flavour_selects_the_engine_pool(tmp_path: Path) -> None:
    from matinee.engine import Viewer, load_catalog
    from matinee.recommendations import SelectionIn, select
    from test_engine import kind_labels, kind_tree, make_table, reference, write_data

    cat = load_catalog(make_table(), write_data(tmp_path, kind_tree()), reference(), kind_labels())
    viewer = Viewer(source="all")
    choices = select(cat, viewer, SelectionIn(source="all", tree="west"))
    assert choices.question is not None
    assert [(o.id, o.count) for o in choices.question.options] == [("laughs", 20), ("option_1", 21)]
    chosen = select(
        cat,
        viewer,
        SelectionIn.model_validate(
            {"source": "all", "tree": "west", "answers": [{"question": "era", "option": "laughs"}]}
        ),
    )
    assert chosen.pool == tuple(range(1, 40, 2))


def test_profile_rating_floor_controls_client_pool(tmp_path: Path) -> None:
    client, _, _, _ = make_world(tmp_path, scores={t: float(t) for t in range(1, 40)})
    store = Store(tmp_path / "store.sqlite")
    profile, token = store.create("Household", None, [])
    store.set_settings(profile.id, Settings(floor="above_middle"), frozenset(), [token])
    client.headers["Authorization"] = f"Bearer {token}"
    result = client.post("/api/client/choices", json={}).json()
    assert result["profile"]["floor"] == "above_middle"
    assert result["pool_count"] == 16  # best 15 of 39 ranked films plus the unranked live-only film
    picked = client.post("/api/client/pick", json={}).json()
    assert picked["film"]["tmdb"] in {*range(25, 40), 99}


def test_unchecked_content_remains_visible_and_attributed(tmp_path: Path) -> None:
    from test_pick import ScriptedDtdd, site_with

    client = site_with(tmp_path, None, ScriptedDtdd({}))
    store = Store(tmp_path / "s.sqlite")
    _, token = store.create("Household", None, [153])
    client.headers["Authorization"] = f"Bearer {token}"
    result = client.post("/api/client/pick", json={}).json()
    assert result["film"] is not None
    assert any("couldn't check" in warning for warning in result["warnings"])
    assert result["credits"] == [{"text": "Powered by DoesTheDogDie.com", "url": "https://www.doesthedogdie.com"}]
