#!/usr/bin/env bash
# Standards gate for matinee. Run from the repository root after ./bootstrap.sh.
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
cd "$SCRIPT_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Expected project Python at $PYTHON_BIN; run ./bootstrap.sh first." >&2
    exit 1
fi

"$PYTHON_BIN" -m ruff format --check .
"$PYTHON_BIN" -m ruff check .
"$PYTHON_BIN" scripts/check_nested_ternaries.py tools scripts
"$PYTHON_BIN" scripts/check_file_size.py tools scripts

# Cognitive complexity: threshold lives in pyproject [tool.complexipy]; -f shows only breaches
"$SCRIPT_DIR/.venv/bin/complexipy" tools scripts -f

# No silent exception swallowing: the BLE001 suppression is banned project-wide
if grep -rn "noqa: BLE001" tools scripts; then
    echo "ERROR: noqa: BLE001 found; bare except Exception is banned" >&2
    exit 1
fi

"$PYTHON_BIN" -m mypy
if [[ -d tests ]]; then
    "$PYTHON_BIN" -m pytest -q
fi
