"""
Pre-tag manual gate verification.

git has no native pre-tag hook, so this script mechanizes the pre-tag
confirmations:
  (a) a sign-off token was provided and is non-empty (thread evidence)
  (b) a review token was provided and is non-empty (thread evidence)
  (c) release readiness (locally verifiable parts):
      - version SSOT aligned (cullinan.__version__ == cullinan.core.__version__)
      - release notes present (RELEASE-v{version}.md at the repo root)
      - README "Current series" points at the current version
      - working tree clean (a tag must point at a committed state)
  (d) declaration backstop (locally verifiable part):
      - the commit(s) being released carry a well-formed Meta-Sync trailer when
        they touch a release-process / configuration path
        (see scripts/check_sync_declaration.py). This is a backstop only --
        primary enforcement runs on every PR/push in CI.

Usage:
  python scripts/check_tag_gate.py --sign-off-token <TOKEN> --review-token <TOKEN> --sync-token <TOKEN> [--version <VERSION>] [--meta-sync-range <base>..<head>]

``--version`` is optional and defaults to the version read from
``cullinan/_version.py`` (the single source of truth), so this usage line
never pins a release number: pass it only to assert an expected version
explicitly.

Exit code: 0 = PASS (git tag may proceed), 1 = FAIL (blocked).
"""
import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_ssot_version():
    text = (ROOT / "cullinan" / "_version.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        return None
    return match.group(1)


def main():
    parser = argparse.ArgumentParser(description="Pre-tag gate verification")
    parser.add_argument("--sign-off-token", required=True,
                        help="(a) non-empty sign-off token issued by the maintainer")
    parser.add_argument("--review-token", required=True,
                        help="(b) non-empty review token issued by the maintainer")
    parser.add_argument("--sync-token", required=True,
                        help="an opaque sync credential issued by the maintainer")
    parser.add_argument("--version", default=None,
                        help="Expected version (default: read from cullinan/_version.py)")
    parser.add_argument("--meta-sync-range", default=None,
                        help="commit range (base..head) for the declaration backstop "
                             "(default: the commit being tagged)")
    args = parser.parse_args()

    fails = []

    def check(label, ok, detail=""):
        status = "PASS" if ok else "FAIL"
        suffix = f" -- {detail}" if detail else ""
        print(f"{status} {label}{suffix}")
        if not ok:
            fails.append(label)

    # (a) sign-off evidence
    check("(a) sign-off token provided", bool(args.sign_off_token.strip()),
          args.sign_off_token.strip() or "empty")

    # (b) review evidence
    check("(b) review token provided", bool(args.review_token.strip()),
          args.review_token.strip() or "empty")

    # sync credential present (opaque: existence only, meaning is not interpreted here)
    check("Sync credential provided", bool(args.sync_token.strip()),
          args.sync_token.strip() or "empty")

    # (c) release readiness (locally verifiable parts)
    ssot = read_ssot_version()
    expected = args.version or ssot
    check("Version SSOT readable (cullinan/_version.py)", ssot is not None)
    check("Expected version matches SSOT", expected == ssot,
          f"expected={expected} ssot={ssot}")

    if expected:
        notes = ROOT / f"RELEASE-v{expected}.md"
        check(f"Release notes present ({notes.name})", notes.exists())

        readme = (ROOT / "README.MD").read_text(encoding="utf-8")
        check("README Current series aligned", f"**v{expected}**" in readme)

    try:
        sys.path.insert(0, str(ROOT))
        import cullinan
        from cullinan import core
        check("Import smoke + runtime version aligned",
              cullinan.__version__ == expected == core.__version__,
              f"cullinan={cullinan.__version__} core={core.__version__}")
    except Exception as exc:  # noqa: BLE001 - gate must fail, not crash
        check("Import smoke + runtime version aligned", False, repr(exc))

    status = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    check("Working tree clean", status == "", status or "clean")

    # (d) declaration backstop (see scripts/check_sync_declaration.py).
    # Backstop only: the primary enforcement runs on every PR/push in CI. Kept
    # narrow by default (the commit being tagged) so that pre-existing history
    # is not re-flagged; widen with --meta-sync-range for a whole batch.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import check_sync_declaration as declaration_gate

        if args.meta_sync_range:
            base, _, head = args.meta_sync_range.partition("..")
            results = declaration_gate.evaluate_range(str(ROOT), base, head)
        else:
            results = [declaration_gate.evaluate_commit(str(ROOT), "HEAD")]
        reds = [item for item in results if item[0] == "RED"]
        detail = "all clear" if not reds else "; ".join(
            f"{label} -- {text}" for _, label, text in reds
        )
        check("(d) declaration present on governed changes", not reds, detail)
    except Exception as exc:  # noqa: BLE001 - gate must fail, not crash
        check("(d) declaration present on governed changes", False, repr(exc))

    print()
    if fails:
        print(f"TAG GATE FAIL ({len(fails)} check(s) failed) -- do NOT run git tag")
        return 1
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"TAG GATE PASS -- version {expected} @ {stamp}")
    print(f"  (a) sign-off token  : {args.sign_off_token.strip()}")
    print(f"  (b) review token    : {args.review_token.strip()}")
    print("  (c) release readiness: SSOT aligned / release notes / README / clean tree")
    # Every labelled check must also appear in this summary: a check that is
    # enforced but absent from the summary reads as "no such check" to anyone
    # going by the output, which is how a present gate can be mistaken for a
    # missing one.
    print("  (d) change declaration: Meta-Sync trailer present on governed changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
