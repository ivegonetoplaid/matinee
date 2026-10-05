#!/usr/bin/env bash
#
# dev-links.sh: recreate the local convenience symlinks into sibling repos.
#
# The session tracker, the private agent instructions and the prose style guide
# live in private siblings, so every link is gitignored here: a clone of this
# repo carries no pointer to a private sibling. CLAUDE.local.md is read after
# the committed CLAUDE.md, so a session reads the public AGENTS.md first and the
# private instructions second. This lays the links down locally when the
# siblings are present. Idempotent; never overwrites an existing path.
#
# Usage:
#   scripts/dev-links.sh

set -euo pipefail

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$REPO_ROOT"

# link name -> target, relative to the repo root
LINKS=(
    ".session-tracker.md:../library-ops/.session-tracker.md"
    "CLAUDE.local.md:../library-ops/feats/matinee/agents-private.md"
    "STYLE.md:../homelab/STYLE.md"
)

for entry in "${LINKS[@]}"; do
    name="${entry%%:*}"
    target="${entry#*:}"
    if [[ -e "$name" || -L "$name" ]]; then
        echo "skip  $name (already present)"
    elif [[ -e "$target" ]]; then
        ln -s "$target" "$name"
        echo "link  $name -> $target"
    else
        echo "miss  $name (sibling not found at $target; skipped)" >&2
    fi
done
