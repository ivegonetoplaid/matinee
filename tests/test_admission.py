"""The door word: who gets past the locked door, what a stranger reaches, and how a guess is answered."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from matinee.engine import load_catalog
from matinee.store import Store
from matinee.table import FilmTable
from matinee.web.admission import COOKIE, KEY_FILE, LIFE_S, Admission, AdmissionError, Mode
from matinee.web.app import create_app
from matinee.web.common import TOKENS_COOKIE
from matinee.web.config import GREETINGS, Config, ConfigError, from_env
from matinee.web.theatre import Theatre
from test_engine import reference, write_data
from test_viewing import FakeDtdd
from test_web_library import SECRET_KEY, SECRET_URL, FakeLibrary, write_film_table

WORD = "Open, Sesame! 1983"  # relaxes to "opensesame1983"
STRICT = "Correct Horse Battery"


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


def make_app(
    state: Path, word: str | None = WORD, mode: Mode = "relaxed", clock: Clock | None = None, delay: float = 0.0
) -> FastAPI:
    data = state / "data"
    if not data.exists():
        write_data(data)
        write_film_table(state / "films.sqlite")

    def catalog_of(table: FilmTable) -> Any:
        return load_catalog(table, data, reference())

    theatre = Theatre(FakeLibrary(), state / "films.sqlite", catalog_of=catalog_of)
    config = Config(SECRET_URL, SECRET_KEY, state, "https://seerr.invalid", "d" * 16, word, mode, GREETINGS["gin"])
    return create_app(
        config, theatre, Store(state / "matinee.sqlite"), FakeDtdd(), clock=clock or Clock(), wrong_word_delay_s=delay
    )


def client_of(app: FastAPI) -> TestClient:
    return TestClient(app, base_url="https://testserver")


STRANGER_REFUSED = [
    ("GET", "/api/door"),
    ("POST", "/api/first"),
    ("POST", "/api/walk"),
    ("POST", "/api/pick"),
    ("POST", "/api/notes"),
    ("POST", "/api/profiles"),
    ("GET", "/api/quips"),
    ("GET", "/api/topics"),
    ("GET", "/api/exclusions"),
    ("GET", "/api/film/5"),
    ("GET", "/img/poster/5/m"),
    ("GET", "/img/backdrop/5/l"),
    ("DELETE", "/api/profiles/1"),
    ("GET", "/robots.txt"),
]


@pytest.mark.parametrize("method,path", STRANGER_REFUSED)
def test_a_stranger_reaches_nothing_but_the_page_and_the_word_check(tmp_path: Path, method: str, path: str) -> None:
    client = client_of(make_app(tmp_path))
    resp = client.request(method, path, json={})
    assert resp.status_code == 401 and resp.json()["error"] == "not_admitted"
    assert resp.headers["x-robots-tag"] == "noindex" and "default-src 'self'" in resp.headers["content-security-policy"]


def test_the_page_its_files_and_the_word_check_answer_a_stranger(tmp_path: Path) -> None:
    client = client_of(make_app(tmp_path))
    for path in ("/", "/static/css/matinee.css", "/static/js/main.js", "/static/avatars/popcorn-80.webp"):
        assert client.get(path).status_code == 200, path
    assert client.get("/api/admission").json() == {"locked": True, "admitted": False, "greeting": GREETINGS["gin"]}


def test_the_right_word_admits_the_device_for_400_days(tmp_path: Path) -> None:
    client = client_of(make_app(tmp_path))
    resp = client.post("/api/admission", json={"word": WORD})
    assert resp.status_code == 200 and resp.json()["admitted"] is True
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=") and f"Max-Age={LIFE_S}" in cookie
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert client.get("/api/door").status_code == 200
    assert client.get("/api/admission").json() == {"locked": True, "admitted": True, "greeting": GREETINGS["gin"]}


def test_an_admission_ends_after_400_days(tmp_path: Path) -> None:
    clock = Clock()
    client = client_of(make_app(tmp_path, clock=clock))
    client.post("/api/admission", json={"word": WORD})
    clock.now += LIFE_S - 60
    assert client.get("/api/door").status_code == 200
    clock.now += 120
    assert client.get("/api/door").status_code == 401


@pytest.mark.parametrize("value", ["1", "admitted", "true", "1800000000.", "1800000000.abc", "x.y", ""])
def test_a_hand_made_cookie_admits_nothing(tmp_path: Path, value: str) -> None:
    client = client_of(make_app(tmp_path))
    client.cookies.set(COOKIE, value, domain="testserver.local")
    assert client.get("/api/door").status_code == 401


def test_a_cookie_survives_a_restart_and_ends_when_the_word_or_mode_changes(tmp_path: Path) -> None:
    first = client_of(make_app(tmp_path))
    first.post("/api/admission", json={"word": WORD})
    cookie = first.cookies[COOKIE]
    for app, admitted in [
        (make_app(tmp_path), True),
        (make_app(tmp_path, word="Another Phrase Entirely"), False),
        (make_app(tmp_path, word=WORD, mode="strict"), False),
    ]:
        later = client_of(app)
        later.cookies.set(COOKIE, cookie, domain="testserver.local")
        assert (later.get("/api/door").status_code == 200) is admitted


def test_a_cookie_from_another_installation_admits_nothing(tmp_path: Path) -> None:
    here = client_of(make_app(tmp_path / "a"))
    here.post("/api/admission", json={"word": WORD})
    elsewhere = client_of(make_app(tmp_path / "b"))  # the same word, its own secret
    elsewhere.cookies.set(COOKIE, here.cookies[COOKIE], domain="testserver.local")
    assert elsewhere.get("/api/door").status_code == 401


def test_a_profile_token_does_not_admit_a_device(tmp_path: Path) -> None:
    open_app = make_app(tmp_path, word=None)
    old = client_of(open_app)
    old.post("/api/profiles", json={"name": "Before the lock"})
    tokens = old.cookies[TOKENS_COOKIE]
    locked = client_of(make_app(tmp_path))
    locked.cookies.set(TOKENS_COOKIE, tokens, domain="testserver.local")
    assert locked.get("/api/door").status_code == 401
    assert locked.post("/api/admission", json={"word": WORD}).status_code == 200
    assert [(p["name"], p["held"]) for p in locked.get("/api/door").json()["profiles"]] == [("Before the lock", True)]


@pytest.mark.parametrize(
    "typed,admitted",
    [
        ("opensesame1983", True),
        ("OPEN SESAME 1983", True),
        ("open sesame 198", True),  # one deletion
        ("open sesame 19833", True),  # one insertion
        ("open sesane 1983", True),  # one substitution
        ("open sesane 198", False),  # two edits
        ("opne sesame 1983", False),  # a swap is two edits
        ("", False),
        ("x" * 201, False),
    ],
)
def test_relaxed_matching_allows_one_edit(typed: str, admitted: bool) -> None:
    assert Admission(WORD, "relaxed", b"k" * 32).matches(typed) is admitted


@pytest.mark.parametrize("typed,admitted", [(STRICT, True), (STRICT.lower(), False), (STRICT + " ", False)])
def test_strict_matching_wants_the_word_exactly(typed: str, admitted: bool) -> None:
    assert Admission(STRICT, "strict", b"k" * 32).matches(typed) is admitted


def test_a_near_miss_is_turned_away_in_each_mode(tmp_path: Path) -> None:
    relaxed = client_of(make_app(tmp_path / "r"))
    assert relaxed.post("/api/admission", json={"word": "open sesane 198"}).status_code == 401
    strict = client_of(make_app(tmp_path / "s", word=STRICT, mode="strict"))
    resp = strict.post("/api/admission", json={"word": STRICT.lower()})
    assert resp.status_code == 401 and resp.json()["error"] == "wrong_word"
    assert COOKIE not in strict.cookies
    assert strict.get("/api/film/5").status_code == 401 and strict.get("/img/poster/5/m").status_code == 401


def test_with_no_door_word_every_device_is_admitted(tmp_path: Path) -> None:
    client = client_of(make_app(tmp_path, word=None))
    assert client.get("/api/admission").json() == {"locked": False, "admitted": True, "greeting": None}
    assert client.get("/api/door").status_code == 200 and client.get("/api/film/5").status_code == 200
    assert not (tmp_path / KEY_FILE).exists()


def test_a_wrong_word_is_answered_only_after_the_delay(tmp_path: Path) -> None:
    client = client_of(make_app(tmp_path, delay=0.3))
    started = time.monotonic()
    assert client.post("/api/admission", json={"word": "nope"}).status_code == 401
    assert time.monotonic() - started >= 0.3
    started = time.monotonic()
    assert client.post("/api/admission", json={"word": WORD}).status_code == 200
    assert time.monotonic() - started < 0.3


def test_forty_waiting_guesses_go_one_at_a_time_and_delay_nothing_else(tmp_path: Path) -> None:
    delay = 0.05
    app = make_app(tmp_path, delay=delay)

    async def scene() -> tuple[float, float, list[int]]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            started = time.monotonic()
            guesses = [
                asyncio.create_task(client.post("/api/admission", json={"word": f"guess {i}"})) for i in range(40)
            ]
            await asyncio.sleep(delay * 3)  # several guesses are waiting now
            ordinary = time.monotonic()
            page = await client.get("/")
            api = await client.get("/api/admission")
            ordinary = time.monotonic() - ordinary
            answers = await asyncio.gather(*guesses)
            return (
                ordinary,
                time.monotonic() - started,
                [page.status_code, api.status_code, *(a.status_code for a in answers)],
            )

    ordinary, total, codes = asyncio.run(scene())
    assert codes[:2] == [200, 200] and set(codes[2:]) == {401}
    assert total >= 40 * delay  # one at a time, each after its delay
    assert ordinary < 10 * delay  # the page and the status answered while the guesses waited


def test_the_door_word_is_never_said_back(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    client = client_of(make_app(tmp_path))
    replies = [
        client.get("/api/admission"),
        client.post("/api/admission", json={"word": "wrong"}),
        client.post("/api/admission", json={"word": WORD}),
        client.get("/api/door"),
    ]
    for reply in replies:
        assert "esame" not in reply.text.lower() and all("esame" not in v.lower() for v in reply.headers.values())
    assert "esame" not in caplog.text.lower()
    assert "esame" not in repr(Config(SECRET_URL, SECRET_KEY, tmp_path, "https://s.invalid", "d", WORD)).lower()


ENV = {
    "MATINEE_JELLYFIN_URL": SECRET_URL,
    "JELLYFIN_API_KEY": SECRET_KEY,
    "MATINEE_SEERR_URL": "https://seerr.invalid",
    "DTDD_API_KEY": "d",
}


@pytest.mark.parametrize(
    "word,mode,setting",
    [
        ("Sesame 7", "", "MATINEE_DOOR_WORD"),  # seven letters and digits once relaxed
        ("a.b.c.d.e.f.g", "relaxed", "MATINEE_DOOR_WORD"),
        ("Short strict", "strict", None),  # exactly twelve: allowed
        ("Shorter one!", "strict", None),
        ("Too short!!", "strict", "MATINEE_DOOR_WORD"),
        ("Long enough word", "sideways", "MATINEE_DOOR_MATCH"),
    ],
)
def test_a_door_word_too_short_for_its_mode_or_an_unknown_mode_stops_the_start(
    tmp_path: Path, word: str, mode: str, setting: str | None
) -> None:
    env = {**ENV, "MATINEE_STATE": str(tmp_path), "MATINEE_DOOR_WORD": word, "MATINEE_DOOR_MATCH": mode}
    if setting is None:
        assert from_env(env).door_word == word
        return
    with pytest.raises(ConfigError, match=setting) as refused:
        from_env(env)
    assert word.lower() not in str(refused.value).lower()


def test_the_settings_default_to_no_lock_relaxed_and_the_show_greeting(tmp_path: Path) -> None:
    config = from_env({**ENV, "MATINEE_STATE": str(tmp_path), "MATINEE_DOOR_WORD": "   "})
    assert (config.door_word, config.door_match, config.door_greeting) == (None, "relaxed", GREETINGS["show"])
    own = from_env({**ENV, "MATINEE_STATE": str(tmp_path), "MATINEE_DOOR_GREETING": "Psst. Password?"})
    assert own.door_greeting == "Psst. Password?"
    assert (
        from_env({**ENV, "MATINEE_STATE": str(tmp_path), "MATINEE_DOOR_GREETING": "gin"}).door_greeting
        == GREETINGS["gin"]
    )


def test_the_secret_is_made_once_owner_only_and_an_unreadable_one_stops_the_start(tmp_path: Path) -> None:
    make_app(tmp_path)
    secret = tmp_path / KEY_FILE
    first = secret.read_bytes()
    assert len(first) == 32 and (secret.stat().st_mode & 0o777) == 0o600
    make_app(tmp_path)
    assert secret.read_bytes() == first
    secret.write_bytes(b"short")
    with pytest.raises(AdmissionError):
        make_app(tmp_path)
    secret.unlink()
    os.mkdir(secret)
    with pytest.raises(AdmissionError):
        make_app(tmp_path)
