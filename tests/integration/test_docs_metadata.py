"""Every public page says when it last changed, and the date is not a fiction.

Two gates live here, with deliberately different strengths:

* the first reads only the tree, so it runs everywhere -- every page must carry a
  last-changed stamp in one of the two forms the project actually uses, and the
  date must be a real calendar date that is not in the future;
* the second compares that stamp against the commit that last changed the page's
  content, which is the only way to catch a stamp that stopped moving while the
  page kept changing. It needs history, so it skips -- loudly -- on a shallow
  clone rather than passing without having looked.

The last test feeds the first gate a page that is wrong on purpose, because a
check that cannot fail is not a check.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"
# Authoring templates describe a shape, not a page that ships; they carry
# placeholders on purpose and are excluded from the build for the same reason.
EXCLUDED_DIRS = {"templates"}

FRONTMATTER = re.compile(
    r"^last_updated:\s*\"?(\d{4}-\d{2}-\d{2})(?:[T ][0-9:.+Z-]+)?\"?\s*$", re.M
)
BLOCKQUOTE_EN = re.compile(r"^> \*\*Last Updated\*\*:\s*(\d{4}-\d{2}-\d{2})", re.M)
BLOCKQUOTE_ZH = re.compile(r"^> \*\*最后更新\*\*[:：]\s*(\d{4}-\d{2}-\d{2})", re.M)
FORMS = (FRONTMATTER, BLOCKQUOTE_EN, BLOCKQUOTE_ZH)


def shipped_pages() -> list[pathlib.Path]:
    return sorted(
        page
        for page in DOCS.rglob("*.md")
        if not EXCLUDED_DIRS & set(page.relative_to(DOCS).parts)
    )


def declared_date(text: str) -> str | None:
    for pattern in FORMS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def last_content_changes() -> dict[str, str]:
    """Map every path to the date of the last commit that MODIFIED it.

    One `git log` pass instead of one per page: the per-page form costs about
    half a second in a repository this size, which is too much for a docs gate.
    `--follow` takes exactly one path, so it cannot be used here; a page that was
    only moved therefore has no entry and is left to the first gate.
    """
    result = subprocess.run(
        ["git", "log", "--diff-filter=M", "--format=@%cs", "--name-only"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {}

    changes: dict[str, str] = {}
    current = None
    for line in result.stdout.splitlines():
        if line.startswith("@"):
            current = line[1:]
        elif line.strip() and current and line.strip() not in changes:
            changes[line.strip()] = current
    return changes


def test_every_shipped_page_declares_when_it_last_changed():
    missing, malformed, future = [], [], []
    tomorrow = dt.date.today() + dt.timedelta(days=1)

    for page in shipped_pages():
        rel = page.relative_to(REPO_ROOT).as_posix()
        stamp = declared_date(page.read_text(encoding="utf-8"))
        if stamp is None:
            missing.append(rel)
            continue
        try:
            when = dt.date.fromisoformat(stamp)
        except ValueError:
            malformed.append(f"{rel} ({stamp})")
            continue
        if when > tomorrow:
            future.append(f"{rel} ({stamp})")

    assert not missing, (
        "these pages never say when they last changed, so a reader cannot tell "
        f"current from stale: {missing}"
    )
    assert not malformed, f"these pages carry a date that is not a date: {malformed}"
    assert not future, f"these pages claim a last change in the future: {future}"


def test_the_declared_date_is_not_older_than_the_last_change():
    changes = last_content_changes()
    usable = [p for p in shipped_pages() if p.relative_to(REPO_ROOT).as_posix() in changes]
    if not usable:
        pytest.skip(
            "no git history available for any page (shallow clone) -- the drift "
            "check would pass without having compared anything, so it does not run"
        )

    stale = []
    for page in usable:
        rel = page.relative_to(REPO_ROOT).as_posix()
        stamp = declared_date(page.read_text(encoding="utf-8"))
        changed_on = changes[rel]
        if stamp and changed_on > stamp:
            stale.append(f"{rel}: says {stamp}, last changed {changed_on}")

    assert not stale, (
        "these pages changed after the date they advertise, so the date is not "
        "telling a reader anything: " + "; ".join(stale)
    )


def test_the_stamp_gate_can_actually_fail():
    """A page without a stamp must be reported, not waved through."""
    assert declared_date("# Title\n\nNo metadata here.\n") is None
    assert declared_date('last_updated: "2026-10-27"\n\n# Title\n') == "2026-10-27"
    assert declared_date("# T\n\n> **Last Updated**: 2026-10-27\n") == "2026-10-27"
    assert declared_date("# T\n\n> **最后更新**：2026-10-27\n") == "2026-10-27"
