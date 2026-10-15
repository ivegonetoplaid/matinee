"""The languages a film is in, and the languages the film table holds, which the language preference offers.

A film's TMDB original language is a two-letter code. A library copy's audio
tracks carry their own tags, read by the nightly rebuild: a three-letter ISO
639-2 code in either of its forms ("fre" and "fra" both), which `two_letter`
turns into the two-letter code TMDB uses, from the shipped table
(`data/languages.json`). A tag with no two-letter form, among them the
placeholders "und" (undetermined), "zxx" (no linguistic content), "mul" and
"mis", or a code the table does not hold, counts as untagged, and so does a
track with no tag at all. A track whose name marks it as a commentary, an audio
description or the score alone is not the film in its language, and is passed
over: a Thai film with an English commentary has no English copy. TMDB's own placeholder for a film with no language
(`xx`) is never offered as a language, and a film carrying only it holds no
known language.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable
from functools import cache
from pathlib import Path

import pandas as pd

from matinee.reference import DATA

PLACEHOLDERS = frozenset({"xx"})
# The names a file gives a track that is not the film in a language. Measured on a 4,126-film library (2026-10-14):
# 866 commentaries, 14 isolated scores or music-only tracks and 4 audio descriptions; 28 films had a language only
# through one of them.
EXTRA_TRACK = re.compile(r"commentary|descripti|isolated|music only", re.IGNORECASE)


@cache
def codes(path: Path = DATA / "languages.json") -> dict[str, str]:
    """Each three-letter code with a two-letter form, and that form."""
    found = json.loads(path.read_text(encoding="utf-8"))["codes"]
    return {str(three): str(two) for three, two in found.items()}


def two_letter(tag: object) -> str | None:
    """The two-letter code an audio track's language tag names; None for an untagged track or a tag with no
    two-letter form."""
    if not isinstance(tag, str):
        return None
    word = tag.strip().lower()
    if len(word) == 2 and word in codes().values():
        return word
    return codes().get(word)


def extra_track(name: object) -> bool:
    """Whether an audio track's name marks it as a commentary, an audio description or the score alone."""
    return isinstance(name, str) and EXTRA_TRACK.search(name) is not None


def audio_languages(tags: Iterable[object]) -> frozenset[str] | None:
    """The languages a copy's audio tracks are tagged with; None when every track is untagged, or there are none."""
    found = frozenset(code for code in map(two_letter, tags) if code is not None)
    return found or None


def heard_only(original: object, audio: object, ticked: frozenset[str]) -> list[str]:
    """The ticked languages a library copy's audio is in, when the film's own language is known and not ticked: the
    languages it reached the viewer in only through its copy. Empty otherwise."""
    if not ticked or not isinstance(audio, frozenset) or not isinstance(original, str):
        return []
    if not original or original in PLACEHOLDERS or original in ticked:
        return []
    return sorted(audio & ticked)


def held(films: pd.DataFrame) -> list[tuple[str, int]]:
    """Each language the films are in, with how many films are in it, most films first, then by code. A film is in
    its original language and in each language its library copy's audio tracks are tagged with, once for each."""
    counts: Counter[str] = Counter()
    for original, tracks in zip(films["language"], films["audio"], strict=True):
        known = set(tracks) if isinstance(tracks, frozenset) else set()
        if isinstance(original, str) and original and original not in PLACEHOLDERS:
            known.add(original)
        counts.update(known)
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
