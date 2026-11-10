"""Tests for the PR spec declaration check (scripts/check_spec_declaration.py).

Canonical copy: repository scrutable-runtime, tests/test_spec_declaration_gate.py,
version 4. A copy in another repository stays byte-identical. Standard
library only: run with ``python3 tests/test_spec_declaration_gate.py`` or pytest.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Protocol

_ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    path = _ROOT / "scripts" / "check_spec_declaration.py"
    spec = importlib.util.spec_from_file_location("check_spec_declaration", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module spec from {path}")
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve their annotations through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load()


class _Outcome(Protocol):
    """The fields of the script's Outcome these tests read; the import is dynamic."""

    @property
    def level(self) -> str: ...

    @property
    def message(self) -> str: ...


_DEFAULT = gate.compile_spec_paths(list(gate.DEFAULT_SPEC_PATHS))
_SHA = "a" * 40
_REQUIRED_A = "Spec impact: required\nSpec files: docs/spec/a.md\n"

# Isolated from the developer's git config, hooks and signing.
_GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _level(body: str, allowed: object = _DEFAULT) -> str:
    result = gate.read_declaration(body, allowed)
    if isinstance(result, gate.Outcome):
        return str(result.level)
    return "paths"


class DeclarationForms(unittest.TestCase):
    def test_missing_or_unclear_declarations_only_warn(self) -> None:
        for body in (
            "Fixes a typo.",
            "Spec impact: maybe",
            "Spec impact: none\nSpec impact: none",
            "Spec impact: none\nSpec files: docs/spec/a.md",
            "Spec files: docs/spec/a.md",
            "**Spec impact:** none",
            "Spec\u00a0impact: none",
            "Spec impact: **none**",
            "Spec impact: no\u200bne",
            "Spec impact: `none`",
            "`Spec impact`: none",
            "`Spec impact: none`",
        ):
            with self.subTest(body=body):
                self.assertEqual(_level(body), "warning")

    def test_none_passes_with_or_without_a_blank_files_line(self) -> None:
        for body in (
            "Spec impact: none",
            "- spec IMPACT:   None  ",
            "Spec impact: none\r\nSpec files:",
        ):
            with self.subTest(body=body):
                self.assertEqual(_level(body), "pass")

    def test_unreadable_required_declarations_fail(self) -> None:
        for body in (
            "Spec impact: required",
            "Spec impact: required\nSpec impact: none\nSpec files: docs/spec/a.md",
            "Spec impact: required\nSpec files: docs/spec/a.md\nSpec files: x",
            "Spec impact: required\nSpec files: docs/spec/a.md, docs/spec/a.md",
            "Spec impact: required\n**Spec files:** docs/spec/a.md",
            "**Spec impact:** required\nSpec files: docs/spec/a.md",
            "Spec impact\u200b: Required\nSpec files: docs/spec/a.md",
            "Spec impact: **required**\nSpec files: docs/spec/a.md",
            "Spec impact: requ\u200bired\nSpec files: docs/spec/a.md",
            "Spec impact: `required`\nSpec files: docs/spec/a.md",
            "`Spec impact`: required\nSpec files: docs/spec/a.md",
            "`Spec impact: required`\nSpec files: docs/spec/a.md",
            "**`Spec impact`**: `required`\nSpec files: docs/spec/a.md",
            "Spec impact: **`required`**\nSpec files: docs/spec/a.md",
            "Spec impact: _`required`_\nSpec files: docs/spec/a.md",
            "Spec impact: required\n`Spec files: docs/spec/a.md`",
            "Spec impact: required\nSpec files: `docs/spec/a.md`",
        ):
            with self.subTest(body=body):
                self.assertEqual(_level(body), "error")

    def test_paths_outside_the_allowed_globs_fail(self) -> None:
        for value in (
            "docs/spec/../../etc/passwd.md",
            "docs/spec/./a.md",
            "/docs/spec/a.md",
            "docs/other.md",
            "docs/spec/a.txt",
            "docs/spec/.hidden.md",
            "docs\\spec\\a.md",
            "`docs/spec/a.md`",
            "docs/spec/a.md,",
            "docs/spec/a\u200b.md",
            "docs/spec/$(touch x).md",
        ):
            with self.subTest(value=value):
                body = f"Spec impact: required\nSpec files: {value}"
                self.assertEqual(_level(body), "error")

    def test_default_allows_nested_docs_spec_markdown(self) -> None:
        body = "Spec impact: required\nSpec files: docs/spec/sub/x-1.md, docs/spec/b.md"
        paths = gate.read_declaration(body, _DEFAULT)
        self.assertEqual(paths, ["docs/spec/sub/x-1.md", "docs/spec/b.md"])

    def test_configured_globs_replace_the_default(self) -> None:
        allowed = gate.compile_spec_paths(
            ["extensions/*/README.md", "docs/axiom-runtime/spec/**/*.md"]
        )
        for value, level in (
            ("extensions/timer/README.md", "paths"),
            ("docs/axiom-runtime/spec/a.md", "paths"),
            ("extensions/timer/sub/README.md", "error"),
            ("extensions/README.md", "error"),
            ("docs/spec/a.md", "error"),
        ):
            with self.subTest(value=value):
                body = f"Spec impact: required\nSpec files: {value}"
                self.assertEqual(_level(body, allowed), level)

    def test_malformed_globs_are_refused(self) -> None:
        for glob in ("/docs/spec/*.md", "docs/../x.md", "docs/spec/**", "docs/*.txt"):
            with self.subTest(glob=glob), self.assertRaises(gate.CheckError):
                gate.compile_spec_paths([glob])


class Events(unittest.TestCase):
    def test_malformed_events_are_refused(self) -> None:
        both = {"base": {"sha": _SHA}, "head": {"sha": _SHA}}
        for raw in (
            "not json",
            json.dumps([]),
            json.dumps({"action": "opened"}),
            json.dumps({"pull_request": {**both, "body": 3}}),
            json.dumps({"pull_request": {**both, "head": {"sha": "HEAD"}}}),
            json.dumps({"pull_request": {**both, "head": _SHA}}),
        ):
            with self.subTest(raw=raw), self.assertRaises(gate.CheckError):
                gate.parse_event(raw)

    def test_edited_event_judges_the_current_body(self) -> None:
        event = {
            "action": "edited",
            "changes": {"body": {"from": "Spec impact: required"}},
            "pull_request": {
                "body": "Spec impact: none",
                "base": {"sha": _SHA},
                "head": {"sha": "b" * 40},
            },
        }
        pr = gate.parse_event(json.dumps(event))
        self.assertEqual(_level(pr.body), "pass")


class _RepoCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.write("docs/spec/a.md", "# A\n")
        self.write("docs/spec/b.md", "# B\n")
        self.write("docs/old.md", "# Old\n")
        self.commit("base")
        self.git("checkout", "-q", "-b", "pr")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            capture_output=True,
            text=True,
            check=True,
            env=_GIT_ENV,
        ).stdout.strip()

    def write(self, name: str, text: str) -> None:
        (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / name).write_text(text)

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)

    def evaluate(self, body: str = _REQUIRED_A) -> _Outcome:
        pr = gate.PullRequest(
            body, self.git("rev-parse", "main"), self.git("rev-parse", "pr")
        )
        outcome: _Outcome = gate.evaluate(self.repo, pr, _DEFAULT)
        return outcome

    def assert_due(self, outcome: _Outcome, reason: str) -> None:
        self.assertEqual(outcome.level, "error")
        self.assertTrue(outcome.message.startswith(gate.STILL_DUE), outcome.message)
        self.assertIn(reason, outcome.message)


class DiffChecks(_RepoCase):
    def test_edited_spec_passes_and_reports_the_path(self) -> None:
        self.write("docs/spec/a.md", "# A\nNew rule.\n")
        self.commit("edit")
        outcome = self.evaluate()
        self.assertEqual(outcome.level, "pass")
        self.assertIn("docs/spec/a.md", outcome.message)

    def test_declared_spec_the_pr_did_not_touch_is_due(self) -> None:
        self.write("src.py", "x = 1\n")
        self.commit("code only")
        self.assert_due(self.evaluate(), "docs/spec/a.md is unchanged")

    def test_base_branch_edit_after_branching_does_not_count(self) -> None:
        # The PR leaves a.md alone; main edits it later. Comparing with the base
        # tip instead of the merge base would see a difference and wrongly pass.
        self.commit("pr work")
        self.git("checkout", "-q", "main")
        self.write("docs/spec/a.md", "# A\nMain moved on.\n")
        self.commit("main edit")
        self.assert_due(self.evaluate(), "unchanged")

    def test_deleted_spec_is_due(self) -> None:
        (self.repo / "docs/spec/a.md").unlink()
        self.commit("delete")
        self.assert_due(self.evaluate(), "does not exist")

    def test_pure_rename_into_declared_path_is_due(self) -> None:
        self.git("mv", "docs/old.md", "docs/spec/new.md")
        self.commit("rename")
        body = "Spec impact: required\nSpec files: docs/spec/new.md\n"
        self.assert_due(self.evaluate(body), "renames or copies")

    def test_new_spec_with_new_content_passes(self) -> None:
        self.git("mv", "docs/old.md", "docs/spec/new.md")
        self.write("docs/spec/new.md", "# Old\nNow a spec.\n")
        self.commit("rename and edit")
        body = "Spec impact: required\nSpec files: docs/spec/new.md\n"
        self.assertEqual(self.evaluate(body).level, "pass")

    def test_symlink_at_declared_path_is_due(self) -> None:
        (self.repo / "docs/spec/a.md").unlink()
        (self.repo / "docs/spec/a.md").symlink_to("b.md")
        self.commit("symlink")
        self.assert_due(self.evaluate(), "not a regular file")

    def test_one_good_path_does_not_hide_a_missed_one(self) -> None:
        self.write("docs/spec/a.md", "# A\nNew rule.\n")
        self.commit("edit a only")
        body = "Spec impact: required\nSpec files: docs/spec/a.md, docs/spec/b.md\n"
        self.assert_due(self.evaluate(body), "docs/spec/b.md is unchanged")

    def test_head_missing_from_shallow_checkout_cannot_run(self) -> None:
        pr = gate.PullRequest(_REQUIRED_A, self.git("rev-parse", "main"), "f" * 40)
        with self.assertRaisesRegex(gate.CheckError, "not in the checkout"):
            gate.evaluate(self.repo, pr, _DEFAULT)


class EntryPoint(_RepoCase):
    def run_main(self, body: object, *argv: str) -> tuple[int, str, str]:
        event = self.tmp / "event.json"
        summary = self.tmp / "summary.md"
        summary.write_text("")
        payload = {
            "pull_request": {
                "body": body,
                "base": {"sha": self.git("rev-parse", "main")},
                "head": {"sha": self.git("rev-parse", "pr")},
            }
        }
        event.write_text(json.dumps(payload))
        environ = {"GITHUB_EVENT_PATH": str(event), "GITHUB_STEP_SUMMARY": str(summary)}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gate.main(list(argv), environ, self.repo)
        return code, out.getvalue(), summary.read_text()

    def test_body_text_cannot_inject_workflow_commands(self) -> None:
        # splitlines also breaks at NEL and LINE SEPARATOR, so an unescaped echo
        # of this value would show up below as a forged command line.
        body = (
            "Spec impact: required\n"
            "Spec files: docs/spec/a.md, x\x85::error::forged\u2028::add-mask::y%0A\n"
        )
        code, out, summary = self.run_main(body)
        commands = [line for line in out.splitlines() if line.startswith("::")]
        self.assertEqual(code, 1)
        self.assertEqual(len(commands), 1)
        self.assertTrue(commands[0].startswith("::error title=Spec declaration::"))
        self.assertNotIn("forged", commands[0] + summary)

    def test_due_spec_turns_the_check_red_with_the_notice(self) -> None:
        code, out, summary = self.run_main(_REQUIRED_A)
        self.assertEqual(code, 1)
        self.assertIn(gate.STILL_DUE, out)
        self.assertIn(gate.STILL_DUE, summary)

    def test_null_body_warns_without_failing(self) -> None:
        code, out, summary = self.run_main(None)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("::warning "))
        self.assertIn("No spec declaration", summary)

    def test_spec_path_argument_reaches_the_check(self) -> None:
        self.write("extensions/timer/README.md", "# Timer\n")
        self.commit("add extension doc")
        body = "Spec impact: required\nSpec files: extensions/timer/README.md\n"
        self.assertEqual(self.run_main(body)[0], 1)
        argv = ("--spec-path", "extensions/*/README.md")
        self.assertEqual(self.run_main(body, *argv)[0], 0)

    def test_missing_event_cannot_run(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(gate.main([], {}, self.repo), 1)
        self.assertIn("GITHUB_EVENT_PATH", out.getvalue())


class Workflow(unittest.TestCase):
    def test_workflow_reruns_on_body_edits_without_privilege(self) -> None:
        text = (_ROOT / ".github/workflows/spec-declaration.yml").read_text()
        run_lines = re.findall(r"(?m)^\s*run:.*$", text)
        self.assertNotIn("pull_request_target", text)
        self.assertRegex(text, r"(?m)^\s*types:\s*\[[^\]]*\bedited\b")
        self.assertRegex(text, r"(?m)^permissions:\s*\n\s+contents:\s*read\s*$")
        self.assertIn("persist-credentials: false", text)
        self.assertEqual(len(run_lines), 1)
        self.assertIn("scripts/check_spec_declaration.py", run_lines[0])
        self.assertNotIn("${{", run_lines[0])


if __name__ == "__main__":
    unittest.main()
