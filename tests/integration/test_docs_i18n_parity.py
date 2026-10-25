# -*- coding: utf-8 -*-
"""Every page in the nav must exist in both languages.

`scripts/check_i18n_coverage.py` had been crashing on the ``!ENV`` tag in
``mkdocs.yml`` since that tag was introduced, so nobody ran it -- and nobody
noticed that ``packaging.md`` had no Chinese counterpart: the page was in the
nav, and the zh site simply had nothing to show for it.

A check that cannot run is a check that does not exist, so this makes the run
part of the ordinary test suite.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_i18n_coverage.py"


def _run() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_the_script_runs_at_all():
    """It used to die on ``!ENV``; a crash is not a pass."""
    result = _run()
    assert result.returncode == 0, f"i18n coverage check failed: {result.stdout} {result.stderr}"
    assert "Traceback" not in result.stderr


def test_every_nav_page_has_a_chinese_counterpart():
    result = _run()
    # The script always prints the header, even when the list underneath is
    # empty, so the assertion looks at what follows it rather than at the header.
    missing = [
        line[2:].strip()
        for line in result.stdout.splitlines()
        if line.startswith("- ") and line[2:].strip()
    ]
    assert not missing, (
        "a page in the nav has no Chinese version; either translate it or take it "
        f"out of the nav: {missing}"
    )
