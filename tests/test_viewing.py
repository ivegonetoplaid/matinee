"""Exclusions set and applied: the paced DoesTheDogDie client, the topic list, and walks for a viewer."""

from __future__ import annotations

import contextlib
import http.client
import io
import json
import sqlite3
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from matinee.dtdd import (
    BACKOFF_S,
    MONTH_RESERVE,
    RATE_PER_S,
    REQUESTS_PER_HOUR,
    RESERVE_HOLD_S,
    TOPICS_KEEP_S,
    TOPICS_REFRESH_S,
    USER_AGENT,
    Dtdd,
    DtddCeiling,
    DtddError,
    DtddGone,
    Topic,
)
from matinee.engine import load_catalog
from matinee.store import Store
from matinee.table import FilmTable
from matinee.web.app import create_app
from matinee.web.config import Config
from matinee.web.theatre import Theatre
from test_engine import TREE, reference, write_data
from test_web_library import SECRET_KEY, SECRET_URL, FakeLibrary, seat_for, write_film_table

TOPICS = [
    {"id": 188, "name": "there's blood/gore", "minimalName": "blood/gore", "keywords": "blood", "topicCategoryId": 4},
    {"id": 153, "name": "a dog dies", "minimalName": "dog death", "keywords": "dog", "topicCategoryId": 1},
    {"name": "no id"},
]


class Answering:
    """An opener that records requests and answers with the next queued body or error."""

    def __init__(self, answers: list[Any]) -> None:
        self.answers = answers
        self.requests: list[urllib.request.Request] = []

    def __call__(self, req: urllib.request.Request, timeout: float) -> Any:
        self.requests.append(req)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return io.BytesIO(json.dumps(answer).encode())


class Clock:
    def __init__(self) -> None:
        self.now = 100.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_requests_are_paced_named_and_keyed() -> None:
    opener, clock = Answering([TOPICS] * 6), Clock()
    client = Dtdd("secret-key", opener=opener, clock=clock, sleep=clock.sleep)
    first = client.topics()
    client.get("/topics", 10.0, 10.0)  # a search and its item request may go back to back
    assert clock.slept == []
    clock.now += 0.5
    client.get("/topics", 10.0, 10.0)
    assert clock.slept == [pytest.approx((1 - 0.5 * RATE_PER_S) / RATE_PER_S)]
    for _ in range(3):
        client.get("/topics", 10.0, 10.0)
    assert clock.slept[-1] == pytest.approx(1 / RATE_PER_S)
    assert [t.id for t in first] == [188, 153]
    assert first[0] == Topic(188, "there's blood/gore", "blood/gore", "blood", 4)
    req = opener.requests[0]
    assert req.get_method() == "GET" and req.full_url == "https://www.doesthedogdie.com/api/v3/topics"
    assert req.get_header("User-agent") == USER_AGENT and req.get_header("X-api-key") == "secret-key"


@pytest.mark.parametrize(
    "answer",
    [
        urllib.error.HTTPError("u", 429, "slow down", {}, None),  # type: ignore[arg-type]
        urllib.error.URLError("down"),
        TimeoutError(),
        {"not": "a list"},
    ],
)
def test_failures_are_one_error(answer: Any) -> None:
    client = Dtdd("k", opener=Answering([answer]))
    with pytest.raises(DtddError):
        client.topics()


class FakeDtdd(Dtdd):
    def __init__(self, down: bool = False) -> None:
        super().__init__("k")
        self.down = down

    def topics(self) -> list[Topic]:
        if self.down:
            raise DtddError("DoesTheDogDie did not answer")
        return [Topic(188, "there's blood/gore", "blood/gore", "blood", 4), Topic(153, "a dog dies", "dog", "dog", 1)]


@pytest.fixture
def site(tmp_path: Path) -> tuple[TestClient, Store, FakeDtdd]:
    data = write_data(tmp_path / "data")
    write_film_table(tmp_path / "films.sqlite")

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data, reference())

    theatre = Theatre(FakeLibrary(), tmp_path / "films.sqlite", catalog_of=catalog_of)
    store, dtdd = Store(tmp_path / "matinee.sqlite"), FakeDtdd()
    config = Config(SECRET_URL, SECRET_KEY, tmp_path, "https://seerr.invalid", "d" * 16)
    app = create_app(config, theatre, store, dtdd, clock=lambda: 0.0)
    return TestClient(app, base_url="https://testserver"), store, dtdd


def test_topics_carry_the_credit_and_fail_in_words(site: Any) -> None:
    client, _, dtdd = site
    body = client.get("/api/topics").json()
    assert body["credit"] == "Powered by DoesTheDogDie.com" and body["link"] == "https://www.doesthedogdie.com"
    assert [t["id"] for t in body["topics"]] == [188, 153]
    dtdd.down = True
    resp = client.get("/api/topics")
    assert resp.status_code == 503
    assert resp.json() == {"error": "topics_unavailable", "message": "I can't load the list of topics right now."}


def test_the_page_is_given_the_pick_lines_and_caps(site: Any) -> None:
    client, _store, _dtdd = site
    body = client.get("/api/quips").json()
    assert body["caps"] == {"line": 64, "pair": 76}
    assert "borrow" not in body
    assert set(body["categories"]) == {"universal", "horror", "comedy", "action"}
    assert "How about this one?" in body["categories"]["universal"]["reveal"]


def test_saved_topics_apply_to_every_walk(site: Any) -> None:
    client, _, _ = site
    me = client.post("/api/profiles", json={"name": "Nell"}).json()
    saved = client.put(f"/api/profiles/{me['id']}/topics", json={"topics": [188]})
    assert saved.status_code == 200 and saved.json()["topics"] == [188] and "exclusions" not in saved.json()
    after = client.post(
        "/api/walk",
        json={"tree": "west", "answers": [{"question": "era", "option": 1}], "viewer": {"profile_id": me["id"]}},
    ).json()
    assert after["question"]["id"] == "kind"  # topic 188 skips the gore question


def test_without_a_profile_only_the_first_questions_pool_is_given(site: Any, tmp_path: Path) -> None:
    client, store, _ = site
    first = client.post("/api/first", json={})
    assert first.status_code == 200 and first.json()["pool"] == list(range(1, 40)) + [99]
    sneaking = {"tree": "west", "viewer": {"topics": [188]}}
    assert client.post("/api/walk", json=sneaking).status_code == 403
    assert client.post("/api/walk", json={"tree": "west"}).status_code == 403
    assert client.cookies.get("matinee_tokens") is None
    with sqlite3.connect(tmp_path / "matinee.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM profiles").fetchone() == (0,)  # nothing was saved


def test_a_profiles_topics_skip_the_gore_question(site: Any) -> None:
    client, _, _ = site
    squeamish = {"tree": "west", "answers": [{"question": "era", "option": 1}], "viewer": seat_for(client, [188])}
    assert client.post("/api/walk", json=squeamish).json()["question"]["id"] == "kind"


def test_only_the_device_holding_a_profile_may_use_or_change_it(site: Any) -> None:
    client, store, _ = site
    other, owner_token = store.create("Owner", None, [153])
    walk = client.post("/api/walk", json={"tree": "west", "viewer": {"profile_id": other.id}})
    assert walk.status_code == 403
    change = client.put(f"/api/profiles/{other.id}/topics", json={"topics": []})
    assert change.status_code == 403
    assert store.holding([owner_token])[owner_token].topics == frozenset({153})


def test_misfit_answers_are_refused(site: Any) -> None:
    client, _, _ = site
    me = seat_for(client)
    misfit = client.post(
        "/api/walk", json={"tree": "west", "answers": [{"question": "gore", "option": 0}], "viewer": me}
    )
    assert misfit.status_code == 400 and misfit.json()["error"] == "refused"
    assert client.post("/api/walk", json={"tree": "nope", "viewer": me}).status_code == 400


def test_first_question_greets_a_profile_by_name(site: Any) -> None:
    client, _, _ = site
    me = client.post("/api/profiles", json={"name": "Ada"}).json()
    first = client.post("/api/first", json={"viewer": {"profile_id": me["id"]}}).json()
    assert first["lines"] == ["Right this way."] and first["name"] == "Ada"
    assert first["options"] == [{"say": "Cowboys.", "tree": "west", "label": "Western"}]
    assert first["pool"] == list(range(1, 40)) + [99]  # every film the answers offer this viewer
    assert client.post("/api/first", json={}).json()["name"] is None


def test_the_pace_stays_under_thirty_a_minute() -> None:
    opener, clock = Answering([TOPICS] * 100), Clock()
    sent: list[float] = []

    def record(req: urllib.request.Request, timeout: float) -> Any:
        sent.append(clock.now)
        return opener(req, timeout)

    client = Dtdd("k", opener=record, clock=clock, sleep=clock.sleep)
    for _ in range(100):
        client.get("/topics", 10.0, 10.0)
    busiest = max(sum(1 for t in sent if start <= t < start + 60) for start in sent)
    assert busiest < 30


def test_the_real_opener_carries_the_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[float] = []

    def fake(req: urllib.request.Request, timeout: float) -> Any:
        seen.append(timeout)
        return io.BytesIO(b"[]")

    monkeypatch.setattr("matinee.dtdd.urllib.request.urlopen", fake)
    Dtdd("k").get("/topics", 3.0, 1.0)
    assert seen == [3.0]


def test_a_caller_waits_its_turn_only_so_long() -> None:
    client = Dtdd("k", opener=Answering([TOPICS]))
    client._lock.acquire()
    try:
        with pytest.raises(DtddError, match="busy"):
            client.get("/topics", 3.0, 0.05)
    finally:
        client._lock.release()
    assert client.get("/topics", 3.0, 0.05)  # the lock is one shared lock, and free again


def test_calls_never_overlap() -> None:
    active, peak = [0], [0]
    guard = threading.Lock()

    def slow(req: urllib.request.Request, timeout: float) -> Any:
        with guard:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        threading.Event().wait(0.02)
        with guard:
            active[0] -= 1
        return io.BytesIO(b"[]")

    client = Dtdd("k", opener=slow, sleep=lambda _s: None)
    threads = [threading.Thread(target=client.get, args=("/topics", 3.0, 5.0)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 1


@pytest.mark.parametrize("answer", [http.client.RemoteDisconnected("gone"), ConnectionResetError(), ValueError()])
def test_dropped_connections_are_one_error(answer: Exception) -> None:
    with pytest.raises(DtddError):
        Dtdd("k", opener=Answering([answer])).topics()


def test_saving_one_profile_leaves_the_others(site: Any) -> None:
    client, store, _ = site
    other, token = store.create("Other", None, [153])
    me = client.post("/api/profiles", json={"name": "Me"}).json()
    client.put(f"/api/profiles/{me['id']}/topics", json={"topics": [188]})
    assert store.holding([token])[token].topics == frozenset({153})


def test_the_allowance_holds_after_idle_hours_and_slow_answers() -> None:
    clock = Clock()
    sent: list[float] = []

    def slow(req: urllib.request.Request, timeout: float) -> Any:
        sent.append(clock.now)
        clock.now += 0.5  # each answer takes half a second
        return io.BytesIO(json.dumps(TOPICS).encode())

    client = Dtdd("k", opener=slow, clock=clock, sleep=clock.sleep)
    for burst in range(3):
        clock.now += 3600  # an idle hour must not bank more than BURST
        for _ in range(40):
            client.get("/topics", 10.0, 10.0)
        del burst
    busiest = max(sum(1 for t in sent if start <= t < start + 60) for start in sent)
    assert busiest < 30


class Headed(io.BytesIO):
    """A response body carrying headers, as urllib's responses do."""

    def __init__(self, body: Any, headers: dict[str, str]) -> None:
        super().__init__(json.dumps(body).encode())
        self.headers = headers


def refusal(code: int, headers: dict[str, str]) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("u", code, "refused", headers, None)  # type: ignore[arg-type]


def test_the_server_makes_at_most_its_hourly_ceiling_of_requests() -> None:
    assert REQUESTS_PER_HOUR == 120
    opener, clock = Answering([TOPICS] * (REQUESTS_PER_HOUR + 1)), Clock()
    client = Dtdd("k", opener=opener, clock=clock, sleep=clock.sleep)
    for _ in range(REQUESTS_PER_HOUR):
        client.get("/topics", 10.0, 10.0)
    with pytest.raises(DtddCeiling):
        client.get("/topics", 10.0, 10.0)
    assert len(opener.requests) == REQUESTS_PER_HOUR  # the refused call never reached DoesTheDogDie
    clock.now += 3600
    assert client.get("/topics", 10.0, 10.0)


def test_a_refusal_holds_every_request_for_its_retry_after() -> None:
    opener, clock = Answering([refusal(429, {"Retry-After": "30"}), TOPICS]), Clock()
    client = Dtdd("k", opener=opener, clock=clock, sleep=clock.sleep)
    with pytest.raises(DtddError):
        client.get("/topics", 10.0, 10.0)
    clock.now += 29
    with pytest.raises(DtddError, match="holding"):
        client.get("/topics", 10.0, 10.0)
    assert len(opener.requests) == 1
    clock.now += 1
    assert client.get("/topics", 10.0, 10.0)


def test_a_refusal_without_retry_after_backs_off_doubling_until_an_answer() -> None:
    clock = Clock()
    answers = [refusal(503, {}), refusal(429, {}), TOPICS, refusal(429, {})]
    client = Dtdd("k", opener=Answering(list(answers)), clock=clock, sleep=clock.sleep)
    holds = []
    for _ in answers:
        with contextlib.suppress(DtddError):
            client.get("/topics", 10.0, 10.0)
        holds.append(client._held_until - clock.now)
        clock.now = max(clock.now, client._held_until)
    assert holds[0] == BACKOFF_S and holds[1] == 2 * BACKOFF_S
    assert holds[3] == BACKOFF_S  # the answer in between reset the doubling


def test_the_months_reserve_holds_requests_for_hours() -> None:
    answers = [
        Headed(TOPICS, {"X-RateLimit-Remaining-Month": str(MONTH_RESERVE)}),  # at the reserve itself: no hold
        Headed(TOPICS, {"X-RateLimit-Remaining-Month": str(MONTH_RESERVE - 1)}),
        Headed(TOPICS, {}),
    ]
    clock = Clock()
    client = Dtdd("k", opener=lambda req, timeout: answers.pop(0), clock=clock, sleep=clock.sleep)
    client.get("/topics", 10.0, 10.0)
    client.get("/topics", 10.0, 10.0)
    with pytest.raises(DtddError, match="left this month"):
        client.get("/topics", 10.0, 10.0)
    assert len(answers) == 1  # the held call sent nothing
    clock.now += RESERVE_HOLD_S
    assert client.get("/topics", 10.0, 10.0)


def test_a_404_is_gone_and_long_refusal_runs_stay_capped() -> None:
    with pytest.raises(DtddGone):
        Dtdd("k", opener=Answering([refusal(404, {})])).topics()
    clock = Clock()
    client = Dtdd("k", opener=Answering([refusal(429, {})]), clock=clock, sleep=clock.sleep)
    client._refusals = 2000  # a long run of refusals must not overflow the backoff
    with pytest.raises(DtddError):
        client.get("/topics", 10.0, 10.0)
    assert client._held_until - clock.now == 3600.0


def test_the_topic_list_is_kept_twenty_nine_days_and_served_stale_to_thirty() -> None:
    clock = Clock()
    opener = Answering([TOPICS, TOPICS, urllib.error.URLError("down"), urllib.error.URLError("down")])
    client = Dtdd("k", opener=opener, clock=clock, sleep=clock.sleep)
    assert [t.id for t in client.topics()] == [188, 153]
    client.topics()
    assert len(opener.requests) == 1  # kept
    clock.now += TOPICS_REFRESH_S
    client.topics()
    assert len(opener.requests) == 2  # refreshed on day 29
    clock.now += TOPICS_REFRESH_S
    assert [t.id for t in client.topics()] == [188, 153]  # refresh failed; the kept copy is under 30 days
    clock.now += TOPICS_KEEP_S - TOPICS_REFRESH_S
    with pytest.raises(DtddError):
        client.topics()  # past 30 days nothing is served


def test_a_question_footnote_reaches_the_page(site: Any, tmp_path: Path) -> None:
    tree = json.loads(json.dumps(TREE))
    tree["questions"][0]["footnote"] = "*specials have their own answer."
    (tmp_path / "data" / "trees" / "west.json").write_text(json.dumps(tree))
    client, _, _ = site
    assert (
        client.post("/api/walk", json={"tree": "west", "viewer": seat_for(client)}).json()["question"]["footnote"]
        == tree["questions"][0]["footnote"]
    )


def test_the_first_question_says_whether_this_viewers_picks_are_checked(site: Any) -> None:
    client, _, _ = site
    assert client.post("/api/first", json={"viewer": seat_for(client, [188])}).json()["checked"] is True
    assert client.post("/api/first", json={"viewer": seat_for(client)}).json()["checked"] is False
