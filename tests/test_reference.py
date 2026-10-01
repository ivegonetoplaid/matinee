"""The reference statistics: which films form a tree's reference, and what is measured over them.

The fixture is built so that the wrong statistic gives a different number: every
score has two tags whose mean differs from their maximum and from the first tag,
the gore values are uneven so percentile methods disagree, one film sits
exactly on the floor, one passes only the
second floor, and one carries the tree's genre only as its second genre.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from matinee.genome import Genome, GenomeError, load_genome
from matinee.reference import (
    DATA,
    Floor,
    ReferenceError,
    ScaleSpec,
    TreeSpec,
    compute,
    from_json,
    load_reference,
    load_specs,
    problems,
    reference_films,
    spec_of,
    to_json,
)

TAGS = ("scary", "frightening", "tense", "gore_a", "gore_b", "fun_a", "fun_b")
ROWS = [
    [0.9, 0.7, 0.0, 0.1, 0.3, 0.0, 0.2],  # 1 Horror: fear 0.8, gore 0.2, fun 0.1
    [0.2, 0.2, 0.8, 0.5, 0.3, 0.2, 0.0],  # 2 Thriller: fear 0.2, passes only on tense; gore 0.4, fun 0.1
    [0.5, 0.5, 0.0, 0.0, 0.2, 0.1, 0.1],  # 3 Horror: fear exactly on the floor; gore 0.1, fun 0.1
    [0.3, 0.1, 0.1, 0.9, 0.9, 0.5, 0.5],  # 4 Horror, under both floors
    [0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9],  # 5 Comedy, wrong genre
    [0.9, 0.9, 0.0, 0.9, 0.7, 1.0, 0.8],  # 6 Comedy|Thriller: in by its second genre; gore 0.8, fun 0.9
]
GENRES = {1: "Horror", 2: "Thriller", 3: "Horror", 4: "Horror", 5: "Comedy", 6: "Comedy|Thriller"}
GORE_CUTS = (0.24, 0.68)  # linear percentiles 40 and 90 of 0.1, 0.2, 0.4, 0.8


def genome() -> Genome:
    return Genome(
        release="test",
        movie_ids=np.arange(1, 7),
        tags=TAGS,
        relevance=np.array(ROWS, dtype=np.float32),
        tmdb_by_movie={m: 100 + m for m in range(1, 7)},
        genres_by_movie={m: frozenset(g.split("|")) for m, g in GENRES.items()},
    )


def spec() -> TreeSpec:
    return TreeSpec(
        tree="horror",
        genres=("Horror", "Thriller"),
        floor_any=(Floor("fear", ("scary", "frightening"), 0.5), Floor("thrill", ("tense",), 0.6)),
        scales={"gore": ScaleSpec("gore", ("gore_a", "gore_b"), (40.0, 90.0))},
    )


def test_reference_is_any_genre_and_any_floor_inclusive() -> None:
    assert reference_films(genome(), spec()).tolist() == [True, True, True, False, False, True]


def test_scale_cuts_are_linear_percentiles_of_tag_means() -> None:
    cuts = compute(genome(), [spec()]).trees["horror"].scales["gore"].cuts
    assert cuts == pytest.approx(GORE_CUTS, abs=1e-6)


def test_cut_fixture_separates_percentile_methods() -> None:
    """Guards the fixture itself: the other methods must not agree with the expected cuts."""
    gore = np.array([0.1, 0.2, 0.4, 0.8])
    for method in ("nearest", "lower", "higher"):
        assert not np.allclose(np.percentile(gore, [40, 90], method=method), GORE_CUTS)
    assert not np.allclose(np.percentile(gore, [60, 10]), GORE_CUTS)


def test_the_reference_counts_its_films() -> None:
    assert compute(genome(), [spec()]).trees["horror"].films == 4


def test_no_floor_takes_every_genre_film() -> None:
    assert reference_films(genome(), TreeSpec("any", ("Horror",), (), {})).sum() == 3


def test_json_round_trip_rerun_identical_and_six_places() -> None:
    ref = compute(genome(), [spec()])
    text = to_json(ref)
    assert to_json(compute(genome(), [spec()])) == text
    assert from_json(text) == ref
    cuts = json.loads(text)["trees"]["horror"]["scales"]["gore"]["cuts"]
    assert all(round(c, 6) == c for c in cuts)


def _changed(**kw: Any) -> TreeSpec:
    return replace(spec(), **kw)


@pytest.mark.parametrize(
    "changed",
    [
        _changed(scales={"gore": ScaleSpec("gore", ("gore_a",), (40.0, 90.0))}),
        _changed(scales={"gore": ScaleSpec("gore", ("gore_a", "gore_b"), (40.0, 95.0))}),
        _changed(scales={"gore": spec().scales["gore"], "extra": ScaleSpec("x", ("fun_a",), (50.0,))}),
        _changed(genres=("Horror",)),
        _changed(floor_any=(Floor("fear", ("scary", "frightening"), 0.4),)),
        TreeSpec("action", ("Action",), (), {}),
    ],
)
def test_problems_flags_every_uncovered_definition(changed: TreeSpec) -> None:
    ref = compute(genome(), [spec()])
    assert problems(ref, [spec()]) == []
    assert problems(ref, [changed])


def test_shipped_reference_covers_every_tree() -> None:
    """Fails when a tree file changes and tools/build_reference.py was not rerun."""
    assert problems(load_reference(), load_specs(DATA / "trees")) == []


def _doc(reference: dict[str, object]) -> dict[str, object]:
    return {
        "scores": {"fear": ["scary", "frightening"], "thrill": ["tense"], "gore": ["gore_a", "gore_b"]},
        "reference": reference,
        "scales": {"gore": {"score": "gore", "percentiles": [40, 90]}},
    }


def test_spec_of_reads_tree_file_sections() -> None:
    doc = _doc({"movielens_genres": ["Horror", "Thriller"], "floor_any": {"fear": 0.5, "thrill": 0.6}})
    assert spec_of("horror", doc) == spec()
    assert spec_of("comedy", {"questions": []}) is None
    floorless = spec_of("western", _doc({"movielens_genres": ["Western"], "floor_any": {}}))
    assert floorless is not None and floorless.floor_any == ()


@pytest.mark.parametrize(
    "reference",
    [
        {"movielens_genres": ["Horror"], "floor": {"fear": 0.5}},
        {"movielens_genres": ["Horror"]},
        {"movielens_genres": ["Horror"], "floor_any": {"undefined": 0.2}},
    ],
)
def test_spec_of_refuses_misspelt_or_undefined(reference: dict[str, object]) -> None:
    with pytest.raises(ReferenceError):
        spec_of("bad", _doc(reference))


def test_unknown_tag_is_refused() -> None:
    with pytest.raises(GenomeError):
        genome().mean_of(["no such tag"])


def _write_dataset(ml: Path, values: list[float], date: str) -> None:
    ml.mkdir(exist_ok=True)
    (ml / "README.txt").write_text(f"Intro.\nThis dataset was generated on {date}.\n")
    (ml / "genome-tags.csv").write_text("tagId,tag\n1,alpha\n2,beta\n")
    rows = [f"{m},{t},{values[(m - 1) * 2 + t - 1]}" for m in (1, 2) for t in (1, 2)]
    (ml / "genome-scores.csv").write_text("movieId,tagId,relevance\n" + "\n".join(rows) + "\n")
    (ml / "links.csv").write_text("movieId,imdbId,tmdbId\n1,1,501\n2,2,502\n")
    (ml / "movies.csv").write_text("movieId,title,genres\n1,A (2000),Horror|Thriller\n2,B (2001),Comedy\n")


def test_loader_reads_genres_release_and_matrix(tmp_path: Path) -> None:
    _write_dataset(tmp_path, [0.1, 0.9, 0.2, 0.8], "March 1, 2026")
    g = load_genome(tmp_path)
    assert g.release == "MovieLens ml-latest, generated March 1, 2026"
    assert g.genres_by_movie[1] == frozenset({"Horror", "Thriller"})
    assert g.tmdb_by_movie == {1: 501, 2: 502}
    assert g.mean_of(["alpha", "beta"]).tolist() == pytest.approx([0.5, 0.5])
    assert g.relevance[1].tolist() == pytest.approx([0.2, 0.8])


def test_cache_is_rebuilt_when_the_source_changes_even_to_an_older_time(tmp_path: Path) -> None:
    ml, cache = tmp_path / "ml", tmp_path / "cache.npz"
    _write_dataset(ml, [0.1, 0.9, 0.2, 0.8], "March 1, 2026")
    assert load_genome(ml, cache).relevance[0].tolist() == pytest.approx([0.1, 0.9])
    _write_dataset(ml, [0.3, 0.7, 0.4, 0.6], "April 1, 2026")
    os.utime(ml / "genome-scores.csv", (1_000_000, 1_000_000))
    assert load_genome(ml, cache).relevance[0].tolist() == pytest.approx([0.3, 0.7])


def test_unstamped_cache_is_rebuilt(tmp_path: Path) -> None:
    ml, cache = tmp_path / "ml", tmp_path / "cache.npz"
    _write_dataset(ml, [0.1, 0.9, 0.2, 0.8], "March 1, 2026")
    np.savez(cache, movies=np.array([9]), relevance=np.zeros((1, 2), dtype=np.float32))
    assert load_genome(ml, cache).movie_ids.tolist() == [1, 2]
