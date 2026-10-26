# -*- coding: utf-8 -*-
"""Every configuration option has to be visible in at least one example.

The declaration trailer in a commit message records that someone *decided*
something about the four non-code aspects. It does not prove the example exists.
`max_request_body_bytes` shipped through a green pipeline with no example at all,
which is the gap this file closes: an option nobody can see demonstrated is an
option readers learn about from the changelog.

Options that predate this check are listed below and frozen rather than
ignored: the allowlist may shrink, never grow, and a new option that arrives
without an example fails immediately. It is down to one entry -- an option that
refuses to run cannot be demonstrated.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "cullinan" / "support" / "config.py"
EXAMPLES = REPO_ROOT / "examples"

# Options that predate this check. Adding a name here is a decision to ship an
# option with no example -- say so in the commit message rather than quietly
# extending the list.
# ``root_module`` is the only option that cannot be shown by a working call: the
# startup path it selected was removed, the parameter is kept for source
# compatibility, and passing it now warns and does nothing. Demonstrating it as
# if it worked would be worse than leaving it out, so it is named here with that
# reason instead of being quietly dropped.
UNCOVERED_BEFORE_THIS_CHECK = frozenset({"root_module"})


def _configure_options() -> list[str]:
    tree = ast.parse(CONFIG.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "configure"
    )
    args = function.args.posonlyargs + function.args.args + function.args.kwonlyargs
    return [arg.arg for arg in args if arg.arg not in {"cls", "self"}]


def _kwargs_from(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name == "configure":
                found.update(keyword.arg for keyword in node.keywords if keyword.arg)
    return found


def _covered_at_call_sites() -> set[str]:
    """Options actually passed to ``configure`` in an example.

    A substring test is not a test: appending a commented-out option name to any
    README used to satisfy it without a single call. This parses the calls --
    every ``.py`` in examples/, plus python fences in their READMEs -- and reads
    the keyword arguments, which is the only thing that shows an option in use.
    """
    covered: set[str] = set()
    for path in EXAMPLES.rglob("*.py"):
        covered |= _kwargs_from(ast.parse(path.read_text(encoding="utf-8", errors="ignore")))
    for path in EXAMPLES.rglob("*.md"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for block in re.findall(r"```python\n(.*?)```", text, re.S):
            try:
                covered |= _kwargs_from(ast.parse(block))
            except SyntaxError:
                continue
    return covered


def test_a_new_option_never_ships_without_an_example():
    covered = _covered_at_call_sites()
    missing = {option for option in _configure_options() if option not in covered}
    new_gaps = missing - UNCOVERED_BEFORE_THIS_CHECK
    assert not new_gaps, (
        "these configuration options are not shown in any example, so a reader "
        f"cannot see what they do: {sorted(new_gaps)}"
    )


def test_the_allowlist_only_shrinks():
    """A name here that has since been covered must be removed from the list."""
    covered = _covered_at_call_sites()
    now_covered = sorted(name for name in UNCOVERED_BEFORE_THIS_CHECK if name in covered)
    assert not now_covered, (
        "these options are covered by an example now, so they should not stay on the "
        f"uncovered list: {now_covered}"
    )


def test_the_allowlist_has_no_ghosts():
    """Every frozen name must still be a real option; a rename must not linger."""
    options = set(_configure_options())
    ghosts = sorted(name for name in UNCOVERED_BEFORE_THIS_CHECK if name not in options)
    assert not ghosts, f"these names are no longer configuration options: {ghosts}"


@pytest.mark.parametrize("option", ["max_request_body_bytes", "drain_timeout"])
def test_the_options_that_shipped_with_this_line_are_shown(option):
    """The two options added for the shutdown work must never lose their example."""
    assert option in _covered_at_call_sites()
