#!/usr/bin/env python3
"""Turn a PR's CI check red while a spec update its body declares is still due.

Canonical copy: repository scrutable-runtime, scripts/check_spec_declaration.py,
version 4. A copy of this file or of tests/test_spec_declaration_gate.py in
another repository stays byte-identical. Change the canonical copy first, then
propagate it; configure each repository through ``--spec-path`` in its workflow,
never by editing a copy.

Reads the ``pull_request`` event at ``GITHUB_EVENT_PATH`` and the git objects of
the checkout in the working directory. Standard library only. Exit 1 is a red
check, which notifies the operator; it does not gate merging. Only an explicit
``Spec impact: required`` can fail: while a declared file is unchanged, or when
the declaration cannot be read. Every other body warns or passes. The
declaration form is documented in the repository's own instructions, such as
its AGENTS.md, CLAUDE.md or README.

The PR body is untrusted. No text from it reaches a shell, and it reaches the job
log only through ``repr`` on lines that cannot start a workflow command.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DEFAULT_SPEC_PATHS = ("docs/spec/**/*.md",)
STILL_DUE = "Do not merge; the declared spec update is still due."

# Every path segment starts with a letter, digit, '_' or '-', so '.', '..' and
# hidden names never match. A declared path must pass this before any pattern.
_SEGMENT = r"[A-Za-z0-9_-][A-Za-z0-9_.-]*"
_SAFE_PATH = re.compile(rf"(?:{_SEGMENT}/)*{_SEGMENT}")
_PATTERN_SEGMENT = re.compile(r"\*\*|[A-Za-z0-9_*-][A-Za-z0-9_.*-]*")
_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_STRICT_FIELD = re.compile(
    r"[ \t]*(?:[-*][ \t]+)?spec (impact|files)[ \t]*:[ \t]*(.*)",
    re.IGNORECASE | re.ASCII,
)
# Anything a reader would take for a declaration line, after Unicode
# canonicalisation. Such a line that is not in the strict form still counts, so
# a mistyped 'required' is caught rather than read as no declaration. The
# Markdown wrappers recognised are emphasis ('*', '_') and inline code ('`').
_MARKDOWN_WRAPPERS = "*_`"
_LOOSE_FIELD = re.compile(r"[\s>*_`#-]*spec[\s*_`]+(impact|files)[\s*_`]*:(.*)")
_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_REGULAR_FILE_MODES = ("100644", "100755")
_EVIDENCE_LIMIT = 120

Level = Literal["pass", "warning", "error"]


@dataclass(frozen=True)
class Outcome:
    """What the check concluded; ``message`` never carries text from the PR body."""

    level: Level
    message: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class PullRequest:
    """The three event fields the check reads."""

    body: str
    base_sha: str
    head_sha: str


@dataclass(frozen=True)
class _Field:
    label: Literal["impact", "files"]
    value: str
    canonical: str
    line: str
    number: int
    plain: bool


@dataclass(frozen=True)
class SpecPaths:
    """Where a declared spec may live, as configured and as one matcher."""

    globs: tuple[str, ...]
    matcher: re.Pattern[str]


class CheckError(Exception):
    """The event, the checkout or the configuration cannot support a verdict."""


def compile_spec_paths(patterns: list[str]) -> SpecPaths:
    """Turn ``--spec-path`` globs into one matcher; ``*`` stays in one segment."""
    alternatives = []
    for pattern in patterns:
        segments = pattern.split("/")
        valid = all(_PATTERN_SEGMENT.fullmatch(s) for s in segments)
        if not valid or segments[-1] == "**" or not pattern.endswith(".md"):
            raise CheckError(f"--spec-path {pattern!r} is not a relative *.md glob")
        parts = []
        for index, segment in enumerate(segments):
            if segment == "**":
                parts.append("(?:[^/]+/)*")
                continue
            parts.append(re.escape(segment).replace(r"\*", "[^/]*"))
            if index < len(segments) - 1:
                parts.append("/")
        alternatives.append("".join(parts))
    matcher = re.compile("|".join(f"(?:{a})" for a in alternatives))
    return SpecPaths(tuple(patterns), matcher)


def _sha(pull_request: dict[str, object], side: str) -> str:
    ref = pull_request.get(side)
    sha: object = None
    if isinstance(ref, dict):
        sha = ref.get("sha")
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise CheckError(f"event field pull_request.{side}.sha is not a commit id")
    return sha


def parse_event(raw: str) -> PullRequest:
    """Validate a ``pull_request`` event; other GitHub fields are ignored."""
    try:
        event = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CheckError(f"event file is not JSON: {error}") from error
    no_pull_request = "event has no pull_request object; run on pull_request only"
    if not isinstance(event, dict):
        raise CheckError(no_pull_request)
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        raise CheckError(no_pull_request)
    body = pull_request.get("body")
    if body is None:
        body = ""
    if not isinstance(body, str):
        raise CheckError("event field pull_request.body is not text")
    return PullRequest(body, _sha(pull_request, "base"), _sha(pull_request, "head"))


def _canonical(line: str) -> str:
    text = unicodedata.normalize("NFKC", line)
    return "".join(c for c in text if unicodedata.category(c) != "Cf").casefold()


def _fields(body: str) -> list[_Field]:
    fields = []
    for number, line in enumerate(_LINE_BREAK.split(body), start=1):
        loose = _LOOSE_FIELD.match(_canonical(line))
        if loose is None:
            continue
        label: Literal["impact", "files"] = "impact"
        if loose.group(1) == "files":
            label = "files"
        # Intent is read from the canonical value, so formatting or an invisible
        # character inside 'required' is still seen as required, and unreadable.
        canonical = loose.group(2).strip(" \t" + _MARKDOWN_WRAPPERS)
        strict = _STRICT_FIELD.fullmatch(line)
        value = canonical
        if strict is not None:
            value = strict.group(2).strip()
        plain = strict is not None and value.casefold() == canonical
        fields.append(_Field(label, value, canonical, line, number, plain))
    return fields


def _advisory(impacts: list[_Field], files: list[_Field]) -> Outcome:
    if not impacts:
        return Outcome(
            "warning",
            "No spec declaration. Add 'Spec impact: none', or 'Spec impact: required' "
            "with a 'Spec files:' line, to the PR body.",
        )
    unclear = [f for f in impacts + files if not f.plain]
    if len(impacts) > 1 or unclear or impacts[0].value.lower() != "none":
        return Outcome(
            "warning",
            "The spec declaration is unclear. Use one plain 'Spec impact: none' "
            "or 'Spec impact: required' line.",
            tuple(f.line for f in impacts + files),
        )
    if any(f.value for f in files):
        return Outcome(
            "warning", "'Spec impact: none' also lists 'Spec files'; check which holds."
        )
    return Outcome("pass", "No spec change declared. The reviewer confirms the scope.")


def _unreadable(problem: str, evidence: tuple[str, ...] = ()) -> Outcome:
    return Outcome(
        "error",
        f"'Spec impact: required' is declared, but {problem} "
        "Fix the declaration so this check can confirm the spec update.",
        evidence,
    )


def _required(
    impacts: list[_Field], files: list[_Field], allowed: SpecPaths
) -> list[str] | Outcome:
    unclear = [f for f in impacts + files if not f.plain]
    if unclear:
        return _unreadable(
            f"PR body line {unclear[0].number} is not in the plain "
            "'Spec impact: ...' or 'Spec files: ...' form, with no formatting, "
            "unusual spaces or invisible characters.",
            (unclear[0].line,),
        )
    if len(impacts) > 1:
        return _unreadable("the PR body has more than one 'Spec impact' line.")
    if len(files) != 1:
        return _unreadable(f"the PR body has {len(files)} 'Spec files' lines, not 1.")
    entries = [entry.strip() for entry in files[0].value.split(",")]
    bad = tuple(
        e
        for e in entries
        if not (_SAFE_PATH.fullmatch(e) and allowed.matcher.fullmatch(e))
    )
    if bad:
        return _unreadable(
            f"{len(bad)} 'Spec files' entry or entries match none of "
            f"{', '.join(allowed.globs)}. List paths separated by commas, with no "
            "empty entries.",
            bad,
        )
    if len(set(entries)) != len(entries):
        return _unreadable("'Spec files' lists the same path more than once.")
    return entries


def read_declaration(body: str, allowed: SpecPaths) -> list[str] | Outcome:
    """Return the paths a required declaration names, or the early outcome."""
    fields = _fields(body)
    impacts = [f for f in fields if f.label == "impact"]
    files = [f for f in fields if f.label == "files"]
    if not any(f.canonical == "required" for f in impacts):
        return _advisory(impacts, files)
    return _required(impacts, files, allowed)


@dataclass(frozen=True)
class _Entry:
    mode: str
    kind: str
    oid: str


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "--literal-pathspecs", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        command = " ".join(args[:2])
        raise CheckError(f"git {command} failed: {result.stderr.strip()}")
    return result.stdout


def _tree(repo: Path, commit: str, *paths: str) -> dict[str, _Entry]:
    args = ["ls-tree", "-z", "--full-tree"]
    if not paths:
        args.append("-r")
    listing = _git(repo, *args, commit, "--", *paths)
    entries: dict[str, _Entry] = {}
    for record in filter(None, listing.split("\0")):
        meta, name = record.split("\t", 1)
        mode, kind, oid = meta.split(" ")
        entries[name] = _Entry(mode, kind, oid)
    return entries


def _resolve(repo: Path, pr: PullRequest) -> str:
    for sha in (pr.base_sha, pr.head_sha):
        probe = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True,
            check=False,
        )
        if probe.returncode != 0:
            raise CheckError(f"commit {sha} is not in the checkout; fetch full history")
    return _git(repo, "merge-base", pr.base_sha, pr.head_sha).strip()


def _problem(
    path: str,
    head: dict[str, _Entry],
    base: dict[str, _Entry],
    base_all: dict[str, _Entry],
) -> str | None:
    entry = head.get(path)
    if entry is None:
        return f"{path} does not exist at the PR head"
    if entry.kind != "blob" or entry.mode not in _REGULAR_FILE_MODES:
        return f"{path} is not a regular file at the PR head"
    before = base.get(path)
    if before is not None and before.oid == entry.oid:
        return f"{path} is unchanged by the PR"
    if before is None and any(e.oid == entry.oid for e in base_all.values()):
        return f"{path} only renames or copies an existing file without editing it"
    return None


def check_paths(repo: Path, pr: PullRequest, paths: list[str]) -> Outcome:
    """Require each path to be a regular file at head whose content the PR changed.

    Content is compared with the merge base, which is what the PR's diff shows. A
    file new at its path must not match any blob already at the merge base.
    """
    merge_base = _resolve(repo, pr)
    head = _tree(repo, pr.head_sha, *paths)
    base = _tree(repo, merge_base, *paths)
    base_all = _tree(repo, merge_base)
    problems = [p for p in (_problem(x, head, base, base_all) for x in paths) if p]
    if problems:
        return Outcome("error", f"{STILL_DUE} " + "; ".join(problems) + ".")
    return Outcome(
        "pass",
        "Declared spec files changed: "
        + ", ".join(paths)
        + ". The reviewer still checks that the text is correct.",
    )


def evaluate(repo: Path, pr: PullRequest, allowed: SpecPaths) -> Outcome:
    """Run the whole check for one pull request."""
    declared = read_declaration(pr.body, allowed)
    if isinstance(declared, Outcome):
        return declared
    return check_paths(repo, pr, declared)


def _command_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def report(outcome: Outcome, summary_path: Path | None) -> int:
    """Write the outcome to the job log and summary; return the exit code."""
    if outcome.level == "pass":
        print(outcome.message)
    else:
        title = "Spec declaration"
        print(f"::{outcome.level} title={title}::{_command_data(outcome.message)}")
    for item in outcome.evidence:
        print(f"evidence: {item[:_EVIDENCE_LIMIT]!r}")
    if summary_path is not None:
        icon = {"pass": "✅", "warning": "⚠️", "error": "❌"}[outcome.level]
        with summary_path.open("a", encoding="utf-8") as summary:
            summary.write(f"### Spec declaration\n\n{icon} {outcome.message}\n")
    return 1 if outcome.level == "error" else 0


def _arguments(argv: list[str]) -> list[str]:
    parser = argparse.ArgumentParser(description="Check a PR's spec declaration.")
    parser.add_argument(
        "--spec-path",
        action="append",
        metavar="GLOB",
        help="where a declared spec may live, e.g. 'docs/spec/**/*.md'; repeatable "
        f"(default: {', '.join(DEFAULT_SPEC_PATHS)})",
    )
    patterns: list[str] | None = parser.parse_args(argv).spec_path
    return patterns or list(DEFAULT_SPEC_PATHS)


def main(argv: list[str], environ: dict[str, str], repo: Path) -> int:
    """Entry point; ``environ`` supplies the GitHub Actions file paths."""
    summary = environ.get("GITHUB_STEP_SUMMARY")
    summary_path: Path | None = None
    if summary:
        summary_path = Path(summary)
    try:
        allowed = compile_spec_paths(_arguments(argv))
        event_path = environ.get("GITHUB_EVENT_PATH")
        if not event_path:
            raise CheckError("GITHUB_EVENT_PATH is not set")
        try:
            raw = Path(event_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise CheckError(f"cannot read the event file: {error}") from error
        outcome = evaluate(repo, parse_event(raw), allowed)
    except CheckError as error:
        outcome = Outcome("error", f"Spec declaration check could not run: {error}")
    return report(outcome, summary_path)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], dict(os.environ), Path.cwd()))
