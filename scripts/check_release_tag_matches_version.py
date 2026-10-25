#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Refuse to publish a tag whose version is not the one the code carries.

The publisher workflow runs on the `release: published` event, and it uploads
whatever commit the tag points at. If the tag and `cullinan/_version.py`
disagree, the artefact that reaches the package index is labelled with a version
the code does not claim -- and PyPI does not allow a version to be reused, so
the mistake cannot be undone, only yanked.

`check_tag_gate.py` already compares them before a tag is created, but that runs
on a developer's machine against the working tree. This check runs inside the
publishing job against the actual tag ref, which is the last place it can still
stop anything.

Usage::

    python scripts/check_release_tag_matches_version.py --tag v0.96a5
    python scripts/check_release_tag_matches_version.py --self-test
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional, Sequence

_TAG_PREFIXES = ("refs/tags/", "tags/")


def normalise_tag(tag: str) -> str:
    """Return the version a tag name advertises, dropping any ref prefix and `v`."""
    value = tag.strip()
    for prefix in _TAG_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    if value.startswith("v"):
        value = value[1:]
    return value


def read_version(repo: Path) -> Optional[str]:
    version_file = repo / "cullinan" / "_version.py"
    if not version_file.is_file():
        return None
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', version_file.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def check(tag: str, version: Optional[str]) -> List[str]:
    """Return a list of problems; an empty list means the tag may be published."""
    problems: List[str] = []
    if not tag or not tag.strip():
        return ["no tag was given, so the version could not be compared"]
    if version is None:
        return ["the package version could not be read from cullinan/_version.py"]

    advertised = normalise_tag(tag)
    if not advertised:
        problems.append(f"the tag {tag!r} does not name a version")
    elif advertised != version:
        problems.append(
            f"the tag advertises {advertised} but cullinan/_version.py says {version}; "
            "publishing this tag would upload an artefact labelled with a version the code does not claim"
        )
    return problems


def _self_test() -> int:
    failures = 0

    def expect(name: str, tag: str, version: str, should_pass: bool) -> None:
        nonlocal failures
        problems = check(tag, version)
        if (not problems) == should_pass:
            print(f"  ok   {name}")
        else:
            failures += 1
            print(f"  FAIL {name}: got {problems or 'no problems'}")

    print("self-test: matching tags pass")
    expect("v-prefixed tag", "v0.96a5", "0.96a5", True)
    expect("bare tag", "0.96a5", "0.96a5", True)
    expect("full ref", "refs/tags/v0.96a5", "0.96a5", True)

    print("self-test: mismatches are refused")
    expect("different version", "v0.96a4", "0.96a5", False)
    expect("same minor, different alpha", "v0.96a5", "0.96a6", False)
    expect("prefix does not hide a mismatch", "refs/tags/v0.96a5", "0.95", False)

    print("self-test: degenerate input is refused rather than waved through")
    expect("empty tag", "", "0.96a5", False)
    if check("v0.96a5", None):
        print("  ok   unreadable version is refused")
    else:
        failures += 1
        print("  FAIL unreadable version is refused: reported no problem")

    if failures:
        print(f"SELF-TEST FAILED ({failures} case(s))")
        return 1
    print("SELF-TEST PASSED")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", default=None, help="tag name to verify (e.g. v0.96a5 or refs/tags/v0.96a5)")
    parser.add_argument("--repo", default=".", help="repository root (default: current directory)")
    parser.add_argument("--self-test", action="store_true", help="run the built-in red/green cases and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    repo = Path(args.repo).resolve()
    version = read_version(repo)
    problems = check(args.tag or "", version)

    if problems:
        print("RELEASE TAG CHECK FAIL")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"RELEASE TAG CHECK PASS -- tag {normalise_tag(args.tag)} matches cullinan/_version.py ({version})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
