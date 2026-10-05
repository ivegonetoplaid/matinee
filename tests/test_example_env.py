"""example.env names every setting Matinee reads, each commented out, with no value filled in."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_example_env_names_every_setting_the_spec_lists_and_fills_in_none() -> None:
    spec = (ROOT / "docs" / "spec" / "matinee.md").read_text(encoding="utf-8")
    listed = {
        name for row in re.findall(r"^\| (`[A-Z_]+`.*?) \|", spec, re.M) for name in re.findall(r"`([A-Z_]+)`", row)
    }
    text = (ROOT / "example.env").read_text(encoding="utf-8")
    named = set(re.findall(r"^# ([A-Z_]+)=", text, re.M))
    assert named == listed
    assert not re.search(r"^[A-Z_]+=", text, re.M)  # nothing is set until the installer uncomments it
    for line in re.findall(r"^# (?:[A-Z_]*(?:TOKEN|KEY|WORD))=(.*)$", text, re.M):
        assert line == ""  # no key, token or door word is ever filled in
