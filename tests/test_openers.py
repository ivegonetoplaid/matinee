"""Matinee answers what a viewer just said: a line it speaks opens with a stock interjection or a lone word set
off by punctuation ("So, …", "Very well. …", "Horror. …") only when it is named in KEPT, a line written to land
that way on purpose.

The count covers the data files' door openings, questions, replies and pick lines, and every sentence the
page or the server says to a viewer. The page's and the server's sentences are found as string literals in
their source; a literal that matches the form but is not Matinee speaking (an answer a viewer taps, a CSS
selector) is named in NOT_SPOKEN, so a new one fails here until someone decides which it is.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterator
from pathlib import Path

from matinee.reference import DATA

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "src/matinee/web/static/js"
SERVER = ROOT / "src/matinee/web"

# Lines that take the form on purpose, each with what it is doing. A new line in the form fails until it is named
# here or rewritten.
KEPT = {
    "Hi, ${suggestion.name}.": "the front door greets a returning viewer by name",
    "life, uh, finds a way.": "Jurassic Park",
    "war. war never changes.": "Fallout",
    "right. we'll keep the naughty bits offstage.": "the beat before the promise is the joke",
    "very well. I shall fetch the wheel of nonsense.": "the butler's voice is the joke",
    "Sheesh. Tough crowd. Tough crowd.": "a comic's aside",
    "okay, who's on the couch?": "the kids' door talks the way a parent does",
    "comedies, camp and the gloriously awful. let's find you one.": "a list, not an interjection",
    "paws, claws and whiskers, coming up.": "a list, not an interjection",
}

# A lone word set off by a comma, full stop, colon or exclamation mark, or one of the stock phrases.
LONE = re.compile(r"^[\"'(]*[A-Za-z']+(?:[,.:!]|\.\.\.|…)(?:\s|$)")
STOCK = re.compile(
    r"^[\"'(]*(very well|no problem|one moment|of course|all right|right then|heads up|fair enough|no matter"
    r"|welcome back|very good|oh,? good)\b",
    re.IGNORECASE,
)

# Literals in the page and server source that take the form but are not Matinee speaking.
NOT_SPOKEN = {
    "button, input",  # CSS selectors and media queries
    "input, button",
    "(pointer: coarse)",
    "private, max-age={}",  # a response header
    "set, checked at each pick",  # the server's log
    "Matinee: a private screening",  # a heading only a screen reader hears
    "Yes, that's me",  # answers a viewer taps
    "No, someone else",
    "No PIN",
    "PIN, four digits",
    "Yes, let me pick from a list",
    "No, show me everything",
    "Search, like spiders or needles",  # a field's placeholder
    "Yes, delete it",
    "No, keep it",
    "Never mind, show me everything",
    "Never mind, keep my list",
}


def opens_stock(line: str) -> bool:
    """True when `line` opens with a stock interjection or a lone word set off by punctuation."""
    return bool(LONE.match(line) or STOCK.match(line))


def data_lines(data: Path = DATA) -> Iterator[tuple[str, str]]:
    """Every line the data files give Matinee, as (where, line)."""
    for path in sorted((data / "trees").glob("*.json")):
        tree = json.loads(path.read_text(encoding="utf-8"))
        yield f"{path.name} opening", tree["opening"]
        for q in tree.get("questions", []):
            yield f"{path.name} {q['id']} ask", q["ask"]
            for i, o in enumerate(q["options"]):
                if o.get("reply"):
                    yield f"{path.name} {q['id']} reply {i}", o["reply"]
    first = json.loads((data / "first_question.json").read_text(encoding="utf-8"))
    for i, line in enumerate(first["lines"]):
        yield f"first_question.json line {i}", line
    yield "first_question.json source ask", first["source"]["ask"]
    for o in first["source"]["options"]:
        yield f"first_question.json source reply {o['source']}", o["reply"]
    quips = json.loads((data / "quips.json").read_text(encoding="utf-8"))
    for category, sets in quips["categories"].items():
        for kind, lines in sets.items():
            for i, line in enumerate(lines):
                yield f"quips.json {category} {kind} {i}", line


LITERAL = re.compile(r'"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`|\'((?:[^\'\\\n]|\\.)*)\'')


def page_lines(page: Path = PAGE) -> Iterator[tuple[str, str]]:
    """Every string literal in the page's scripts, comments aside, as (where, literal)."""
    for path in sorted(page.glob("*.js")):
        for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = raw.split("//", 1)[0] if raw.lstrip().startswith("//") or " // " in raw else raw
            for m in LITERAL.finditer(code):
                text = next(g for g in m.groups() if g is not None)
                yield f"{path.name}:{n}", text


def _docstrings(tree: ast.AST) -> set[int]:
    nodes = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, nodes) and node.body and isinstance(node.body[0], ast.Expr)
    }


def _fstring(node: ast.JoinedStr) -> str:
    """An f-string's literal parts, each placeholder read as "{}"."""
    out = []
    for part in node.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            out.append(part.value)
        else:
            out.append("{}")
    return "".join(out)


def server_lines(server: Path = SERVER) -> Iterator[tuple[str, str]]:
    """Every string constant in the web server's modules, docstrings aside, as (where, text); an f-string is
    read as its literal parts with each placeholder as "{}"."""
    for path in sorted(server.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstrings(tree)
        parts = {id(v) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for v in node.values}
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                yield f"{path.name}:{node.lineno}", _fstring(node)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip | parts:
                yield f"{path.name}:{node.lineno}", node.value


def stock_openers() -> list[tuple[str, str]]:
    """Every spoken line that opens in the stock form, wherever it lives."""
    found = [(where, line) for where, line in data_lines() if opens_stock(line)]
    for where, text in [*page_lines(), *server_lines()]:
        if text in NOT_SPOKEN or not opens_stock(text):
            continue
        found.append((where, text))
    return found


def test_only_lines_kept_on_purpose_open_with_a_stock_interjection_or_a_lone_word() -> None:
    found = [(where, line) for where, line in stock_openers() if line not in KEPT]
    assert not found, "\n".join(f"{where}: {line}" for where, line in found)


def test_every_kept_line_is_still_spoken_and_still_takes_the_form() -> None:
    spoken = {line for _, line in stock_openers()}
    assert not set(KEPT) - spoken, sorted(set(KEPT) - spoken)


def test_the_form_is_recognised() -> None:
    for line in (
        "So, what are we in the mood for?",
        "very well. stand back.",
        "Horror. excellent choice.",
        "Done.",
        "Oh, I almost recommended a film.",
        "abracadabra...",
        "Heads up: it's one where {}.",
        "Hi, {}.",
        "Fair enough. Moving on.",
        "Sheesh! Tough crowd.",
        "very good. somebody save the city.",
        "oh good. a meet-cute.",
    ):
        assert opens_stock(line), line
    for line in (
        "Right this way.",
        "I have a bad feeling about this...",
        "Pull up a chair.",
        "True stories, and here's one worth your time.",
        "War never changes.",
        "Who's watching?",
        "soft blankets and no monsters.",
        "so what are you in for?",
    ):
        assert not opens_stock(line), line


def test_every_not_spoken_literal_still_exists() -> None:
    texts = {text for _, text in [*page_lines(), *server_lines()]}
    assert not NOT_SPOKEN - texts, sorted(NOT_SPOKEN - texts)
