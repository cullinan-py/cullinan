# -*- coding: utf-8 -*-
"""Unit tests for ``scripts/check_channel_sync.py``.

A release has two channels -- the package and the documentation site's `pre`
channel -- and only the first is touched by pushing, tagging and publishing. The
check exists so the second cannot be silently left behind, which happened before
the check existed. These exercise the decision function directly, so they stay
fast and do not need a network or a second branch.
"""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_channel_sync.py"

assert SCRIPT_PATH.is_file(), f"script missing: {SCRIPT_PATH}"
_spec = importlib.util.spec_from_file_location("check_channel_sync", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)


def test_matching_channels_pass():
    ok, message = checker.verdict("0.96a5", "0.96a5")
    assert ok is True
    assert "0.96a5" in message


def test_a_stale_docs_channel_is_a_mismatch():
    """The exact regression this check was written for."""
    ok, message = checker.verdict("0.96a5", "0.96a4")
    assert ok is False
    assert "0.96a5" in message and "0.96a4" in message


@pytest.mark.parametrize("released,docs_channel", [
    (None, "0.96a5"),
    ("0.96a5", None),
    (None, None),
])
def test_an_unreadable_channel_is_never_agreement(released, docs_channel):
    """A blind spot must not read as a pass."""
    ok, _ = checker.verdict(released, docs_channel)
    assert ok is False


def test_parse_version_reads_the_literal():
    assert checker.parse_version('__version__ = "0.96a5"\n') == "0.96a5"
    assert checker.parse_version("__version__ = '1.0'\n") == "1.0"


def test_parse_version_on_unparseable_input():
    assert checker.parse_version("") is None
    assert checker.parse_version("VERSION = 3\n") is None


def test_local_version_matches_the_ssot():
    assert checker.read_local_version() == "0.96a7.post1"


def test_bundled_self_test_passes():
    assert checker.self_test() == 0
