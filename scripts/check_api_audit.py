#!/usr/bin/env python3
"""Check that the API-side actions a release performs were written down.

The pre-push guard sees `git push` and nothing else. A release also merges a pull
request and creates a GitHub release -- both are server-side writes that never pass
through a local hook, so the guard's log has no line for them. `§5.9` requires the
person doing them to append a `kind=api` line, and this file is what reads those
lines back.

Two questions, and both have shipped wrong:

* **Is each line well formed?** `action` from a closed set, `id` taken from the
  service (a PR number, a tag name) rather than invented, an `auth=` naming the
  authorization it was performed under. A free-form line cannot be reconciled
  against the server, so it is not evidence.
* **Does every closed authorization have one?** An authorization that ends without
  a matching API line is either an authorization that was never used -- fine -- or
  a write nobody recorded, which is the failure `G-1` names. The two are told apart
  by asking the server: the gate cannot do that offline, so it reports the pair and
  leaves the reconciliation to the reader, naming what to check.

Retroactive lines (`retro=1`) are accepted but marked: a rule that lands after the
action it governs can only be satisfied this way, and calling those lines ordinary
evidence would be claiming they were written at the time.

Usage::

    python scripts/check_api_audit.py --log <path to push-audit.log>
    python scripts/check_api_audit.py --self-test
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: Actions that write to the remote through the API rather than through `git push`.
ACTIONS = ("pr_merge", "release_create", "tag_delete")

#: The fields every line must carry. ``retro`` and ``reason`` are extra, and
#: ``reason`` is required when ``retro`` is present. The timestamp is checked
#: separately: it is the leading field the guard already writes, not a ``ts=`` pair,
#: so "no stamp" and "unparseable stamp" get the same actionable message.
REQUIRED = ("kind", "action", "id", "actor", "auth")

_FIELD = re.compile(r"(\w+)=(\S+)")
_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def parse_line(line: str) -> dict[str, str]:
    """The key/value pairs on one log line, first occurrence wins.

    The leading ISO-8601 stamp is exposed as ``ts``: it is the one field that is not
    written as ``key=value``, and it is the field that places the line relative to a
    tag.
    """
    fields: dict[str, str] = {}
    head, _, rest = line.partition(" ")
    if _STAMP.match(head):
        fields["ts"] = head
    else:
        rest = line
    for key, value in _FIELD.findall(rest):
        fields.setdefault(key, value)
    return fields


def api_lines(text: str) -> list[tuple[int, dict[str, str]]]:
    """Every ``kind=api`` line, with its 1-based number."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        fields = parse_line(line)
        if fields.get("kind") == "api":
            found.append((number, fields))
    return found


def check(text: str) -> list[str]:
    """Problems with the ``kind=api`` lines, or an empty list when they are usable."""
    problems: list[str] = []
    for number, fields in api_lines(text):
        missing = [key for key in REQUIRED if not fields.get(key)]
        if missing:
            problems.append(f"line {number}: missing {', '.join(missing)}")
            continue
        if fields["action"] not in ACTIONS:
            problems.append(
                f"line {number}: action {fields['action']!r} is not one of "
                f"{', '.join(ACTIONS)} -- an open set cannot be reconciled"
            )
        if fields.get("retro") == "1" and not fields.get("reason"):
            problems.append(
                f"line {number}: retro=1 without reason= -- a late entry has to say why "
                f"it is late, or it reads as evidence written at the time"
            )
        if not _STAMP.match(fields.get("ts", "")):
            problems.append(
                f"line {number}: ts={fields.get('ts', '')!r} is not an ISO-8601 UTC stamp; "
                f"a line that cannot be placed in time cannot be reconciled against the tag"
            )
    return problems


def authorizations_without_api_line(text: str) -> list[str]:
    """Authorizations that appear in the log but never as an API action.

    Not a failure on its own: an authorization can be spent entirely on ``git push``.
    Reported so the reconciliation has a starting point.
    """
    push_auths = set()
    api_auths = set()
    for line in text.splitlines():
        fields = parse_line(line)
        auth = fields.get("auth")
        if not auth:
            continue
        if fields.get("kind") == "api":
            api_auths.add(auth)
        elif fields.get("op"):
            push_auths.add(auth)
    return sorted(push_auths - api_auths)


def self_test() -> int:
    good = (
        "2026-10-31T12:49:00Z kind=api action=pr_merge id=#52 actor=ORCH auth=A-78 "
        "url=https://example/52\n"
        "2026-10-31T12:54:55Z kind=api action=tag_delete id=v0.96a11 actor=ORCH auth=A-78\n"
        "2026-10-31T12:00:00Z auth=A-70 op=create ref=refs/tags/v0.96a11\n"
    )
    cases = [
        ("well-formed lines", good, []),
        ("unknown action",
         "2026-10-31T12:00:00Z kind=api action=push_branch id=x1 actor=ORCH auth=A-1\n",
         ["is not one of"]),
        ("missing auth",
         "2026-10-31T12:00:00Z kind=api action=pr_merge id=#1 actor=ORCH\n",
         ["missing auth"]),
        ("retro without reason",
         "2026-10-31T12:00:00Z kind=api action=pr_merge id=#1 actor=ORCH auth=A-1 retro=1\n",
         ["retro=1 without reason"]),
        ("no timestamp",
         "kind=api action=pr_merge id=#1 actor=ORCH auth=A-1\n",
         ["is not an ISO-8601 UTC stamp"]),
    ]
    failures = []
    for label, text, expected_fragments in cases:
        problems = check(text)
        if not expected_fragments:
            ok = not problems
        else:
            ok = any(fragment in problem for problem in problems for fragment in expected_fragments)
        if not ok:
            failures.append(label)
        print(f"  {label:28s} {'ok' if ok else 'MISMATCH'}  {problems or ''}")

    # The reconciliation listing must find the authorization that only pushed.
    listed = authorizations_without_api_line(good)
    ok = listed == ["A-70"]
    if not ok:
        failures.append("reconciliation listing")
    print(f"  {'reconciliation listing':28s} {'ok' if ok else 'MISMATCH'}  {listed}")

    if failures:
        print(f"SELFTEST: FAIL ({', '.join(failures)})")
        return 1
    print(f"SELFTEST: PASS ({len(cases) + 1} cases, both directions)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--log", default=None, help="path to push-audit.log")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.log:
        parser.error("--log is required (or --self-test)")

    path = Path(args.log)
    if not path.is_file():
        print(f"NOT RUN: no audit log at {path}")
        return 2
    text = path.read_text(encoding="utf-8", errors="replace")

    problems = check(text)
    found = api_lines(text)
    print(f"api lines: {len(found)}")
    for problem in problems:
        print(f"  - {problem}")

    unpaired = authorizations_without_api_line(text)
    if unpaired:
        print(
            "authorizations with push lines but no API line (not a failure -- an "
            "authorization can be spent entirely on git push; listed for reconciliation):"
        )
        for auth in unpaired:
            print(f"  - {auth}")

    if problems:
        print("RESULT: RED")
        return 1
    print("RESULT: GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
