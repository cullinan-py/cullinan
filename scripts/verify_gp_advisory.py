#!/usr/bin/env python3
"""Advisory candidate finder for two documentation / surface review criteria.

This script is advisory only. It prints candidates for a human to judge and
never decides PASS or FAIL: its exit code is 0 whenever it runs. The two
criteria it supports both carry a semantic component that no machine check can
decide here:

* whether the replacement named by a deprecation's ``alternative`` actually
  exists and is callable - ``alternative`` is free prose, so it cannot be
  resolved automatically;
* whether some surface "accepts input but does not act on it" - that is a
  behavioural property of running code, not of its text.

Because of that, the finder reports candidates instead of asserting a verdict,
and nothing here is execution-verified. Read the output while preparing a
release; do not wire it into a gate and do not treat a short list as proof.

Usage:
  python scripts/verify_gp_advisory.py [--repo <path>]
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

ADVISORY_BANNER = (
    "advisory candidates only - not machine-checked, not a gate, "
    "no PASS/FAIL is produced"
)

# Phrases that mark a docstring as describing a surface which is still
# accepted but no longer does what its name suggests (a "silent" surface).
# This is a deliberately narrow, non-exhaustive hint set: it points a reviewer
# at candidates to read, it does not decide anything.
SILENT_FACE_PHRASES = (
    "is ignored",
    "are ignored",
    "no longer",
    "no-op",
    "is not supported",
    "accepted but",
    "does nothing",
)


def _iter_python_files(root: Path) -> Iterator[Path]:
    package = root / "cullinan"
    if not package.is_dir():
        return
    for path in sorted(package.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _decorator_is_deprecated(decorator: ast.AST) -> bool:
    node = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(node, ast.Name):
        return node.id == "deprecated"
    if isinstance(node, ast.Attribute):
        return node.attr == "deprecated"
    return False


def iter_alternative_targets(root: Path) -> List[Tuple[str, int, str]]:
    """Return ``(relative_path, line, alternative)`` for each ``alternative=``.

    The scan face is "APIs that declare a replacement" - decorator call sites
    whose name is ``deprecated`` and which pass an ``alternative`` keyword. A
    free-form string scan of the whole package is deliberately not used: it
    cannot tell a declaration from a mention in prose.
    """
    found: List[Tuple[str, int, str]] = []
    for path in _iter_python_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            tree = _parse(path)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for decorator in node.decorator_list:
                if not _decorator_is_deprecated(decorator):
                    continue
                if not isinstance(decorator, ast.Call):
                    continue
                for keyword in decorator.keywords:
                    if keyword.arg != "alternative":
                        continue
                    if isinstance(keyword.value, ast.Constant) and isinstance(
                        keyword.value.value, str
                    ):
                        found.append(
                            (relative, decorator.lineno, keyword.value.value)
                        )
    return found


def iter_silent_face_candidates(root: Path) -> List[Tuple[str, int, str, str]]:
    """Return ``(relative_path, line, name, phrase)`` candidate "silent" sites.

    A candidate is a function / method whose docstring says the surface is
    accepted but inert (matched against ``SILENT_FACE_PHRASES``). Presence on
    this list is a prompt to read the code, not a finding: the phrase may
    describe intended behaviour, and the list is not exhaustive.
    """
    found: List[Tuple[str, int, str, str]] = []
    for path in _iter_python_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            tree = _parse(path)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            docstring = ast.get_docstring(node, clean=False) or ""
            lowered = docstring.lower()
            for phrase in SILENT_FACE_PHRASES:
                if phrase in lowered:
                    found.append((relative, node.lineno, node.name, phrase))
                    break
    return found


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Advisory candidate finder (prints candidates; never a verdict)"
    )
    parser.add_argument("--repo", default=".", help="repository root (default: .)")
    args = parser.parse_args(argv)

    root = Path(args.repo).resolve()
    print(f"== {ADVISORY_BANNER} ==")

    print()
    print("-- declared deprecation replacements (verify each target exists) --")
    targets = iter_alternative_targets(root)
    if not targets:
        print("  (none found)")
    for relative, line, alternative in targets:
        print(f"  {relative}:{line}: {alternative}")

    print()
    print("-- candidate surfaces accepted but possibly inert (read each) --")
    candidates = iter_silent_face_candidates(root)
    if not candidates:
        print("  (none found)")
    for relative, line, name, phrase in candidates:
        print(f'  {relative}:{line}: {name}() -- docstring says "{phrase}"')

    print()
    print(
        f"total: {len(targets)} replacement declaration(s), "
        f"{len(candidates)} silent-face candidate(s); "
        f"neither count is a verdict"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
