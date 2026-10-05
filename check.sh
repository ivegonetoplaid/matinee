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
"$PYTHON_BIN" scripts/check_nested_ternaries.py src tools scripts tests
"$PYTHON_BIN" scripts/check_file_size.py src tools scripts tests

# Cognitive complexity: threshold lives in pyproject [tool.complexipy]; -f shows only breaches
"$SCRIPT_DIR/.venv/bin/complexipy" src tools scripts -f

# No silent exception swallowing: the BLE001 suppression is banned project-wide
if grep -rn "noqa: BLE001" src tools scripts tests; then
    echo "ERROR: noqa: BLE001 found; bare except Exception is banned" >&2
    exit 1
fi

if [[ ! -x "$SCRIPT_DIR/node_modules/.bin/eslint" ]]; then
    echo "ESLint is not installed; run ./bootstrap.sh" >&2
    exit 1
fi
"$SCRIPT_DIR/node_modules/.bin/eslint" src/matinee/web/static
node --test "tests/js/*.test.mjs"

"$PYTHON_BIN" -m mypy
if [[ -d tests ]]; then
    # A runaway test fails here instead of taking the host's memory: the suite peaks near 200 MB and 15 s
    (ulimit -v 4000000 && timeout 300 "$PYTHON_BIN" -m pytest -q)
fi
