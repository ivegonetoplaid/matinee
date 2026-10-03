"""The fifteen avatars ship as finished web images: two sizes each, square, small, and never a source image."""

from __future__ import annotations

from pathlib import Path

from matinee.store import AVATARS
from matinee.web.app import STATIC

AVATAR_DIR = STATIC / "avatars"
SIZES = (256, 80)  # twice the front door's tile (128 px) and the top bar's mark (40 px)
LARGEST_PAIL = max(p.stat().st_size for p in (STATIC / "pails").glob("*.webp"))


def webp_size(path: Path) -> tuple[int, int]:
    """The canvas of an extended (VP8X) WebP, as every avatar with transparency is written."""
    head = path.read_bytes()[:30]
    assert head[:4] == b"RIFF" and head[8:12] == b"WEBP" and head[12:16] == b"VP8X", path.name
    width = int.from_bytes(head[24:27], "little") + 1
    height = int.from_bytes(head[27:30], "little") + 1
    return width, height


def test_every_avatar_ships_square_at_both_sizes_and_nothing_else_does() -> None:
    expected = {f"{a}-{n}.webp" for a in AVATARS for n in SIZES}
    assert {p.name for p in AVATAR_DIR.iterdir()} == expected
    for avatar in AVATARS:
        for n in SIZES:
            assert webp_size(AVATAR_DIR / f"{avatar}-{n}.webp") == (n, n)


def test_the_avatars_stay_within_their_budget() -> None:
    tiles = [(AVATAR_DIR / f"{a}-256.webp").stat().st_size for a in AVATARS]
    assert max(tiles) <= LARGEST_PAIL
    assert sum(p.stat().st_size for p in AVATAR_DIR.iterdir()) < 1_000_000
