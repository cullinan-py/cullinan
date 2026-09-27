# -*- coding: utf-8 -*-
"""Single-source check for the extension-point registry.

``cullinan.core.extensions`` used to be a byte-for-byte copy of
``cullinan.support.extensions`` and carried its **own** registry singleton, so an
extension point registered through one module path was invisible through the
other. The copy is now an explicit re-export of ``cullinan.support.extensions``
(canonical), which makes both module paths hand back the same objects.

Falsifiability: before the single-sourcing these identity checks were all
``False``; each assertion below is red against a reintroduced copy and green once
the two paths share one module.

The import path is preserved on purpose - it is what consumers write - so this
module must keep ``import cullinan.core.extensions`` working.
"""
import importlib

import pytest

import cullinan.core.extensions as core_extensions
import cullinan.support.extensions as support_extensions

# Only the re-exported names belong to the shared surface; the copy shipped
# exactly these six, and the canonical module has no module-level __all__.
REEXPORTED_NAMES = (
    "ExtensionCategory",
    "ExtensionPoint",
    "ExtensionRegistry",
    "get_extension_registry",
    "list_extension_points",
    "reset_extension_registry",
)


def test_registry_singleton_is_shared():
    assert (
        core_extensions.get_extension_registry()
        is support_extensions.get_extension_registry()
    ), "both module paths must resolve to one registry instance"


def test_registry_accessor_is_the_same_function_object():
    # Stronger than "two equivalent functions": re-export, not re-implementation.
    assert (
        core_extensions.get_extension_registry
        is support_extensions.get_extension_registry
    )


@pytest.mark.parametrize("name", REEXPORTED_NAMES)
def test_reexported_names_are_the_same_objects(name):
    assert getattr(core_extensions, name) is getattr(support_extensions, name)


def test_a_registration_through_one_path_is_visible_through_the_other():
    """The user-visible consequence of the split registry, exercised end to end."""
    support_extensions.reset_extension_registry()
    try:
        registered = core_extensions.get_extension_registry()
        assert registered is support_extensions.get_extension_registry()

        # The registry's lazily-built built-in points must be reachable from
        # either module path, because there is only one registry.
        assert registered.get_extension_points()
        assert support_extensions.list_extension_points(category="middleware")
    finally:
        support_extensions.reset_extension_registry()


def test_legacy_import_path_still_resolves():
    # The copy is kept, not deleted: consumers may still import this path.
    module = importlib.import_module("cullinan.core.extensions")

    assert module is core_extensions


def test_the_copy_declares_no_extra_module_level_all():
    # An __all__ here would add names to the declared-surface union and move the
    # framework's frozen declaration counts; ``import X as X`` avoids that.
    assert not hasattr(core_extensions, "__all__")
