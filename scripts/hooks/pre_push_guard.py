#!/usr/bin/env python3
"""Pre-push guard: refuse remote writes that no live authorization covers.

Opt-in and local. Two ways to wire it up:

  A. Wrapper hook. Put a `pre-push` wrapper in the git hooks directory that
     execs this file, then point the config below at the authorization json.
     This is what the repository actually uses; it works from every worktree,
     since the hooks directory is shared.
  B. `git config --local core.hooksPath scripts/hooks`, with a `pre-push`
     executable sitting next to this file.

Both ways need the config line:

    git config --local rwGuard.authFile <path to authorization json>

Once installed, a missing or unreadable authorization file is a refusal, not a
pass. Installing the guard is itself the statement that pushes have to be
covered.

The authorization file is JSON:

    {
      "authorization_id": "example-id",
      "granted_by": "user",
      "allowed_refs": ["refs/heads/release/0.0a0"],
      "allowed_uses": 1
    }

An update to a remote ref is allowed only when the ref is listed and the
authorization still has uses left. Uses are counted from push-audit.log, an
append-only file written next to the authorization file, so the count does not
depend on anyone remembering to decrement a field.

Limits, stated plainly. A local hook is skipped by `git push --no-verify`; it is
also skipped if the hooks path is pointed elsewhere (`git config --local
core.hooksPath <other dir>`); and it cannot see pushes made from another clone.
It is a barrier at the point of action, not a guarantee. The append-only log is
the part that resists quiet removal, because it is reconciled against the
remote's own reflog afterwards - and that reconciliation is what has to be run
independently, since none of the bypasses above are detectable from here.

Exit codes: 0 allow, 1 refuse, 2 configuration error (also a refusal).
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import tempfile

CONFIG_KEY = "rwGuard.authFile"
AUDIT_NAME = "push-audit.log"


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def configured_auth_file():
    result = run(["git", "config", "--local", "--get", CONFIG_KEY])
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def load_auth(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def count_uses(audit_path, authorization_id):
    if not os.path.isfile(audit_path):
        return 0
    marker = "auth={}".format(authorization_id)
    used = 0
    with open(audit_path, encoding="utf-8") as handle:
        for line in handle:
            if marker in line:
                used += 1
    return used


def parse_refs(stdin_text):
    refs = []
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            refs.append(
                {
                    "local_ref": parts[0],
                    "local_sha": parts[1],
                    "remote_ref": parts[2],
                    "remote_sha": parts[3],
                }
            )
    return refs


def evaluate(auth, refs, uses_so_far):
    """Pure decision: returns (allowed, reasons)."""
    if auth is None:
        return False, ["no authorization file configured"]
    reasons = []
    allowed_refs = list(auth.get("allowed_refs") or [])
    total = auth.get("allowed_uses")
    identifier = auth.get("authorization_id") or "<unnamed>"
    if total is None:
        reasons.append("authorization {} has no allowed_uses field".format(identifier))
    elif uses_so_far >= int(total):
        reasons.append(
            "authorization {} is used up ({}/{} recorded in the audit log)".format(
                identifier, uses_so_far, total
            )
        )
    if not refs:
        reasons.append("no ref update on stdin: cannot tell what would be written")
    for ref in refs:
        remote_ref = ref.get("remote_ref", "")
        if remote_ref not in allowed_refs:
            reasons.append(
                "remote ref {!r} is not listed in the authorization".format(remote_ref)
            )
    return (not reasons), reasons


def append_audit(audit_path, auth, refs):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    head = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    identifier = auth.get("authorization_id") or "<unnamed>"
    lines = []
    for ref in refs:
        lines.append(
            " ".join(
                [
                    stamp,
                    "auth={}".format(identifier),
                    "granted_by={}".format(auth.get("granted_by", "?")),
                    "ref={}".format(ref.get("remote_ref", "")),
                    "to={}".format(ref.get("local_sha", "")[:12]),
                    "was={}".format(ref.get("remote_sha", "")[:12]),
                    "head={}".format(head[:12]),
                ]
            )
        )
    with open(audit_path, "a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line + "\n")


def guard(stdin_text):
    auth_file = configured_auth_file()
    if not auth_file:
        return 2, [
            "no authorization file configured (git config --local {} ...)".format(CONFIG_KEY)
        ]
    if not os.path.isfile(auth_file):
        return 2, ["configured authorization file does not exist: {}".format(auth_file)]
    try:
        auth = load_auth(auth_file)
    except (OSError, ValueError) as exc:
        return 2, ["authorization file is not readable JSON: {}".format(exc)]

    refs = parse_refs(stdin_text)
    audit_path = os.path.join(os.path.dirname(os.path.abspath(auth_file)), AUDIT_NAME)
    uses = count_uses(audit_path, auth.get("authorization_id"))
    allowed, reasons = evaluate(auth, refs, uses)
    if not allowed:
        return 1, reasons
    append_audit(audit_path, auth, refs)
    print(
        "pre-push guard: allowed by authorization {} (use {}/{})".format(
            auth.get("authorization_id"), uses + 1, auth.get("allowed_uses")
        )
    )
    return 0, []


def self_test():
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        auth_file = os.path.join(tmp, "auth.json")
        ref_line = "refs/heads/x {} refs/heads/x {}".format("a" * 40, "b" * 40)

        def write(payload):
            with open(auth_file, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)

        cases = []

        write({"authorization_id": "T", "allowed_refs": [], "allowed_uses": 0})
        cases.append(("no uses left", json.load(open(auth_file)), 0, False))
        cases.append(("unlisted ref", json.load(open(auth_file)), 0, False))

        write({"authorization_id": "T2", "allowed_refs": ["refs/heads/x"], "allowed_uses": 1})
        cases.append(("covered and unused", json.load(open(auth_file)), 0, True))
        cases.append(("covered but used", json.load(open(auth_file)), 1, False))

        write({"authorization_id": "T3", "allowed_refs": ["refs/heads/x"]})
        cases.append(("missing allowed_uses", json.load(open(auth_file)), 0, False))

        cases.append(("no authorization at all", None, 0, False))

        for label, auth, uses, expected in cases:
            allowed, _ = evaluate(auth, parse_refs(ref_line), uses)
            mark = "ok" if allowed == expected else "MISMATCH"
            if allowed != expected:
                failures.append(label)
            print("  {:24s} expect={!s:5s} got={!s:5s} {}".format(label, expected, allowed, mark))

        # The audit log is what counts uses, so a second pass must be refused.
        write({"authorization_id": "T4", "allowed_refs": ["refs/heads/x"], "allowed_uses": 1})
        append_audit(os.path.join(tmp, AUDIT_NAME), json.load(open(auth_file)), parse_refs(ref_line))
        used = count_uses(os.path.join(tmp, AUDIT_NAME), "T4")
        allowed, _ = evaluate(json.load(open(auth_file)), parse_refs(ref_line), used)
        if allowed or used != 1:
            failures.append("append-only log counts uses")
        print(
            "  {:24s} expect={!s:5s} got={!s:5s}".format(
                "log counts uses", False, allowed
            )
        )

    if failures:
        print("self-test FAILED: {}".format(", ".join(failures)))
        return 1
    print("self-test: all cases behave as expected (not always-refuse, not always-allow)")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    code, reasons = guard(sys.stdin.read())
    if code != 0:
        sys.stderr.write("pre-push guard: refusing to write to the remote.\n")
        for reason in reasons:
            sys.stderr.write("  - {}\n".format(reason))
        sys.stderr.write(
            "  A remote write needs an authorization that names the ref and has uses left;\n"
            "  see the project's remote-write authorization rules.\n"
        )
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
