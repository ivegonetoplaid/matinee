"""Check Matinee's tree pools against the answer key and the reachability rule.

Reads the library from Jellyfin and scores from the MovieLens tag genome, builds
each tree's pool by the inclusive rule, and reports three things:

1. Reachability: every film must have at least one home.
2. Expected homes: every film must be reachable through a tree its own genre tags
   point at, not only by accident.
3. The answer key: list films (genome list tags) and hand fixtures in
   data/answer_key.json, plus the horror and comedy fixture files.

The inclusive rule: a tree takes every film carrying its genre tag. A film
leaves a tree only when it barely reaches for that tree's own effect (its score
is under the tree's floor) and it has another home to land in: the Comedy tag
for horror, action and drama, the kids tree for family films. A film with no
genome score is never removed for a missing score. Films no other tree claims
fall to the drama tree, which is the home for serious films of any genre.

The kids tree is the exception: it is gated and fails closed. A film enters only
with a passing certificate, and sorts into three age bands. Films the gate
refuses stay in the adult trees. House pins in data/house_overrides.json add single
films the rule misses. A film in the same TMDB collection as a kids film joins
the kids tree when its certificate and adult signal allow (the franchise rule).
A kids film stays in the adult trees too, except that one with no genome entry
(too few adult raters) is kids-only in every tree, and one offered to little ones
or the whole family never counts as adult horror.

Read-only against Jellyfin. Run on a host with the ml-latest dataset, passing the
server URL and the API key.

Usage: JELLYFIN_API_KEY=... python3 tools/check_trees.py --jellyfin URL [--ml DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
EFFECT_FLOOR = {"fear": 0.20, "excite": 0.30, "weight": 0.13}
ADVENTURE_EXCITEMENT = 0.60
SLEEP_ENCHANTMENT, SLEEP_EDGE = 0.55, 0.40
KIDS_GENRES = {"Animation", "Family"}
LITTLE_CERTS = {"G", "TV-Y", "TV-Y7", "TV-G", "E"}
FAMILY_CERTS = LITTLE_CERTS | {"PG", "TV-PG"}
TEEN_CERTS = {"PG-13", "TV-14"}
KIDS_UNTAGGED_YOUNG = 0.50
KIDS_ADULT_CEILING = 0.40
LITTLE_FRIGHT, LITTLE_ADULT = 0.30, 0.25
ROUGH_FRIGHT = 0.45
WONDER_BAR = EXPLORE_BAR = 0.45
DRAMA_STRAYS = {
    "Crime",
    "Mystery",
    "Thriller",
    "Romance",
    "War",
    "History",
    "Music",
    "Science Fiction",
    "Fantasy",
    "Adventure",
}

SCORES = {
    "fear": ["scary", "frightening", "creepy", "horror"],
    "laugh": ["comedy", "funny", "silly fun"],
    "excite": ["action", "action packed", "good action"],
    "weight": ["drama", "dramatic", "emotional", "moving", "touching", "harsh"],
    "ench": ["fairy tale", "childhood", "fantasy", "whimsical", "magic", "fantasy world", "fairy tales"],
    "edge": ["violent", "gore", "disturbing", "tense", "brutal"],
    "young": ["kids", "children", "cute", "cute!", "talking animals"],
    "fright": ["scary", "creepy", "dark fantasy"],
    "language": ["foul language"],
    "sex": ["sex", "sexual", "sex comedy", "nudity", "nudity (topless)", "notable nudity"],
    "crude": ["crude humor", "gross-out"],
    "drugs": ["drugs"],
    "wonder": ["fantasy world", "magic", "fantasy", "mythology", "fairy tale", "imagination", "dragons", "wizards"],
    "explore": ["treasure", "treasure hunt", "pirates", "archaeology", "jungle", "island"],
}
# Trees a film's genre tag is expected to lead to. "western" and "documentary"
# are decided shallow trees (§38) not yet designed; "kids" is the next tree.
EXPECTED = {
    "Horror": {"horror"},
    "Comedy": {"comedy"},
    "Action": {"action"},
    "Adventure": {"action", "drama", "kids", "sleep", "fantasy"},
    "Drama": {"drama"},
    "Crime": {"drama", "action", "horror"},
    "Mystery": {"drama", "action", "horror"},
    "Thriller": {"drama", "action", "horror"},
    "Romance": {"drama", "comedy"},
    "Science Fiction": {"action", "drama", "horror", "kids"},
    "Fantasy": {"fantasy", "action", "sleep", "kids", "drama", "horror"},
    "War": {"drama", "action"},
    "History": {"drama", "action"},
    "Western": {"western"},
    "Documentary": {"documentary"},
    "Animation": {"kids"},
    "Family": {"kids"},
    "Music": {"drama", "comedy", "documentary"},
    "TV Movie": {"horror", "comedy", "action", "drama", "kids"},
}


@dataclass(frozen=True)
class Film:
    tmdb: int
    name: str
    year: int | None
    genres: frozenset[str]


@dataclass
class Report:
    failures: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def say(self, text: str) -> None:
        self.lines.append(text)

    def fail(self, text: str) -> None:
        self.failures.append(text)
        self.lines.append(f"FAIL {text}")


def load_library(base_url: str, key: str) -> tuple[pd.DataFrame, list[str]]:
    """The library keyed by TMDB id, and the names of films with no TMDB id (invisible to Matinee)."""
    url = (
        f"{base_url.rstrip('/')}/Items?IncludeItemTypes=Movie&Recursive=true"
        "&Fields=Genres,ProviderIds,ProductionYear,OfficialRating"
    )
    req = urllib.request.Request(url, headers={"X-Emby-Token": key})
    with urllib.request.urlopen(req, timeout=60) as resp:
        items = json.load(resp)["Items"]
    rows = []
    no_id = [
        f"{it['Name']} ({it.get('ProductionYear')})"
        for it in items
        if not (it.get("ProviderIds") or {}).get("Tmdb", "").isdigit()
    ]
    for it in items:
        tmdb = (it.get("ProviderIds") or {}).get("Tmdb", "")
        if tmdb.isdigit():
            rows.append(
                {
                    "tmdb": int(tmdb),
                    "name": it["Name"],
                    "year": it.get("ProductionYear"),
                    "genres": frozenset(it.get("Genres") or []),
                    "cert": it.get("OfficialRating") or "",
                }
            )
    return pd.DataFrame(rows).drop_duplicates("tmdb").set_index("tmdb"), sorted(no_id)


def load_scores(ml: Path, lib: pd.DataFrame, extra_tags: list[str]) -> pd.DataFrame:
    links = pd.read_csv(ml / "links.csv").dropna(subset=["tmdbId"])
    links = links[links.tmdbId.astype(int).isin(lib.index)]
    movie_to_tmdb = dict(zip(links.movieId, links.tmdbId.astype(int), strict=True))
    tags = pd.read_csv(ml / "genome-tags.csv").set_index("tagId").tag
    wanted = {t for group in SCORES.values() for t in group} | set(extra_tags)
    tag_ids = [i for i, t in tags.items() if t in wanted]
    chunks = pd.read_csv(ml / "genome-scores.csv", chunksize=5_000_000)
    g = pd.concat(c[c.movieId.isin(movie_to_tmdb) & c.tagId.isin(tag_ids)] for c in chunks)
    g = g.pivot(index="movieId", columns="tagId", values="relevance")
    g.columns = [tags[c] for c in g.columns]
    g.index = [movie_to_tmdb[m] for m in g.index]
    g = g[~g.index.duplicated()]
    scores = pd.DataFrame({k: g[v].mean(axis=1) for k, v in SCORES.items()})
    return scores.join(g[[t for t in extra_tags if t in g.columns]])


def leaves_for_comedy(lib: pd.DataFrame, s: pd.DataFrame, effect: str) -> pd.Series:
    """True where `effect` is under its floor and a Comedy tag gives the film a landing.

    A missing score never removes a film: unknown is not the same as absent.
    """
    below = s[effect].reindex(lib.index).lt(EFFECT_FLOOR[effect]).fillna(False)
    return below & lib.genres.apply(lambda g: "Comedy" in g)


def under(x: pd.Series, limit: float) -> pd.Series:
    """True where x is below limit or unknown: a missing score is not evidence of a problem."""
    return x.isna() | x.lt(limit)


def over(x: pd.Series, limit: float) -> pd.Series:
    """True where x is at or above limit; unknown counts as not over."""
    return x.ge(limit).fillna(False)


def franchise_members(lib: pd.DataFrame, entered: pd.Series, collections: dict[int, int]) -> pd.Series:
    """Films sharing a TMDB collection with a film that entered the kids pool on its own."""
    kid_colls = {collections[t] for t in lib.index[entered] if t in collections}
    return pd.Series([collections.get(t) in kid_colls for t in lib.index], index=lib.index)


def kids_bands(
    lib: pd.DataFrame, s: pd.DataFrame, pins: dict[int, str], collections: dict[int, int]
) -> dict[str, pd.Series]:
    """The gated kids pool split into little, family and older bands (older includes family).

    Fails closed: a film enters only on a passing certificate, a PG-13 film only
    when it is non-comedy animation or Family-tagged and its adult signal is low.
    """
    sc = s.reindex(lib.index)

    def has(name: str) -> pd.Series:
        return lib.genres.apply(lambda g: name in g)

    tagged = lib.genres.apply(lambda g: bool(KIDS_GENRES & g))
    adult = sc[["language", "sex", "crude", "drugs"]].max(axis=1)
    family_cert = lib.cert.isin(FAMILY_CERTS)
    teen_ok = (
        lib.cert.isin(TEEN_CERTS)
        & tagged
        & ((has("Animation") & ~has("Comedy")) | has("Family"))
        & under(adult, KIDS_ADULT_CEILING)
    )
    untagged = ~tagged & family_cert & over(sc["young"], KIDS_UNTAGGED_YOUNG)
    pinned = pd.Series(lib.index.isin(list(pins)), index=lib.index)
    entered = (tagged & family_cert) | teen_ok | untagged
    franchise = (
        franchise_members(lib, entered, collections)
        & ~entered
        & lib.cert.isin(FAMILY_CERTS | TEEN_CERTS)
        & under(adult, KIDS_ADULT_CEILING)
    )
    pool = entered | franchise | pinned
    pinned_older = pd.Series(lib.index.isin([t for t, b in pins.items() if b == "older"]), index=lib.index)
    rough = over(sc["fright"], ROUGH_FRIGHT) | lib.cert.isin(TEEN_CERTS) | pinned_older
    little = (
        pool
        & lib.cert.isin(LITTLE_CERTS)
        & under(sc["fright"], LITTLE_FRIGHT)
        & under(adult, LITTLE_ADULT)
        & ~pinned_older
    )
    return {"little": little, "family": pool & ~rough, "older": pool, "tagged": tagged, "franchise": franchise}


def build_pools(
    lib: pd.DataFrame, s: pd.DataFrame, pins: dict[int, str], collections: dict[int, int]
) -> dict[str, pd.Series]:
    tagged = {name: lib.genres.apply(lambda g, n=name: n in g) for name in EXPECTED}
    bands = kids_bands(lib, s, pins, collections)
    young_kids = bands["tagged"] & (bands["little"] | bands["family"])
    kids_only = young_kids & s["laugh"].reindex(lib.index).isna()
    excite = s["excite"].reindex(lib.index)
    pools = {
        "horror": tagged["Horror"] & ~young_kids & ~leaves_for_comedy(lib, s, "fear"),
        "comedy": tagged["Comedy"] & ~kids_only,
        "action": (tagged["Action"] | (tagged["Adventure"] & (excite.isna() | excite.ge(ADVENTURE_EXCITEMENT))))
        & ~kids_only
        & ~leaves_for_comedy(lib, s, "excite"),
        "kids": bands["older"],
        "kids:little": bands["little"],
        "kids:family": bands["family"],
        "western": tagged["Western"],
        "documentary": tagged["Documentary"],
    }
    wonder, explore = s["wonder"].reindex(lib.index), s["explore"].reindex(lib.index)
    pools["fantasy"] = (
        ((tagged["Fantasy"] | tagged["Adventure"]) & (over(wonder, WONDER_BAR) | over(explore, EXPLORE_BAR)))
        | (tagged["Fantasy"] & wonder.isna())
    ) & ~kids_only
    pools["kids:franchise"] = bands["franchise"]
    claimed = pools["horror"] | pools["comedy"] | pools["action"] | pools["fantasy"]
    strays = lib.genres.apply(lambda g: bool(DRAMA_STRAYS & g)) & ~claimed
    pools["drama"] = (tagged["Drama"] | strays) & ~kids_only & ~leaves_for_comedy(lib, s, "weight")
    ench, edge = s["ench"].reindex(lib.index), s["edge"].reindex(lib.index)
    pools["sleep"] = (ench.ge(SLEEP_ENCHANTMENT) & edge.lt(SLEEP_EDGE)).fillna(False)
    return pools


def homes_of(tmdb: int, pools: dict[str, pd.Series]) -> set[str]:
    """Trees and modes holding the film; kids age bands are reported, not counted as homes."""
    return {name for name, pool in pools.items() if ":" not in name and pool.get(tmdb, False)}


def band_of(tmdb: int, pools: dict[str, pd.Series]) -> str:
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


def check_reachability(lib: pd.DataFrame, pools: dict[str, pd.Series], report: Report) -> None:
    reached = pd.concat([p for n, p in pools.items() if ":" not in n], axis=1).any(axis=1)
    report.say(f"\n== reachability: {int(reached.sum())} of {len(lib)} films have a home ==")
    for name, pool in pools.items():
        report.say(f"  {name:12s} {int(pool.sum()):5d}")
    for tmdb in lib.index[~reached]:
        f = lib.loc[tmdb]
        report.fail(f"unreachable: {f['name']} ({f.year}) genres={'/'.join(sorted(f.genres)) or 'none'}")


def check_expected(lib: pd.DataFrame, pools: dict[str, pd.Series], report: Report) -> None:
    misses = []
    for tmdb_label, f in lib.iterrows():
        tmdb = int(str(tmdb_label))
        want = expected_for(f.genres)
        if want and not (homes_of(tmdb, pools) & want):
            homes = sorted(homes_of(tmdb, pools)) or "nothing"
            misses.append(f"{f['name']} ({f.year}) {'/'.join(sorted(f.genres))} -> in {homes}")
    report.say(f"\n== expected homes: {len(misses)} films not reachable through their own genres ==")
    for m in misses:
        report.fail(f"unexpected home: {m}")


def check_lists(
    lib: pd.DataFrame, s: pd.DataFrame, pools: dict[str, pd.Series], key: dict[str, Any], report: Report
) -> None:
    thresholds = key["list_tags"].get("thresholds", {})
    for tag in key["list_tags"]["tags"]:
        threshold = thresholds.get(tag, key["list_tags"]["threshold"])
        if tag not in s.columns:
            report.fail(f"list tag missing from genome: {tag}")
            continue
        members = [t for t in s.index[s[tag].ge(threshold)] if t in lib.index]
        bad = [t for t in members if not (homes_of(t, pools) & expected_for(lib.loc[t].genres))]
        report.say(
            f"\n== list '{tag}': {len(members) - len(bad)} of {len(members)} reachable through their own genres =="
        )
        for t in bad:
            report.fail(f"list '{tag}': {lib.loc[t]['name']} -> in {sorted(homes_of(t, pools)) or 'nothing'}")


def check_film(entry: dict[str, Any], lib: pd.DataFrame, pools: dict[str, pd.Series], report: Report) -> None:
    tmdb, title = entry["tmdb"], entry["title"]
    if tmdb not in lib.index:
        report.fail(f"fixture '{title}' tmdb {tmdb} not in library")
        return
    held = lib.loc[tmdb]["name"]
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


def tmdb_by_title(title: str, lib: pd.DataFrame, report: Report) -> int | None:
    """The one library film with this exact title, or None with a failure recorded."""
    hits = lib.index[lib["name"].str.casefold() == title.casefold()]
    if len(hits) != 1:
        report.fail(f"fixture '{title}' matches {len(hits)} library films by title; add a tmdb id")
        return None
    return int(hits[0])


def tree_fixture_entries(lib: pd.DataFrame, report: Report) -> list[dict[str, Any]]:
    """The horror and comedy fixture films as must_reach entries for their own tree."""
    entries = []
    for fname, tree in (("horror.json", "horror"), ("comedy.json", "comedy")):
        for f in json.loads((DATA / "fixtures" / fname).read_text())["films"]:
            tmdb = int(f["tmdb"]) if "tmdb" in f else tmdb_by_title(f["title"], lib, report)
            if tmdb is not None:
                entries.append({"title": f["title"], "tmdb": tmdb, "must_reach": [tree]})
    return entries


def check_fixtures(lib: pd.DataFrame, pools: dict[str, pd.Series], key: dict[str, Any], report: Report) -> None:
    before = len(report.failures)
    entries = key["films"] + tree_fixture_entries(lib, report)
    for entry in entries:
        check_film(entry, lib, pools, report)
    failed = len(report.failures) - before
    report.say(f"\n== fixtures: {failed} failures across {len(entries)} fixture films ==")


def load_collections(path: Path) -> dict[int, int]:
    """TMDB id to collection id, newest record per film; empty when the cache is absent."""
    if not path.exists():
        return {}
    latest: dict[int, dict[str, Any]] = {}
    for line in path.read_text().splitlines():
        rec = json.loads(line)
        latest[rec["tmdb"]] = rec
    return {t: r["collection_id"] for t, r in latest.items() if r["collection_id"] is not None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jellyfin", required=True, help="Jellyfin base URL")
    parser.add_argument("--ml", type=Path, default=Path("/tmp/matinee/ml-latest"))
    parser.add_argument(
        "--tmdb",
        type=Path,
        default=Path.home() / ".local/share/matinee/tmdb/films.jsonl",
        help="TMDB cache written by fetch_tmdb.py",
    )
    args = parser.parse_args()
    api_key = os.environ.get("JELLYFIN_API_KEY", "").strip()
    if not api_key:
        parser.error("JELLYFIN_API_KEY is not set")
    key = json.loads((DATA / "answer_key.json").read_text())
    pins = {p["tmdb"]: p["band"] for p in json.loads((DATA / "house_overrides.json").read_text())["kids"]}
    collections = load_collections(args.tmdb)
    lib, no_id = load_library(args.jellyfin, api_key)
    s = load_scores(args.ml, lib, key["list_tags"]["tags"])
    pools = build_pools(lib, s, pins, collections)
    report = Report()
    report.say(f"library {len(lib)} films with a TMDB id; {len(s)} with genome scores; floors {EFFECT_FLOOR}")
    report.say(f"TMDB cache: {len(collections)} films in a collection, from {args.tmdb}")
    if not collections:
        report.fail(f"no TMDB collections loaded from {args.tmdb}; the franchise rule did not run")
    added = lib.index[pools["kids:franchise"]]
    report.say(f"franchise rule added {len(added)} films to kids: " + "; ".join(sorted(lib.loc[added, "name"])))
    check_fixtures(lib, pools, key, report)
    check_lists(lib, s, pools, key, report)
    check_expected(lib, pools, report)
    check_reachability(lib, pools, report)
    print("\n".join(report.lines))
    print(f"\n== metadata: {len(no_id)} films have no TMDB id in Jellyfin and are invisible to Matinee ==")
    for name in no_id:
        print(f"  {name}")
    print(f"\n{len(report.failures)} failures; {len(no_id)} films without a TMDB id")
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
