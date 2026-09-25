"""Plant deliberate breaks in a scratch copy of a repository and report which test assertion caught each one.

Usage: `python mutate.py REPO MUTATIONS.json WORKDIR [--python PY] [--tests DIR] [--package NAME]
[--also CMD] [--per-assertion]`. REPO is copied (git's tracked and untracked-but-not-ignored files) to
WORKDIR/copy, so the real working tree is never touched. MUTATIONS.json is a list of objects `{"id",
"file", "old", "new", "why"}`: `old` is replaced by `new` in `file` (relative to the repo) and must
occur exactly once, otherwise the mutation is reported `invalid` rather than silently run unchanged.
The unmutated baseline runs first and every test must pass. Each mutation is applied alone and pytest
runs with a JUnit report. `--also CMD` runs a shell command in the copy after each mutation (for
example the real tool plus a `cmp` against its committed output); its exit status is recorded as
`also_ok`, and the harness refuses to start if CMD fails on the unmutated copy. `--per-assertion`
rewrites the test files so that exactly one assertion is live at a time (every other `assert` becomes
a bare expression and every other `pytest.raises` becomes `contextlib.suppress`), then reruns every
mutation per assertion; a kill is `assert` when the live assertion itself failed and `crash` when the
test died of another exception first. PYTHONPATH is pinned to the copy's `src`, and the harness
refuses to run if the package under test imports from anywhere else, which guards against an
editable install pointing back at the real tree. Output: WORKDIR/manifest.json and a table on stdout.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def copy_repo(repo: Path, dest: Path) -> None:
    files = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-co", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split("\0")
    if dest.exists():
        shutil.rmtree(dest)
    for rel in filter(None, files):
        src = repo / rel
        if src.is_file():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / rel)


def run_tests(copy: Path, py: str, tests: str, env: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Test name -> (outcome, failure message)."""
    report = copy / ".mutate-junit.xml"
    report.unlink(missing_ok=True)
    subprocess.run(
        [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={report}", tests],
        cwd=copy,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if not report.exists():
        return {"<collection>": ("fail", "no junit report")}
    out = {}
    for case in ET.parse(report).getroot().iter("testcase"):
        bad = case.find("failure")
        if bad is None:
            bad = case.find("error")
        out[case.get("name", "?")] = ("pass", "") if bad is None else ("fail", bad.get("message", ""))
    return out


def _is_raises(node: ast.AST) -> bool:
    return isinstance(node, ast.With) and any(
        isinstance(i.context_expr, ast.Call) and ast.unparse(i.context_expr.func) == "pytest.raises" for i in node.items
    )


def assertions(path: Path) -> list[tuple[int, str]]:
    """(line, enclosing test function) of every assert and pytest.raises block in a test file."""
    out = []
    for fn in ast.walk(ast.parse(path.read_text())):
        if isinstance(fn, ast.FunctionDef) and fn.name.startswith("test"):
            out += [(n.lineno, fn.name) for n in ast.walk(fn) if isinstance(n, ast.Assert) or _is_raises(n)]
    return sorted(out)


class _OnlyOne(ast.NodeTransformer):
    def __init__(self, keep: int) -> None:
        self.keep = keep

    def visit_Assert(self, node: ast.Assert) -> ast.AST:
        return node if node.lineno == self.keep else ast.copy_location(ast.Expr(node.test), node)

    def visit_With(self, node: ast.With) -> ast.AST:
        self.generic_visit(node)
        if _is_raises(node) and node.lineno != self.keep:
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and ast.unparse(call.func) == "pytest.raises":
                    call.func = ast.Attribute(ast.Name("contextlib", ast.Load()), "suppress", ast.Load())
                    call.keywords = []
        return node


def only_one(source: str, keep: int) -> str:
    tree = _OnlyOne(keep).visit(ast.parse(source))
    future = [i for i, n in enumerate(tree.body) if isinstance(n, ast.ImportFrom) and n.module == "__future__"]
    at = future[-1] + 1 if future else 0
    tree.body.insert(at, ast.Import([ast.alias("contextlib")]))
    return ast.unparse(ast.fix_missing_locations(tree)) + "\n"


def _kind(message: str) -> str:
    return "assert" if message.startswith(("assert", "AssertionError", "Failed: DID NOT RAISE")) else "crash"


def mutate_all(copy, py, tests, env, mutations, also):
    results = []
    for m in mutations:
        target = copy / m["file"]
        original = target.read_text()
        count = original.count(m["old"])
        entry = {k: m.get(k) for k in ("id", "file", "why")}
        if count != 1:
            entry.update(status="invalid", reason=f"'old' occurs {count} times")
            results.append(entry)
            continue
        target.write_text(original.replace(m["old"], m["new"]))
        try:
            outcome = run_tests(copy, py, tests, env)
            entry["failed"] = {t: msg[:160] for t, (v, msg) in outcome.items() if v != "pass"}
            entry["status"] = "killed" if entry["failed"] else "survived"
            entry["also_ok"] = also()
        finally:
            target.write_text(original)
        results.append(entry)
    return results


def per_assertion(copy: Path, py: str, tests: str, env: dict[str, str], mutations: list[dict]) -> dict:
    """Rerun every mutation once per live assertion; print and return what each assertion caught."""
    per: dict[str, dict[str, str]] = {}
    for test_file in sorted((copy / tests).rglob("test_*.py")):
        source = test_file.read_text()
        for line, fn in assertions(test_file):
            key = f"{test_file.relative_to(copy)}:{line} ({fn})"
            test_file.write_text(only_one(source, line))
            try:
                per[key] = _kills_for(
                    copy, py, tests, env, mutations, fn, "with pytest.raises" in source.splitlines()[line - 1]
                )
            finally:
                test_file.write_text(source)
    print()
    for key, kills in per.items():
        shown = ", ".join(f"{i}{'' if k == 'assert' else '(' + k + ')'}" for i, k in kills.items())
        print(f"{key}: {shown or 'CAUGHT NOTHING'}")
    return per


def _kills_for(copy, py, tests, env, mutations, fn: str, raises: bool) -> dict[str, str]:
    if run_tests(copy, py, tests, env).get(fn, ("fail", ""))[0] != "pass":
        return {"<baseline>": "variant fails unmutated"}
    kills = {}
    for e in mutate_all(copy, py, tests, env, mutations, lambda: None):
        if fn in e.get("failed", {}):
            kills[e["id"]] = "assert" if raises else _kind(e["failed"][fn])
    return kills


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", type=Path)
    ap.add_argument("mutations", type=Path)
    ap.add_argument("workdir", type=Path)
    ap.add_argument("--python", default=None, help="interpreter; default REPO/.venv/bin/python")
    ap.add_argument("--tests", default="tests")
    ap.add_argument("--package", default="matinee", help="package whose import path is verified")
    ap.add_argument("--also", default=None, help="shell command run in the copy after each mutation")
    ap.add_argument("--per-assertion", action="store_true")
    args = ap.parse_args()
    repo, work = args.repo.resolve(), args.workdir.resolve()
    py = args.python or str(repo / ".venv/bin/python")
    copy = work / "copy"
    copy_repo(repo, copy)
    env = {**os.environ, "PYTHONPATH": str(copy / "src"), "PYTHONDONTWRITEBYTECODE": "1"}

    where = subprocess.run(
        [py, "-c", f"import {args.package}; print({args.package}.__file__)"],
        cwd=copy,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not where.startswith(str(copy)):
        sys.exit(f"{args.package} imports from {where}, not the copy; refusing to run")

    def also() -> bool | None:
        if not args.also:
            return None
        return subprocess.run(args.also, shell=True, cwd=copy, env=env, capture_output=True).returncode == 0  # noqa: S602 -- --also is a shell command the developer passes on this tool's own command line

    baseline = run_tests(copy, py, args.tests, env)
    if not baseline or any(v != "pass" for v, _ in baseline.values()):
        sys.exit(f"baseline does not pass: {baseline}")
    if also() is False:
        sys.exit("the --also command fails on the unmutated copy; fix the command before reading any result")
    mutations = json.loads(args.mutations.read_text())
    results = mutate_all(copy, py, args.tests, env, mutations, also)
    manifest: dict[str, object] = {"baseline": sorted(baseline), "mutations": results}
    for e in results:
        failed = ", ".join(e.get("failed", {})) or "-"
        print(f"{e['id']:5} {e['status']:9} also_ok={e.get('also_ok')!s:5} {failed}")

    if args.per_assertion:
        manifest["per_assertion"] = per_assertion(copy, py, args.tests, env, mutations)

    (work / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
