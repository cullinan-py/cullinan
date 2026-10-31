# -*- coding: utf-8 -*-
"""The release-matrix gate must be able to say both things.

``scripts/check_release_matrix.py`` decides whether a candidate commit may be
tagged. Two failure modes make such a gate worthless, and both have shipped here
before:

* **It always passes.** A gate that has only ever seen green input cannot be
  distinguished from a gate that does nothing. ``test_the_builtin_cases_can_fail``
  runs its self-test, which contains red cases as well as green ones.
* **It refuses everything.** A rule read too literally refuses valid input and gets
  switched off. ``test_a_real_shaped_evidence_file_passes`` feeds the shape a real
  run produces -- several platforms, several python versions, counts that add up --
  and requires GREEN.

The evidence files this gate reads live outside the repository (they quote CI run
ids and per-platform counts), so these tests build their own.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_release_matrix.py"
COMMIT = "a" * 40


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=120,
    )


def _evidence(**overrides) -> dict:
    payload = {
        "producer": "gh_api",
        "candidate_commit": COMMIT,
        "measured_at": "2026-10-31T11:58:00Z",
        "baseline_source": "prev_tag",
        "baseline_value": 1501,
        "platforms": [
            {"name": "ubuntu-latest", "python": "3.9", "collected": 1501,
             "passed": 1497, "skipped": 4, "failed": 0, "errors": 0},
            {"name": "ubuntu-latest", "python": "3.13", "collected": 1501,
             "passed": 1499, "skipped": 2, "failed": 0, "errors": 0},
            {"name": "windows-latest", "python": "3.13", "collected": 1501,
             "passed": 1496, "skipped": 5, "failed": 0, "errors": 0},
        ],
    }
    payload.update(overrides)
    return payload


def test_the_builtin_cases_can_fail():
    """The gate's own red cases must run and pass, or the gate is unproven."""
    completed = _run("--self-test")
    assert completed.returncode == 0, completed.stdout[-1500:]
    assert "SELFTEST: PASS" in completed.stdout


def test_a_real_shaped_evidence_file_passes(tmp_path):
    """A real run's shape -- several platforms, several interpreters -- is GREEN."""
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(_evidence()), encoding="utf-8")

    completed = _run("--evidence", str(path), "--commit", COMMIT)
    assert completed.returncode == 0, completed.stdout[-1500:]
    assert "GREEN" in completed.stdout


def test_hand_typed_evidence_is_refused(tmp_path):
    """The defect this gate exists for: a file someone typed is not a run.

    ``producer`` is the only field that separates the two, so its absence and its
    being an unknown value both have to refuse.
    """
    for producer in ("manual", None):
        payload = _evidence()
        if producer is None:
            payload.pop("producer")
        else:
            payload["producer"] = producer
        path = tmp_path / f"evidence-{producer}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        completed = _run("--evidence", str(path), "--commit", COMMIT)
        assert completed.returncode != 0, completed.stdout
        assert "RED" in completed.stdout


def test_evidence_for_another_commit_is_refused(tmp_path):
    """Green on a different commit is the "it passed last night" failure."""
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(_evidence(candidate_commit="b" * 40)), encoding="utf-8")

    completed = _run("--evidence", str(path), "--commit", COMMIT)
    assert completed.returncode != 0, completed.stdout
    assert "RED" in completed.stdout


def test_unreadable_evidence_is_not_run_rather_than_green(tmp_path):
    """Missing evidence must not collapse into a pass -- that is the whole point."""
    completed = _run("--evidence", str(tmp_path / "absent.json"), "--commit", COMMIT)
    assert completed.returncode != 0, completed.stdout
    assert "NOT RUN" in completed.stdout
    assert "GREEN" not in completed.stdout
