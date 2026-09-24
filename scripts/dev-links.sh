#!/usr/bin/env bash
#
# dev-links.sh: recreate the local convenience symlinks into sibling repos.
#
# The session tracker lives in the private workbench and the shared coding
# standards in a private sibling, so both are gitignored here: a clone of this
# repo carries no pointer to a private sibling. CLAUDE.md points at AGENTS.md
# for tools that read only CLAUDE.md; the leak gate refuses committed symlinks,
# so it is laid down here too. This lays the links down locally
# when the siblings are present. Idempotent; never overwrites an existing path.
#
# Usage:
#   scripts/dev-links.sh

set -euo pipefail

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$REPO_ROOT"

# link name -> target, relative to the repo root
LINKS=(
    "CLAUDE.md:AGENTS.md"
    ".session-tracker.md:../library-ops/.session-tracker.md"
    "CODING_STANDARDS.md:../homelab/CODING_STANDARDS.md"
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
