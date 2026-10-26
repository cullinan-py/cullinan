#!/usr/bin/env python
"""Check that a release reached BOTH channels, not just one.

A published release has two channels: the package (PyPI, fed by the tagged
commit) and the documentation site's `pre` channel (fed from the `preview`
branch). Pushing a release branch, tagging and publishing a release update the
first and touch neither the second nor the docs build -- so a release can look
finished while the documentation channel still advertises the previous version.

This script compares the version the docs channel carries against the version
that was released, so the mismatch is a machine signal instead of something a
person has to notice.

Usage:
  python scripts/check_channel_sync.py --version 0.96a5
  python scripts/check_channel_sync.py --version 0.96a5 --preview-ref origin/preview
  python scripts/check_channel_sync.py --self-test

Exit code: 0 = the two channels agree, 1 = they disagree, 2 = undeterminable.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = "cullinan/_version.py"
DEFAULT_PREVIEW_REF = "origin/preview"

_VERSION_RE = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def parse_version(source):
    """Return the version literal from a ``_version.py`` body, or None."""
    match = _VERSION_RE.search(source or "")
    return match.group(1) if match else None


def verdict(released, docs_channel):
    """Judge the two channel versions.

    Returns ``(ok, message)``. An undeterminable input is never reported as
    agreement: a check that cannot see the far side has not passed.
    """
    if not released:
        return False, "the released version could not be determined"
    if not docs_channel:
        return False, "the docs channel version could not be determined"
    if released == docs_channel:
        return True, "both channels carry {}".format(released)
    return False, (
        "channel mismatch: released {} but the docs channel carries {} -- the "
        "release has not reached the documentation site (merge the release "
        "content into the preview branch, then re-check)".format(
            released, docs_channel
        )
    )


def read_version_at(ref):
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", "{}:{}".format(ref, VERSION_FILE)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return parse_version(result.stdout)


def read_local_version():
    path = ROOT / VERSION_FILE
    if not path.is_file():
        return None
    return parse_version(path.read_text(encoding="utf-8"))


def self_test():
    cases = [
        ("0.96a5", "0.96a5", True, "identical versions agree"),
        ("0.96a5", "0.96a4", False, "a stale docs channel is a mismatch"),
        ("0.96a5", None, False, "an unreadable far side is not agreement"),
        (None, "0.96a5", False, "an unknown released version is not agreement"),
    ]
    ok = True
    for released, docs, expected, label in cases:
        got, _ = verdict(released, docs)
        flag = "ok " if got == expected else "BAD"
        if got != expected:
            ok = False
        print("  [{}] {:<46} expect={} got={}".format(flag, label, expected, got))
    parsed = parse_version('__version__ = "0.96a5"\n')
    if parsed != "0.96a5":
        ok = False
        print("  [BAD] parser expected 0.96a5 got {!r}".format(parsed))
    else:
        print("  [ok ] parser reads the version literal")
    print("self-test: {}".format(
        "all cases behave as expected (not always-green, not always-red)"
        if ok else "FAILURES PRESENT"
    ))
    return 0 if ok else 1


def main():
    parser = argparse.ArgumentParser(description="Release channel sync check")
    parser.add_argument("--version", default=None,
                        help="the released version (default: the local SSOT)")
    parser.add_argument("--preview-ref", default=DEFAULT_PREVIEW_REF,
                        help="the ref that feeds the docs `pre` channel")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    released = args.version or read_local_version()
    docs_channel = read_version_at(args.preview_ref)

    ok, message = verdict(released, docs_channel)
    print("released:      {}".format(released))
    print("docs channel:  {} ({})".format(docs_channel, args.preview_ref))
    print()
    if ok:
        print("CHANNEL SYNC PASS -- {}".format(message))
        return 0
    if released and docs_channel:
        print("CHANNEL SYNC FAIL -- {}".format(message))
        return 1
    print("CHANNEL SYNC UNKNOWN -- {}".format(message))
    return 2


if __name__ == "__main__":
    sys.exit(main())
