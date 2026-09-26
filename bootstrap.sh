#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$SCRIPT_DIR/.venv}"

# VENV_DIR takes an environment override and is handed straight to a recursive
# delete, so a mistyped one would take whatever it names with it. A directory
# holding no pyvenv.cfg is not a virtualenv and is never this script's to remove.
if [[ -e "$VENV_DIR" && ! -f "$VENV_DIR/pyvenv.cfg" ]]; then
    echo "bootstrap.sh: '$VENV_DIR' exists but is not a virtualenv (no pyvenv.cfg)." >&2
    echo "Refusing to delete it. Remove it yourself, or point VENV_DIR elsewhere." >&2
    exit 1
fi

rm -rf "$VENV_DIR"
"$PYTHON_BIN" -m venv "$VENV_DIR"

VENV_PYTHON="$VENV_DIR/bin/python"

"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -e "$SCRIPT_DIR[dev]"
(cd "$SCRIPT_DIR" && npm ci --no-fund --no-audit)
"$VENV_PYTHON" -m pre_commit install --config "$REPO_ROOT/.pre-commit-config.yaml"
