# -*- coding: utf-8 -*-
"""Mechanical guard: the agent working directory must never enter the tree.

``.workbuddy/`` holds machine-specific, agent-local working files (including
absolute paths and references that do not belong in a published repository).
It is kept out of version control only by a ``.gitignore`` rule - a promise
with no enforcement behind it. This guard turns that promise into a check that
fails loudly on the two ways the promise can be broken:

* a ``.workbuddy/`` path that is already tracked (``git add -f`` defeats the
  ignore rule silently);
* a ``.workbuddy/`` path that is no longer ignored (a plain ``git add .``
  would then sweep it in).

Both are red. The predicate is a plain string test on repo-relative paths, so
it is exercised directly, in both directions, below.
"""
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

GUARDED_DIRECTORY = ".workbuddy"


def guarded_paths(paths):
    """Return the repo-relative paths that fall under the guarded directory."""
    prefix = f"{GUARDED_DIRECTORY}/"
    return sorted(
        path for path in paths if path == GUARDED_DIRECTORY or path.startswith(prefix)
    )


def _git_paths(root: Path, *args: str):
    try:
        completed = subprocess.run(
            ["git", *args, "-z"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:  # noqa: BLE001
        pytest.fail(
            f"cannot enumerate repository paths (git is required by this guard): {error}"
        )
    return [path for path in completed.stdout.split("\0") if path]


def test_guarded_predicate_fires_on_working_directory_paths():
    """The predicate is red for guarded paths and green for look-alikes."""
    # Red: the exact shapes a leak would produce.
    assert guarded_paths([".workbuddy/memory/2026-01-01.md"]) == [
        ".workbuddy/memory/2026-01-01.md"
    ]
    assert guarded_paths([".workbuddy"]) == [".workbuddy"]
    assert guarded_paths([".workbuddy/nested/deep/file.txt"]) == [
        ".workbuddy/nested/deep/file.txt"
    ]
    # Green: unrelated paths must not fire, including near-miss names.
    assert guarded_paths(["cullinan/web/middleware/body_decoder.py"]) == []
    assert guarded_paths([".workbuddy-backup/notes.md"]) == []
    assert guarded_paths(["docs/testing.md"]) == []


def test_agent_working_directory_is_never_tracked_or_unignored():
    """No ``.workbuddy/`` path may be tracked or fall out of the ignore rule."""
    tracked = guarded_paths(_git_paths(REPO_ROOT, "ls-files"))
    unignored = guarded_paths(
        _git_paths(REPO_ROOT, "ls-files", "--others", "--exclude-standard")
    )
    offenders = sorted(set(tracked) | set(unignored))
    assert not offenders, (
        "the agent working directory must stay out of version control; these "
        "paths would be committed: " + ", ".join(offenders)
    )
