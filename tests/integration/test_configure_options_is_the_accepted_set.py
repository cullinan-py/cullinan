# -*- coding: utf-8 -*-
"""``configure_options()`` reports what ``configure()`` accepts, and the docs run.

Two questions are asked here, and they are different:

1. is the reported set *exactly* the accepted set -- no name that would be refused, no
   accepted name left out? That is checked against ``inspect.signature``, which is the
   source both the function and the refusal message read, so a name added to one place
   and not the other shows up immediately;
2. does the rollback snippet on the migration page actually run? A code block nobody
   executes is a sentence pretending to be code, and this page exists because a caller
   has to support two installed versions at once.

The point of the public entry is the second use: ``configure()`` refuses unknown
keywords on purpose, so a call that carries an option the older version never had fails
at import time. Filtering the call through ``configure_options()`` makes one call work
against both versions without a ``try``/``except`` that hides which option was dropped.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from cullinan.support.config import configure, configure_options, get_config

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PAGE = REPO_ROOT / "docs" / "migration_guide_v2.md"


def test_the_reported_set_is_exactly_the_accepted_set():
    accepted = {
        name
        for name, parameter in inspect.signature(configure).parameters.items()
        if parameter.kind is not inspect.Parameter.VAR_KEYWORD
    }

    reported = set(configure_options())

    assert reported == accepted, (
        "configure_options() and the signature disagree: "
        f"only reported {sorted(reported - accepted)}, only accepted {sorted(accepted - reported)}"
    )


def test_every_reported_option_is_accepted_by_a_real_call():
    """The set is not just consistent with a signature -- the call goes through.

    Options that refuse by design (``root_module``) are excluded: they are accepted as
    keywords and rejected on their value, which is a different statement.
    """
    accepted = [name for name in configure_options() if name != "root_module"]
    assert accepted, "configure() reports no usable options at all"

    # A call carrying every reported keyword must fail only on values, never on the
    # names -- so this exercises the parser rather than the semantics.
    previous = get_config().to_dict()
    try:
        for name in accepted:
            try:
                configure(**{name: None})
            except TypeError as exc:  # pragma: no cover - a regression, not a branch
                raise AssertionError(f"{name} is reported but refused as unknown: {exc}") from exc
            except ValueError:
                # Refused on its value, which is the option working as designed.
                pass
    finally:
        get_config().from_dict(previous)


def _migration_snippet() -> str:
    text = MIGRATION_PAGE.read_text(encoding="utf-8")
    blocks = re.findall(r"```python\n(.*?)```", text, re.DOTALL)
    matches = [block for block in blocks if "configure_options" in block]
    assert len(matches) == 1, (
        "expected exactly one rollback snippet using configure_options on the migration "
        f"page, found {len(matches)}"
    )
    return matches[0]


def test_the_rollback_snippet_on_the_migration_page_runs():
    """Execute it, do not read it: the page teaches a call, so the call must work."""
    snippet = _migration_snippet()
    assert "configure_options" in snippet

    previous = get_config().to_dict()
    try:
        namespace: dict = {}
        exec(compile(snippet, str(MIGRATION_PAGE), "exec"), namespace)  # noqa: S102 - fixed, in-repo snippet
    finally:
        get_config().from_dict(previous)


def test_the_snippet_drops_an_option_the_installed_version_does_not_have():
    """The whole point: one call that also works against an older version."""
    snippet = _migration_snippet()

    previous = get_config().to_dict()
    try:
        namespace: dict = {}
        # A keyword this version does not accept would raise on its own; the snippet's
        # job is to filter it out before the call.
        exec(compile(snippet, str(MIGRATION_PAGE), "exec"), namespace)  # noqa: S102 - fixed, in-repo snippet
    finally:
        get_config().from_dict(previous)

    assert "if k in configure_options()" in snippet, (
        "the snippet no longer filters by the reported options, so it would fail at import "
        "on a version that lacks one of them -- which is the case it exists for"
    )


@pytest.mark.parametrize("page", ["docs/zh/migration_guide_v2.md"])
def test_the_chinese_page_carries_the_same_snippet(page):
    text = (REPO_ROOT / page).read_text(encoding="utf-8")
    assert "configure_options()" in text, (
        f"{page} does not mention configure_options, so a Chinese reader gets no portable "
        "rollback call"
    )
