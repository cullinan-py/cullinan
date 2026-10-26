# -*- coding: utf-8 -*-
"""The stateless-controller check: it must catch state, and it must not cry wolf.

The module had no coverage, so neither half of that sentence was ever executed
by the suite -- a validator that never fires and a validator that always fires
both pass an empty test file.
"""

from __future__ import annotations

import warnings

import pytest

from cullinan.web.controller.stateless_validator import (
    StatefulControllerError,
    StatefulControllerWarning,
    check_controller_init_source,
    validate_stateless_controller,
)


def _make(stateful: bool, extra: dict = None):
    extra = extra or {}

    class Sample:
        def __init__(self):
            if stateful:
                self.current_user = None
            for name, value in extra.items():
                setattr(self, name, value)

        def handle(self):
            return "ok"

    return Sample


def test_state_in_init_is_reported_as_a_warning_by_default():
    cls = validate_stateless_controller(_make(True))

    with pytest.warns(StatefulControllerWarning, match="current_user"):
        cls()

    assert cls().handle() == "ok"


def test_strict_mode_raises_instead_of_warning():
    cls = validate_stateless_controller(_make(True), strict=True)

    with pytest.raises(StatefulControllerError, match="current_user"):
        cls()


def _stateful_warnings_raised_by(cls):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cls()
    return [w for w in caught if issubclass(w.category, StatefulControllerWarning)]


def test_a_clean_controller_is_quiet():
    cls = validate_stateless_controller(_make(False))

    assert _stateful_warnings_raised_by(cls) == []


def test_framework_managed_attributes_are_not_reported():
    """``response`` and friends are injected by the framework, not request state."""
    cls = validate_stateless_controller(_make(False, {"response": object()}))

    assert _stateful_warnings_raised_by(cls) == []


class AssigningController:
    def __init__(self):
        self.current_user = None


class QuietController:
    def __init__(self):
        self.count = 0


class PlainController:
    pass


def test_source_check_finds_an_assignment_in_strict_mode():
    with pytest.raises(StatefulControllerError, match="current_user"):
        check_controller_init_source(AssigningController, strict=True)


def test_source_check_is_informational_by_default():
    # Non-strict only logs; the contract is that it does not raise.
    assert check_controller_init_source(AssigningController) is None


def test_source_check_ignores_a_controller_with_no_init():
    assert check_controller_init_source(PlainController) is None
