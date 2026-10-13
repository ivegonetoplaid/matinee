"""The languages the film table holds, which the language preference offers.

A film holds its TMDB original language, a two-letter code. TMDB's own
placeholder for a film with no language (`xx`) is never offered as a language,
and a film carrying only it holds no known language.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd

PLACEHOLDERS = frozenset({"xx"})


def held(films: pd.DataFrame) -> list[tuple[str, int]]:
    """Each language the films hold, with how many films hold it: most films first, then by code."""
    counts = Counter(str(code) for code in films["language"].dropna() if str(code) and str(code) not in PLACEHOLDERS)
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
