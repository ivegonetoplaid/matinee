# Matinee

A film picker for a home media library. Instead of a grid of posters, Matinee
asks two or three questions in plain language (what are we in the mood for,
then a question or two about that mood) and hands you one film to watch, with a
way to roll again.

It reads your Jellyfin library, the MovieLens tag genome and TMDB, and writes to
none of them.

## Status

First build complete. A viewer passes the box office, answers a few questions on
a wall of the library's posters, and is handed one film. The behaviour Matinee
promises is written down in `docs/spec/matinee.md`.

## Layout

- `src/matinee/`: the engine, the offline film table, profiles, the
  DoesTheDogDie check and the web server; `src/matinee/web/static/` is the page.
- `data/trees/`, `data/modes/`: the question trees and modes.
- `data/answer_key.json`, `data/fixtures/`, `data/house_overrides.json`: what
  the trees are checked against, and single films pinned by hand.
- `tools/rebuild_table.py`: builds the offline film table from the library,
  TMDB and the tag genome; `--daily HH:MM` rebuilds it every night.
- `tools/check_trees.py`: checks every tree against the film table:
  reachability, the answer key and the famous-film lists, at three library sizes.
- `tools/notes.py`: lists viewers' open notes, records a ruling on one, and
  clears a forgotten PIN, run
  inside the server's image against its state directory.
- `docs/spec/`: the specification.

## Running

```sh
DATA_DIR=... JELLYFIN_URL=... JELLYFIN_API_KEY=... \
uvicorn --factory matinee.web.main:build --workers 1
```

A Plex library takes `PLEX_URL` and `PLEX_TOKEN` in place of the Jellyfin pair;
set one server, never both. `SEERR_URL` and `DTDD_API_KEY` are optional.
`DOOR_WORD` optionally locks the site behind a word; `DOOR_MATCH` (`relaxed` or
`strict`) and `DOOR_GREETING` tune it (spec section 7.2). `POSTERS_FROM=tmdb` has
viewers' browsers load posters and backdrops straight from TMDB's image server;
the default, `server`, keeps every picture on your own server (spec section
11.5). The rebuild reads the same media server settings and `TMDB_TOKEN`.

The `Dockerfile` builds the same server. Run exactly one worker: every
DoesTheDogDie limit, hold and remembered answer lives in the process.

## Development

```sh
./bootstrap.sh     # venv, dev tools, pre-commit hooks
./check.sh         # the standards gate
```

## Data and credits

This product uses the TMDB API but is not endorsed or certified by TMDB.

Content warnings are Powered by DoesTheDogDie.com.

Tag genome data from MovieLens:

- F. Maxwell Harper and Joseph A. Konstan. 2015. The MovieLens Datasets: History
  and Context. ACM Transactions on Interactive Intelligent Systems 5, 4:
  19:1-19:19. https://doi.org/10.1145/2827872
- Jesse Vig, Shilad Sen and John Riedl. 2012. The Tag Genome: Encoding Community
  Knowledge to Support Novel Interaction. ACM Transactions on Interactive
  Intelligent Systems 2, 3.

## Licence

Matinee is free software: you can redistribute it and modify it under the terms
of the GNU Affero General Public License, version 3 or (at your option) any
later version. The full text is in `LICENSE`. If you run a modified Matinee for
other people over a network, the licence asks you to offer them its source.

That covers everything in this repository except the third-party material,
which stays under its owners' terms:

- `data/reference.json` is derived from the MovieLens tag genome and carries
  that dataset's conditions, stated in its `licence` field: research and
  non-commercial use only, and redistribution only under the same conditions.
- `src/matinee/web/static/credits/tmdb.svg` is TMDB's logo, used under TMDB's
  terms.
- Data fetched at run time from TMDB, DoesTheDogDie and your media server is
  governed by those services' own terms. TMDB's default licence and
  DoesTheDogDie's free tier are both non-commercial.
- Dependencies keep their own licences.
