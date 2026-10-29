#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Decide whether a JUnit report says the suite passed.

A release workflow that trusts "the pipeline is green" is trusting a status it cannot
see. This repository has published a tag whose commit carried no test runs at all: the
suite had passed on a different commit with the same tree. Same content, different
commit -- so the evidence existed, but not where the release looked.

The way out is to produce the evidence where it is consumed: run the suite during the
publish job and judge the report it just wrote. This module is that judgement, kept
separate so it can be exercised without a CI run.

Four ways a report fails to say "passed":

  * it is missing or unparseable -- no report is not a passing report;
  * it holds zero tests -- a vacuous run;
  * it holds failures or errors;
  * every test was skipped -- green, and nothing verified.

The report is read rather than the process exit code because the exit code is a single
bit: it cannot distinguish "0 tests collected" from "1200 passed", and both are
possible ways for a suite to stop testing anything.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_UNDECIDABLE = 2


def evaluate(path: Path, min_tests: int = 1) -> tuple[int, str]:
    """Read a JUnit XML report and say whether it supports calling the suite green."""
    if not path.is_file():
        return EXIT_UNDECIDABLE, f"{path} does not exist: no report is not a passing report"

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return EXIT_UNDECIDABLE, f"{path} is not valid XML: {exc}"

    # pytest writes <testsuites><testsuite …/></testsuites>; other tools write the
    # suite directly. Both are accepted, and the counts are summed because a run split
    # across suites must not be judged by its largest part alone.
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        return EXIT_UNDECIDABLE, f"{path} contains no <testsuite> element"

    tests = sum(int(s.get("tests") or 0) for s in suites)
    failures = sum(int(s.get("failures") or 0) for s in suites)
    errors = sum(int(s.get("errors") or 0) for s in suites)
    skipped = sum(int(s.get("skipped") or 0) for s in suites)

    if tests < min_tests:
        return EXIT_REFUSED, f"only {tests} test(s) in the report, expected at least {min_tests}"
    if failures or errors:
        detail = []
        for suite in suites:
            for case in suite.iter("testcase"):
                for bad in list(case.findall("failure")) + list(case.findall("error")):
                    detail.append(f"{case.get('classname')}::{case.get('name')}")
        names = "; ".join(detail[:6]) + (" …" if len(detail) > 6 else "")
        return EXIT_REFUSED, f"{failures} failure(s) and {errors} error(s): {names}"
    if skipped >= tests:
        return EXIT_REFUSED, f"all {tests} test(s) were skipped: nothing verified the code"

    return EXIT_OK, f"{tests} test(s), {skipped} skipped, 0 failures, 0 errors"


# ---------------------------------------------------------------------------
# self-test: a checker only ever observed passing is indistinguishable from a
# checker that cannot fail, so the red cases live here
# ---------------------------------------------------------------------------

_CLEAN = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest" tests="1289" failures="0" errors="0" skipped="3"/></testsuites>
"""

_ONE_FAILURE = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest" tests="1289" failures="1" errors="0" skipped="3">
  <testcase classname="tests.core.test_x" name="test_y"><failure message="boom"/></testcase>
</testsuite></testsuites>
"""

_EMPTY = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest" tests="0" failures="0" errors="0" skipped="0"/></testsuites>
"""

_ALL_SKIPPED = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest" tests="4" failures="0" errors="0" skipped="4"/></testsuites>
"""

_SPLIT = """<?xml version="1.0"?>
<testsuites>
  <testsuite name="a" tests="600" failures="0" errors="0" skipped="1"/>
  <testsuite name="b" tests="689" failures="0" errors="0" skipped="2"/>
</testsuites>
"""

_SPLIT_WITH_ERROR = """<?xml version="1.0"?>
<testsuites>
  <testsuite name="a" tests="600" failures="0" errors="0" skipped="1"/>
  <testsuite name="b" tests="689" failures="0" errors="1" skipped="2"/>
</testsuites>
"""

_BROKEN = "not xml at all"


def self_test(tmpdir: Path) -> int:
    samples = [
        ("clean run", _CLEAN, 1, EXIT_OK),
        ("one failure", _ONE_FAILURE, 1, EXIT_REFUSED),
        ("zero tests", _EMPTY, 1, EXIT_REFUSED),
        ("all skipped", _ALL_SKIPPED, 1, EXIT_REFUSED),
        ("across two suites", _SPLIT, 1000, EXIT_OK),
        ("second suite has an error", _SPLIT_WITH_ERROR, 1, EXIT_REFUSED),
        ("below the floor", _CLEAN, 5000, EXIT_REFUSED),
        ("not xml", _BROKEN, 1, EXIT_UNDECIDABLE),
    ]
    failures = 0
    for index, (label, body, floor, expected) in enumerate(samples):
        path = tmpdir / f"sample-{index}.xml"
        path.write_text(body, encoding="utf-8")
        code, message = evaluate(path, floor)
        ok = code == expected
        print(f"  {'ok  ' if ok else 'FAIL'}  {label:28} -> {code} (expected {expected})  {message[:60]}")
        if not ok:
            failures += 1

    missing = tmpdir / "does-not-exist.xml"
    code, _ = evaluate(missing)
    ok = code == EXIT_UNDECIDABLE
    print(f"  {'ok  ' if ok else 'FAIL'}  {'missing report':28} -> {code} (expected {EXIT_UNDECIDABLE})")
    if not ok:
        failures += 1

    print(f"SELFTEST: {'PASS' if not failures else f'{failures} FAILURE(S)'}")
    return EXIT_OK if not failures else EXIT_REFUSED


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", nargs="?", help="JUnit XML written by the test run")
    parser.add_argument(
        "--min-tests",
        type=int,
        default=1,
        help="floor for the number of tests (a handful of tests is not a suite)",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            return self_test(Path(directory))

    if not args.report:
        print("need a report path (or --self-test)", file=sys.stderr)
        return EXIT_UNDECIDABLE

    code, message = evaluate(Path(args.report), args.min_tests)
    stream = sys.stdout if code == EXIT_OK else sys.stderr
    prefix = {EXIT_OK: "JUNIT OK", EXIT_REFUSED: "JUNIT REFUSED", EXIT_UNDECIDABLE: "JUNIT UNDECIDABLE"}[code]
    print(f"{prefix} -- {message}", file=stream)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
