"""The pick's tags: the shipped words per film, the skip list, and what reaches a pick."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from matinee.genome import Genome
from matinee.reference import REFERENCE_PATH, load_reference
from matinee.tags import SHOWN, SKIP_FILE, TAGS_FILE, WORDS_PER_FILM, TagsError, load_tags, read_skip, write_tags


def test_no_skip_list_word_reaches_any_films_tags_and_every_covered_film_shows_four() -> None:
    skip = read_skip()
    tags = load_tags()
    assert len(tags.shown) >= 16_000  # every genome film with a TMDB id
    assert all(not set(t) & skip for t in tags.shown.values())
    assert all(len(t) == SHOWN for t in tags.shown.values())  # the shipped list leaves four for every film
    assert tags.of(609) == ["supernatural", "ghosts", "creepy", "frightening"]  # Poltergeist


def test_a_film_the_genome_does_not_cover_has_no_tags() -> None:
    assert load_tags().of(10_000_000) == []


def test_the_skip_list_holds_each_group_the_decision_names_and_leaves_the_words_a_viewer_wants() -> None:
    skip = read_skip()
    named = {"criterion", "imdb top 250", "based on a book", "oscar", "comedy", "nudity", "visually appealing"}
    assert named <= skip, sorted(named - skip)
    wanted = {"supernatural", "ghosts", "time travel", "gay", "friendship", "predictable"}
    assert not wanted & skip, sorted(wanted & skip)


def test_every_skip_list_entry_is_a_genome_word_so_none_is_a_silent_typo() -> None:
    words = set(json.loads(TAGS_FILE.read_text(encoding="utf-8"))["words"])
    assert read_skip() <= words and len(read_skip()) >= 4


def test_the_shipped_tags_carry_the_licence_the_release_and_room_for_a_longer_skip_list() -> None:
    doc = json.loads(TAGS_FILE.read_text(encoding="utf-8"))
    assert doc["licence"] == json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))["licence"]
    assert doc["source"] == load_reference().source
    assert {len(w) for w in doc["films"].values()} == {WORDS_PER_FILM}
    assert TAGS_FILE.stat().st_size < 20_000_000  # far under GitHub's 100 MB file limit


def test_an_edited_skip_list_takes_effect_on_the_next_read(tmp_path: Path) -> None:
    longer = tmp_path / "skip.txt"
    longer.write_text(SKIP_FILE.read_text(encoding="utf-8") + "\n  ghosts  \n# a note\n", encoding="utf-8")
    poltergeist = load_tags(skip_path=longer).of(609)
    assert "ghosts" not in poltergeist and len(poltergeist) == SHOWN


def test_written_tags_keep_each_films_strongest_words_in_order_and_the_first_movie_wins(tmp_path: Path) -> None:
    genome = Genome(
        release="r",
        movie_ids=np.array([1, 2, 3]),
        tags=("x", "y", "z"),
        relevance=np.array([[0.1, 0.9, 0.5], [0.8, 0.2, 0.3], [0.0, 0.0, 1.0]], dtype=np.float32),
        tmdb_by_movie={1: 11, 2: 22, 3: 11},
        genres_by_movie={},
    )
    write_tags(genome, tmp_path / "t.json", "terms")
    (tmp_path / "skip.txt").write_text("x\n", encoding="utf-8")
    back = load_tags(tmp_path / "t.json", tmp_path / "skip.txt")
    assert back.of(11) == ["y", "z"] and back.of(22) == ["z", "y"]
    assert json.loads((tmp_path / "t.json").read_text())["licence"] == "terms"


@pytest.mark.parametrize("films", [{"1": [7]}, {"1": "x"}, {"one": [0]}, [[0]]])
def test_malformed_tags_and_a_missing_skip_list_are_refused(tmp_path: Path, films: object) -> None:
    (tmp_path / "t.json").write_text(json.dumps({"source": "s", "words": ["a", "b"], "films": films}))
    (tmp_path / "skip.txt").write_text("", encoding="utf-8")
    with pytest.raises(TagsError):
        load_tags(tmp_path / "t.json", tmp_path / "skip.txt")
    with pytest.raises(TagsError):
        load_tags(TAGS_FILE, tmp_path / "absent.txt")


def test_a_skip_list_saved_in_another_encoding_is_refused_as_unreadable(tmp_path: Path) -> None:
    (tmp_path / "skip.txt").write_bytes(b"caf\xe9\n")
    with pytest.raises(TagsError):
        load_tags(TAGS_FILE, tmp_path / "skip.txt")
