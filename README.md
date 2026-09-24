# Matinee

A film picker for a home media library. Instead of a grid of posters, Matinee
asks two or three questions in plain language (what are we doing tonight, what
do you want it to do to you, how much do you want to sweat) and hands you one
film to watch, with a way to roll again.

It reads your Jellyfin library, the MovieLens tag genome and TMDB, and writes to
none of them.

## Status

Design complete, build starting. The question trees for horror, comedy, action,
drama, kids, and fantasy and adventure, plus a "something to fall asleep to"
mode, are defined in `data/`. `tools/check_trees.py` tests them against a real
library: every film must be reachable, and every film in a set of famous lists
must be reachable through its own genres.

## Layout

- `data/trees/`, `data/modes/`: the question trees and modes.
- `data/answer_key.json`, `data/fixtures/`, `data/house_overrides.json`: what
  the trees are checked against, and single films pinned by hand.
- `tools/check_trees.py`: builds each tree's pool and checks reachability and
  the answer key.
- `tools/fetch_tmdb.py`: caches TMDB collection membership and keywords.

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
