"""The review queue: every note is open when filed, and a ruling records a status, a reason and the label ruling."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from matinee.store import Note, Store, StoreError


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "matinee.sqlite")


def filed(store: Store, name: str = "Ada", tmdb: int = 603) -> int:
    profile, _ = store.create(name, None, [], [])
    store.note(Note(profile.id, tmdb, "horror", "genre", ("Scary.",), True, "not scary", ("thriller",)))
    return store.notes()[-1].id


def test_a_new_note_is_open_with_everything_the_viewer_said(store: Store) -> None:
    note_id = filed(store)
    [note] = store.notes()
    assert note.id == note_id and note.status == "open" and note.reason is None and note.ruling is None
    assert (note.profile, note.tmdb, note.tree, note.kind) == ("Ada", 603, "horror", "genre")
    assert note.path == ("Scary.",) and note.rushed and note.comment == "not scary" and note.belongs == ("thriller",)
    assert note.at.startswith("20") and note.ruled_at is None


def test_an_accepted_note_carries_its_reason_and_label_ruling_and_leaves_the_queue(store: Store) -> None:
    note_id = filed(store)
    before = store.rule(note_id, "accepted", "  fair, it is a thriller ", "moved to thriller in settle 2026-10-03")
    assert before.status == "open"
    after = store.filed(note_id)
    assert after.status == "accepted" and after.reason == "fair, it is a thriller"
    assert after.ruling == "moved to thriller in settle 2026-10-03" and after.ruled_at is not None
    assert store.notes() == [] and [n.id for n in store.notes("accepted")] == [note_id]


def test_a_second_ruling_replaces_the_first_and_returns_it(store: Store) -> None:
    note_id = filed(store)
    store.rule(note_id, "accepted", "looked right", "r-1")
    replaced = store.rule(note_id, "rejected", "on a second look it is horror")
    assert (replaced.status, replaced.reason, replaced.ruling) == ("accepted", "looked right", "r-1")
    now = store.filed(note_id)
    assert (now.status, now.reason, now.ruling) == ("rejected", "on a second look it is horror", None)
    assert [n.id for n in store.notes("rejected")] == [note_id]


@pytest.mark.parametrize(
    "status,reason,ruling,code",
    [
        ("accepted", "fine", None, "bad_ruling"),
        ("rejected", "fine", "r-1", "bad_ruling"),
        ("rejected", "   ", None, "bad_reason"),
        ("rejected", "two\nlines", None, "bad_reason"),
        ("rejected", "x" * 301, None, "bad_reason"),
        ("accepted", "fine", "  ", "bad_reason"),
    ],
)
def test_a_ruling_needs_one_line_and_a_label_ruling_only_when_accepted(
    store: Store, status: str, reason: str, ruling: str | None, code: str
) -> None:
    note_id = filed(store)
    with pytest.raises(StoreError) as refused:
        store.rule(note_id, status, reason, ruling)  # type: ignore[arg-type]
    assert refused.value.code == code
    assert store.filed(note_id).status == "open"


def test_a_ruling_on_a_note_that_does_not_exist_is_refused(store: Store) -> None:
    filed(store)
    with pytest.raises(StoreError) as refused:
        store.rule(99, "rejected", "no such note")
    assert refused.value.code == "no_note"
    with pytest.raises(StoreError):
        store.filed(99)


def test_the_queue_lists_oldest_first(store: Store) -> None:
    first, second = filed(store, "Ada", 1), filed(store, "Bo", 2)
    assert [n.id for n in store.notes()] == [first, second]


def test_a_note_outlives_the_profile_that_filed_it(store: Store, tmp_path: Path) -> None:
    note_id = filed(store, "Gone")
    keeper = filed(store, "Stays", 2)
    with sqlite3.connect(tmp_path / "matinee.sqlite") as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("DELETE FROM profiles WHERE name = 'Gone'")
    queue = store.notes()
    assert [(n.id, n.profile) for n in queue] == [(note_id, None), (keeper, "Stays")]
    assert queue[0].comment == "not scary" and queue[0].status == "open"
    store.rule(note_id, "rejected", "the viewer is gone, the film is right")
    assert store.filed(note_id).profile is None
