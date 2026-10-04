"""Matinee's lines for a pick, read from data/quips.json, and the rules every line keeps.

Each category (universal, or a tree or mode by its file name) may hold reveal lines, nope lines and rush
lines.
The caps are character counts: no single line may exceed
`line`, and a nope line and a reveal line shown together may not exceed `pair`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from matinee.reference import DATA

QUIPS_PATH = DATA / "quips.json"
UNIVERSAL = "universal"
QUOTES = "\"'“”‘’«»"
# Words a sentence-case line may still capitalise: "I" and its contractions.
_ALWAYS_CAPITAL = re.compile(r"^I('(m|d|ve|ll|s))?$")


class QuipsError(ValueError):
    """The quips file is missing or not the shape Matinee reads."""


class QuipSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reveal: tuple[str, ...] = ()
    nope: tuple[str, ...] = ()
    rush: tuple[str, ...] = ()


class Caps(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    line: int
    pair: int


class Quips(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    note: str = ""
    caps: Caps
    categories: dict[str, QuipSet]

    @model_validator(mode="after")
    def _universal_holds_both_sets(self) -> Quips:
        """Every set falls back on universal's, so universal must hold lines of every kind."""
        universal = self.categories.get(UNIVERSAL)
        if universal is None or not universal.reveal or not universal.nope or not universal.rush:
            raise ValueError(
                f"the {UNIVERSAL!r} category must hold reveal, nope and rush lines, which every set falls back on"
            )
        return self


def load_quips(path: Path = QUIPS_PATH) -> Quips:
    """The quips file, or QuipsError naming the file and what was wrong with it."""
    try:
        return Quips.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise QuipsError(f"{path}: {exc}") from exc


def in_title_case(line: str) -> bool:
    """Whether a line capitalises the words after its first, as a title does. A word in capitals for
    emphasis ("DO IT"), and "I", do not count; a line needs two such words after its first to read as
    a title."""
    words = re.findall(r"[A-Za-z][A-Za-z']*", line)[1:]
    counted = [w for w in words if not (w.isupper() or _ALWAYS_CAPITAL.match(w))]
    return len(counted) >= 2 and all(w[0].isupper() for w in counted)


def line_problems(line: str, cap: int) -> list[str]:
    """What is wrong with one line, each naming the line."""
    problems = []
    if len(line) > cap:
        problems.append(f"{line!r} has {len(line)} characters; the cap for one line is {cap}")
    if line[:1] in QUOTES and line[-1:] in QUOTES:
        problems.append(f"{line!r} is wrapped in quotation marks")
    if in_title_case(line):
        problems.append(f"{line!r} is in title case; lines are in sentence case")
    return problems


def quip_problems(quips: Quips, categories: set[str]) -> list[str]:
    """Every rule the file breaks, each naming what breaks it. `categories` are the trees and modes
    that exist, by file name."""
    known = categories | {UNIVERSAL}
    problems = [f"category {name!r} is not a tree or mode" for name in quips.categories if name not in known]
    for sets in quips.categories.values():
        for line in (*sets.reveal, *sets.nope, *sets.rush):
            problems.extend(line_problems(line, quips.caps.line))
    return problems
