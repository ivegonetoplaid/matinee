"""The pick's lines (data/quips.json) and the rules each line keeps."""

from __future__ import annotations

import pytest

from matinee.quips import Caps, Quips, QuipSet, load_quips, quip_problems
from matinee.reference import DATA

CATEGORIES = {p.stem for p in (DATA / "trees").glob("*.json")} | {p.stem for p in (DATA / "modes").glob("*.json")}


def _with(line: str = "This one should do nicely.", **extra: object) -> Quips:
    return Quips.model_validate(
        {"caps": {"line": 64, "pair": 76}, "categories": {"universal": {"reveal": [line]}}, **extra},
    )


def test_the_quips_file_keeps_every_rule() -> None:
    assert quip_problems(load_quips(), CATEGORIES) == []


def test_the_caps_are_the_measured_ones() -> None:
    # Set by rendering every approved line as the pick line; raising one to admit a long line fails here.
    assert load_quips().caps == Caps(line=64, pair=76)


def test_the_file_holds_every_approved_line_and_standup_borrows_comedy() -> None:
    quips = load_quips()
    counts = {name: (len(s.reveal), len(s.nope)) for name, s in quips.categories.items()}
    assert counts == {"universal": (16, 22), "horror": (18, 19), "comedy": (22, 29)}
    assert quips.borrow == {"standup": "comedy"}


@pytest.mark.parametrize(
    ("line", "complaint"),
    [
        ("x" * 65, "the cap for one line is 64"),
        ('"How about this one?"', "wrapped in quotation marks"),
        ("“How about this one?”", "wrapped in quotation marks"),
        ("The Reel Has Spoken.", "title case"),
    ],
)
def test_a_line_that_breaks_a_rule_is_refused_by_name(line: str, complaint: str) -> None:
    problems = quip_problems(_with(line), CATEGORIES)
    assert len(problems) == 1
    assert repr(line) in problems[0]
    assert complaint in problems[0]


@pytest.mark.parametrize(
    "line", ["That one doesn't DO IT for you, huh?", "No? I SAID NO.", "I think this is the one.", "x" * 64]
)
def test_emphasis_i_and_a_line_at_the_cap_pass(line: str) -> None:
    assert quip_problems(_with(line), CATEGORIES) == []


def test_a_category_or_a_borrowing_that_is_not_a_tree_or_mode_is_refused() -> None:
    quips = _with(borrow={"cartoons": "universal", "standup": "sitcom"})
    quips = quips.model_copy(update={"categories": {**quips.categories, "sitcom2": QuipSet(reveal=("Fine.",))}})
    problems = quip_problems(quips, CATEGORIES)
    assert "category 'sitcom2' is not a tree or mode" in problems
    assert "borrowing category 'cartoons' is not a tree or mode" in problems
    assert "'standup' borrows from 'sitcom', which holds no lines" in problems
