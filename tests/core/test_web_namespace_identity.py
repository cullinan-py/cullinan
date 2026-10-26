# -*- coding: utf-8 -*-
"""One path must have one identity.

When a package both imports a submodule and rebinds the same name to a
decorator, ``cullinan.web.<name>`` ends up disagreeing with
``sys.modules['cullinan.web.<name>']``. Both names that used to be at risk --
``middleware`` and ``controller`` -- now resolve to their submodules, and the
decorators stay reachable from the top level.
"""
import importlib
import sys
import types

import pytest

CONVERGED_NAMES = ["middleware", "controller"]


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


def test_the_dotted_path_to_a_submodule_is_importable():
    """The form that the divergence broke.

    While the decorator owned ``cullinan.web.controller``, the attribute was a
    function, so ``import cullinan.web.controller.registry as reg`` raised
    "cannot import name ... (unknown location)". Importing the leaf module and
    reaching its names is the thing a caller does when they want one piece of
    the package rather than the whole facade.
    """
    registry = importlib.import_module("cullinan.web.controller.registry")
    assert registry.__name__ == "cullinan.web.controller.registry"
    assert hasattr(registry, "get_controller_registry")


def test_the_controller_decorator_lives_where_the_names_are_not_taken():
    """Two names, two referents, no shadowing.

    ``cullinan.controller`` is the decorator and ``cullinan.web.controller`` is
    the submodule; the submodule exports the decorator under the same name
    inside itself, which is what makes both spellings honest.
    """
    top = importlib.import_module("cullinan")
    web = importlib.import_module("cullinan.web")
    submodule = importlib.import_module("cullinan.web.controller")

    assert isinstance(web.controller, types.ModuleType)
    assert callable(top.controller) and not isinstance(top.controller, types.ModuleType)
    assert submodule.controller is top.controller
