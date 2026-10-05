"""Go through viewers' notes, clear a forgotten PIN, and clear kept DoesTheDogDie topics, in Matinee's own store.

Run on the server, inside the same image as the server, against its state
directory. It writes only Matinee's own store, never a film's placement, labels
or pins: an accepted note is fixed for every viewer through the label rulings
and the settle step.

    python tools/notes.py list
    python tools/notes.py accept <note> "<reason>" --ruling "<the label ruling that fixed it>"
    python tools/notes.py reject <note> "<reason>"
    python tools/notes.py clear-pin "<profile name>"
    python tools/notes.py clear-topics

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
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from matinee.reference import DATA
from matinee.store import FiledNote, Store, StoreError
from matinee.upgrade import ShapeError

MAX_NOTE_ID = 2**62


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
    """Film titles from the state's film table, read-only and made printable (the media server names them), and
    door labels from the first question."""
    films: dict[int, str] = {}
    table = state / "films.sqlite"
    if table.exists():
        with sqlite3.connect(f"file:{table}?mode=ro", uri=True) as db:
            for tmdb, name, year in db.execute("SELECT tmdb, name, year FROM films"):
                films[int(tmdb)] = printable(f"{name} ({year})" if year else str(name))
    first = json.loads((data / "first_question.json").read_text(encoding="utf-8"))
    return Names(films, {o["tree"]: o["label"] for o in first["options"]})


def printable(text: str) -> str:
    """Viewer text made safe for the operator's terminal: one line, with no control or format character left."""
    flat = " ".join(text.split())
    return "".join("\ufffd" if unicodedata.category(c).startswith("C") else c for c in flat)


def what_was_wrong(note: FiledNote, door: str, names: Names) -> str:
    """The viewer's choice in the panel's own words, with where a "Not <genre> at all" film belongs, by door."""
    if note.kind == "genre":
        where = f"; belongs in {', '.join(names.door(t) for t in note.belongs)}" if note.belongs else ""
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
        f"    wrong: {what_was_wrong(note, door, names)}",
    ]
    if note.comment:
        lines.append(f"    comment: {printable(note.comment)}")
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
    print("\n".join(describe(note, names)))
    if args.command == "accept":
        status, before = "accepted", store.rule(note.id, "accepted", args.reason, args.ruling)
    else:
        status, before = "rejected", store.rule(note.id, "rejected", args.reason)
    if before.status != "open":
        ruling = f" ({before.ruling})" if before.ruling else ""
        print(f"Replaced the earlier ruling: {before.status}, {before.reason}{ruling}.")
    print(f"Recorded: {status}.")
    return 0


def clear_pin(store: Store, args: argparse.Namespace) -> int:
    profile = store.clear_pin(args.name)
    print(f"Cleared the PIN on {profile.name}. It now opens without one.")
    return 0


def clear_topics(store: Store) -> int:
    cleared = store.clear_topics()
    print(f"Cleared the DoesTheDogDie topics of {cleared} {'profile' if cleared == 1 else 'profiles'}.")
    return 0


def note_id(text: str) -> int:
    number = int(text)
    if not 0 < number < MAX_NOTE_ID:
        raise argparse.ArgumentTypeError(f"no note is numbered {text}")
    return number


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--state", type=Path, default=os.environ.get("MATINEE_STATE"), help="Matinee's state directory")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="the open notes, oldest first")
    accept = commands.add_parser("accept", help="accept a note, naming the label ruling that fixed it")
    accept.add_argument("note", type=note_id)
    accept.add_argument("reason")
    accept.add_argument("--ruling", required=True, help="the label ruling that fixed it")
    reject = commands.add_parser("reject", help="reject a note")
    reject.add_argument("note", type=note_id)
    reject.add_argument("reason")
    pin = commands.add_parser("clear-pin", help="clear one profile's PIN and any lockout on it")
    pin.add_argument("name")
    commands.add_parser("clear-topics", help="clear every profile's DoesTheDogDie topics, kept since a key was removed")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.state is None or not (args.state / "matinee.sqlite").is_file():
        print(f"No Matinee store in {args.state}; pass --state or set MATINEE_STATE.", file=sys.stderr)
        return 2
    try:
        store = Store(args.state / "matinee.sqlite")
        if args.command == "list":
            return list_open(store, load_names(args.state))
        if args.command == "clear-pin":
            return clear_pin(store, args)
        if args.command == "clear-topics":
            return clear_topics(store)
        return rule(store, load_names(args.state), args)
    except (StoreError, ShapeError) as exc:
        print(f"Refused: {exc}.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
