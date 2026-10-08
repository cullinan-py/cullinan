# -*- coding: utf-8 -*-
"""One path must have one identity.

When a package both imports a submodule and rebinds the same name to a
decorator, ``cullinan.web.<name>`` ends up disagreeing with
``sys.modules['cullinan.web.<name>']``. These tests pin the resolved identity
for ``middleware`` -- already converged so the submodule wins -- and record the
``controller`` divergence as a known, deliberate state rather than letting it
drift unnoticed.
"""
import importlib
import sys
import types

import pytest

CONVERGED_NAMES = ["middleware"]


@pytest.mark.parametrize("name", CONVERGED_NAMES)
def test_web_attribute_is_the_submodule(name):
    web = importlib.import_module("cullinan.web")
    attribute = getattr(web, name)
    assert isinstance(attribute, types.ModuleType), (
        f"cullinan.web.{name} must be the submodule, got {type(attribute).__name__}"
    )


@pytest.mark.parametrize("name", CONVERGED_NAMES)
def test_web_attribute_matches_sys_modules(name):
    web = importlib.import_module("cullinan.web")
    assert getattr(web, name) is sys.modules[f"cullinan.web.{name}"], (
        f"cullinan.web.{name} and sys.modules disagree: one path, two identities"
    )


@pytest.mark.parametrize("name", ["controller", "middleware"])
def test_top_level_decorator_is_reachable(name):
    top = importlib.import_module("cullinan")
    decorator = getattr(top, name)
    assert callable(decorator) and not isinstance(decorator, types.ModuleType), (
        f"the {name} decorator must stay reachable from the top level"
    )


@pytest.mark.parametrize("name", ["controller", "middleware"])
def test_top_level_names_are_exported(name):
    top = importlib.import_module("cullinan")
    assert name in top.__all__


def test_controller_identity_is_known_divergent():
    """Recorded divergence, not an endorsement.

    ``cullinan.web.controller`` still resolves to the decorator while
    ``sys.modules`` holds the module. Switching it is a breaking change --
    ``from cullinan.web import controller`` is used by the maintained examples
    -- so it has to go through the deprecation process (ADR, migration note,
    window) instead of riding along with an unrelated slice.

    If this test fails, the switch happened: update the migration guide, the
    examples and the release notes in the same change, and delete this test.
    """
    web = importlib.import_module("cullinan.web")
    attribute = getattr(web, "controller")
    assert not isinstance(attribute, types.ModuleType), (
        "cullinan.web.controller changed referent -- finish the deprecation "
        "process (ADR + migration note + examples + release notes) and remove "
        "this known-divergence test"
    )
