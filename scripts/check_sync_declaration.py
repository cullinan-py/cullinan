#!/usr/bin/env python3
"""Meta-Sync declaration gate for release-process and configuration changes.

Background
----------
A handful of repository paths carry release-process or team-convention weight:
the CI workflow definitions, the release tag gate, the release verification
helpers, the contributor / security / license / documentation-site config, the
version single source of truth, and the release-critical keys of
``pyproject.toml``. When a commit touches any of them the change is expected to
be deliberate, so its commit message must carry a machine-readable declaration
in a trailer::

    Meta-Sync: required id=<opaque-token>
    Meta-Sync: n-a reason=<free text, at least 8 characters>

This script verifies *only* that such a declaration is present and well formed
when a governed path is touched. The ``<token>`` is opaque: it is never resolved
or interpreted here. Whether the declaration is substantively accurate is a
human judgement and is deliberately out of scope for this check.

The trailer key is neutral on purpose and carries no product-internal meaning.
Never put free-form internal references inside the trailer -- commit messages
become part of the public history.

Usage
-----
    python scripts/check_sync_declaration.py --repo . --range <base>..<head>
    python scripts/check_sync_declaration.py --repo . --commit <sha>
    python scripts/check_sync_declaration.py --repo . --worktree
    python scripts/check_sync_declaration.py --self-test

Exit code: 0 = every inspected commit is GREEN, 1 = at least one RED.
"""
from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

TRAILER_KEY = "Meta-Sync"

# ---------------------------------------------------------------------------
# Governed surface (file level)
#
# Definition of the surface is intentionally data, not logic: extending it
# changes what the gate enforces and must be reviewed as such.
# ---------------------------------------------------------------------------
GOVERNED_GLOBS: Tuple[Tuple[str, str], ...] = (
    (".github/workflows/*.yml", "CI workflow definition"),
    (".github/workflows/*.yaml", "CI workflow definition"),
    ("scripts/check_tag_gate.py", "release tag gate"),
    ("scripts/verify_*.py", "release verification helper"),
    ("CONTRIBUTING.md", "contributor / PR process"),
    ("SECURITY.md", "disclosure process"),
    ("LICENSE", "license and distribution"),
    ("mkdocs.yml", "documentation site configuration"),
    ("cullinan/_version.py", "version single source of truth"),
)

# ``pyproject.toml`` is *not* listed above: it holds both release-critical keys
# and ordinary tooling configuration, so it is triggered per changed key instead
# of per file (see ``pyproject_trigger``).
PYPROJECT = "pyproject.toml"

_BUILD_SYSTEM = "[build-system]"
_PROJECT_PREFIX = "[project"
_DYNAMIC_SECTION = "[tool.setuptools.dynamic]"
_NON_TRIGGER_SECTIONS = (
    "[tool.setuptools.package-data]",
    "[tool.setuptools.packages.find]",
)

_REQUIRED_ID = re.compile(r"^required\s+id=([A-Za-z0-9][A-Za-z0-9._-]{2,63})$")
_NA_REASON = re.compile(r"^n-a\s+reason=(.+)$", re.DOTALL)


# ---------------------------------------------------------------------------
# File-level surface matching
# ---------------------------------------------------------------------------
def _glob_to_re(pattern: str) -> "re.Pattern[str]":
    """Compile a restricted glob (``*`` only, never crossing ``/``)."""
    pieces = []
    for ch in pattern:
        pieces.append("[^/]*" if ch == "*" else re.escape(ch))
    return re.compile("^" + "".join(pieces) + "$")


_GOVERNED_RE: Tuple[Tuple["re.Pattern[str]", str, str], ...] = tuple(
    (_glob_to_re(glob), glob, why) for glob, why in GOVERNED_GLOBS
)


def normalize_path(raw: str) -> str:
    """Normalise a repo-relative path. Only an exact leading ``./`` is stripped."""
    path = raw.replace("\\", "/")
    if path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


def governed_reason(path: str) -> Optional[str]:
    """Return why ``path`` is governed, or ``None`` (``pyproject.toml`` excluded)."""
    normalized = normalize_path(path)
    for rx, glob, why in _GOVERNED_RE:
        if rx.match(normalized):
            return f"{glob} -- {why}"
    return None


def governed_hits(paths: Iterable[str]) -> List[Tuple[str, str]]:
    """File-level hits only (``pyproject.toml`` needs content -- see below)."""
    hits: List[Tuple[str, str]] = []
    for raw in paths:
        if not raw:
            continue
        reason = governed_reason(raw)
        if reason:
            hits.append((normalize_path(raw), reason))
    return hits


# ---------------------------------------------------------------------------
# ``pyproject.toml``: triggered per changed key, not per file
#
# A change triggers when at least one *substantive* changed line falls in:
#   * ``[build-system]``                      -- build backend / release machinery
#   * any ``[project...]`` section            -- identity, version, distribution metadata
#   * ``[tool.setuptools.dynamic]``           -- version source
#   * any *unknown non-tool* section          -- fail-safe: unknown means trigger
# Comment and blank lines never trigger on their own.
# Changes limited to ``[tool.setuptools.package-data]``,
# ``[tool.setuptools.packages.find]`` or any other ``[tool.*]`` table do not
# trigger: they configure package contents / tooling, not release semantics.
# ---------------------------------------------------------------------------
def _section_per_line(lines: Sequence[str]) -> List[str]:
    """Map each line to its enclosing TOML table ('' for top level)."""
    current = ""
    sections: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped
        sections.append(current)
    return sections


def _classify(line: str, section: str) -> Optional[str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if section == _BUILD_SYSTEM:
        return "T1 [build-system]"
    if section.startswith(_PROJECT_PREFIX):
        return f"T2 {section}"
    if section == _DYNAMIC_SECTION:
        return "T3 [tool.setuptools.dynamic]"
    if section in _NON_TRIGGER_SECTIONS:
        return None
    if section.startswith("[tool."):
        return None
    return f"T4 fail-safe (unknown non-tool section `{section or 'top level'}`)"


def pyproject_trigger(
    before_lines: Sequence[str], after_lines: Sequence[str]
) -> Tuple[bool, str]:
    """Pure predicate: does this ``pyproject.toml`` change trigger? (trigger, why)."""
    before = list(before_lines or [])
    after = list(after_lines or [])
    before_sections = _section_per_line(before)
    after_sections = _section_per_line(after)
    matcher = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
    reasons: List[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        for idx in range(i1, i2):
            found = _classify(before[idx], before_sections[idx])
            if found:
                reasons.append(found)
        for idx in range(j1, j2):
            found = _classify(after[idx], after_sections[idx])
            if found:
                reasons.append(found)
    if not reasons:
        return False, "no released-key change (content / tooling section only)"
    return True, "; ".join(dict.fromkeys(reasons))


# ---------------------------------------------------------------------------
# Declaration parsing (trailing occurrence wins)
# ---------------------------------------------------------------------------
def parse_declaration(message: str) -> Tuple[str, str]:
    """Return ``(state, detail)`` with state in {absent, required, n-a, malformed}."""
    trailer_value: Optional[str] = None
    for line in message.splitlines():
        match = re.match(r"^\s*" + re.escape(TRAILER_KEY) + r"\s*:\s*(.*)$", line)
        if match:
            trailer_value = match.group(1).strip()
    if trailer_value is None:
        return "absent", ""
    if trailer_value.startswith("required"):
        found = _REQUIRED_ID.match(trailer_value)
        if found:
            return "required", found.group(1)
        return (
            "malformed",
            f"required form is invalid: {trailer_value!r} (expected `required id=<token>`)",
        )
    if trailer_value.startswith("n-a"):
        found = _NA_REASON.match(trailer_value)
        if found and len(found.group(1).strip()) >= 8:
            return "n-a", found.group(1).strip()
        return "malformed", f"n-a reason missing or too short (>= 8 chars): {trailer_value!r}"
    return "malformed", f"unknown value: {trailer_value!r} (expected `required` or `n-a`)"


# ---------------------------------------------------------------------------
# Verdict (pure)
# ---------------------------------------------------------------------------
def judge(hits: Sequence[Tuple[str, str]], message: str) -> Tuple[str, str]:
    """Return ``("GREEN"|"RED", detail)`` for a set of governed hits + message."""
    state, detail = parse_declaration(message)
    if not hits:
        return "GREEN", "not-triggered (no governed path touched)"
    if state in ("required", "n-a"):
        return "GREEN", f"declared ({state}: {detail})"
    touched = "; ".join(path for path, _ in hits)
    if state == "malformed":
        return "RED", f"malformed ({detail}); touched: {touched}"
    return (
        "RED",
        f"missing (governed path touched with no {TRAILER_KEY} trailer); touched: {touched}",
    )


# ---------------------------------------------------------------------------
# Git access
# ---------------------------------------------------------------------------
def _git(args: Sequence[str], repo: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(stderr or f"git {' '.join(args)} failed")
    return proc.stdout.decode("utf-8", "replace")


def _blob_lines(repo: str, rev: Optional[str], path: str) -> List[str]:
    """Lines of ``path`` at ``rev``; ``rev=None`` reads the working tree."""
    if rev is None:
        absolute = Path(repo) / path
        if not absolute.is_file():
            return []
        return absolute.read_text(encoding="utf-8", errors="replace").splitlines()
    try:
        out = _git(["show", f"{rev}:{path}"], repo)
    except RuntimeError:
        return []
    return out.splitlines()


def commit_paths(repo: str, rev: str) -> List[str]:
    out = _git(["show", "--pretty=format:", "--name-only", "-z", rev], repo)
    return [p for p in out.split("\0") if p]


def commit_message(repo: str, rev: str) -> str:
    return _git(["log", "-1", "--format=%B", rev], repo)


def commit_subject(repo: str, rev: str) -> str:
    return _git(["log", "-1", "--format=%h %s", rev], repo).strip()


def range_shas(repo: str, base: str, head: str) -> List[str]:
    out = _git(["rev-list", "--reverse", f"{base}..{head}"], repo)
    return [sha for sha in out.split() if sha]


def worktree_paths(repo: str) -> List[str]:
    """Changed paths in the working tree, **including untracked** files."""
    out = _git(["status", "--porcelain", "-z", "-uall"], repo)
    parts = out.split("\0")
    paths: List[str] = []
    index = 0
    while index < len(parts):
        record = parts[index]
        if not record:
            index += 1
            continue
        status, path = record[:2], record[3:]
        if status[0:1] in ("R", "C"):
            index += 1  # rename/copy: the next record is the source path
        paths.append(path)
        index += 1
    return paths


def hits_for_commit(repo: str, rev: str) -> List[Tuple[str, str]]:
    """Governed hits introduced by ``rev`` (``pyproject.toml`` via key predicate)."""
    return _hits_for(repo, commit_paths(repo, rev), f"{rev}^", rev)


def hits_for_worktree(repo: str) -> List[Tuple[str, str]]:
    return _hits_for(repo, worktree_paths(repo), "HEAD", None)


def _hits_for(
    repo: str, paths: Sequence[str], before_ref: Optional[str], after_ref: Optional[str]
) -> List[Tuple[str, str]]:
    hits: List[Tuple[str, str]] = []
    for raw in paths:
        if not raw:
            continue
        path = normalize_path(raw)
        reason = governed_reason(path)
        if reason:
            hits.append((path, reason))
            continue
        if path == PYPROJECT:
            before = _blob_lines(repo, before_ref, path)
            after = _blob_lines(repo, after_ref, path)
            triggered, why = pyproject_trigger(before, after)
            if triggered:
                hits.append((path, f"{PYPROJECT} -- {why}"))
    return hits


# ---------------------------------------------------------------------------
# Structured evaluation (also used by the release tag gate backstop)
# ---------------------------------------------------------------------------
def evaluate_commit(repo: str, rev: str) -> Tuple[str, str, str]:
    """Return ``(verdict, label, detail)`` for one commit."""
    hits = hits_for_commit(repo, rev)
    verdict, detail = judge(hits, commit_message(repo, rev))
    return verdict, commit_subject(repo, rev), detail


def evaluate_range(repo: str, base: str, head: str) -> List[Tuple[str, str, str]]:
    """Return ``[(verdict, label, detail), ...]`` for ``base..head`` (oldest first)."""
    results: List[Tuple[str, str, str]] = []
    for sha in range_shas(repo, base, head):
        results.append(evaluate_commit(repo, sha))
    return results


# ---------------------------------------------------------------------------
# Self test (red/green contrast -- guards against always-red / always-green)
# ---------------------------------------------------------------------------
_PATH_CASES: Tuple[Tuple[str, Sequence[str], str, str], ...] = (
    ("S1 governed + valid required",
     [".github/workflows/ci.yml"], "ci: x\n\nMeta-Sync: required id=abc0001\n", "GREEN"),
    ("S2 governed + valid n-a",
     ["CONTRIBUTING.md"], "docs: x\n\nMeta-Sync: n-a reason=wording only, no policy change\n", "GREEN"),
    ("S3 governed + no declaration",
     ["scripts/check_tag_gate.py"], "fix: x\n", "RED"),
    ("S4 governed + empty n-a reason",
     ["SECURITY.md"], "docs: x\n\nMeta-Sync: n-a reason=\n", "RED"),
    ("S5 governed + required without id",
     ["LICENSE"], "chore: x\n\nMeta-Sync: required\n", "RED"),
    ("S6 governed + unknown value",
     ["mkdocs.yml"], "docs: x\n\nMeta-Sync: maybe\n", "RED"),
    ("S7 non-governed + no declaration",
     ["cullinan/core/model.py"], "feat: x\n", "GREEN"),
    ("S8 non-governed + declaration",
     ["docs/guide.md"], "docs: x\n\nMeta-Sync: required id=abc0002\n", "GREEN"),
    ("S9 version SSOT + declaration",
     ["cullinan/_version.py"], "release: x\n\nMeta-Sync: required id=abc0003\n", "GREEN"),
    ("S10 declaration in body, not last line",
     ["SECURITY.md"], "docs: x\n\nMeta-Sync: required id=abc0004\n\nmore body\n", "GREEN"),
)

_PP_PKGDATA_BEFORE = (
    "[project]",
    'name = "cullinan"',
    "",
    "[tool.setuptools.package-data]",
    'cullinan = ["py.typed"]',
)
_PP_PKGDATA_AFTER = (
    "[project]",
    'name = "cullinan"',
    "",
    "[tool.setuptools.package-data]",
    'cullinan = ["py.typed", "_contracts.json"]',
)
_PP_DYNAMIC_BEFORE = ("[project]", 'name = "cullinan"', 'dynamic = ["version"]')
_PP_DYNAMIC_AFTER = ("[project]", 'name = "cullinan"', "dynamic = []")
_PP_BUILD_BEFORE = ("[build-system]", 'requires = ["setuptools>=61"]')
_PP_BUILD_AFTER = ("[build-system]", 'requires = ["setuptools>=61", "wheel"]')
_PP_UNKNOWN_BEFORE = ("[project]", 'name = "cullinan"')
_PP_UNKNOWN_AFTER = ("[project]", 'name = "cullinan"', "", "[dependency-groups]", 'dev = ["ruff"]')
_PP_TOOL_BEFORE = ("[tool.ruff]", "line-length = 100")
_PP_TOOL_AFTER = ("[tool.ruff]", "line-length = 110")
_PP_COMMENT_BEFORE = ("# top comment", "[project]", 'name = "cullinan"')
_PP_COMMENT_AFTER = ("# changed comment", "[project]", 'name = "cullinan"')

_PYPROJECT_CASES: Tuple[Tuple[str, Sequence[str], Sequence[str], bool], ...] = (
    ("P1 pyproject: package-data increment only => no trigger",
     _PP_PKGDATA_BEFORE, _PP_PKGDATA_AFTER, False),
    ("P2 pyproject: [project] dynamic change => trigger",
     _PP_DYNAMIC_BEFORE, _PP_DYNAMIC_AFTER, True),
    ("P3 pyproject: [build-system] change => trigger",
     _PP_BUILD_BEFORE, _PP_BUILD_AFTER, True),
    ("P4 pyproject: unknown non-tool section => trigger (fail-safe)",
     _PP_UNKNOWN_BEFORE, _PP_UNKNOWN_AFTER, True),
    ("P5 pyproject: [tool.ruff] change => no trigger",
     _PP_TOOL_BEFORE, _PP_TOOL_AFTER, False),
    ("P6 pyproject: comment-only change => no trigger",
     _PP_COMMENT_BEFORE, _PP_COMMENT_AFTER, False),
)


def self_test() -> int:
    print("== Meta-Sync declaration gate -- self test (red/green contrast) ==")
    ok = True
    for name, paths, message, want in _PATH_CASES:
        got, detail = judge(governed_hits(list(paths)), message)
        mark = "ok " if got == want else "FAIL"
        ok = ok and got == want
        print(f"  [{mark}] {name:<46} expected {want:<5} got {got:<5} | {detail[:64]}")
    print("  -- pyproject.toml (per-key trigger) --")
    for name, before, after, want in _PYPROJECT_CASES:
        triggered, why = pyproject_trigger(list(before), list(after))
        hits = [(PYPROJECT, why)] if triggered else []
        got, _ = judge(hits, "chore: x\n")
        expected = "RED" if want else "GREEN"
        mark = "ok " if got == expected else "FAIL"
        ok = ok and got == expected
        print(
            f"  [{mark}] {name:<46} expected trigger={str(want):<5} "
            f"got trigger={str(triggered):<5} | {why[:48]}"
        )
    print("== result: " + ("all ok (not always-red, not always-green)" if ok else "FAILED") + " ==")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Meta-Sync declaration gate (presence/shape only)."
    )
    parser.add_argument("--repo", help="path to the repository to inspect")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--range", dest="commit_range", help="commit range base..head")
    group.add_argument("--commit", help="single commit sha")
    group.add_argument("--worktree", action="store_true", help="working tree (incl. untracked)")
    parser.add_argument("--self-test", action="store_true", help="run the built-in red/green cases")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    if not args.repo or not (args.commit_range or args.commit or args.worktree):
        parser.error("need --repo plus one of --range / --commit / --worktree (or --self-test)")

    repo = args.repo
    if args.commit_range:
        base, _, head = args.commit_range.partition("..")
        results = evaluate_range(repo, base, head)
        if not results:
            print("GREEN not-triggered (no commits in range)")
            return 0
        worst = 0
        for verdict, label, detail in results:
            print(f"[{verdict:<5}] {label}\n         {detail}")
            if verdict == "RED":
                worst = 1
        return worst

    if args.commit:
        verdict, label, detail = evaluate_commit(repo, args.commit)
        print(f"[{verdict}] {label}\n        {detail}")
        return 0 if verdict == "GREEN" else 1

    hits = hits_for_worktree(repo)
    verdict, detail = judge(hits, "")
    count = len(worktree_paths(repo))
    print(f"[{verdict}] worktree (incl. untracked, {count} change(s))\n        {detail}")
    return 0 if verdict == "GREEN" else 1


if __name__ == "__main__":
    sys.exit(main())
