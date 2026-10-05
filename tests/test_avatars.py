"""Avatars: optional, one of the fifteen Matinee offers, set by the device holding the profile."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from matinee.store import AVATARS, Store, StoreError


def test_fifteen_avatars_are_offered() -> None:
    assert len(AVATARS) == 15 and len(set(AVATARS)) == 15


def test_a_profile_is_made_with_an_avatar_or_none_and_two_may_share_one(tmp_path: Path) -> None:
    store = Store(tmp_path / "matinee.sqlite")
    assert store.create("Ada", None, [], "popcorn")[0].avatar == "popcorn"
    assert store.create("Bo", None, [], "popcorn")[0].avatar == "popcorn"
    assert store.create("Cy", None, [])[0].avatar is None
    with pytest.raises(StoreError) as refused:
        store.create("Di", None, [], "spaceship")
    assert refused.value.code == "bad_avatar"


def test_an_avatar_matinee_no_longer_offers_reads_as_none(tmp_path: Path) -> None:
    store = Store(tmp_path / "matinee.sqlite")
    me, token = store.create("Ada", None, [], "vhs")
    with sqlite3.connect(tmp_path / "matinee.sqlite") as db:
        db.execute("UPDATE profiles SET avatar = 'laserdisc' WHERE id = ?", (me.id,))
    assert store.holding([token])[token].avatar is None
