"""Each library copy's audio track languages: how a tag is read, how each media server gives them, and how the film
table keeps them. Only the nightly rebuild asks for them."""

from __future__ import annotations

import io
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from matinee.genome import Scores
from matinee.languages import audio_languages, codes, extra_track, held, two_letter
from matinee.library import LibraryFilm
from matinee.library.jellyfin import JellyfinReader, parse_film
from matinee.library.plex import audio_of
from matinee.reference import DATA
from matinee.table import build_table, load_table, with_live, write_table
from test_plex import ITEM, SECTIONS, reader
from test_web_library import SECRET_KEY, SECRET_URL

# Every tag the household's Jellyfin and Plex libraries carried when this was measured, and how each reads.
MEASURED = {
    "eng": "en", "fra": "fr", "spa": "es", "jpn": "ja", "deu": "de", "tur": "tr", "hin": "hi", "por": "pt",
    "rus": "ru", "ita": "it", "pol": "pl", "kor": "ko", "ukr": "uk", "swe": "sv", "tha": "th", "hun": "hu",
    "tam": "ta", "lat": "la", "ron": "ro", "ces": "cs", "nor": "no", "nld": "nl", "ara": "ar", "mal": "ml",
    "dan": "da", "fin": "fi", "fas": "fa", "ind": "id", "cat": "ca", "nob": "no", "isl": "is", "urd": "ur",
    "ell": "el", "tel": "te", "kan": "kn",
    "yue": "cn",  # Cantonese, as TMDB names a Cantonese original language
    "zho": None,  # Chinese names no one language TMDB uses (zh is Mandarin, cn Cantonese)
    "und": None, "zxx": None, "myn": None, "dum": None, "tai": None,
}  # fmt: skip


@pytest.mark.parametrize(
    ("tag", "code"),
    [
        *MEASURED.items(),
        ("fre", "fr"),  # the bibliographic form of a code with two
        ("ger", "de"),
        ("nno", "no"),  # TMDB has one Norwegian
        ("chi", None),
        ("ENG", "en"),
        (" jpn ", "ja"),
        ("en", "en"),
        ("nb", None),  # a two-letter code TMDB never gives a film
        ("zh", None),
        ("mul", None),
        ("mis", None),
        ("xx", None),  # TMDB's own placeholder
        ("zz", None),
        ("", None),
        (None, None),
        (3, None),
    ],
)
def test_a_tag_reads_as_the_two_letter_code_tmdb_uses_or_as_untagged(tag: object, code: str | None) -> None:
    assert two_letter(tag) == code


def test_the_shipped_code_table_maps_only_to_two_letter_codes() -> None:
    table = json.loads((DATA / "languages.json").read_text(encoding="utf-8"))["codes"]
    assert table == codes()
    assert all(len(three) == 3 and len(two) == 2 and two.islower() for three, two in table.items())
    assert len(table) > 180 and not {"und", "zxx", "mul", "mis"} & set(table)


def test_a_copy_with_only_untagged_tracks_has_no_languages() -> None:
    assert audio_languages(["eng", None, "und", "fre"]) == frozenset({"en", "fr"})
    assert audio_languages([None, "und", "", "zxx"]) is None
    assert audio_languages([]) is None


def jellyfin_item(*languages: object) -> dict[str, Any]:
    streams = [
        {"Type": "Video"},
        *({"Type": "Audio", "Language": lang} for lang in languages),
        {"Type": "Subtitle", "Language": "spa"},
    ]
    return {"Id": "a" * 32, "Name": "Film", "ProviderIds": {"Tmdb": "5"}, "MediaStreams": streams}


def test_a_jellyfin_item_carries_its_audio_languages_and_never_its_subtitles() -> None:
    assert parse_film(jellyfin_item("eng", "fra")).audio == frozenset({"en", "fr"})
    assert parse_film(jellyfin_item(None, "und")).audio is None
    assert parse_film({"Id": "a" * 32, "Name": "Film"}).audio is None  # streams not asked for


def test_a_commentary_description_or_score_is_no_copy_in_its_language() -> None:
    """Shutter (2004) is Thai with an English commentary; counting the commentary put it before English-only viewers."""
    jellyfin = jellyfin_item("tha")
    jellyfin["MediaStreams"].append({"Type": "Audio", "Language": "eng", "Title": "Commentary by film critics"})
    assert parse_film(jellyfin).audio == frozenset({"th"})
    commentary = {"streamType": 2, "languageCode": "eng", "title": "Commentary by film critics"}
    thai = {"streamType": 2, "languageCode": "tha", "title": "5.1 Surround Mix"}
    assert audio_of({"Media": [{"Part": [{"Stream": [thai, commentary]}]}]}) == frozenset({"th"})


# Track names from the measured library: the first four are extras, the rest are the film itself.
@pytest.mark.parametrize(
    ("name", "extra"),
    [
        ("Commentary by Director Gabe Ibanez", True),
        ("English / DD 2.0 / 48 kHz / 192 kbps / 16-bit (Audio Descriptive)", True),
        ("Isolated Score & Effects", True),
        ("FLAC / 1.0 / 48 kHz / 717 kbps / 24-bit (Music Only Track)", True),
        ("5.1 Surround Mix", False),
        ("English / DTS-HD MA 2.0 / 48 kHz", False),
        (None, False),
    ],
)
def test_a_track_name_marks_an_extra_by_its_words(name: object, extra: bool) -> None:
    assert extra_track(name) is extra


def test_the_jellyfin_film_list_asks_for_streams_only_when_audio_is_asked_for(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    def answer(req: Any, timeout: float) -> Any:
        asked.append(req.full_url)
        return io.BytesIO(json.dumps({"Items": [jellyfin_item("jpn")]}).encode())

    monkeypatch.setattr("matinee.library.jellyfin.urllib.request.urlopen", answer)
    reader_ = JellyfinReader(SECRET_URL, SECRET_KEY)
    assert reader_.films()[0].audio == frozenset({"ja"})  # a fake server sends streams either way
    assert [reader_.films(audio=True)[0].audio] == [frozenset({"ja"})]
    plain, with_audio = asked  # one request each, either way
    assert "MediaStreams" not in plain and "MediaStreams" in with_audio


def test_with_audio_the_jellyfin_list_is_read_in_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    library = [{**jellyfin_item("eng"), "Id": f"{n:032x}"} for n in range(7)]
    asked: list[str] = []

    def answer(req: Any, timeout: float) -> Any:
        asked.append(req.full_url)
        start = int(req.full_url.split("StartIndex=")[1].split("&")[0])
        return io.BytesIO(json.dumps({"Items": library[start : start + 3]}).encode())

    monkeypatch.setattr("matinee.library.jellyfin.urllib.request.urlopen", answer)
    monkeypatch.setattr("matinee.library.jellyfin.AUDIO_PAGE", 3)
    films = JellyfinReader(SECRET_URL, SECRET_KEY).films(audio=True)
    assert [f.item_id for f in films] == [f"{n:032x}" for n in range(7)]
    assert ["StartIndex=0&Limit=3" in asked[0], "StartIndex=3&" in asked[1], "StartIndex=6&" in asked[2]] == [True] * 3
    assert len(asked) == 3


@pytest.mark.parametrize(("size", "pages"), [(6, 3), (7, 3)])  # 6 films: the empty third page ends it; 7: the short one
def test_the_paged_read_ends_on_a_short_page(monkeypatch: pytest.MonkeyPatch, size: int, pages: int) -> None:
    library = [{**jellyfin_item("eng"), "Id": f"{n:032x}"} for n in range(size)]
    asked: list[str] = []

    def answer(req: Any, timeout: float) -> Any:
        asked.append(req.full_url)
        start = int(req.full_url.split("StartIndex=")[1].split("&")[0])
        return io.BytesIO(json.dumps({"Items": library[start : start + 3]}).encode())

    monkeypatch.setattr("matinee.library.jellyfin.urllib.request.urlopen", answer)
    monkeypatch.setattr("matinee.library.jellyfin.AUDIO_PAGE", 3)
    assert len(JellyfinReader(SECRET_URL, SECRET_KEY).films(audio=True)) == size
    assert len(asked) == pages


def plex_details(key: str, *codes_: object) -> dict[str, Any]:
    streams = [
        {"streamType": 1},
        *({"streamType": 2, "languageCode": c} for c in codes_),
        {"streamType": 3, "languageCode": "spa"},
    ]
    return {
        "ratingKey": key,
        "Media": [{"Part": [{"Stream": streams}]}, {"Part": [{"Stream": [{"streamType": 2, "languageCode": "deu"}]}]}],
    }


def test_plex_reads_audio_from_each_films_details_in_batches_only_when_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = {
        **SECTIONS,
        "/library/metadata/390193,390193,8": {
            "MediaContainer": {"Metadata": [plex_details("390193", "eng", "und"), plex_details("8", None)]}
        },
    }
    plex_reader, plex = reader(monkeypatch, answers)
    plain = plex_reader.films()
    assert [f.audio for f in plain] == [None, None, None]
    assert not any("/library/metadata/" in r.full_url for r in plex.sent)
    heard = plex_reader.films(audio=True)
    assert [f.audio for f in heard] == [frozenset({"en", "de"}), frozenset({"en", "de"}), frozenset({"de"})]
    assert [r.get_method() for r in plex.sent] == ["GET"] * len(plex.sent)


def test_plex_asks_for_at_most_a_hundred_films_details_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    many = [{**ITEM, "ratingKey": str(n)} for n in range(1, 251)]
    answers: dict[str, Any] = {
        "/library/sections": {"MediaContainer": {"Directory": [{"key": "1", "type": "movie"}]}},
        "/library/sections/1/all?type=1&includeGuids=1": {"MediaContainer": {"Metadata": many}},
    }
    for start in (1, 101, 201):
        keys = [str(n) for n in range(start, min(start + 100, 251))]
        answers[f"/library/metadata/{','.join(keys)}"] = {
            "MediaContainer": {"Metadata": [plex_details(k, "fra") for k in keys]}
        }
    plex_reader, plex = reader(monkeypatch, answers)
    films = plex_reader.films(audio=True)
    assert len([r for r in plex.sent if "/library/metadata/" in r.full_url]) == 3
    assert {f.audio for f in films} == {frozenset({"fr", "de"})}


def film(tmdb: int, audio: frozenset[str] | None, item: str = "a") -> LibraryFilm:
    return LibraryFilm(item * 32, tmdb, f"Film {tmdb}", 2000, frozenset(), "", 90.0, 6.0, None, audio)


NO_GENOME = Scores(tags=(), rows={}, relevance=pd.DataFrame().to_numpy(), release="")


def test_the_table_keeps_every_copys_languages_and_none_for_a_film_with_no_copy(tmp_path: Path) -> None:
    films = [
        film(5, frozenset({"en"})),
        film(5, frozenset({"fr"}), "b"),
        film(6, None),
        film(6, None, "b"),  # two untagged copies: no languages, never an empty set
        film(7, frozenset({"ja"})),
    ]
    table, report = build_table(films, NO_GENOME, {}, datetime.now(UTC))
    assert table.films.audio.to_dict() == {5: frozenset({"en", "fr"}), 6: None, 7: frozenset({"ja"})}
    assert report.with_audio == 2
    write_table(table, tmp_path / "films.sqlite")
    assert load_table(tmp_path / "films.sqlite").films.audio.to_dict() == table.films.audio.to_dict()
    live, _ = with_live(table, [film(5, None), film(6, None)])  # the live read carries no audio: last night's stands
    assert live.films.audio.to_dict() == {5: frozenset({"en", "fr"}), 6: None}


def test_a_table_written_before_audio_was_kept_is_read_with_none(tmp_path: Path) -> None:
    table, _ = build_table([film(5, frozenset({"en"}))], NO_GENOME, {}, datetime.now(UTC))
    write_table(table, tmp_path / "films.sqlite")
    with sqlite3.connect(tmp_path / "films.sqlite") as db:
        db.execute("ALTER TABLE films DROP COLUMN audio")
    assert load_table(tmp_path / "films.sqlite").films.audio.to_dict() == {5: None}


def test_a_film_is_in_its_original_language_and_each_language_its_copy_is_tagged_with() -> None:
    films = pd.DataFrame(
        {
            "language": ["en", "fr", "xx", None, "ja"],
            "audio": [frozenset({"en", "fr"}), None, frozenset({"de"}), frozenset({"de"}), None],
        }
    )
    assert held(films) == [("de", 2), ("fr", 2), ("en", 1), ("ja", 1)]
