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
6. Answer coverage: every film a tree's pool holds is reachable through its answers,
   no path ends on no film, and how many questions each tree asks.
7. Smaller libraries: the same trees built against a random third and a random
   tenth of the library, drawn with the fixed seeds in SAMPLES, must keep every
   film reachable, and a film both hold in a tree's pool must reach the same
   answers of that tree (decision 58). Fixtures are checked on the full
   library only, since a sample may not hold them.

Reads nothing live. Usage: python3 tools/check_trees.py [--table FILE]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from matinee.engine import Catalog, EngineError, house_flavour, load_catalog, reachable, scale_members, walk_ends
from matinee.labels import LabelsError, load_labels
from matinee.pools import House
from matinee.reference import DATA
from matinee.table import FilmTable, load_table

DEFAULT_TABLE = Path.home() / ".local/share/matinee/films.sqlite"
SAMPLES = (("a third", 1 / 3, 3), ("a tenth", 1 / 10, 10))  # name, share of the library, fixed seed
GORE_PROMISES = ("spotless", "rip")  # pails an unknown film could break the promise of
# Trees a film's genre tag is expected to lead to.
EXPECTED = {
    "Horror": {"horror"},
    "Comedy": {"comedy", "standup"},
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
    "Documentary": {"nonfiction", "standup"},
    "Animation": {"kids"},
    "Family": {"kids"},
    "Music": {"drama", "comedy", "nonfiction"},
    "TV Movie": {"horror", "comedy", "action", "drama", "kids"},
}
Pools = dict[str, pd.Series]


@dataclass
class Report:
    failures: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    prefix: str = ""

    def say(self, text: str) -> None:
        self.lines.append(text)

    def fail(self, text: str) -> None:
        self.failures.append(f"{self.prefix}{text}")
        self.lines.append(f"FAIL {self.prefix}{text}")


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
    """The horror and comedy fixture films as must_reach entries for their own tree.

    A comedy fixture expecting standup must reach the standup path instead, since standup specials are
    held out of the comedy tree (decision 26). Each fixture's expected and must_not kinds ride along as
    flavour_in and flavour_out, checked only in a tree that defines flavours.
    """
    entries = []
    for fname, tree in (("horror.json", "horror"), ("comedy.json", "comedy")):
        for f in json.loads((DATA / "fixtures" / fname).read_text())["films"]:
            tmdb = int(f["tmdb"]) if "tmdb" in f else tmdb_by_title(f["title"], table, report)
            home = "standup" if "standup" in f.get("expect", []) else tree
            if tmdb is not None:
                entries.append(
                    {
                        "title": f["title"],
                        "tmdb": tmdb,
                        "must_reach": [home],
                        "flavour_in": {tree: f.get("expect", [])},
                        "flavour_out": {tree: f.get("must_not", [])},
                    }
                )
    return entries


def check_fixtures(
    table: FilmTable, pools: Pools, gore: pd.DataFrame, entries: list[dict[str, Any]], report: Report
) -> None:
    before = len(report.failures)
    for entry in entries:
        check_film(entry, table, pools, gore, report)
    failed = len(report.failures) - before
    report.say(f"\n== fixtures: {failed} failures across {len(entries)} fixture films ==")


def _flavour_pin_wants(house: House, fixture: dict[int, Any]) -> list[tuple[int, str, bool]]:
    """Each flavour pin with whether its fixture asserts it through flavour_in or flavour_out."""
    wants = []
    for (tree, flavour), pins in house.flavour_pins.items():
        for t, member in pins.items():
            side = "flavour_in" if member else "flavour_out"
            wants.append((t, f"{side} {tree} {flavour}", flavour in fixture.get(t, {}).get(side, {}).get(tree, [])))
    return wants


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
    wants += _flavour_pin_wants(house, fixture)
    for tmdb, want, held in sorted(wants):
        if not held:
            report.fail(f"house pin tmdb {tmdb} needs an answer-key fixture asserting {want}")


def check_flavour_fixtures(cat: Catalog, entries: list[dict[str, Any]], report: Report) -> None:
    """Fixtures with flavour_in or flavour_out must be in, or out of, those flavours after house pins.

    A tree defining no flavours is skipped: its fixtures name payoffs, not flavours.
    """
    index = cat.table.films.index
    wants = [
        (entry, tree_id, flavour, member)
        for entry in entries
        for side, member in (("flavour_in", True), ("flavour_out", False))
        for tree_id, flavours in entry.get(side, {}).items()
        if cat.trees[tree_id].flavours
        for flavour in flavours
    ]
    for entry, tree_id, flavour, member in wants:
        held = house_flavour(cat, cat.trees[tree_id], flavour)[index == entry["tmdb"]]
        if held.size and bool(held[0]) != member:
            side = "in" if member else "out of"
            report.fail(f"'{entry['title']}' must be {side} {tree_id} flavour {flavour}")


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

    Also fails a path that ends on no film, and reports how many questions each tree asks. Returns each
    tree file's reachable films keyed by its pool name, which the other checks use as that tree's home, so
    they judge what a viewer can actually be offered.
    """
    reached: dict[str, pd.Series] = {}
    index = cat.table.films.index
    report.say("\n== answer coverage: films reachable through each tree's answers, and questions asked ==")
    for tree_id, tree in sorted(cat.trees.items()):
        ends = walk_ends(cat, tree_id)
        walked = pd.Series(reachable(cat, tree_id), index=index)
        asked = sorted({len(answers) for answers, _ in ends})
        report.say(
            f"  {tree_id:12s} {int(walked.sum()):5d} reachable of {int(pools[tree.pool].sum()):5d};"
            f" asks {asked[0]}-{asked[-1]} questions over {len(ends)} paths"
        )
        for answers, step in ends:
            if not step.pool:
                report.fail(f"answers: a {tree_id} path ends on no film: {[(a.question, a.option) for a in answers]}")
        for tmdb in index[pools[tree.pool] & ~walked]:
            report.fail(
                f"answers: {_label(cat.table, int(tmdb))} is in the {tree_id} pool but no answer path reaches it"
            )
        reached[tree.pool] = walked
    return reached


def check_same_answers(full: Catalog, sample: Catalog, report: Report) -> None:
    """A film must reach the same answers in every library (decision 58).

    Compared for every answer of every tree, over the films both libraries hold in that tree's pool: pool
    membership itself may differ, because the franchise and stray rules read which films are present.
    """
    rows = full.table.films.index.get_indexer(sample.table.films.index)
    for (tree_id, question, option), mask in sample.masks.items():
        pool = sample.trees[tree_id].pool
        both = sample.pools[pool] & full.pools[pool][rows]
        theirs = full.masks[(tree_id, question, option)][rows]
        for tmdb in sample.ids[both & (mask != theirs)]:
            report.fail(
                f"answers: {_label(sample.table, int(tmdb))} changes its {tree_id} '{question}' answer {option}"
                " with the library's size"
            )


def check_sample(full: Catalog, name: str, share: float, seed: int, report: Report, data: Path = DATA) -> None:
    """Build every tree against a random share of the library and hold it to reachability and placements."""
    ids = full.table.films.index.to_numpy()
    rng = np.random.default_rng(seed)
    chosen = rng.choice(ids, size=round(len(ids) * share), replace=False)
    table = full.table.subset([int(t) for t in chosen])
    cat = load_catalog(table, data, full.reference, full.labels)
    report.prefix = f"[{name}] "
    report.say(f"\n######## {name} of the library: {len(table.films)} films, seed {seed} ########")
    pools = {n: pd.Series(mask, index=table.films.index) for n, mask in cat.pools.items()}
    pools.update(check_answer_coverage(cat, pools, report))
    check_same_answers(full, cat, report)
    check_expected(table, pools, report)
    check_reachability(table, pools, report)
    report.prefix = ""


def check_first_question(cat: Catalog, report: Report) -> None:
    """Every answer of the first question must name a tree or mode file, or it would be silently hidden."""
    for option in cat.first_options:
        if option.tree not in cat.trees:
            report.fail(f"first question: '{option.say}' leads to '{option.tree}', which names no tree or mode file")


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
    parser.add_argument("--labels", type=Path, help="labels file; default: labels.json beside the table")
    args = parser.parse_args()
    key = json.loads((DATA / "answer_key.json").read_text())
    table = load_table(args.table)
    report = Report()
    try:
        cat = load_catalog(table, labels=load_labels(args.labels or args.table.with_name("labels.json")))
    except (EngineError, LabelsError) as exc:
        print(f"FAIL {exc}; run tools/build_reference.py if the statistics are stale")
        return 1
    house = cat.house
    pools = {name: pd.Series(mask, index=table.films.index) for name, mask in cat.pools.items()}
    gore = scale_members(cat, cat.trees["horror"], "gore")
    report.say(f"film table {args.table}: {len(table.films)} films, {int(table.has_genome().sum())} with genome scores")
    report.say(f"built {table.built_at:%Y-%m-%d %H:%M}, genome {table.release}")
    for tree_id, labels in cat.labels.trees.items():
        report.say(f"labels: {len(labels.kinds)} films labelled in {tree_id}, {len(labels.out)} labelled out of it")
        kept = table.films.index[pools[cat.trees[tree_id].pool] & table.films.index.isin(list(labels.out))]
        if len(kept):
            names = "; ".join(_label(table, int(t)) for t in kept)
            report.say(f"  labelled out of {tree_id} but kept there, having no other home: {names}")
    added = table.films.index[pools["kids:franchise"]]
    report.say(f"franchise rule added {len(added)} films to kids: " + "; ".join(sorted(table.films.loc[added, "name"])))
    check_data(table, report)
    check_first_question(cat, report)
    pools.update(check_answer_coverage(cat, pools, report))
    check_pins_in_key(house, key, report)
    entries = key["films"] + tree_fixture_entries(table, report)
    check_fixtures(table, pools, gore, entries, report)
    check_flavour_fixtures(cat, entries, report)
    check_gore(table, pools, house, gore, report)
    check_lists(table, pools, key, report)
    check_expected(table, pools, report)
    check_reachability(table, pools, report)
    for name, share, seed in SAMPLES:
        check_sample(cat, name, share, seed, report)
    print("\n".join(report.lines))
    print(f"\n{len(report.failures)} failures")
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
