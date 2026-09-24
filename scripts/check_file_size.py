#!/usr/bin/env python3
"""Warn on oversized files and hard-fail classes with too many direct methods.

Two deliberately asymmetric signals: file line count is a stderr-only
warning (a large but cohesive file must never be forced apart), while class
direct-method count is a hard gate scoped to ``src/`` (test classes
legitimately carry many ``test_`` methods, so the gate never touches them).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

LINE_WARN_THRESHOLD = 700
METHOD_HARD_LIMIT = 30

# "path/to/module.py::ClassName", the path relative to src/, mapped to a
# one-line reason. "scheduled" names a queued godfile split -- a ratchet target:
# delete the entry the moment that split lands so the gate re-tightens on the
# smaller class automatically. "exempt" is genuinely cohesive and permanent.
#
# An entry keeps its class off the hard gate, so a wrong or stale key silently
# widens the gate. Two checks close that: a class that drops under the cap fails
# until its entry goes, and a full src/ scan fails on any entry matching no
# class at all.
ALLOWLIST: dict[str, str] = {}


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


class _ClassMethodVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.classes: list[tuple[str, int, int]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        count = sum(isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) for child in node.body)
        self.classes.append((node.name, node.lineno, count))
        self.generic_visit(node)


def _classes_in(path: Path) -> tuple[tuple[str, int, int], ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    visitor = _ClassMethodVisitor()
    visitor.visit(tree)
    return tuple(visitor.classes)


def _src_index(path: Path) -> int | None:
    parts = path.parts
    return parts.index("src") if "src" in parts else None


def _relative_key(path: Path, src_index: int) -> str:
    """Return the allowlist path key: the file's path relative to ``src/``.

    The package name stays in the key, so two packages under ``src/`` cannot
    collide on one entry and inherit each other's exemption.
    """
    return "/".join(path.parts[src_index + 1 :])


def _warn_line_counts(files: tuple[Path, ...]) -> None:
    for path in files:
        n_lines = len(path.read_text(encoding="utf-8").splitlines())
        if n_lines > LINE_WARN_THRESHOLD:
            print(
                f"{path}: {n_lines} lines (over {LINE_WARN_THRESHOLD}, consider splitting)",
                file=sys.stderr,
            )


def _check_allowlisted(path: Path, name: str, lineno: int, count: int, reason: str) -> bool:
    """Report an allowlisted class, failing once it no longer needs the entry."""
    if count <= METHOD_HARD_LIMIT:
        print(
            f"{path}:{lineno}: class {name} is down to {count} direct methods "
            f"(cap {METHOD_HARD_LIMIT}) and no longer needs its allowlist entry; "
            "delete it from scripts/check_file_size.py to re-tighten the gate",
            file=sys.stderr,
        )
        return True
    print(f"{path}:{lineno}: {name} — {count} methods ({reason})")
    return False


def _check_class_methods(files: tuple[Path, ...]) -> tuple[bool, set[str]]:
    """Check every class against the cap; return the verdict and the keys hit."""
    failed = False
    matched: set[str] = set()
    for path in files:
        src_index = _src_index(path)
        if src_index is None:
            continue
        key_prefix = _relative_key(path, src_index)
        for name, lineno, count in _classes_in(path):
            key = f"{key_prefix}::{name}"
            reason = ALLOWLIST.get(key)
            if reason is not None:
                matched.add(key)
                failed |= _check_allowlisted(path, name, lineno, count, reason)
                continue
            if count > METHOD_HARD_LIMIT:
                failed = True
                print(
                    f"{path}:{lineno}: class {name} has {count} direct methods "
                    f"(> {METHOD_HARD_LIMIT}); split it or add an allowlist "
                    "entry in scripts/check_file_size.py",
                    file=sys.stderr,
                )
    return failed, matched


def _check_stale_entries(matched: set[str]) -> bool:
    """Fail on an allowlist entry that matched no class in the scan.

    A key naming a class that was renamed, moved, or deleted is never looked up,
    so without this the entry survives forever and silently holds the gate open
    for whatever later takes that name.
    """
    stale = sorted(set(ALLOWLIST) - matched)
    for key in stale:
        print(
            f"{key}: allowlisted class not found; it was renamed, moved, or "
            "deleted -- drop the entry from scripts/check_file_size.py",
            file=sys.stderr,
        )
    return bool(stale)


def _scans_whole_src(paths: list[str]) -> bool:
    """Report whether the requested paths cover the entire ``src`` tree.

    The stale-entry check is only meaningful over a full scan; a narrower run
    would call every unvisited entry stale.
    """
    return any(Path(p).name == "src" and Path(p).is_dir() for p in paths)


def main(argv: list[str]) -> int:
    """Return a failing exit code when a src/ class exceeds the method cap."""
    paths = argv[1:] or ["src", "tests"]
    files = _python_files(paths)
    _warn_line_counts(files)
    failed, matched = _check_class_methods(files)
    if _scans_whole_src(paths):
        failed |= _check_stale_entries(matched)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
