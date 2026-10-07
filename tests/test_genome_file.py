"""The genome scores Matinee ships: every tag a reader names is in them, and they read back exactly."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from matinee.genome import Genome, GenomeError, Scores
from matinee.genome_file import GENOME_FILE, load_scores, tags_read, write_scores
from matinee.reference import DATA, REFERENCE_PATH, load_reference
from matinee.table import FilmTable
from matinee.trees import load_trees


def test_the_shipped_scores_hold_every_tag_a_reader_names_for_every_genome_film() -> None:
    shipped = load_scores()
    assert set(tags_read()) <= set(shipped.tags)
    assert len(shipped.rows) >= 16_000  # every genome film with a TMDB id, not only the labelled ones
    assert shipped.relevance.shape == (len(shipped.rows), len(shipped.tags))
    reference = load_reference()
    assert shipped.release == reference.source  # the gore cuts were measured on this release
    licence = json.loads(REFERENCE_PATH.read_text())["licence"]
    assert json.loads(GENOME_FILE.read_text())["licence"] == licence


def test_every_reader_finds_its_tags_in_a_table_built_from_the_shipped_scores() -> None:
    shipped = load_scores()
    ids = sorted(shipped.rows)[:5]
    films = pd.DataFrame(index=pd.Index(ids, name="tmdb"))
    relevance = shipped.relevance[[shipped.rows[t] for t in ids]]
    table = FilmTable(films, shipped.tags, relevance, datetime.now(UTC), None, shipped.release)
    for tree in load_trees().values():
        for tags in tree.scores.values():
            table.mean_of(list(tags))
    for tag in json.loads((DATA / "answer_key.json").read_text())["list_tags"]["tags"]:
        table.tag(tag)


def test_a_tag_a_tree_names_is_a_tag_read(tmp_path: Path) -> None:
    data = tmp_path / "data"
    shutil.copytree(DATA / "trees", data / "trees")
    shutil.copy(DATA / "answer_key.json", data / "answer_key.json")
    assert "jump scares" not in tags_read(data)
    horror = json.loads((data / "trees" / "horror.json").read_text())
    horror["scores"]["fear"].append("jump scares")
    (data / "trees" / "horror.json").write_text(json.dumps(horror))
    assert "jump scares" in tags_read(data)
    assert "afi 100" in tags_read(data) and "fear" not in tags_read(data)  # list tags, never score names


def test_scores_read_back_as_the_same_float32_at_five_places(tmp_path: Path) -> None:
    published = np.array([[0.03199999999999997, 0.02225], [0.99975, 1e-05]], dtype=np.float32)
    scores = Scores("test", ("a", "b"), {578: 0, 11: 1}, published)
    write_scores(scores, tmp_path / "g.json", "terms")
    back = load_scores(tmp_path / "g.json")
    assert back.tags == ("a", "b") and back.release == "test"
    for tmdb, row in scores.rows.items():
        assert np.array_equal(back.relevance[back.rows[tmdb]], published[row])
    assert json.loads((tmp_path / "g.json").read_text())["licence"] == "terms"


@pytest.mark.parametrize("films", [{"1": [0.1]}, {"1": [0.1, "x"]}, {"one": [0.1, 0.2]}])
def test_malformed_scores_are_refused(tmp_path: Path, films: dict[str, object]) -> None:
    (tmp_path / "g.json").write_text(json.dumps({"source": "s", "tags": ["a", "b"], "films": films}))
    with pytest.raises(GenomeError):
        load_scores(tmp_path / "g.json")
    with pytest.raises(GenomeError):
        load_scores(tmp_path / "absent.json")


def test_scores_key_the_genome_by_tmdb_id_and_the_first_movie_wins() -> None:
    genome = Genome(
        release="r",
        movie_ids=np.array([1, 2, 3, 4]),
        tags=("x", "y", "z"),
        relevance=np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9], [0.0, 0.0, 0.0]], dtype=np.float32),
        tmdb_by_movie={1: 11, 2: 22, 3: 11},
        genres_by_movie={},
    )
    scores = genome.scores(("z", "x"))
    assert set(scores.rows) == {11, 22}  # movie 4 has no TMDB id
    assert scores.relevance[scores.rows[11]].tolist() == pytest.approx([0.3, 0.1])
    assert scores.relevance[scores.rows[22]].tolist() == pytest.approx([0.6, 0.4])
