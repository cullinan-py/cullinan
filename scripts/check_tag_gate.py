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
  (e) docs channel reconciliation (locally verifiable part):
      - every docs page that advertises a current version advertises the SSOT
        one, and the set of pages carrying a banner is exactly
        EXPECTED_BANNER_PAGES (a count would tolerate a page losing its banner
        while another still had one).
  (f) credential scope (locally verifiable part):
      - the review and sync credentials carry `#tree=<40 hex>` and it equals the tree
        of the commit being tagged. The sign-off credential is exempt: it binds to its
        evidence bundle, not to the tree.
      LIMIT: this compares format and scope, not authenticity. A string that is shaped
      like a credential and names the right tree passes whether or not it was ever
      issued; that is what the issuing process is for, and a gate that claimed
      otherwise would be lying about what it checked. Sign-off is exempt because its
      credential carries an evidence-bundle hash, not a tree -- requiring a tree there
      would reject every valid sign-off.

  (g) test evidence (locally verifiable part):
      - a JUnit report from a full `pytest tests` run on this tree, judged by
        scripts/check_junit.py. A report the gate cannot read, one holding zero tests,
        one holding failures or errors, and one where everything was skipped are all
        FAIL -- "no evidence" and "evidence of nothing" are not weaker kinds of pass.
      LIMIT: it reads the report it is given. It cannot tell whether that report came
      from this commit; that guarantee comes from running the suite here rather than
      trusting a status, which is what the publish workflow now does.

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

#: Banner shapes in use, both near the top of a page: the docs home pages write
#: ``**Current version: X**`` / ``**当前版本：X**``, the guide pages write
#: ``**Version**: X`` / ``**版本**：X``.
#:
#: The colon is matched as ``[：:]`` rather than hard-coded, because the width is
#: not a property of the language: most Chinese pages use the full-width one, but
#: ``docs/zh/quick_reference_di.md`` uses the ASCII one. An English-only pattern
#: covers half the tree and -- worse -- reports green on the half it never read.
#:
#: Two shapes are *excluded* rather than compared, because they make a different
#: claim about the same words:
#:
#: * a ``v`` prefix (``**版本**：v0.90``) marks applicability -- "this page
#:   describes how v0.90 behaves" -- which is a historical statement that must not
#:   be dragged to the current release;
#: * a ``+`` suffix (``**Version**: 0.90a5+``) gives the *oldest* release the
#:   feature set applies to.
#:
#: Both are filtered in code, not with pattern-level lookarounds: a ``(?!\+)``
#: makes the greedy group backtrack and capture ``0.90a`` out of ``0.90a5+``,
#: which then looks like a legitimate (if odd) version. Only a bare version
#: asserts "this is the version you are reading".
DOC_BANNER_PATTERNS = (
    re.compile(r"\*\*Current version:\s*(v?[0-9][0-9A-Za-z._-]*)\*\*"),
    re.compile(r"\*\*当前版本[：:]\s*(v?[0-9][0-9A-Za-z._-]*)\*\*"),
    re.compile(r"\*\*Version\*\*:\s*(v?[0-9][0-9A-Za-z._-]*)"),
    re.compile(r"\*\*版本\*\*[：:]\s*(v?[0-9][0-9A-Za-z._-]*)"),
)

#: Pages that carry a version banner. Enumerated rather than counted: with a
#: count, deleting the banner from some pages still passes as long as enough
#: remain somewhere, which is the failure this is meant to catch. A page that
#: starts or stops carrying one has to be listed here, and that edit is the
#: reminder that the page belongs to the published version surface.
#:
#: Four other pages under `docs/` also contain a version literal and are
#: deliberately absent: `framework_semantics.md` (and its `zh/` pair) names the
#: release that introduced a rule (`v0.96a2`, `v0.96a5`), and
#: `migration_guide_v2.md` (and its pair) is organised by the release each
#: behaviour changed in. Those literals are history, not a claim about the
#: current release, so requiring them to match the SSOT would make them false.
#: Checked when this note was written: `grep -rl '0\.96a9' docs/` returns exactly
#: the ten keys below, and every remaining literal in `docs/` is of that
#: historical kind -- the distinction is written down here so that the next
#: reader does not have to re-derive it, or mistake the gap for an oversight.
EXPECTED_BANNER_PAGES = {
    "README.md": 1,
    "zh/README.md": 1,
    "architecture.md": 1,
    "zh/architecture.md": 1,
    "dependency_injection_guide.md": 1,
    "zh/dependency_injection_guide.md": 1,
    # These two carry a banner in two places, and both are published claims.
    "extension_development_guide.md": 2,
    "zh/extension_development_guide.md": 2,
    "quick_reference_di.md": 1,
    "zh/quick_reference_di.md": 1,
}

#: A credential binds itself to the tree it was issued for by carrying
#: ``#tree=<40 hex>``. Binding to the tree rather than the commit is deliberate:
#: a merge commit and the commit it merges can share one tree, so a commit-bound
#: token would reject a valid approval.
TREE_BINDING = re.compile(r"#tree=([0-9a-f]{40})")


def read_ssot_version():
    text = (ROOT / "cullinan" / "_version.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        return None
    return match.group(1)


def find_doc_banners(docs_dir):
    """``(relative path, advertised version)`` for every page banner found.

    A banner immediately followed by ``+`` states the oldest release its content
    applies to, not the current one, so it is skipped here rather than in the
    pattern (see DOC_BANNER_PATTERNS).
    """
    found = []
    for page in sorted(docs_dir.rglob("*.md")):
        text = page.read_text(encoding="utf-8", errors="replace")
        for pattern in DOC_BANNER_PATTERNS:
            for match in pattern.finditer(text):
                version = match.group(1)
                # ``v`` prefix and ``+`` suffix are applicability claims, not
                # statements about the version being read -- see the note above.
                if version[:1] in ("v", "V"):
                    continue
                if text[match.end(1):match.end(1) + 1] == "+":
                    continue
                found.append((page.relative_to(docs_dir).as_posix(), version))
    return found


def banner_findings(banners, expected_version, expected_pages=None):
    """``(clean, detail)`` for a banner scan, comparing versions *and* pages.

    Two separate failures, deliberately reported apart: a page advertising the
    wrong version, and a page missing from (or added to) the expected set. The
    second one is why the set is enumerated -- a count would report "11 found"
    whether or not one of them was a duplicate on the same page.
    """
    pages = EXPECTED_BANNER_PAGES if expected_pages is None else expected_pages
    stale = [(page, version) for page, version in banners if version != expected_version]
    found: dict[str, int] = {}
    for page, _version in banners:
        found[page] = found.get(page, 0) + 1
    missing = sorted(page for page, count in pages.items() if found.get(page, 0) < count)
    unexpected = sorted(set(found) - set(pages))
    if missing:
        return False, "missing banner on " + ", ".join(missing)
    if unexpected:
        return False, "banner on an unlisted page: " + ", ".join(unexpected)
    if stale:
        return False, "; ".join(f"{page} says {version}" for page, version in stale)
    return True, "aligned"


def choose_reference_tree(tag_tree: str | None, head_tree: str, version: str | None) -> tuple[str, str]:
    """Return the tree the credentials must name, and what that tree is.

    Before the tag exists, the tree being tagged *is* ``HEAD``, so ``HEAD`` is the
    right answer and the gate is normally run at exactly that moment.

    After the tag exists it is not: the tag is the fixed point, ``HEAD`` moves. Reading
    ``HEAD`` then makes this check fail for every later commit, against credentials that
    are perfectly correct -- a structural false negative that fires on its own the first
    time anybody runs the gate after tagging. The check's own name and its summary line
    both say "the tagged tree", so the value has to come from the tag when there is one.
    """
    if tag_tree:
        return tag_tree, f"tag v{version}"
    return head_tree, "HEAD (no tag yet)"


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
    parser.add_argument("--junit", required=True,
                        help="(g) JUnit XML from a full `pytest tests` run on the tree "
                             "being tagged (`--junit-xml=<path>`)")
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

    # (e) docs version banners. The docs pages carry the version as a *copy* --
    # they are not generated from the SSOT, so nothing made them move with it,
    # and until now nothing compared them either. This is that comparison: every
    # banner found must name the SSOT version, and the set of pages carrying one
    # must be exactly the expected set, so that a page cannot quietly lose its
    # banner while the check still counts enough of them elsewhere.
    banners = find_doc_banners(ROOT / "docs")
    banners_clean, detail = banner_findings(banners, expected)
    # The label stays a literal: the summary/registration correspondence test
    # compares the two sets of labels, and a label carrying an interpolated value
    # would change shape from run to run and make that comparison meaningless.
    check(
        "(e) docs version banners aligned",
        banners_clean,
        f"{len(banners)} found on {len({page for page, _v in banners})} page(s) -- {detail}",
    )

    # (f) credential -> tree binding. Until now (b) and the sync credential were
    # only tested for being non-empty, so a token issued for an earlier tree was
    # accepted just as readily as one issued for the tree being tagged -- the gate
    # said PASS while the approval pointed somewhere else.
    #
    # The binding is to the *tree*, not the commit: `d69e66d` and the merge commit
    # `86fc32d` are different commits with the same tree, so a commit-bound token
    # would reject a perfectly valid approval. Sign-off is exempt on purpose --
    # that credential carries a hash of the evidence bundle, not of the tree.
    head_tree = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    # A tag is a fixed point; HEAD is not. Prefer the tag once it exists.
    tag_tree = None
    if expected:
        probe = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--verify", "--quiet",
             f"refs/tags/v{expected}^{{commit}}^{{tree}}"],
            capture_output=True, text=True,
        )
        if probe.returncode == 0:
            tag_tree = probe.stdout.strip()
    reference_tree, reference_label = choose_reference_tree(tag_tree, head_tree, expected)
    unbound = []
    mismatched = []
    for slot, token in (("(b) review", args.review_token), ("sync", args.sync_token)):
        match = TREE_BINDING.search(token)
        if match is None:
            unbound.append(slot)
        elif match.group(1) != reference_tree:
            mismatched.append(f"{slot} bound to {match.group(1)}")
    if unbound:
        detail = (
            f"no #tree=<40-hex> on: {', '.join(unbound)} -- reissue the token in the "
            f"bound form ('...#tree={reference_tree}')"
        )
    elif mismatched:
        detail = (
            f"bound to a different tree than {reference_label} ({reference_tree}): "
            + "; ".join(mismatched)
        )
    else:
        detail = f"both bound to {reference_label} ({reference_tree})"
    check(
        "(f) review and sync credentials bound to the tagged tree",
        not unbound and not mismatched,
        detail,
    )

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

    # (g) test evidence. Until this existed, every labelled check above read tokens,
    # banners and files -- not one of them asked whether the code had been tested. A
    # tree with a failing test in it would have passed all of (a) through (f).
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import check_junit

        code, detail = check_junit.evaluate(Path(args.junit))
        check("(g) full suite passed on this tree", code == 0, detail)
    except Exception as exc:  # noqa: BLE001 - a gate must fail, not crash
        check("(g) full suite passed on this tree", False, repr(exc))

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
    print("  (e) docs version banners: every banner names the SSOT version")
    print("  (f) credential scope: review + sync tokens bound to the tagged tree")
    print("      (format and scope only -- authenticity comes from the issuing process)")
    print("  (g) test evidence: a full pytest run on this tree, reported green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
