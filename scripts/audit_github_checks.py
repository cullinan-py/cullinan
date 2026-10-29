#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Report whether GitHub has check runs for a commit, and what they concluded.

This is an **audit** tool, not a release gate. The distinction matters, and it was
learned the hard way.

Asking GitHub "what ran on this commit" sounds like the right gate, and it is what
found the problem: the commit that `v0.96a9` points at carries three check runs --
`deploy`, `deploy`, `docs` -- and no test run at all. The suite had passed on a
different commit with the same tree. The evidence existed; it was simply not attached
to the commit being released.

But that same fact makes the API unusable as a gate. Tagging a merge commit whose
parent is the tested branch head produces exactly this shape, and a gate that refuses
it would refuse every release this project makes. Making the gate cleverer -- "accept
a commit with the same tree" -- needs a way to enumerate commits by tree, which the
checks API does not offer.

So the gate lives where the evidence can be produced rather than looked up:
`scripts/check_junit.py` judges a report written by the publish job itself. This module
stays as the tool that answers the audit question, which is still worth being able to
answer:

    Did the thing we shipped ever run its tests anywhere GitHub can see?

Usage:

    audit_github_checks.py --sha <sha> [--repo owner/name]
    audit_github_checks.py --sha <sha> --file check-runs.json
    audit_github_checks.py --self-test

Exit codes: 0 all accounted for, 1 something failed or was never tested,
2 no answer obtainable. The red cases are exercised by --self-test, because a checker
only ever observed passing is indistinguishable from one that cannot fail.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_UNDECIDABLE = 2

#: Conclusions that do not block a release. `skipped` is here because a conditional
#: job that legitimately does not apply must not stop a release; it is handled again
#: below so that a *test* job cannot hide behind it.
ACCEPTABLE = {"success", "neutral", "skipped"}

#: Anything else -- failure, cancelled, timed_out, action_required, stale -- refuses.
BLOCKING = {"failure", "cancelled", "timed_out", "action_required", "stale"}

#: A run whose name matches this is taken to be a test run. Deliberately loose: the
#: point is to require that *something* exercised the code, not to pin job names that
#: get renamed.
TEST_NAME = re.compile(r"\b(test|tests|pytest|suite|matrix)\b", re.IGNORECASE)


def evaluate(runs: list[dict], sha: str) -> tuple[int, list[str]]:
    """Decide whether `sha` may be published, given its check runs.

    Returns (exit_code, reasons). An empty reason list accompanies EXIT_OK.
    """
    if not runs:
        return EXIT_REFUSED, [
            f"no check runs reported for {sha[:12]}: nothing ran, which is not the same "
            f"as nothing failing"
        ]

    reasons: list[str] = []
    completed = 0
    succeeded = 0
    test_seen = 0
    test_succeeded = 0

    for run in runs:
        name = run.get("name") or "(unnamed)"
        status = (run.get("status") or "").lower()
        conclusion = (run.get("conclusion") or "").lower()

        if status != "completed":
            reasons.append(f"{name}: still {status or 'unknown'}, not completed")
            continue

        completed += 1

        if conclusion in BLOCKING or conclusion not in ACCEPTABLE:
            reasons.append(f"{name}: {conclusion or 'no conclusion'}")
            continue

        if conclusion == "success":
            succeeded += 1

        if TEST_NAME.search(name):
            test_seen += 1
            if conclusion == "success":
                test_succeeded += 1

    if completed == 0:
        reasons.append("not one run reached a conclusion")

    if succeeded == 0 and not reasons:
        reasons.append("every run was skipped or neutral: nothing verified the code")

    if test_seen == 0:
        reasons.append(
            "no run looks like a test (expected a name containing test/tests/pytest/"
            "suite/matrix); lint and packaging alone do not establish that the code works"
        )
    elif test_succeeded == 0:
        reasons.append("every test-like run was skipped, so no test actually ran")

    return (EXIT_OK, []) if not reasons else (EXIT_REFUSED, reasons)


def fetch_runs(repo: str, sha: str, token: str) -> list[dict]:
    """Read check runs for a commit from the GitHub API."""
    url = f"https://api.github.com/repos/{repo}/commits/{sha}/check-runs?per_page=100"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed host
        payload = json.load(response)
    return payload.get("check_runs", [])


# ---------------------------------------------------------------------------
# self-test: the red cases are the reason this file exists
# ---------------------------------------------------------------------------

_CLEAN = [
    {"name": "test (ubuntu-latest / py3.13)", "status": "completed", "conclusion": "success"},
    {"name": "lint", "status": "completed", "conclusion": "success"},
]

_SAMPLES = [
    ("all green", _CLEAN, EXIT_OK),
    (
        "one test failed",
        [
            {"name": "test (ubuntu-latest / py3.13)", "status": "completed", "conclusion": "success"},
            {"name": "test (ubuntu-latest / py3.9)", "status": "completed", "conclusion": "failure"},
        ],
        EXIT_REFUSED,
    ),
    ("no runs at all", [], EXIT_REFUSED),
    (
        "a run still going",
        [{"name": "test (ubuntu-latest / py3.13)", "status": "in_progress", "conclusion": None}],
        EXIT_REFUSED,
    ),
    (
        "lint only, no test",
        [{"name": "lint", "status": "completed", "conclusion": "success"}],
        EXIT_REFUSED,
    ),
    (
        "every job skipped",
        [
            {"name": "test (ubuntu-latest / py3.13)", "status": "completed", "conclusion": "skipped"},
            {"name": "lint", "status": "completed", "conclusion": "skipped"},
        ],
        EXIT_REFUSED,
    ),
    (
        "cancelled test",
        [{"name": "test (ubuntu-latest / py3.13)", "status": "completed", "conclusion": "cancelled"}],
        EXIT_REFUSED,
    ),
    (
        "a conditional job skipped but the test passed",
        _CLEAN + [{"name": "docs", "status": "completed", "conclusion": "skipped"}],
        EXIT_OK,
    ),
]


def self_test() -> int:
    failures = 0
    for label, runs, expected in _SAMPLES:
        code, reasons = evaluate(runs, "0" * 40)
        ok = code == expected
        print(f"  {'ok  ' if ok else 'FAIL'}  {label:44} -> {code} (expected {expected})")
        if not ok:
            failures += 1
            for reason in reasons:
                print(f"          {reason}")
    print(f"SELFTEST: {'PASS' if not failures else f'{failures} FAILURE(S)'}")
    return EXIT_OK if not failures else EXIT_REFUSED


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sha", help="commit to judge")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--file", help="read check runs from this JSON instead of the API")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    if not args.sha:
        print("need --sha (or --self-test)", file=sys.stderr)
        return EXIT_UNDECIDABLE

    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            payload = json.load(handle)
        runs = payload.get("check_runs", payload if isinstance(payload, list) else [])
    else:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token or not args.repo:
            print(
                "cannot ask GitHub what ran: set GH_TOKEN (and --repo, or "
                "GITHUB_REPOSITORY). Refusing rather than assuming the checks passed.",
                file=sys.stderr,
            )
            return EXIT_UNDECIDABLE
        try:
            runs = fetch_runs(args.repo, args.sha, token)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"cannot reach the API ({exc}); refusing rather than assuming", file=sys.stderr)
            return EXIT_UNDECIDABLE

    code, reasons = evaluate(runs, args.sha)
    if code == EXIT_OK:
        print(f"AUDIT: all accounted for -- {len(runs)} check run(s) on {args.sha[:12]}, all accounted for")
        for run in runs:
            print(f"  {run.get('conclusion'):8} {run.get('name')}")
        return EXIT_OK

    print(f"AUDIT: not covered -- {args.sha[:12]}", file=sys.stderr)
    for reason in reasons:
        print(f"  {reason}", file=sys.stderr)
    print(
        "\nA release cannot be taken back: a version may be yanked but never reused. "
        "Fix the tree, let the checks run, then release.",
        file=sys.stderr,
    )
    return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
