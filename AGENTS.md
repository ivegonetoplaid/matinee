# Matinee — Agent Addendum

Matinee is a film picker for a home media library. A viewer answers two or three
conversational questions and is handed one film, tonight's showing, with a
`WATCH THIS` and a `ROLL AGAIN`. It reads a Jellyfin library, the MovieLens tag
genome and TMDB, and writes to none of them.

Follow the global agent rules first, then this addendum. `CODING_STANDARDS.md` is
binding for every line of code here.

## Where things live

- **This repository holds code and the contracts the code honours.** The question
  trees and modes are in `data/trees/` and `data/modes/`; the answer key and
  fixtures the trees are tested against are in `data/`; the tree checker and the
  TMDB fetcher are in `tools/`.
- **The design record lives in the private workbench**, a sibling checkout of the
  operator's `library-ops` repository: `feats/matinee/decisions.md` (current
  decisions, the build contract), `feats/matinee/tracker-slim.md` (feature
  tracker) and `discussions/matinee-discussion-log.md` (the reasoning). Read the
  decisions before changing a tree. Working files (build reports, reviews,
  discussion) go there, never here.
- A behaviour change amends its spec in `docs/spec/` in the same commit, once a
  spec exists.

## Landmines

- **This repository is destined to be public.** No household identifiers: no
  hostnames, LAN addresses, internal domains, family names, file paths from the
  operator's machines, or credentials. The homelab-leak gate enforces the
  mechanical part on every commit; the rest is on the author. Server URLs and
  keys arrive as arguments and environment variables.
- **Read-only against every media server.** Matinee never writes to Jellyfin or
  Plex. Its own state (profiles, exclusions, corrections, pins) lives in its own
  store.
- **Third-party data comes with terms, and they are part of the design.**
  - DoesTheDogDie: queried one film at a time at the moment of a pick, never
    fetched ahead, never used to build a score; its votes are never kept, and
    only a film's item id is remembered, for at most 30 days. Free tier is
    non-commercial. "Powered by DoesTheDogDie.com" must appear wherever its data
    does.
  - TMDB: cache at most six months; the TMDB logo and the notice "This product
    uses the TMDB API but is not endorsed or certified by TMDB" must appear;
    non-commercial under the default licence.
  - MovieLens tag genome: credit Harper and Konstan (2015) and Vig, Sen and
    Riedl (2012); derived tables carry the dataset's share-alike condition. The
    raw dataset is never committed.
- **Every film must stay reachable.** A tree takes every film carrying its genre;
  a film leaves only when it barely reaches for the tree's effect and has another
  home. `tools/check_trees.py` holds the trees to that and to the answer key; a
  rule change must leave it passing.

## Implementation loop

1. `./bootstrap.sh` once (creates `.venv`, installs dev tools, installs the
   pre-commit hooks), then `scripts/dev-links.sh` for the local links.
2. Implement only the requested slice.
3. `./check.sh` before reporting completion. It resolves the venv itself.
4. Report verified facts, then stop for review.

## Branches and commits

- Branch for non-trivial work (`feat/…`, `fix/…`); small contained changes may go
  straight to `main`. Commit only on an explicit yes.
- Never bypass the pre-commit hooks. A gate that blocks a commit is fixed at its
  cause.
