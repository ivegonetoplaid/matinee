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
- `docs/spec/`: the specification.

## Running

```sh
MATINEE_STATE=... MATINEE_JELLYFIN_URL=... MATINEE_SEERR_URL=... \
JELLYFIN_API_KEY=... DTDD_API_KEY=... \
uvicorn --factory matinee.web.main:build --workers 1
```

The `Dockerfile` builds the same server. Run exactly one worker: the
DoesTheDogDie pacing and the per-device lookup allowance live in the process.

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
