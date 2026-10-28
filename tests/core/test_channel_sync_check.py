# -*- coding: utf-8 -*-
"""Unit tests for ``scripts/check_channel_sync.py``.

A release has two channels -- the package and the documentation site's `pre`
channel -- and only the first is touched by pushing, tagging and publishing. The
check exists so the second cannot be silently left behind, which happened before
the check existed. These exercise the decision function directly, so they stay
fast and do not need a network or a second branch.
"""
import importlib.util
import re
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
    # 版本号只有一份正本（`cullinan/_version.py`）。这里写死一个字面量，就等于
    # 又存了一份 —— 每次发布都要记得改两处，而「记得」不是判据。
    # 断言并未空转：它比的是两条独立路径（checker 的正则解析 vs 包导入）；
    # 若正则被改坏、或文件里出现第二个赋值，两条路径就会分叉。
    from cullinan._version import __version__

    assert checker.read_local_version() == __version__
    assert re.fullmatch(r"\d+\.\d+(?:a|b|rc)\d+", __version__), (
        f"{__version__!r} is not an alpha/beta/rc release string; "
        "if the release-line shape changed, change this criterion first"
    )


def test_bundled_self_test_passes():
    assert checker.self_test() == 0
