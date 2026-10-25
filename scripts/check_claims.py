#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check that every positioning claim still has its evidence.

The page that describes this framework to the outside world claims exactly what
it can show. That is only true for as long as somebody checks, because the usual
decay is silent: a test file is renamed, the guide is rewritten, the page keeps
its sentence and stops being true.

This reads the machine-readable claim block out of the page and verifies, for
each claim:

* every evidence path exists;
* every ``path::Name`` symbol is actually declared in that file.

Usage::

    python scripts/check_claims.py
    python scripts/check_claims.py --self-test
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import List, Optional, Sequence

CLAIMS_BLOCK = re.compile(r"```json\n(.*?)```", re.DOTALL)


def extract_claims(text: str) -> dict:
    """Return the parsed claim block, or raise ValueError if it is not there."""
    matches = CLAIMS_BLOCK.findall(text)
    for block in matches:
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "claims" in payload:
            return payload
    raise ValueError("no JSON block containing a 'claims' key was found")


def declared_names(path: Path) -> set:
    """Return every class, function and module-level assignment name in a file."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    names: set = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def check(repo: Path, payload: dict) -> List[str]:
    """Return the problems with the claim set; an empty list means it holds."""
    problems: List[str] = []
    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims:
        return ["the claim block declares no claims, so the page is unverified prose"]

    seen_ids: List[str] = []
    for claim in claims:
        identifier = claim.get("id", "<no id>")
        seen_ids.append(identifier)

        if not claim.get("claim"):
            problems.append(f"{identifier}: has no claim text")

        evidence = claim.get("evidence") or []
        if not evidence:
            problems.append(f"{identifier}: has no evidence, so the claim is unsupported")
            continue

        for relative in evidence:
            if not (repo / relative).exists():
                problems.append(f"{identifier}: evidence path does not exist: {relative}")

        for reference in claim.get("symbols") or []:
            if "::" not in reference:
                problems.append(f"{identifier}: symbol reference must be 'path::Name', got {reference!r}")
                continue
            relative, name = reference.split("::", 1)
            target = repo / relative
            if not target.is_file():
                problems.append(f"{identifier}: symbol file does not exist: {relative}")
                continue
            try:
                names = declared_names(target)
            except SyntaxError as error:
                problems.append(f"{identifier}: {relative} could not be parsed ({error})")
                continue
            if name not in names:
                problems.append(f"{identifier}: {relative} does not declare {name!r}")

    duplicates = sorted({identifier for identifier in seen_ids if seen_ids.count(identifier) > 1})
    if duplicates:
        problems.append(f"claim ids used more than once: {', '.join(duplicates)}")

    return problems


def _self_test() -> int:
    import tempfile

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "code.py").write_text("class Present:\n    pass\n", encoding="utf-8")
        (repo / "doc.md").write_text("x", encoding="utf-8")

        healthy = {
            "claims": [
                {"id": "A", "claim": "something", "evidence": ["doc.md"], "symbols": ["code.py::Present"]}
            ]
        }
        if check(repo, healthy):
            failures += 1
            print(f"  FAIL healthy claim set reported: {check(repo, healthy)}")
        else:
            print("  ok   healthy claim set passes")

        cases = {
            "missing evidence path": {
                "claims": [{"id": "A", "claim": "c", "evidence": ["nope.md"], "symbols": []}]
            },
            "missing symbol": {
                "claims": [{"id": "A", "claim": "c", "evidence": ["doc.md"], "symbols": ["code.py::Absent"]}]
            },
            "no evidence at all": {"claims": [{"id": "A", "claim": "c", "evidence": [], "symbols": []}]},
            "empty claim set": {"claims": []},
            "duplicate id": {
                "claims": [
                    {"id": "A", "claim": "c", "evidence": ["doc.md"], "symbols": []},
                    {"id": "A", "claim": "d", "evidence": ["doc.md"], "symbols": []},
                ]
            },
        }
        for name, payload in cases.items():
            if check(repo, payload):
                print(f"  ok   {name} is reported")
            else:
                failures += 1
                print(f"  FAIL {name} was not reported")

    print("SELF-TEST PASSED" if not failures else f"SELF-TEST FAILED ({failures} case(s))")
    return 1 if failures else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".", help="repository root (default: current directory)")
    parser.add_argument("--page", default=None, help="page holding the claim block (default: docs/why-cullinan.md)")
    parser.add_argument("--self-test", action="store_true", help="run the built-in red/green cases and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    repo = Path(args.repo).resolve()
    page = Path(args.page) if args.page else repo / "docs" / "why-cullinan.md"
    if not page.is_file():
        print(f"CLAIMS CHECK FAIL: no positioning page at {page}")
        return 1

    try:
        payload = extract_claims(page.read_text(encoding="utf-8"))
    except ValueError as error:
        print(f"CLAIMS CHECK FAIL: {error}")
        return 1

    problems = check(repo, payload)
    if problems:
        print("CLAIMS CHECK FAIL")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    total = len(payload["claims"])
    print(f"CLAIMS CHECK PASS -- {total} claim(s), {total} with evidence, 0 unsupported")
    return 0


if __name__ == "__main__":
    sys.exit(main())
