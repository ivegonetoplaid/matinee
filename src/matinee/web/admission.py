"""The door word: whether a device is admitted past the locked door.

With no door word set, every device is admitted. With one set, a device is
admitted only by an admission cookie this server issued: the time it was issued
and an HMAC-SHA256 over that time, the match mode and the door word, keyed by an
installation secret made once at the first start and kept in the state directory.
Only the server can make or check one, so a value set by hand admits nothing, and
holding one gives no way of testing guesses at the word away from the server.
Changing the word or the mode ends every admission; a restart or a redeploy does
not. An admission lasts 400 days. A profile token never admits a device.

In relaxed mode both words lose letter case, spaces and punctuation before they
are compared, and they may differ by one single-character edit. In strict mode
the typed word must equal the door word exactly.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import unicodedata
from pathlib import Path
from typing import Literal

Mode = Literal["relaxed", "strict"]
COOKIE = "matinee_admit"
LIFE_S = 400 * 24 * 3600
RELAXED_MIN = 8
STRICT_MIN = 12
KEY_FILE = "door.key"
SECRET_BYTES = 32
MAX_TYPED = 200  # a longer guess is wrong without being compared
CLOCK_SKEW_S = 300


class AdmissionError(RuntimeError):
    """The installation secret cannot be made or read; Matinee does not start."""


def edits(a: str, b: str) -> int:
    """Levenshtein distance: single-character insertions, deletions and substitutions."""
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def relaxed_key(text: str) -> str:
    """The word as relaxed mode compares it: no letter case, no spaces, no punctuation."""
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


def too_long(word: str) -> bool:
    """Whether the door word is longer than any typed word Matinee compares, so that nobody could ever give it."""
    return len(word) > MAX_TYPED


def too_short(word: str, mode: Mode) -> bool:
    """Whether the door word is shorter than its mode allows: 8 after relaxing, or 12 as typed."""
    if mode == "relaxed":
        return len(relaxed_key(word)) < RELAXED_MIN
    return len(word) < STRICT_MIN


def load_secret(state: Path) -> bytes:
    """The installation secret, made once with 32 random bytes and kept, owner-only, in the state directory."""
    path = state / KEY_FILE
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "wb") as out:
            out.write(secrets.token_bytes(SECRET_BYTES))
    try:
        secret = path.read_bytes()
    except OSError as exc:
        raise AdmissionError(f"the door's secret at {path} cannot be read") from exc
    if len(secret) != SECRET_BYTES:
        raise AdmissionError(f"the door's secret at {path} is not {SECRET_BYTES} bytes")
    return secret


class Admission:
    """The door word's check. `locked` is False when no door word is set, and then every device is admitted."""

    def __init__(self, word: str | None, mode: Mode, secret: bytes) -> None:
        self._word = word
        self._mode = mode
        self._secret = secret

    @property
    def locked(self) -> bool:
        return self._word is not None

    def _mac(self, issued: int) -> str:
        message = f"{issued}\x00{self._mode}\x00{self._word}".encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    def issue(self, now: float) -> str:
        issued = int(now)
        return f"{issued}.{self._mac(issued)}"

    def admits(self, cookie: str | None, now: float) -> bool:
        """Whether this admission cookie was issued by this server, for this word, within the last 400 days."""
        if not self.locked:
            return True
        issued_text, _, mac = (cookie or "").partition(".")
        if not issued_text.isascii() or not issued_text.isdigit() or len(issued_text) > 12:
            return False
        issued = int(issued_text)
        if not hmac.compare_digest(mac.encode(), self._mac(issued).encode()):
            return False
        return issued - CLOCK_SKEW_S <= now < issued + LIFE_S

    def matches(self, typed: str) -> bool:
        """Whether a typed word opens the door, as the mode compares it."""
        word = self._word
        if word is None:
            return True
        if len(typed) > MAX_TYPED:
            return False
        if self._mode == "strict":
            return hmac.compare_digest(typed.encode("utf-8", "surrogatepass"), word.encode("utf-8", "surrogatepass"))
        a, b = relaxed_key(typed), relaxed_key(word)
        return abs(len(a) - len(b)) <= 1 and edits(a, b) <= 1
