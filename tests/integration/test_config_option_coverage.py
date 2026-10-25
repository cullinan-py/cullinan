# -*- coding: utf-8 -*-
"""Every configuration option has to be visible in at least one example.

The declaration trailer in a commit message records that someone *decided*
something about the four non-code aspects. It does not prove the example exists.
`max_request_body_bytes` shipped through a green pipeline with no example at all,
which is the gap this file closes: an option nobody can see demonstrated is an
option readers learn about from the changelog.

The seven names below were already uncovered when this check was introduced.
They are frozen rather than ignored: the allowlist may shrink, never grow, and a
new option that arrives without an example fails immediately.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "cullinan" / "support" / "config.py"
EXAMPLES = REPO_ROOT / "examples"

# Options that predate this check. Adding a name here is a decision to ship an
# option with no example -- say so in the commit message rather than quietly
# extending the list.
UNCOVERED_BEFORE_THIS_CHECK = frozenset(
    {
        "root_module",
        "project_root",
        "verbose",
        "exclude_packages",
        "server_engine",
        "asgi_server",
        "server_host",
    }
)


def _configure_options() -> list[str]:
    tree = ast.parse(CONFIG.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "configure"
    )
    args = function.args.posonlyargs + function.args.args + function.args.kwonlyargs
    return [arg.arg for arg in args if arg.arg not in {"cls", "self"}]


def _examples_text() -> str:
    parts = []
    for path in EXAMPLES.rglob("*"):
        if path.suffix in {".py", ".md", ".json"}:
            parts.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


def test_a_new_option_never_ships_without_an_example():
    text = _examples_text()
    missing = {option for option in _configure_options() if option not in text}
    new_gaps = missing - UNCOVERED_BEFORE_THIS_CHECK
    assert not new_gaps, (
        "these configuration options are not shown in any example, so a reader "
        f"cannot see what they do: {sorted(new_gaps)}"
    )


def test_the_allowlist_only_shrinks():
    """A name here that has since been covered must be removed from the list."""
    text = _examples_text()
    now_covered = sorted(name for name in UNCOVERED_BEFORE_THIS_CHECK if name in text)
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
    assert option in _examples_text()
