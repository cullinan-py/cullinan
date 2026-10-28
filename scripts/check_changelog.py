#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check that the changelog actually covers the versions that were released.

A changelog is only useful if it is complete at the moment somebody reads it,
and the failure mode is silent: a release ships, nobody appends an entry, and
the file keeps looking healthy because it is still valid Markdown.  This check
turns that into a non-zero exit.

What it enforces:

* the newest entry is the version the package advertises (the single source of
  truth), so the file cannot drift behind a release;
* entries are **continuous** from the oldest recorded version to the newest --
  every version released in between has one.  The repository's history predates
  the changelog (``0.52`` .. ``0.94``), so a full-history requirement would
  mean inventing entries; continuity from the first recorded version is the
  honest form of the same guarantee, and it is the one that catches a forgotten
  release from here on;
* no version is recorded twice, and no entry is empty;
* the newest entry is organised by change type, using only the types listed
  below -- the point of the structure is that a reader can find "what broke"
  without reading everything.

Usage::

    python scripts/check_changelog.py
    python scripts/check_changelog.py --self-test
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

# Keep a Changelog's vocabulary, plus Documentation: this project ships prose
# as part of a release, so "the guide now says X" is a change a reader looks
# for rather than noise.
ALLOWED_SECTIONS = (
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
    "Documentation",
)

# Vocabulary that only means something to whoever maintains the release
# machinery: what a gate checks, what a credential binds to, how an exemption
# is scoped. It is unreadable outside the project, and this file ships with the
# package, so an entry that uses it is talking to the wrong reader.
#
# The list is short and literal on purpose. A pattern like "gate" would also
# match `gateway`, and a rule that fires on a legitimate word teaches people to
# ignore it; one unambiguous term per line is worth more than a clever regex.
# Checked on the newest entry and on `Unreleased` only -- history written before
# this rule existed is left as written.
MAINTENANCE_TERMS = (
    "credential",
    "sign-off",
    "signoff",
    "evidence bundle",
    "exempt",
    "#tree=",
    "#sha256=",
    "check_tag_gate",
    "gate_pre_push",
    "pre-push gate",
    "identifier scan",
    "internal reference",
    "allowlist",
    "pattern table",
    "sign-off credential",
)

_VERSION_HEADING = re.compile(r"^##\s+v?(\S+)\s*$", re.MULTILINE)
_SECTION_HEADING = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class Entry:
    version: str
    body: str
    sections: List[str] = field(default_factory=list)

    @property
    def bullets(self) -> int:
        return sum(1 for line in self.body.splitlines() if line.lstrip().startswith(("- ", "* ")))


def parse_changelog(text: str) -> List[Entry]:
    """Return the version entries in the order they appear (newest first)."""
    matches = list(_VERSION_HEADING.finditer(text))
    entries: List[Entry] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():end]
        sections = [heading.strip() for heading in _SECTION_HEADING.findall(body)]
        entries.append(Entry(version=match.group(1), body=body, sections=sections))
    return entries


def _version_key(version: str) -> Tuple:
    """Order versions the way a reader would, not the way strings sort.

    ``0.96a5`` has to come after ``0.96a4`` and before ``0.96``; a plain string
    comparison puts ``0.96a5`` before ``0.96a13`` and would mis-order the alpha
    line badly enough to break the continuity check.
    """
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:(a|b|rc)(\d+))?(?:\.?(?:post|rc)(\d+))?$", version)
    if match is None:
        # Unknown shape: keep it comparable without pretending to understand it.
        return (0, 0, 0, "", 0, 0)
    major, minor, patch, stage, stage_number, post = match.groups()
    stage_rank = {"a": 0, "b": 1, "rc": 2, None: 3}[stage]
    return (
        int(major),
        int(minor),
        int(patch or 0),
        stage_rank,
        int(stage_number or 0),
        int(post or 0),
    )


def released_tags(repo: Path) -> List[str]:
    """Return the version tags of the repository, normalised (no ``v`` prefix)."""
    try:
        completed = subprocess.run(
            ["git", "tag", "-l", "v*"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    tags = [line.strip().lstrip("v") for line in completed.stdout.splitlines() if line.strip()]
    return sorted(tags, key=_version_key)


def current_version(repo: Path) -> Optional[str]:
    version_file = repo / "cullinan" / "_version.py"
    if not version_file.is_file():
        return None
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', version_file.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def check(text: str, tags: Sequence[str], version: Optional[str]) -> List[str]:
    """Return a list of problems; an empty list means the changelog is healthy."""
    problems: List[str] = []
    entries = parse_changelog(text)
    if not entries:
        return ["the changelog has no version entries at all"]

    if not tags:
        # Seen in CI: ``actions/checkout`` clones shallow, ``git tag`` returns
        # nothing, and the continuity check silently did nothing while printing
        # PASS. A gate that cannot see what it is checking must say so.
        problems.append(
            "no release tags are visible, so the entries cannot be checked for continuity "
            "(a shallow clone hides tags; run with full history or fetch them)"
        )

    # An ``Unreleased`` section is legitimate -- work that has landed on the
    # branch but not in a tag belongs somewhere, and hiding it is how a
    # changelog becomes fiction. It is simply not a claim about a release, so
    # it is excluded from the "newest entry" and duplicate tests.
    released = [entry for entry in entries if entry.version.lower() != "unreleased"]
    if not released:
        return ["the changelog records no released versions, only an Unreleased section"]

    seen = [entry.version for entry in released]
    duplicates = sorted({name for name in seen if seen.count(name) > 1})
    if duplicates:
        problems.append(f"versions recorded more than once: {', '.join(duplicates)}")

    for entry in entries:
        if entry.bullets == 0:
            problems.append(f"v{entry.version} has no bullet points, so it records nothing")

    allowed = {name.lower() for name in ALLOWED_SECTIONS}
    for entry in entries:
        for section in entry.sections:
            if section.lower() not in allowed:
                problems.append(
                    f"v{entry.version} uses an unknown change type {section!r}; "
                    f"allowed: {', '.join(ALLOWED_SECTIONS)}"
                )

    newest = released[0]
    if version is not None and newest.version != version:
        problems.append(
            f"the newest entry is v{newest.version} but the package advertises {version}; "
            "the changelog lags the release"
        )

    # Continuity: every released version at or above the oldest recorded one
    # must be present. Versions the changelog predates are out of scope, and
    # saying so is the point -- see the module docstring.
    if tags:
        oldest = min((entry.version for entry in released), key=_version_key)
        expected = [tag for tag in tags if _version_key(tag) >= _version_key(oldest)]
        missing = [tag for tag in expected if tag not in seen]
        if missing:
            problems.append(
                "released but not recorded in the changelog: " + ", ".join(f"v{tag}" for tag in missing)
            )

    # Entries parked under ``Unreleased`` while the version they will ship in
    # already has its own section do not go unrecorded -- they go unannounced.
    # The reader of that version will not see them, and the continuity checks
    # below deliberately skip the section they sit in.
    #
    # Only a *pending* version can be in this state: once it is tagged, work
    # that lands afterwards legitimately belongs under ``Unreleased`` again.
    if version and version not in tags:
        pending_sections = [e for e in entries if e.version.lower() == version.lower()]
        parked = [e for e in entries if e.version.lower() == "unreleased" and e.bullets]
        if pending_sections and parked:
            problems.append(
                f"v{version} is not tagged yet and has its own section, but "
                f"{sum(e.bullets for e in parked)} "
                "entries still sit under Unreleased; they will ship in that version without "
                "appearing in it"
            )

    # The structured convention applies going forward: the newest released
    # entry and any Unreleased section must be typed. Entries already released
    # before the convention existed are history and are left as written.
    must_be_typed = [newest] + [entry for entry in entries if entry.version.lower() == "unreleased"]
    for entry in must_be_typed:
        if not entry.sections:
            problems.append(
                f"v{entry.version} is not organised by change type; every new entry must use "
                f"at least one of: {', '.join(ALLOWED_SECTIONS)}"
            )

    # An entry that names the machinery is not a smaller version of the right
    # entry -- it is a different document. It reads as an internal note because
    # that is what it is, and the reader it reaches is a user who cannot act on
    # it. Reported with the offending terms so the fix is obvious.
    for entry in must_be_typed:
        lowered = entry.body.lower()
        found = sorted({term for term in MAINTENANCE_TERMS if term.lower() in lowered})
        if found:
            problems.append(
                f"v{entry.version} describes maintenance machinery "
                f"({', '.join(found)}); a changelog entry states what changed for a user of the "
                "package, not how the checks that guard it are built"
            )

    return problems


_SAMPLE_HEALTHY = """# Changelog

## v0.97

### Added

- a thing

### Fixed

- another thing

## v0.96

### Added

- an older thing
"""

_SAMPLE_MISSING_VERSION = """# Changelog

## v0.98

### Added

- a thing

## v0.96

### Added

- an older thing
"""

_SAMPLE_UNTYPED = """# Changelog

## v0.97

- a thing
"""

_SAMPLE_BAD_TYPE = """# Changelog

## v0.97

### Tweaked

- a thing
"""

_SAMPLE_EMPTY = """# Changelog

## v0.97

### Added
"""

_SAMPLE_MAINTENANCE_TERMS = """# Changelog

## v0.97

### Changed

- `check_tag_gate.py` now compares the review and sync credential against `#tree=<40 hex>`
"""

_SAMPLE_MAINTENANCE_LEGACY = """# Changelog

## v0.97

### Added

- a thing

## v0.96

### Changed

- `check_tag_gate.py` now compares the review and sync credential against `#tree=<40 hex>`
"""


def _self_test() -> int:
    failures = 0

    def expect(name: str, text: str, tags: Sequence[str], version: str, should_pass: bool) -> None:
        nonlocal failures
        problems = check(text, tags, version)
        passed = not problems
        if passed != should_pass:
            failures += 1
            print(f"  FAIL {name}: expected {'pass' if should_pass else 'problems'}, got {problems or 'no problems'}")
        else:
            print(f"  ok   {name}")

    print("self-test: healthy input passes")
    expect("continuous and typed", _SAMPLE_HEALTHY, ["0.96", "0.97"], "0.97", True)

    print("self-test: each defect is reported")
    expect("released version missing", _SAMPLE_MISSING_VERSION, ["0.96", "0.97", "0.98"], "0.98", False)
    expect("newest entry not typed", _SAMPLE_UNTYPED, ["0.96", "0.97"], "0.97", False)
    expect("unknown change type", _SAMPLE_BAD_TYPE, ["0.97"], "0.97", False)
    expect("empty section", _SAMPLE_EMPTY, ["0.97"], "0.97", False)

    print("self-test: an entry that describes the machinery is reported, history is not")
    expect(
        "maintenance vocabulary in the newest entry",
        _SAMPLE_MAINTENANCE_TERMS,
        ["0.96", "0.97"],
        "0.97",
        False,
    )
    expect(
        "the same vocabulary in an older entry is history",
        _SAMPLE_MAINTENANCE_LEGACY,
        ["0.96", "0.97"],
        "0.97",
        True,
    )
    expect("changelog behind the release", _SAMPLE_HEALTHY, ["0.96", "0.97"], "0.98", False)

    print("self-test: continuity starts at the oldest recorded version")
    # 0.52 .. 0.94 predate the changelog; they must not be demanded.
    expect("older releases out of scope", _SAMPLE_HEALTHY, ["0.52", "0.94", "0.96", "0.97"], "0.97", True)

    print("self-test: ordering understands the alpha line")
    expect(
        "alpha ordering",
        "## v0.96a13\n\n### Added\n\n- later\n\n## v0.96a9\n\n### Added\n\n- earlier\n",
        ["0.96a9", "0.96a13"],
        "0.96a13",
        True,
    )

    print("self-test: entries parked under Unreleased while their version ships")
    PENDING = (
        "## Unreleased\n\n### Added\n\n- parked\n\n"
        "## v0.97\n\n### Added\n\n- shipped\n\n## v0.96\n\n### Added\n\n- older\n"
    )
    expect("pending version with parked entries", PENDING, ["0.96"], "0.97", False)
    # Same text, but 0.97 is tagged: parking the next thing under Unreleased is
    # the normal way to work, and must stay allowed.
    expect("tagged version, new work in Unreleased", PENDING, ["0.96", "0.97"], "0.97", True)

    print("self-test: an Unreleased section is allowed but is not a release claim")
    expect(
        "unreleased on top",
        "## Unreleased\n\n### Added\n\n- in flight\n\n" + _SAMPLE_HEALTHY.split("# Changelog\n", 1)[1],
        ["0.96", "0.97"],
        "0.97",
        True,
    )
    expect(
        "unreleased must be typed too",
        "## Unreleased\n\n- in flight\n\n" + _SAMPLE_HEALTHY.split("# Changelog\n", 1)[1],
        ["0.96", "0.97"],
        "0.97",
        False,
    )

    # Two parked sections must be counted together: reporting only the first
    # one understates how much would ship unannounced, and the message is the
    # only thing a reader gets.
    split_example = (
        "## Unreleased\n\n### Added\n\n- a\n- b\n- c\n\n"
        "## Unreleased\n\n### Added\n\n- d\n- e\n\n"
        "## v0.97\n\n### Added\n\n- shipped\n"
    )
    problems = check(split_example, ["0.96"], "0.97")
    if not any("5 entries" in p for p in problems):
        failures += 1
        print(f"  FAIL split parked sections are counted together: got {problems}")
    else:
        print("  ok   split parked sections are counted together")

    print("self-test: history predating the convention is grandfathered")
    expect(
        "old entry left untyped",
        "## v0.97\n\n### Added\n\n- new\n\n## v0.96\n\n- old, as written at the time\n",
        ["0.96", "0.97"],
        "0.97",
        True,
    )

    if failures:
        print(f"SELF-TEST FAILED ({failures} case(s))")
        return 1
    print("SELF-TEST PASSED")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".", help="repository root (default: current directory)")
    parser.add_argument("--changelog", default=None, help="path to the changelog (default: <repo>/CHANGELOG.md)")
    parser.add_argument("--self-test", action="store_true", help="run the built-in red/green cases and exit")
    parser.add_argument("--quiet", action="store_true", help="print only failures")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    repo = Path(args.repo).resolve()
    changelog = Path(args.changelog) if args.changelog else repo / "CHANGELOG.md"
    if not changelog.is_file():
        print(f"CHANGELOG CHECK FAIL: no changelog at {changelog}")
        return 1

    text = changelog.read_text(encoding="utf-8")
    tags = released_tags(repo)
    version = current_version(repo)
    problems = check(text, tags, version)

    if problems:
        print("CHANGELOG CHECK FAIL")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    if not args.quiet:
        entries = parse_changelog(text)
        print(f"CHANGELOG CHECK PASS -- {len(entries)} entries, newest v{entries[0].version}, "
              f"{len(tags)} released tags considered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
