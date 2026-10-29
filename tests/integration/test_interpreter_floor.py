# -*- coding: utf-8 -*-
"""The declared interpreter floor is 3.9; nothing newer than that may ship.

``requires-python`` says ``>=3.9``, while the default CI runs 3.13 and the cross-OS
matrix also runs 3.13 apart from one job. So a construct that 3.9 rejects passes
everywhere until the oldest job runs -- and that job exists to catch platform
differences, not language-level ones a parser can see.

Two constructs fail on 3.9, and both fail at *import* time rather than at call time:

* ``X | Y`` in an annotation. PEP 604 arrived in 3.10. Without
  ``from __future__ import annotations`` the expression is evaluated when the
  function is defined, so the module cannot be imported at all.
* ``match`` statements. 3.10 syntax; the module does not even parse.

PEP 585 (``list[int]``, ``dict[str, int]``) is deliberately **not** flagged: that
landed in 3.9, and flagging it would fire on correct code. Getting these two mixed up
is how a check acquires a reputation for crying wolf.

Reading source rather than importing means the check runs on any interpreter and
fails in the same place a 3.9 job would, without waiting for that job to be queued.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCANNED = ("cullinan", "examples", "scripts", "tests")

#: ``ast.Match`` does not exist before 3.10, so it is looked up rather than named.
_MATCH = getattr(ast, "Match", None)


def _has_future_annotations(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if any(alias.name == "annotations" for alias in node.names):
                return True
    return False


def _annotations(tree: ast.Module):
    """Yield the annotation expressions of a module.

    Only these are evaluated eagerly. A ``X | Y`` used in an ordinary expression is a
    different thing -- ``dict | dict`` exists since 3.9 -- so scanning the whole tree
    would report code that runs fine.
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
            for argument in arguments:
                if argument.annotation is not None:
                    yield argument.annotation
            for variadic in (node.args.vararg, node.args.kwarg):
                if variadic is not None and variadic.annotation is not None:
                    yield variadic.annotation
            if node.returns is not None:
                yield node.returns
        elif isinstance(node, ast.AnnAssign):
            yield node.annotation


def _sources():
    for scope in SCANNED:
        directory = ROOT / scope
        if directory.is_dir():
            yield from sorted(directory.rglob("*.py"))


def test_no_pep604_union_in_an_annotation_without_the_future_import():
    """``int | None`` in a signature needs 3.10 unless annotations stay unevaluated."""
    offenders = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _has_future_annotations(tree):
            continue
        lines = sorted(
            {
                node.lineno
                for annotation in _annotations(tree)
                for node in ast.walk(annotation)
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
            }
        )
        if lines:
            offenders.append(f"{path.relative_to(ROOT)}:{lines}")

    assert not offenders, (
        "these annotations use PEP 604 unions, which 3.9 rejects at import time; "
        "either add 'from __future__ import annotations' or use typing.Optional:\n  "
        + "\n  ".join(offenders)
    )


def test_no_match_statement():
    """A ``match`` statement cannot be parsed by 3.9 at all."""
    if _MATCH is None:  # pragma: no cover - only on an interpreter too old to have it
        pytest.skip("this interpreter has no match statement, so nothing here can use one")

    offenders = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        lines = sorted(node.lineno for node in ast.walk(tree) if isinstance(node, _MATCH))
        if lines:
            offenders.append(f"{path.relative_to(ROOT)}:{lines}")

    assert not offenders, (
        "a match statement is 3.10 syntax and 3.9 cannot parse these files:\n  "
        + "\n  ".join(offenders)
    )


def test_the_scan_actually_reaches_the_examples():
    """A check that scans nothing passes for the wrong reason."""
    relative = [path.relative_to(ROOT) for path in _sources()]
    scanned = {path.parts[0] for path in relative}

    assert scanned == set(SCANNED), f"scanned {sorted(scanned)}, expected {sorted(SCANNED)}"
    assert any(path.parts[0] == "examples" and path.name == "root.py" for path in relative), (
        "the example this check was written for is not in the scan"
    )
