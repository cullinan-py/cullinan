#!/usr/bin/env python3
"""Check a release note for the two things a release note can get wrong.

A release note is written for someone who will never see the repository's
workflow. It can fail that reader in two ways, and both have shipped:

* **It can describe the machinery.** Which check runs, what a credential binds
  to, how an exemption is scoped. That text is unreadable outside the project,
  and the note is published where a user reads it.
* **It can drift from the template.** A note with no `Delivery Notes` section,
  or one section renamed, is not obviously wrong -- it just quietly stops
  answering the question that section exists for.

The vocabulary list is imported from ``check_changelog`` rather than repeated:
two lists of the same thing is how the two files end up disagreeing.

Usage::

    python scripts/check_release_note.py                      # newest RELEASE-v*.md at repo root
    python scripts/check_release_note.py path/to/RELEASE-vX.md
    python scripts/check_release_note.py --self-test

Exit codes: 0 clean, 1 findings, 2 configuration error (also a failure).
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_changelog import MAINTENANCE_TERMS, _version_key  # noqa: E402  (one list, not two)

#: The sections the project's template requires, in the order it gives them.
REQUIRED_SECTIONS = (
    "Overview",
    "Highlights",
    "Compatibility Notes",
    "Delivery Notes",
    "Upgrade Notes",
)

_SECTION = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_NOTE_VERSION = re.compile(r"RELEASE-v(.+)\.md$")


def check_text(text: str, name: str = "<note>") -> list[str]:
    """Return one line per problem. Empty list means the note is usable."""
    problems: list[str] = []

    found = [section.strip() for section in _SECTION.findall(text)]
    missing = [section for section in REQUIRED_SECTIONS if section not in found]
    if missing:
        problems.append(
            f"{name}: missing section(s) {', '.join(missing)}; a reader who skims for "
            f"delivery or upgrade answers finds nothing where they expect it"
        )
    extra = [
        section
        for section in found
        if section not in REQUIRED_SECTIONS and section.lower() != "authoring rules"
    ]
    if extra:
        problems.append(
            f"{name}: section(s) outside the template: {', '.join(extra)}; a new section "
            f"is a new question the reader has to learn to ask"
        )

    lowered = text.lower()
    hits = sorted({term for term in MAINTENANCE_TERMS if term.lower() in lowered})
    if hits:
        problems.append(
            f"{name}: describes maintenance machinery ({', '.join(hits)}); a release note "
            f"states what changed for a user of the package, not how the checks that guard "
            f"it are built"
        )

    if _CJK.search(text):
        problems.append(
            f"{name}: contains non-English text; the note is published in English only, and "
            f"a mixed-language note is a merged draft rather than a finished one"
        )

    return problems


def newest_note(root: Path) -> Path | None:
    """Return the note for the newest version, not the last name in sort order.

    Sorting the file names as strings puts ``RELEASE-v0.96a9.md`` after
    ``RELEASE-v0.96a10.md``, so from the tenth alpha onwards the check read the
    previous release and reported on it -- the file it was asked to guard was
    never opened, and the run still looked like a run. The version is parsed and
    ordered the way a reader orders versions, using the same key the changelog
    check uses so the two cannot disagree about which release is newest.
    """
    notes = [note for note in root.glob("RELEASE-v*.md") if not note.name.endswith(".amended.md")]

    def sort_key(note: Path) -> tuple:
        match = _NOTE_VERSION.search(note.name)
        return _version_key(match.group(1)) if match else (0, 0, 0, "", 0, 0)

    notes.sort(key=sort_key)
    return notes[-1] if notes else None


# Two samples, and the pair is the point: a note that fails every rule and a
# note that fails none. A checker that has only ever been observed passing is
# indistinguishable from a checker that cannot fail.
_SAMPLE_CLEAN = """# Cullinan 0.97 Release Notes

## Overview

Cullinan `0.97` adds one thing and changes nothing a caller already relied on.

## Highlights

### 1. A new helper

- `cullinan.helpers.trim` removes surrounding whitespace in one call.

## Compatibility Notes

- No public name is removed or renamed.

## Delivery Notes

- Published as a pre-release; `pip install --pre cullinan`.

## Upgrade Notes

- Nothing to change in application code.
"""

_SAMPLE_MAINTENANCE = """# Cullinan 0.97 Release Notes

## Overview

The pre-push gate now runs ten assertions, and the review credential carries
`#tree=<40 hex>` so a commit-bound check cannot reject a valid approval.

## Highlights

### 1. A new helper

- `cullinan.helpers.trim` removes surrounding whitespace in one call.

## Compatibility Notes

- No public name is removed or renamed.

## Delivery Notes

- Published as a pre-release.

## Upgrade Notes

- Nothing to change in application code.
"""

_SAMPLE_MISSING_SECTION = """# Cullinan 0.97 Release Notes

## Overview

A small release.

## Highlights

### 1. A new helper

- `cullinan.helpers.trim` removes surrounding whitespace in one call.

## Compatibility Notes

- No public name is removed or renamed.
"""


def _self_test() -> int:
    failures = 0

    def expect(name: str, text: str, should_pass: bool) -> None:
        nonlocal failures
        problems = check_text(text, name)
        if (not problems) != should_pass:
            failures += 1
            print(f"  FAIL {name}: expected {'clean' if should_pass else 'findings'}, got {problems or 'none'}")
        else:
            print(f"  ok   {name}")

    print("self-test: a note written for a user passes")
    expect("template sections, user-facing vocabulary", _SAMPLE_CLEAN, True)

    print("self-test: each defect is reported")
    expect("describes the machinery", _SAMPLE_MAINTENANCE, False)
    expect("a required section is missing", _SAMPLE_MISSING_SECTION, False)

    print("self-test: the note read is the one for the newest version")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        # The older note is the one that would fail every rule: if the picker
        # takes it, the run says FAIL about the wrong release, and the note that
        # shipped was never read.
        (root / "RELEASE-v0.96a9.md").write_text(_SAMPLE_MAINTENANCE, encoding="utf-8")
        (root / "RELEASE-v0.96a10.md").write_text(_SAMPLE_CLEAN, encoding="utf-8")
        picked = newest_note(root)
        if picked is None or picked.name != "RELEASE-v0.96a10.md":
            failures += 1
            print(f"  FAIL ordering: picked {picked.name if picked else 'nothing'}")
        else:
            print("  ok   ordering: RELEASE-v0.96a10.md over RELEASE-v0.96a9.md")

    print("SELFTEST:", "PASS" if not failures else f"FAIL {failures}")
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", nargs="?", help="release note to check")
    parser.add_argument("--root", default=".", help="repository root (used when no path is given)")
    parser.add_argument("--self-test", action="store_true", help="run the built-in cases and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    note = Path(args.path) if args.path else newest_note(Path(args.root))
    if note is None or not note.is_file():
        print(f"RELEASE NOTE CHECK: no release note found ({note or 'no RELEASE-v*.md at root'})")
        return 2

    problems = check_text(note.read_text(encoding="utf-8", errors="replace"), note.name)
    if problems:
        print("RELEASE NOTE CHECK FAIL")
        for line in problems:
            print("  -", line)
        return 1
    print(f"RELEASE NOTE CHECK PASS -- {note.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
