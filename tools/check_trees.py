"""Check Matinee's trees against the answer key and the reachability rule.

Reads the offline film table the nightly rebuild writes and builds every tree
through the engine (the same module the web page uses). A tree with a file counts
as a film's home only where some complete path of its answers reaches the film.
It reports:

1. Reachability: every film must have at least one home.
2. Expected homes: every film must be reachable through a tree its own genre tags
   point at, not only by accident.
3. The answer key: list films (genome list tags) and hand fixtures in
   data/answer_key.json, plus the horror and comedy fixture files. A fixture may
   also name the gore pail a horror film must land in, or pails it must not.
4. The gore scale: no unpinned film without a genome entry may reach "None. I'm
   squeamish." or "RIP AND TEAR.".
5. The data: every film carries TMDB facts, and the shipped reference statistics
   cover every tree file.
6. Answer coverage: every film a tree's pool holds is reachable through its answers.

Reads nothing live. Usage: python3 tools/check_trees.py [--table FILE]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from matinee.engine import Catalog, EngineError, load_catalog, reachable, scale_members
from matinee.pools import House
from matinee.reference import DATA
from matinee.table import FilmTable, load_table

DEFAULT_TABLE = Path.home() / ".local/share/matinee/films.sqlite"
GORE_PROMISES = ("spotless", "rip")  # pails an unknown film could break the promise of
# Trees a film's genre tag is expected to lead to.
EXPECTED = {
    "Horror": {"horror"},
    "Comedy": {"comedy"},
    "Action": {"action"},
    "Adventure": {"action", "drama", "kids", "sleep", "fantasy"},
    "Drama": {"drama"},
    "Crime": {"drama", "action", "horror", "thriller"},
    "Mystery": {"thriller", "drama", "action", "horror"},
    "Thriller": {"thriller", "drama", "action", "horror"},
    "Romance": {"drama", "comedy"},
    "Science Fiction": {"action", "drama", "horror", "kids"},
    "Fantasy": {"fantasy", "action", "sleep", "kids", "drama", "horror"},
    "War": {"drama", "action"},
    "History": {"drama", "action"},
    "Western": {"western"},
    "Documentary": {"documentary", "standup"},
    "Animation": {"kids"},
    "Family": {"kids"},
    "Music": {"drama", "comedy", "documentary"},
    "TV Movie": {"horror", "comedy", "action", "drama", "kids"},
}
Pools = dict[str, pd.Series]


@dataclass
class Report:
    failures: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def say(self, text: str) -> None:
        self.lines.append(text)

    def fail(self, text: str) -> None:
        self.failures.append(text)
        self.lines.append(f"FAIL {text}")


def _label(table: FilmTable, tmdb: int) -> str:
    f = table.films.loc[tmdb]
    return f"{f['name']} ({f.year})"


def homes_of(tmdb: int, pools: Pools) -> set[str]:
    """Trees and modes holding the film; kids age bands are reported, not counted as homes."""
    return {name for name, pool in pools.items() if ":" not in name and pool.get(tmdb, False)}


def band_of(tmdb: int, pools: Pools) -> str:
    """The youngest kids band offering the film, or an empty string."""
    for band in ("kids:little", "kids:family", "kids"):
        if pools[band].get(tmdb, False):
            return band.replace("kids:", "").replace("kids", "older")
    return ""


def expected_for(genres: frozenset[str]) -> set[str]:
    out: set[str] = set()
    for g in genres:
        out |= EXPECTED.get(g, set())
    return out


def check_reachability(table: FilmTable, pools: Pools, report: Report) -> None:
    reached = pd.concat([p for n, p in pools.items() if ":" not in n], axis=1).any(axis=1)
    report.say(f"\n== reachability: {int(reached.sum())} of {len(table.films)} films have a home ==")
    for name, pool in pools.items():
        report.say(f"  {name:15s} {int(pool.sum()):5d}")
    for tmdb in table.films.index[~reached]:
        genres = "/".join(sorted(table.films.loc[tmdb].genres)) or "none"
        report.fail(f"unreachable: {_label(table, tmdb)} genres={genres}")


def check_expected(table: FilmTable, pools: Pools, report: Report) -> None:
    misses = []
    for tmdb, genres in zip(table.films.index.tolist(), table.films.genres.tolist(), strict=True):
        want = expected_for(genres)
        if want and not (homes_of(tmdb, pools) & want):
            homes = sorted(homes_of(tmdb, pools)) or "nothing"
            misses.append(f"{_label(table, tmdb)} {'/'.join(sorted(genres))} -> in {homes}")
    report.say(f"\n== expected homes: {len(misses)} films not reachable through their own genres ==")
    for m in misses:
        report.fail(f"unexpected home: {m}")


def check_lists(table: FilmTable, pools: Pools, key: dict[str, Any], report: Report) -> None:
    thresholds = key["list_tags"].get("thresholds", {})
    for tag in key["list_tags"]["tags"]:
        threshold = thresholds.get(tag, key["list_tags"]["threshold"])
        if tag not in table.tags:
            report.fail(f"list tag missing from genome: {tag}")
            continue
        members = [int(t) for t in table.films.index[table.tag(tag).ge(threshold)]]
        genres = table.films.genres
        bad = [t for t in members if not (homes_of(t, pools) & expected_for(genres[t]))]
        report.say(
            f"\n== list '{tag}': {len(members) - len(bad)} of {len(members)} reachable through their own genres =="
        )
        for t in bad:
            report.fail(f"list '{tag}': {_label(table, t)} -> in {sorted(homes_of(t, pools)) or 'nothing'}")


def _check_gore(entry: dict[str, Any], gore: pd.DataFrame, report: Report) -> None:
    tmdb, title = entry["tmdb"], entry["title"]
    bands = {b for b in gore.columns if gore.loc[tmdb, b]}
    want = entry.get("gore_band")
    if want and bands != {want}:
        report.fail(f"'{title}' must land in the {want} pail; is in {sorted(bands) or 'none'}")
    for band in entry.get("gore_not", []):
        if band in bands:
            report.fail(f"'{title}' must not be in the {band} pail")


def check_film(entry: dict[str, Any], table: FilmTable, pools: Pools, gore: pd.DataFrame, report: Report) -> None:
    tmdb, title = entry["tmdb"], entry["title"]
    if tmdb not in table.films.index:
        report.fail(f"fixture '{title}' tmdb {tmdb} not in library")
        return
    held = table.films.loc[tmdb]["name"]
    if held.casefold() != title.casefold():
        report.fail(f"fixture '{title}' tmdb {tmdb} is '{held}' in the library; check the id")
        return
    homes = homes_of(tmdb, pools)
    for tree in entry.get("must_reach", []):
        if tree not in homes:
            report.fail(f"'{title}' must reach {tree}; in {sorted(homes) or 'nothing'}")
    for tree in entry.get("must_not", []):
        if tree in homes:
            report.fail(f"'{title}' must not be in {tree}")
    want_band = entry.get("kids_band")
    if want_band and band_of(tmdb, pools) != want_band:
        report.fail(
            f"'{title}' should first be offered to {want_band} kids; is {band_of(tmdb, pools) or 'not in kids'}"
        )
    if "gore_band" in entry or "gore_not" in entry:
        _check_gore(entry, gore, report)


def tmdb_by_title(title: str, table: FilmTable, report: Report) -> int | None:
    """The one library film with this exact title, or None with a failure recorded."""
    hits = table.films.index[table.films["name"].str.casefold() == title.casefold()]
    if len(hits) != 1:
        report.fail(f"fixture '{title}' matches {len(hits)} library films by title; add a tmdb id")
        return None
    return int(hits[0])


def tree_fixture_entries(table: FilmTable, report: Report) -> list[dict[str, Any]]:
    """The horror and comedy fixture films as must_reach entries for their own tree."""
    entries = []
    for fname, tree in (("horror.json", "horror"), ("comedy.json", "comedy")):
        for f in json.loads((DATA / "fixtures" / fname).read_text())["films"]:
            tmdb = int(f["tmdb"]) if "tmdb" in f else tmdb_by_title(f["title"], table, report)
            if tmdb is not None:
                entries.append({"title": f["title"], "tmdb": tmdb, "must_reach": [tree]})
    return entries


def check_fixtures(table: FilmTable, pools: Pools, gore: pd.DataFrame, key: dict[str, Any], report: Report) -> None:
    before = len(report.failures)
    entries = key["films"] + tree_fixture_entries(table, report)
    for entry in entries:
        check_film(entry, table, pools, gore, report)
    failed = len(report.failures) - before
    report.say(f"\n== fixtures: {failed} failures across {len(entries)} fixture films ==")


def check_pins_in_key(house: House, key: dict[str, Any], report: Report) -> None:
    """Every house pin must be an answer-key fixture asserting the pinned placement (decision 46)."""
    fixture = {int(e["tmdb"]): e for e in key["films"]}
    wants: list[tuple[int, str, bool]] = []
    wants += [(t, f"kids_band {b}", fixture.get(t, {}).get("kids_band") == b) for t, b in house.kids_pins.items()]
    for tree, ids in house.tree_pins.items():
        wants += [(t, f"must_reach {tree}", tree in fixture.get(t, {}).get("must_reach", [])) for t in ids]
    for (tree, _), ids in house.payoff_pins.items():
        wants += [(t, f"must_reach {tree}", tree in fixture.get(t, {}).get("must_reach", [])) for t in ids]
    for (_, _, band), ids in house.scale_pins.items():
        wants += [(t, f"gore_band {band}", fixture.get(t, {}).get("gore_band") == band) for t in ids]
    for tmdb, want, held in sorted(wants):
        if not held:
            report.fail(f"house pin tmdb {tmdb} needs an answer-key fixture asserting {want}")


def check_gore(table: FilmTable, pools: Pools, house: House, gore: pd.DataFrame, report: Report) -> None:
    horror = pools["horror"]
    pinned = set().union(*(ids for (t, s, _), ids in house.scale_pins.items() if (t, s) == ("horror", "gore")))
    unknown = horror & ~table.has_genome() & ~table.films.index.isin(list(pinned))
    sizes = ", ".join(f"{b} {int((gore[b] & horror).sum())}" for b in gore.columns)
    report.say(f"\n== gore pails over {int(horror.sum())} horror films: {sizes} ==")
    for band in GORE_PROMISES:
        for tmdb in table.films.index[unknown & gore[band]]:
            report.fail(f"gore: {_label(table, int(tmdb))} has no genome entry and no pin but is in {band}")


def check_answer_coverage(cat: Catalog, pools: Pools, report: Report) -> dict[str, pd.Series]:
    """Every film a tree's pool holds must be reachable through some complete path of its answers.

    Returns each tree file's reachable films keyed by its pool name, which the other checks use as that
    tree's home, so they judge what a viewer can actually be offered.
    """
    reached: dict[str, pd.Series] = {}
    index = cat.table.films.index
    report.say("\n== answer coverage: films in a tree's pool that no path of answers reaches ==")
    for tree_id, tree in sorted(cat.trees.items()):
        walked = pd.Series(reachable(cat, tree_id), index=index)
        stranded = pools[tree.pool] & ~walked
        report.say(f"  {tree_id:12s} {int(walked.sum()):5d} reachable of {int(pools[tree.pool].sum()):5d}")
        for tmdb in index[stranded]:
            report.fail(
                f"answers: {_label(cat.table, int(tmdb))} is in the {tree_id} pool but no answer path reaches it"
            )
        reached[tree.pool] = walked
    return reached


def check_data(table: FilmTable, report: Report) -> None:
    unknown = table.films.index[~table.films.tmdb_known.astype(bool)]
    if len(unknown):
        first = "; ".join(_label(table, int(t)) for t in unknown[:10])
        report.fail(
            f"{len(unknown)} films have no usable TMDB facts; the franchise and standup rules cannot see them."
            f" Run tools/rebuild_table.py. First: {first}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE, help="film table written by rebuild_table.py")
    args = parser.parse_args()
    key = json.loads((DATA / "answer_key.json").read_text())
    table = load_table(args.table)
    report = Report()
    try:
        cat = load_catalog(table)
    except EngineError as exc:
        print(f"FAIL {exc}; run tools/build_reference.py if the statistics are stale")
        return 1
    house = cat.house
    pools = {name: pd.Series(mask, index=table.films.index) for name, mask in cat.pools.items()}
    gore = scale_members(cat, cat.trees["horror"], "gore")
    report.say(f"film table {args.table}: {len(table.films)} films, {int(table.has_genome().sum())} with genome scores")
    report.say(f"built {table.built_at:%Y-%m-%d %H:%M}, genome {table.release}")
    added = table.films.index[pools["kids:franchise"]]
    report.say(f"franchise rule added {len(added)} films to kids: " + "; ".join(sorted(table.films.loc[added, "name"])))
    check_data(table, report)
    pools.update(check_answer_coverage(cat, pools, report))
    check_pins_in_key(house, key, report)
    check_fixtures(table, pools, gore, key, report)
    check_gore(table, pools, house, gore, report)
    check_lists(table, pools, key, report)
    check_expected(table, pools, report)
    check_reachability(table, pools, report)
    print("\n".join(report.lines))
    print(f"\n{len(report.failures)} failures")
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
