"""Every request Matinee makes names itself, so a proxy refusing a library's default agent string never cuts it off."""

from __future__ import annotations

import io
import json
import urllib.request
from typing import Any

import pytest

from matinee import USER_AGENT
from matinee.library.jellyfin import JellyfinReader
from matinee.tmdb import Pacer, fetch_picture, get_json
from matinee.web.seerr import SeerrCheck

sent: list[urllib.request.Request] = []


class Resp(io.BytesIO):
    headers = {"Content-Type": "image/jpeg"}

    def __enter__(self) -> Resp:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def capture(req: urllib.request.Request, timeout: float = 0) -> Resp:
    sent.append(req)
    return Resp(json.dumps({"Items": [], "TotalRecordCount": 0}).encode())


def test_every_outbound_request_names_matinee(monkeypatch: pytest.MonkeyPatch) -> None:
    sent.clear()
    assert SeerrCheck("https://seerr.invalid", opener=capture).answers()
    monkeypatch.setattr("matinee.tmdb.urllib.request.urlopen", capture)
    get_json("https://api.themoviedb.org/3/movie/1", "tok", Pacer(1e9))
    fetch_picture("/p.jpg", "poster", 160, opener=capture)
    monkeypatch.setattr("matinee.library.jellyfin.urllib.request.urlopen", capture)
    JellyfinReader("http://jellyfin.invalid", "jf-key").films()
    assert len(sent) >= 4
    assert all(req.get_header("User-agent") == USER_AGENT for req in sent)


def test_the_jellyfin_key_is_never_carried_to_another_host(monkeypatch: pytest.MonkeyPatch) -> None:
    sent.clear()
    monkeypatch.setattr("matinee.library.jellyfin.urllib.request.urlopen", capture)
    JellyfinReader("http://jellyfin.invalid", "jf-key").films()
    req: Any = sent[0]
    assert req.unredirected_hdrs.get("Authorization") == 'MediaBrowser Token="jf-key"'
    assert "Authorization" not in req.headers
    assert not [h for h in req.header_items() if h[0].lower().startswith("x-emby")]  # Jellyfin 12 refuses them
