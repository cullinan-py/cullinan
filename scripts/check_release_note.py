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

#: The two engines answer an oversized body differently (`413` on one, `400` on the
#: other), so a sentence that names the status without naming the engine tells the
#: reader half of what they need. The phrases below are the ones that identify a
#: sentence as being *about* the body-size refusal; ``413`` alone is not enough,
#: because a published note may list the status among shapes ("`200`, `413`, a `400`
#: followed by a body") or discuss the header it carries, and neither of those is a
#: claim about which engine answers what.
_OVERSIZE_PHRASES = (
    "over the ceiling",
    "too large",
    "oversized",
    "max_request_body_bytes",
)
_ENGINE_NAMES = ("asgi", "tornado")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _engineless_413(text: str, name: str) -> list[str]:
    """A body-size refusal described without the engine that produces it."""
    findings = []
    for sentence in _SENTENCE_END.split(text):
        lowered = sentence.lower()
        if "413" not in lowered:
            continue
        if not any(phrase in lowered for phrase in _OVERSIZE_PHRASES):
            continue
        if any(engine in lowered for engine in _ENGINE_NAMES):
            continue
        findings.append(
            f"{name}: a sentence about the oversized-body refusal names `413` but not the "
            f"engine; the engines answer differently (`413` on one, `400` on the other), so "
            f"the reader cannot tell which one this is about: {sentence.strip()[:90]!r}"
        )
    return findings


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

    problems.extend(_engineless_413(text, name))

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

# The oversized-body rule has its own pair, because it is a rule about one
# sentence rather than about a note. The failing sample is the sentence as it
# shipped in the 0.96a12 note (the engine it meant was ASGI, and the sentence
# never said so); the passing pair is the two sentences most like it that must
# NOT be reported: a status listed among pinned shapes, and the `413` discussed
# for the header it carries. A third, farther neighbour -- a test summary line
# such as "3 failed, 1495 passed, 2 skipped" -- has no `413` in it at all and
# must stay clean, so the rule keeps its scope to the refusal itself.
_SAMPLE_ENGINELESS_413 = "A request that declares itself over the ceiling is answered `413` immediately."

_SAMPLE_413_WITH_ENGINE = "A request that declares itself over the ceiling is answered `413` on ASGI."

_SAMPLE_413_SHAPE_LIST = (
    "A verdict of its own pins the shapes that must fail: `200`, `413`, a `400` followed by "
    "a body, a hang, and a clean close with nothing read."
)

_SAMPLE_413_HEADER_DISCUSSION = (
    "And the early `413` still carries exactly one `Content-Length`: an extra one makes an "
    "intermediary wait for a body that never comes."
)

_SAMPLE_TEST_SUMMARY = "3 failed, 1495 passed, 2 skipped, 25 warnings"


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

    print("self-test: a body-size refusal names its engine")
    # These four go straight to the sentence-level rule rather than through
    # ``check_text``: they are sentences, not notes, and running them as notes
    # would only re-test the section template with the wrong input.
    engineless = _engineless_413(_SAMPLE_ENGINELESS_413, "engineless-413")
    if engineless:
        print("  ok   413 without an engine is reported")
    else:
        failures += 1
        print("  FAIL 413 without an engine is reported: the rule found nothing")
    for label, sample in (
        ("413 with an engine passes", _SAMPLE_413_WITH_ENGINE),
        ("413 among pinned shapes passes", _SAMPLE_413_SHAPE_LIST),
        ("413 discussed for its header passes", _SAMPLE_413_HEADER_DISCUSSION),
        ("a test summary line passes", _SAMPLE_TEST_SUMMARY),
    ):
        stray = _engineless_413(sample, label)
        if stray:
            failures += 1
            print(f"  FAIL {label}: {stray}")
        else:
            print(f"  ok   {label}")

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
