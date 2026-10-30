# -*- coding: utf-8 -*-
"""A summary must not be weaker than the page it summarises.

Two defects in the previous release had the same shape and neither was a wrong
statement: the a6 changelog line said "ASGI 413; Tornado 400" -- true, and silent
about the fact that a client may receive **no status line at all** -- and the
configuration page had no `max_request_body_bytes` section, so the page a reader
consults for a setting did not mention it. Both were *weaker* than the page that
held the measured table, and nothing failed.

So the table is now pinned where it lives. The deployment page must keep all three
client observations (a `400`, a reset with no status line, and a chunked upload
aborted with no status line), the configuration page must point at that section,
and both pages must state which environment variable chooses the engine -- because
a deployment that sets `SERVER_ENGINE` gets the default engine and no error at all.

The checks are text assertions on purpose: the defect is a *missing sentence*, and
nothing else in the toolchain notices a sentence that is not there.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"

#: The three client-observable outcomes, as words a reader can act on. A row can
#: be reworded; shipping without one of these outcomes cannot be.
CLIENT_OBSERVATIONS = {
    "docs/deployment.md": ("`400`", "reset", "no status line", "chunked", "abort"),
    "docs/zh/deployment.md": ("`400`", "重置", "没有状态行", "分块", "中止"),
}

BODY_SECTION_HEADING = {
    "docs/deployment.md": "## Request body size",
    "docs/zh/deployment.md": "## 请求体大小",
}

CONFIG_PAGES = ("docs/configuration.md", "docs/zh/configuration.md")
ENGINE_VARIABLE = ("CULLINAN_ENGINE", "SERVER_ENGINE")


def _section(text: str, heading: str) -> str:
    """The body of one markdown section, up to the next heading of any level."""
    start = text.find(heading)
    assert start != -1, f"the section {heading!r} is gone"
    rest = text[start:]
    following = re.search(r"\n#{1,6} ", rest)
    return rest if following is None else rest[: following.start()]


def missing_observations(text: str, page: str) -> list[str]:
    """Which of the three client observations this page no longer carries."""
    section = _section(text, BODY_SECTION_HEADING[page])
    return [claim for claim in CLIENT_OBSERVATIONS[page] if claim not in section]


@pytest.mark.parametrize("page", sorted(CLIENT_OBSERVATIONS))
def test_every_client_observation_is_still_written_down(page):
    text = (REPO_ROOT / page).read_text(encoding="utf-8")
    missing = missing_observations(text, page)
    assert not missing, (
        f"{page} no longer says what a client observes in these cases: {missing}. "
        "Dropping one of them is how a summary becomes weaker than the measurement."
    )


@pytest.mark.parametrize("page", CONFIG_PAGES)
def test_the_configuration_page_points_at_the_measured_table(page):
    text = (REPO_ROOT / page).read_text(encoding="utf-8")
    assert "deployment.md#request-body-size" in text, (
        f"{page} mentions max_request_body_bytes without linking to the section that "
        "says what a client sees; the knob and its consequences must be one click apart"
    )


@pytest.mark.parametrize("page", CONFIG_PAGES)
def test_the_engine_variable_is_named_and_the_lookalike_is_disowned(page):
    text = (REPO_ROOT / page).read_text(encoding="utf-8")
    for name in ENGINE_VARIABLE:
        assert name in text, f"{page} does not name {name}"
    disowned = ("not a variable this framework reads", "不是框架读的变量")
    assert any(phrase in text for phrase in disowned), (
        f"{page} names SERVER_ENGINE but does not say it is not read; naming it without "
        "the correction leaves the reader with the wrong variable"
    )


def test_the_check_notices_a_deleted_observation():
    """A gate that cannot fail is a comment."""
    text = (REPO_ROOT / "docs/deployment.md").read_text(encoding="utf-8")
    section = _section(text, BODY_SECTION_HEADING["docs/deployment.md"])
    assert "no status line" in section

    # Delete the caveat itself rather than one formatting of it: the row may be
    # reworded, and a check that only recognises the current wording would go
    # green the moment someone rephrased it.
    weakened = text.replace("no status line", "")
    missing = missing_observations(weakened, "docs/deployment.md")
    assert "no status line" in missing, "removing the caveat must be reported"
