"""Every handle in the spec's map names a file that exists and a symbol defined in it.

The map is the part of docs/spec/matinee.md after "# Part 2 — Map". Each of its bullets holds one or more handles in
backticks: `path::symbol`, or a bare `path` for a file or folder named whole. A later span on the same bullet with no
path of its own is another symbol of the last path named (`path::a` / `b`). A span inside parentheses is a
description and is not checked. A path is relative to the repository root.

A symbol is found by its file's type, so a handle cannot pass by matching a word in a comment:

- Python: a function, class or assignment (annotated or not, `self.name =` included) of that name anywhere in the
  module, read with `ast`. `A.b` is a `b` defined inside the class or function `A`.
- JavaScript: `function`, `class`, `const`, `let` or `var` of that name, exported or not; or a method or object
  member defined at the start of a line, as `name(...) {` or `name:`. `A.b` is `A` declared and `b` defined so.
- CSS: a custom property defined as `--name:`, or a selector (`.a`, `.a > .b`, `.a::before`, `:root`,
  `@keyframes a`) standing in some rule's selector list, with no more of a name after it.
- JSON: a key, `"name":`.

Any other file takes no symbol.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "spec" / "matinee.md"
MAP_HEADING = "# Part 2 — Map"
FEWEST_HANDLES = 300  # the map held about 600 symbols when this test was written; far fewer means the parse broke


def spans(line: str) -> list[str]:
    """The backtick spans of a bullet that stand outside parentheses, in order."""
    found: list[str] = []
    depth = 0
    for i, part in enumerate(line.split("`")):
        if i % 2:
            if depth == 0:
                found.append(part)
            continue
        depth = max(0, depth + part.count("(") - part.count(")"))
    return found


def is_path(span: str) -> bool:
    """Whether a span starts with a path; a CSS pseudo-element (`.topbar::before`) does not."""
    head = span.partition("::")[0]
    return "/" in head or (ROOT / head).is_file()


def handles(spec: str) -> list[tuple[str, str | None]]:
    """Each (path, symbol) the map names; symbol None for a path named whole."""
    out: list[tuple[str, str | None]] = []
    for line in spec.split(MAP_HEADING, 1)[1].splitlines():
        if not line.startswith("- "):
            continue
        path = ""
        for span in spans(line):
            if is_path(span):
                path, _, symbol = span.partition("::")
                out.append((path, symbol or None))
            else:
                out.append((path, span))  # another symbol of the last path; "" when the bullet named none first
    return out


def _python_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name))
            names.update(t.attr for t in targets if isinstance(t, ast.Attribute) and _is_self(t.value))
    return names


def _is_self(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "self"


def in_python(text: str, symbol: str) -> bool:
    module = ast.parse(text)
    outer, _, inner = symbol.rpartition(".")
    if not outer:
        return symbol in _python_names(module)
    owners = (
        n
        for n in ast.walk(module)
        if isinstance(n, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) and n.name == outer
    )
    return any(inner in _python_names(owner) - {outer} for owner in owners)


def _js_declared(text: str, name: str) -> bool:
    return re.search(rf"\b(?:function\*?|class|const|let|var)\s+{re.escape(name)}\b", text) is not None


def _js_member(text: str, name: str) -> bool:
    method = rf"^\s*(?:(?:static|async|get|set)\s+)*{re.escape(name)}\s*\(.*\)\s*\{{\s*$"
    member = rf"^\s*{re.escape(name)}\s*:"
    return re.search(method, text, re.M) is not None or re.search(member, text, re.M) is not None


def in_javascript(text: str, symbol: str) -> bool:
    outer, _, inner = symbol.rpartition(".")
    if not outer:
        return _js_declared(text, symbol) or _js_member(text, symbol)
    return _js_declared(text, outer) and _js_member(text, inner)


def in_css(text: str, symbol: str) -> bool:
    css = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    if symbol.startswith("--"):
        return re.search(rf"(?<![\w-]){re.escape(symbol)}\s*:", css) is not None
    wanted = " ".join(symbol.split())
    # A class, state or at-rule may follow more of a compound selector (`.pick-line.hushed`); an element may not.
    before = r"(?<![\w-])" if wanted[0].isalnum() else ""
    alone = rf"{before}{re.escape(wanted)}(?![\w-])"
    return any(re.search(alone, " ".join(s.split())) for s in re.findall(r"([^{};]+)\{", css))


def in_json(text: str, symbol: str) -> bool:
    return re.search(rf'"{re.escape(symbol)}"\s*:', text) is not None


FINDERS = {".py": in_python, ".js": in_javascript, ".mjs": in_javascript, ".css": in_css, ".json": in_json}


def problem(path: str, symbol: str | None) -> str | None:
    """Why the handle does not resolve, or None when it does."""
    where = ROOT / path
    if not path or not where.exists():
        return f"{path or '(no path)'}: no such file"
    if symbol is None:
        return None
    finder = FINDERS.get(where.suffix) if where.is_file() else None
    if finder is None:
        return f"{path}::{symbol}: a {where.suffix or 'folder'} takes no symbol"
    if not finder(where.read_text(encoding="utf-8"), symbol):
        return f"{path}::{symbol}: not defined there"
    return None


def test_every_handle_in_the_map_names_a_file_and_a_symbol_defined_in_it() -> None:
    named = handles(SPEC.read_text(encoding="utf-8"))
    assert len(named) >= FEWEST_HANDLES
    assert [p for p in (problem(path, symbol) for path, symbol in named) if p] == []


def test_each_finder_refuses_a_symbol_its_file_does_not_define() -> None:
    planted = [
        ("src/matinee/store.py", "Store.no_such_method"),
        ("src/matinee/web/static/js/main.js", "noSuchFunction"),
        ("src/matinee/web/static/css/matinee.css", ".no-such-class"),
        ("src/matinee/web/static/css/matinee.css", "--no-such-token"),
        ("data/first_question.json", "no_such_key"),
        ("src/matinee/web/static/avatars", "popcorn"),
        ("no/such/file.py", None),
    ]
    assert [p for p in planted if problem(*p) is None] == []
