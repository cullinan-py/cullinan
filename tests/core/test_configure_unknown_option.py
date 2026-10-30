# -*- coding: utf-8 -*-
"""A misspelt argument to ``configure()`` says what was probably meant.

Python's own refusal names the keyword but not the option that exists, so
``drain_timout`` read as "this release does not have that" instead of "typo" --
and the reader had no cheap way to tell the two apart. That matters here more
than usual: this release is about configuration that is declared, accepted and
then silently ignored, and a misspelling answered with a vague error invites the
reader to conclude the feature is missing rather than misspelt.

What is asserted, in the order the reader meets it: the option is **refused**
(never accepted with a warning -- that would make a typo a switch that does
nothing), the message names the option, the closest accepted name, and the
documentation section, and the exception type is still ``TypeError`` so callers
that already catch it keep working.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from cullinan.support.config import configure, get_config

DOC_ANCHOR = "docs/configuration.md#options-in-code"
#: The headings whose slug is the anchor above. A second entry is the price of a
#: machine-checked pointer: renaming the section is a decision, not a silent rot.
ANCHOR_TO_HEADING = {"options-in-code": "Options in code"}
REPO_ROOT = Path(__file__).resolve().parents[2]


def _refusal(**kwargs) -> TypeError:
    with pytest.raises(TypeError) as caught:
        configure(**kwargs)
    return caught.value


def test_a_misspelt_option_names_the_option_and_the_one_that_was_meant():
    error = _refusal(drain_timout=1)
    message = str(error)

    assert "drain_timout" in message, "the option that was passed must be named"
    assert "not a known option" in message, (
        "the message has to say the name is not an option at all, not that the value is wrong"
    )
    assert "'drain_timeout'" in message, (
        "the closest accepted option must be offered; without it the reader has to guess"
    )
    assert DOC_ANCHOR in message, "the message must point at the section that lists the options"


def test_the_refusal_is_still_a_plain_type_error():
    """No new exception type: downstream ``except TypeError`` must keep working."""
    error = _refusal(drain_timout=1)

    assert type(error) is TypeError, (
        f"a subclass ({type(error).__name__}) would slip past callers that catch TypeError exactly"
    )


def test_a_misspelt_option_is_refused_rather_than_accepted_with_a_warning():
    """``drain_timout`` must not become a silent no-op.

    The tempting alternative -- accept it and log -- is rejected on purpose: the
    value would look configured and change nothing, which is the defect class this
    release exists to remove.
    """
    before = get_config().drain_timeout

    error = _refusal(drain_timout=1.5)

    assert get_config().drain_timeout == before, (
        "the interface refused the call, so nothing may have been assigned"
    )
    assert "drain_timout" in str(error)


def test_every_unknown_option_is_named():
    error = _refusal(drain_timout=1, server_prot=8080)
    message = str(error)

    assert "drain_timout" in message and "server_prot" in message, (
        "refusing one name and hiding the other leaves half the call unexplained"
    )
    assert "'drain_timeout'" in message and "'server_port'" in message


def test_an_unrecognisable_name_is_still_refused_and_documented():
    """No close match exists; the message must still be actionable."""
    message = str(_refusal(zzzz=1))

    assert "zzzz" in message
    assert "not a known option" in message
    assert DOC_ANCHOR in message


def test_the_suggestions_come_from_the_real_signature():
    """The accepted names are read from ``configure``, not from a second list.

    A hand-maintained list would drift the first time an option was added, and
    the drift is invisible: the suggestion simply stops mentioning the new name.
    """
    parameters = {
        name
        for name, parameter in inspect.signature(configure).parameters.items()
        if parameter.kind is not inspect.Parameter.VAR_KEYWORD
    }
    assert {"drain_timeout", "server_port", "max_request_body_bytes"} <= parameters

    message = str(_refusal(drain_timout=1))
    for name in sorted(parameters):
        assert name in message, f"'{name}' is an accepted option but is not offered in the message"


def test_a_known_option_still_works():
    previous = get_config().drain_timeout
    try:
        assert configure(drain_timeout=4.5).drain_timeout == 4.5
    finally:
        get_config().drain_timeout = previous


@pytest.mark.parametrize("page", ["docs/configuration.md", "docs/zh/configuration.md"])
def test_the_section_the_message_points_at_exists(page):
    """A pointer into the docs is only useful while the section is there.

    The English page gets the anchor from its heading; the Chinese page names it
    explicitly, because the default heading id is derived from characters that do
    not survive slugification. Both are accepted, and one of them must match the
    anchor the message names -- so the message cannot come to point at nothing.
    """
    anchor = DOC_ANCHOR.split("#", 1)[1]
    text = (REPO_ROOT / page).read_text(encoding="utf-8")
    explicit = f"{{#{anchor}}}"
    heading_slug = ANCHOR_TO_HEADING[anchor]
    assert explicit in text or f"## {heading_slug}" in text, (
        f"{page} does not carry the section the error message points at ({anchor})"
    )
