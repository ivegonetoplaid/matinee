#!/usr/bin/env python3
"""Reject nested ternary expressions in Python source files."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def _python_files(paths: list[str]) -> tuple[Path, ...]:
    files: list[Path] = []
    for raw_path in paths or ["src", "tests"]:
        path = Path(raw_path)
        if path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
            continue
        if path.suffix == ".py" and path.exists():
            files.append(path)
    return tuple(files)


class _NestedTernaryVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[tuple[int, int]] = []

    def visit_IfExp(self, node: ast.IfExp) -> None:
        if isinstance(node.body, ast.IfExp) or isinstance(node.orelse, ast.IfExp):
            self.violations.append((node.lineno, node.col_offset + 1))
        self.generic_visit(node)


def _check_file(path: Path) -> tuple[tuple[int, int], ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    visitor = _NestedTernaryVisitor()
    visitor.visit(tree)
    return tuple(visitor.violations)


def main(argv: list[str]) -> int:
    """Return a failing exit code when any nested ternary is found."""
    files = _python_files(argv[1:])
    violations_found = False
    for path in files:
        for line, column in _check_file(path):
            violations_found = True
            print(
                f"{path}:{line}:{column}: nested ternary expressions are forbidden",
                file=sys.stderr,
            )
    return 1 if violations_found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
