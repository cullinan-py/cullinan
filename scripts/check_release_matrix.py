#!/usr/bin/env python3
"""Decide whether a candidate commit may be tagged, from cross-platform evidence.

A tag is cut once and cannot be re-cut without burning a version number, so the
evidence that gates it has to answer four questions and refuse when any of them is
unanswered. Each question exists because of a release that failed it:

* **D1 -- is this evidence about the commit being tagged?** "The suite was green
  last night" is not this. The evidence names a commit; the gate compares it with
  the candidate. And the evidence must be *produced by a machine*: a hand-written
  JSON that happens to carry the right sha and the right counts is indistinguishable
  from a real run to any reader, so it is not accepted. Allowed producers are
  ``gh_api`` (``gh run view --json headSha,conclusion`` plus per-job counts) and
  ``junit`` (one report per platform, carrying ``head_sha``).
* **D2 -- are there enough platforms, and do they include the one that publishes?**
  A single host's green is what shipped a release that failed on the next host.
  At least two platforms, and ``ubuntu-latest`` must be among them because that is
  where ``python-publish.yml`` runs.
* **D3 -- do the counts add up, and is the suite no smaller than last time?** Five
  numbers per platform (collected / passed / skipped / failed / errors), with
  ``failed == 0``, ``errors == 0``, and ``collected`` at or above the baseline. The
  baseline must *name where it came from* -- an earlier release's evidence, a
  registered value, or an explicit floor with a reason. A baseline the author picks
  per run is not a baseline: fill in ``1`` and the gate passes.
* **D4 -- was it measured before the tag?** Evidence produced after the tag cannot
  retroactively justify it. If the tag already exists and postdates the evidence's
  ``measured_at``, the gate refuses.

Three states, never two: ``GREEN``, ``RED``, and ``NOT RUN``. ``NOT RUN`` covers
evidence that is absent, unreadable, or missing a field the gate needs -- and it is
reported as a refusal, because "we could not check" has never been a pass. A gate
that collapses ``NOT RUN`` into ``GREEN`` is the failure mode this file exists to
avoid.

Usage::

    python scripts/check_release_matrix.py --evidence evidence.json --commit <sha>
    python scripts/check_release_matrix.py --self-test
    python scripts/check_release_matrix.py --replay <path>...   # red/green proof

The evidence format is documented in ``--help`` and in the ``EVIDENCE`` block below.
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

GREEN, RED, NOT_RUN = "GREEN", "RED", "NOT RUN"

#: The platform that runs ``python-publish.yml``. Evidence without it describes a
#: machine that will not be the one building the artefact.
PUBLISHING_PLATFORM = "ubuntu"

#: Minimum distinct platforms. One is a local run with extra steps.
MIN_PLATFORMS = 2

#: Producers that count as machine-produced. A missing or unknown producer is
#: ``NOT RUN``, not ``RED``: the gate cannot tell what it is looking at.
MACHINE_PRODUCERS = ("gh_api", "junit")

#: Where a baseline may come from. ``prev_tag`` is the previous release's evidence,
#: ``registered`` a value written down before this run, ``floor`` an explicit
#: constant with a stated reason. Anything else is not a baseline.
BASELINE_SOURCES = ("prev_tag", "registered", "floor")

EVIDENCE = """\
{
  "producer": "gh_api" | "junit",
  "candidate_commit": "<40-hex sha the evidence was produced for>",
  "measured_at": "<ISO-8601 UTC, e.g. 2026-10-31T11:58:00Z>",
  "baseline_source": "prev_tag" | "registered" | "floor",
  "baseline_value": <int>,
  "baseline_note": "<where the number came from; required for floor/registered>",
  "platforms": [
    {"name": "ubuntu-latest", "python": "3.13",
     "collected": 1501, "passed": 1499, "skipped": 2, "failed": 0, "errors": 0}
  ]
}
"""

COUNT_FIELDS = ("collected", "passed", "skipped", "failed", "errors")


class Outcome:
    """A verdict plus the reasons it was reached, so the message can be acted on."""

    def __init__(self, state: str, reasons: list[str]):
        self.state = state
        self.reasons = reasons

    @property
    def ok(self) -> bool:
        return self.state == GREEN

    def render(self, label: str = "") -> str:
        head = f"G-MATRIX {self.state}" + (f" @ {label}" if label else "")
        if not self.reasons:
            return head
        return head + "\n" + "\n".join(f"  - {reason}" for reason in self.reasons)


def _not_run(why: str) -> Outcome:
    return Outcome(NOT_RUN, [why])


def _red(why: list[str]) -> Outcome:
    return Outcome(RED, why)


def load_evidence(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Read evidence, or say why it cannot be read."""
    if not path.is_file():
        return None, f"no evidence at {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"{path} is not readable JSON: {exc}"
    if not isinstance(payload, dict):
        return None, f"{path}: the top level must be an object, got {type(payload).__name__}"
    return payload, None


def evaluate(
    evidence: dict[str, Any],
    candidate: str,
    tag_created_at: datetime.datetime | None = None,
) -> Outcome:
    """The decision, as a pure function of the evidence and the candidate.

    Kept separate from I/O so the self-test can drive it without files.
    """
    problems: list[str] = []

    # -- D1: machine-produced, and about this commit -------------------------
    producer = evidence.get("producer")
    if producer not in MACHINE_PRODUCERS:
        problems.append(
            f"producer is {producer!r}; accepted producers are {', '.join(MACHINE_PRODUCERS)} "
            f"-- evidence a person typed is indistinguishable from a run that happened, so it "
            f"does not count as evidence"
        )
    measured_commit = evidence.get("candidate_commit")
    if not isinstance(measured_commit, str) or len(measured_commit) != 40:
        problems.append(f"candidate_commit is {measured_commit!r}, not a 40-hex sha")
    elif measured_commit != candidate:
        problems.append(
            f"evidence is for {measured_commit[:12]}, candidate is {candidate[:12]} -- "
            f"a green run on another commit says nothing about this one"
        )

    # -- D2: enough platforms, including the one that publishes -------------
    platforms = evidence.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        return _not_run("evidence carries no platforms list, so nothing was measured")
    names = [str(entry.get("name", "")) for entry in platforms if isinstance(entry, dict)]
    distinct = sorted({name for name in names if name})
    if len(distinct) < MIN_PLATFORMS:
        problems.append(
            f"{len(distinct)} platform(s) measured ({', '.join(distinct) or 'none'}); "
            f"at least {MIN_PLATFORMS} are required, because one host's green has already "
            f"shipped a release that failed on the next"
        )
    if not any(PUBLISHING_PLATFORM in name for name in distinct):
        problems.append(
            f"no {PUBLISHING_PLATFORM!r} platform among {', '.join(distinct) or 'none'}; that is "
            f"where the publishing workflow runs, so its absence means the artefact was never "
            f"built on the machine that will build it"
        )

    # -- D3: five counts per platform, and a baseline that names its source --
    for entry in platforms:
        if not isinstance(entry, dict):
            problems.append(f"a platform entry is {type(entry).__name__}, not an object")
            continue
        label = entry.get("name", "<unnamed>")
        missing = [field for field in COUNT_FIELDS if not isinstance(entry.get(field), int)]
        if missing:
            problems.append(f"{label}: missing or non-integer {', '.join(missing)}")
            continue
        total = entry["passed"] + entry["skipped"] + entry["failed"] + entry["errors"]
        if total != entry["collected"]:
            problems.append(
                f"{label}: collected={entry['collected']} but passed+skipped+failed+errors="
                f"{total} -- the counts do not describe one run"
            )
        if entry["failed"]:
            problems.append(f"{label}: {entry['failed']} failed")
        if entry["errors"]:
            problems.append(f"{label}: {entry['errors']} error(s)")

    source = evidence.get("baseline_source")
    baseline = evidence.get("baseline_value")
    if source not in BASELINE_SOURCES:
        problems.append(
            f"baseline_source is {source!r}; accepted are {', '.join(BASELINE_SOURCES)} -- "
            f"a baseline nobody can trace is a number the author chose, and choosing 1 passes"
        )
    elif not isinstance(baseline, int) or baseline <= 0:
        problems.append(f"baseline_value is {baseline!r}, not a positive integer")
    elif source in ("floor", "registered") and not str(evidence.get("baseline_note", "")).strip():
        problems.append(
            f"baseline_source is {source!r} but baseline_note is empty -- a floor without a "
            f"stated reason is the same as no floor"
        )
    if isinstance(baseline, int) and baseline > 0:
        for entry in platforms:
            if not isinstance(entry, dict):
                continue
            collected = entry.get("collected")
            if isinstance(collected, int) and collected < baseline:
                problems.append(
                    f"{entry.get('name', '<unnamed>')}: collected={collected} is below the "
                    f"baseline {baseline} -- a smaller suite passing is not the same suite passing"
                )

    # -- D4: measured before the tag ----------------------------------------
    measured_at = evidence.get("measured_at")
    if tag_created_at is not None:
        if not isinstance(measured_at, str):
            problems.append("measured_at is missing, so the evidence cannot be placed before the tag")
        else:
            try:
                stamp = datetime.datetime.fromisoformat(measured_at.replace("Z", "+00:00"))
            except ValueError:
                problems.append(f"measured_at {measured_at!r} is not ISO-8601")
            else:
                if stamp > tag_created_at:
                    problems.append(
                        f"evidence was measured at {measured_at}, after the tag was created at "
                        f"{tag_created_at.isoformat()} -- evidence produced after the tag cannot "
                        f"retroactively justify it"
                    )

    return _red(problems) if problems else Outcome(GREEN, [])


def tag_time(ref: str) -> datetime.datetime | None:
    """When ``ref`` was created, or ``None`` if it does not exist."""
    probe = subprocess.run(
        ["git", "log", "-1", "--format=%cI", ref],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        return None
    try:
        return datetime.datetime.fromisoformat(probe.stdout.strip())
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Self-test: the gate must be able to say both things.
# --------------------------------------------------------------------------

_COMMIT = "1" * 40
_OTHER = "2" * 40


def _good(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "producer": "gh_api",
        "candidate_commit": _COMMIT,
        "measured_at": "2026-10-31T11:58:00Z",
        "baseline_source": "prev_tag",
        "baseline_value": 1501,
        "platforms": [
            {"name": "ubuntu-latest", "python": "3.13", "collected": 1501,
             "passed": 1499, "skipped": 2, "failed": 0, "errors": 0},
            {"name": "windows-latest", "python": "3.13", "collected": 1501,
             "passed": 1496, "skipped": 5, "failed": 0, "errors": 0},
        ],
    }
    payload.update(overrides)
    return payload


def self_test() -> int:
    cases: list[tuple[str, dict[str, Any], str, datetime.datetime | None]] = [
        ("two platforms, all green", _good(), GREEN, None),
        # A hand-written file is the defect D1 exists for.
        ("hand-written evidence", _good(producer="manual"), RED, None),
        ("no producer at all", {k: v for k, v in _good().items() if k != "producer"}, RED, None),
        # Green on the wrong commit is the "it passed last night" failure.
        ("evidence for another commit", _good(candidate_commit=_OTHER), RED, None),
        # One platform is a local run with extra steps.
        ("single platform", _good(platforms=[_good()["platforms"][1]]), RED, None),
        # The publishing host must be measured.
        ("no ubuntu", _good(platforms=[{"name": "windows-latest", "python": "3.13",
                                        "collected": 1501, "passed": 1496,
                                        "skipped": 5, "failed": 0, "errors": 0}]), RED, None),
        # Counts that do not add up describe two different runs.
        ("counts do not add up", _good(platforms=[
            {"name": "ubuntu-latest", "python": "3.13", "collected": 1501,
             "passed": 1499, "skipped": 2, "failed": 1, "errors": 0},
            _good()["platforms"][1],
        ]), RED, None),
        # A baseline the author picks is not a baseline.
        ("baseline with no source", _good(baseline_source="whatever"), RED, None),
        ("floor with no reason", _good(baseline_source="floor", baseline_note=""), RED, None),
        # A smaller suite passing is not the same suite passing.
        ("suite shrank below baseline", _good(baseline_value=1600), RED, None),
        # Evidence after the tag cannot justify it.
        ("measured after the tag", _good(),
         RED, datetime.datetime(2026, 10, 31, 10, 0, tzinfo=datetime.timezone.utc)),
        # Nothing measured is not a pass.
        ("no platforms", _good(platforms=[]), NOT_RUN, None),
    ]

    failures = []
    for label, payload, expected, tag_at in cases:
        outcome = evaluate(payload, _COMMIT, tag_at)
        mark = "ok" if outcome.state == expected else "MISMATCH"
        if outcome.state != expected:
            failures.append(label)
        print(f"  {label:32s} expect={expected:8s} got={outcome.state:8s} {mark}")

    # The reading side must also refuse what it cannot read.
    for label, text, expected in (
        ("not JSON", "{not json", NOT_RUN),
        ("top level is a list", "[]", NOT_RUN),
    ):
        tmp = Path(__file__).with_name("_matrix_selftest.json")
        tmp.write_text(text, encoding="utf-8")
        try:
            payload, problem = load_evidence(tmp)
            got = NOT_RUN if payload is None else "readable"
            mark = "ok" if got == expected or (expected == NOT_RUN and problem) else "MISMATCH"
            if mark == "MISMATCH":
                failures.append(label)
            print(f"  {label:32s} expect={expected:8s} got={got:8s} {mark}")
        finally:
            tmp.unlink(missing_ok=True)

    if failures:
        print(f"SELFTEST: FAIL ({', '.join(failures)})")
        return 1
    print(f"SELFTEST: PASS ({len(cases) + 2} cases, both directions)")
    return 0


def replay(paths: list[str]) -> int:
    """Run the gate over historical evidence and require the stated verdicts."""
    expected = {
        "MATRIX-R51": RED,   # no producer, no baseline source: written before this gate
        "MATRIX-R52": GREEN,  # the first run that satisfied the current rules
    }
    failures = []
    for raw in paths:
        path = Path(raw)
        payload, problem = load_evidence(path)
        if payload is None:
            print(f"  {path.name}: {NOT_RUN} ({problem})")
            continue
        candidate = str(payload.get("candidate_commit", ""))
        outcome = evaluate(payload, candidate)
        want = next((state for prefix, state in expected.items() if prefix in path.name), None)
        mark = "" if want is None else ("ok" if outcome.state == want else f"MISMATCH (want {want})")
        if want is not None and outcome.state != want:
            failures.append(path.name)
        print(f"  {path.name}: {outcome.state} {mark}")
    if failures:
        print(f"REPLAY: FAIL ({', '.join(failures)})")
        return 1
    print("REPLAY: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Decide whether a candidate commit may be tagged, from cross-platform evidence.",
        epilog="Evidence format:\n" + EVIDENCE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--evidence", default=None, help="path to the evidence JSON")
    parser.add_argument("--commit", default=None, help="candidate commit sha")
    parser.add_argument("--self-test", action="store_true", help="run the built-in cases")
    parser.add_argument("--replay", nargs="+", default=None, metavar="PATH",
                        help="run the gate over historical evidence files")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.replay:
        return replay(args.replay)
    if not args.evidence or not args.commit:
        parser.error("--evidence and --commit are required (or --self-test / --replay)")

    payload, problem = load_evidence(Path(args.evidence))
    if payload is None:
        print(Outcome(NOT_RUN, [problem or "evidence unreadable"]).render(args.commit[:12]))
        return 2

    outcome = evaluate(payload, args.commit, tag_time(f"{args.commit}^{{commit}}"))
    print(outcome.render(args.commit[:12]))
    if outcome.state == GREEN:
        return 0
    return 1 if outcome.state == RED else 2


if __name__ == "__main__":
    sys.exit(main())
