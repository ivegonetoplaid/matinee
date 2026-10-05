"""Every request Matinee makes names itself, so a proxy refusing a library's default agent string never cuts it off."""

from __future__ import annotations

import io
import json
import urllib.error
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


@pytest.mark.parametrize(("code", "refused"), [(401, True), (403, True), (500, False)])
def test_a_media_server_that_turns_down_the_key_is_told_apart(
    monkeypatch: pytest.MonkeyPatch, code: int, refused: bool
) -> None:
    from matinee.library import LibraryError, LibraryRefused
    from matinee.library.plex import PlexReader

    def answer(req: urllib.request.Request, timeout: float) -> Resp:
        raise urllib.error.HTTPError(req.full_url, code, "no", {}, None)  # type: ignore[arg-type]

    readers: list[tuple[str, JellyfinReader | PlexReader]] = [
        ("jellyfin", JellyfinReader("http://jellyfin.invalid", "jf-key")),
        ("plex", PlexReader("http://plex.invalid", "px-token")),
    ]
    for module, reader in readers:
        monkeypatch.setattr(f"matinee.library.{module}.urllib.request.urlopen", answer)
        with pytest.raises(LibraryError) as caught:
            reader.films()
        assert isinstance(caught.value, LibraryRefused) is refused and str(code) in str(caught.value)


def test_jellyfin_lists_the_films_inside_collections_and_never_a_collection_as_a_film(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    items = [
        {"Id": "a" * 32, "Name": "Alien", "Type": "Movie", "ProviderIds": {"Tmdb": "348"}},
        {"Id": "b" * 32, "Name": "Alien Collection", "Type": "BoxSet", "ProviderIds": {"Tmdb": "8091"}},
    ]
    asked: list[str] = []

    def answer(req: urllib.request.Request, timeout: float = 0) -> Resp:
        asked.append(req.full_url)
        return Resp(json.dumps({"Items": items, "TotalRecordCount": 2}).encode())

    monkeypatch.setattr("matinee.library.jellyfin.urllib.request.urlopen", answer)
    with caplog.at_level("WARNING", logger="matinee.library"):
        films = JellyfinReader("http://jellyfin.invalid", "jf-key").films()
    assert [f.tmdb for f in films] == [348]
    assert "CollapseBoxSetItems=false" in asked[0] and "1 items that are not movies (BoxSet)" in caplog.text


def test_the_jellyfin_key_is_never_carried_to_another_host(monkeypatch: pytest.MonkeyPatch) -> None:
    sent.clear()
    monkeypatch.setattr("matinee.library.jellyfin.urllib.request.urlopen", capture)
    JellyfinReader("http://jellyfin.invalid", "jf-key").films()
    req: Any = sent[0]
    assert req.unredirected_hdrs.get("Authorization") == 'MediaBrowser Token="jf-key"'
    assert "Authorization" not in req.headers
    assert not [h for h in req.header_items() if h[0].lower().startswith("x-emby")]  # Jellyfin 12 refuses them
