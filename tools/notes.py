"""Go through viewers' notes in Matinee's own store.

Run on the server, inside the same image as the server, against its state
directory. It writes only Matinee's own store, never a film's placement, labels
or pins: an accepted note is fixed for every viewer through the label rulings
and the settle step.

    python tools/notes.py list
    python tools/notes.py accept <note> "<reason>" --ruling "<the label ruling that fixed it>"
    python tools/notes.py reject <note> "<reason>"

The state directory comes from `--state` or MATINEE_STATE. A ruling on a note
already ruled replaces the earlier one and prints it. The film is printed before
any ruling is written.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from matinee.reference import DATA
from matinee.store import FiledNote, Store, StoreError


@dataclass(frozen=True)
class Names:
    """What a note's ids read as: each film's title and year, and each door's label."""

    films: dict[int, str]
    doors: dict[str, str]

    def film(self, tmdb: int) -> str:
        return self.films.get(tmdb, f"film {tmdb} (not in the film table)")

    def door(self, tree: str) -> str:
        return self.doors.get(tree, tree)


def load_names(state: Path, data: Path = DATA) -> Names:
    """Film titles from the state's film table, read-only, and door labels from the first question."""
    films: dict[int, str] = {}
    table = state / "films.sqlite"
    if table.exists():
        with sqlite3.connect(f"file:{table}?mode=ro", uri=True) as db:
            for tmdb, name, year in db.execute("SELECT tmdb, name, year FROM films"):
                films[int(tmdb)] = f"{name} ({year})" if year else str(name)
    first = json.loads((data / "first_question.json").read_text(encoding="utf-8"))
    return Names(films, {o["tree"]: o["label"] for o in first["options"]})


def what_was_wrong(note: FiledNote, door: str) -> str:
    """The viewer's choice in the panel's own words, with where a "Not <genre> at all" film belongs."""
    if note.kind == "genre":
        where = f"; belongs in {', '.join(note.belongs)}" if note.belongs else ""
        return f"Not {door.lower()} at all{where}"
    if note.kind == "kind":
        return f"{door}, but not the kind I asked for"
    return "The right kind, just not a good pick"


def describe(note: FiledNote, names: Names) -> list[str]:
    door = names.door(note.tree)
    answers = [*note.path, "Just pick one!"] if note.rushed else list(note.path)
    lines = [
        f"#{note.id}  {names.film(note.tmdb)}, under {door}",
        f"    filed {note.at[:16].replace('T', ' ')} UTC by {note.profile or 'a deleted profile'}",
        f"    answers: {' > '.join(answers) if answers else '(none)'}",
        f"    wrong: {what_was_wrong(note, door)}",
    ]
    if note.comment:
        lines.append(f"    comment: {note.comment}")
    if note.status != "open":
        ruling = f" ({note.ruling})" if note.ruling else ""
        lines.append(f"    ruled {note.status}: {note.reason}{ruling}")
    return lines


def list_open(store: Store, names: Names) -> int:
    queue = store.notes()
    for note in queue:
        print("\n".join(describe(note, names)))
    print(f"{len(queue)} open {'note' if len(queue) == 1 else 'notes'}.")
    return 0


def rule(store: Store, names: Names, args: argparse.Namespace) -> int:
    note = store.filed(args.note)
    print(f"Note #{note.id}: {names.film(note.tmdb)}, under {names.door(note.tree)}.")
    if args.command == "accept":
        status, before = "accepted", store.rule(note.id, "accepted", args.reason, args.ruling)
    else:
        status, before = "rejected", store.rule(note.id, "rejected", args.reason)
    if before.status != "open":
        ruling = f" ({before.ruling})" if before.ruling else ""
        print(f"Replaced the earlier ruling: {before.status}, {before.reason}{ruling}.")
    print(f"Recorded: {status}.")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--state", type=Path, default=os.environ.get("MATINEE_STATE"), help="Matinee's state directory")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="the open notes, oldest first")
    accept = commands.add_parser("accept", help="accept a note, naming the label ruling that fixed it")
    accept.add_argument("note", type=int)
    accept.add_argument("reason")
    accept.add_argument("--ruling", required=True, help="the label ruling that fixed it")
    reject = commands.add_parser("reject", help="reject a note")
    reject.add_argument("note", type=int)
    reject.add_argument("reason")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.state is None or not (args.state / "matinee.sqlite").is_file():
        print(f"No Matinee store in {args.state}; pass --state or set MATINEE_STATE.", file=sys.stderr)
        return 2
    store = Store(args.state / "matinee.sqlite")
    try:
        if args.command == "list":
            return list_open(store, load_names(args.state))
        return rule(store, load_names(args.state), args)
    except StoreError as exc:
        print(f"Refused: {exc}.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
