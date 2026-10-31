# -*- coding: utf-8 -*-
"""The API-side audit log must be checkable, and must be able to say "no".

A release writes to the remote twice without touching ``git push``: it merges the
pull request and it creates the GitHub release. The pre-push guard cannot see
either, so ``§5.9`` asks the person doing them to append a ``kind=api`` line. That
rule is worth nothing unless something reads the lines back and refuses the ones
that cannot be reconciled -- an open-ended ``action``, a missing authorization, a
line that cannot be placed in time.

``scripts/check_api_audit.py`` is that reader. These tests drive it through its own
self-test (which carries a red case for each rule) and through a real-shaped log,
because a checker that has only ever seen good input is indistinguishable from one
that does nothing.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_api_audit.py"

GOOD = (
    "2026-10-31T12:49:00Z auth=demo-grant granted_by=user remote=https://example op=update "
    "ref=refs/heads/preview to=abc was=def head=abc\n"
    "2026-10-31T12:49:00Z kind=api action=pr_merge id=#52 actor=ORCH auth=demo-grant "
    "url=https://example/pull/52\n"
)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=120,
    )


def test_the_builtin_cases_can_fail():
    """The checker's own red cases must run, or the checker is unproven."""
    completed = _run("--self-test")
    assert completed.returncode == 0, completed.stdout[-1500:]
    assert "SELFTEST: PASS" in completed.stdout


def test_a_reconcilable_log_is_green(tmp_path):
    path = tmp_path / "push-audit.log"
    path.write_text(GOOD, encoding="utf-8")

    completed = _run("--log", str(path))
    assert completed.returncode == 0, completed.stdout[-1500:]
    assert "RESULT: GREEN" in completed.stdout


def test_an_api_line_without_an_authorization_is_red(tmp_path):
    """A write nobody can attribute is the gap this gate exists for."""
    path = tmp_path / "push-audit.log"
    path.write_text(
        "2026-10-31T12:49:00Z kind=api action=pr_merge id=#52 actor=ORCH\n",
        encoding="utf-8",
    )

    completed = _run("--log", str(path))
    assert completed.returncode != 0, completed.stdout
    assert "RESULT: RED" in completed.stdout
    assert "missing auth" in completed.stdout


def test_a_missing_log_is_not_run_rather_than_green(tmp_path):
    """Absence of evidence is not evidence of a clean release."""
    completed = _run("--log", str(tmp_path / "absent.log"))
    assert completed.returncode != 0, completed.stdout
    assert "NOT RUN" in completed.stdout
