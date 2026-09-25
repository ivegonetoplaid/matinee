"""Write data/reference.json: the reference statistics every tree file names.

Reads the MovieLens ml-latest genome and every file in data/trees/, measures each
payoff's mean and standard deviation and each scale's cut points over the tree's
reference films, and writes the result. Running it twice on the same release and
tree files writes an identical file. Rerun it whenever a tree file's scores,
payoffs, scales or reference change; tests/test_reference.py::test_shipped_reference_covers_every_tree
fails in ./check.sh until it is rerun.

Usage: python3 tools/build_reference.py [--ml DIR] [--out FILE]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from matinee.genome import load_genome
from matinee.reference import DATA, REFERENCE_PATH, compute, load_specs, to_json

DEFAULT_ML = Path.home() / ".local/share/matinee/ml-latest"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ml", type=Path, default=DEFAULT_ML, help="ml-latest directory")
    parser.add_argument("--out", type=Path, default=REFERENCE_PATH)
    args = parser.parse_args()
    genome = load_genome(args.ml, cache=args.ml / "genome-matrix.npz")
    ref = compute(genome, load_specs(DATA / "trees"))
    args.out.write_text(to_json(ref), encoding="utf-8")
    for name, tree in ref.trees.items():
        cuts = "; ".join(f"{n} {list(c.cuts)}" for n, c in tree.scales.items())
        print(f"{name}: {tree.films} reference films, {len(tree.payoffs)} payoffs. {cuts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
