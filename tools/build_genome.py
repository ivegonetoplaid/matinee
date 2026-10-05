"""Write data/genome.json: the genome scores Matinee ships, for the maintainer.

Reads the MovieLens ml-latest genome and keeps the relevance of every tag a reader
names (`matinee.genome_file.tags_read`) for every genome film with a TMDB id. The
file carries the dataset's licence conditions, as data/reference.json does. Rerun
it when a tree file, the fall-asleep scores or the answer key names a new tag;
tests/test_genome_file.py fails in ./check.sh until it is rerun. Running it twice
on the same release writes an identical file.

Usage: python3 tools/build_genome.py [--ml DIR] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from matinee.genome import load_genome
from matinee.genome_file import GENOME_FILE, tags_read, write_scores
from matinee.reference import REFERENCE_PATH, load_reference

DEFAULT_ML = Path.home() / ".local/share/matinee/ml-latest"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ml", type=Path, default=DEFAULT_ML, help="ml-latest directory")
    parser.add_argument("--out", type=Path, default=GENOME_FILE)
    args = parser.parse_args()
    genome = load_genome(args.ml, cache=args.ml / "genome-matrix.npz")
    cut_from = load_reference().source
    if genome.release != cut_from:
        print(
            f"{args.ml} is {genome.release}, but the gore cuts in {REFERENCE_PATH} were measured on {cut_from}."
            f" Run tools/build_reference.py --ml {args.ml} first, so both files come from one release.",
            file=sys.stderr,
        )
        return 1
    scores = genome.scores(tags_read())
    licence = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))["licence"]
    write_scores(scores, args.out, licence)
    print(f"{len(scores.rows)} films, {len(scores.tags)} tags, {scores.release}: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
