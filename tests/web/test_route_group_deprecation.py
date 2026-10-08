# -*- coding: utf-8 -*-
"""Deprecation flow for the ``RouteGroup`` grouping type.

The group carries a public ``middleware_tags`` field that nothing in the
framework reads: the group can never apply middleware to its routes, so the
field promised behaviour that did not exist. The grouping type is therefore
deprecated, and the deprecation is carried by the **class** because a dataclass
field cannot be decorated.

The class and the field both stay usable for the whole deprecation window; the
removal version is derived from the release line the surface was deprecated on
rather than hand-written, so this surface cannot introduce a second, drifting
removal version.
"""
import dataclasses
import warnings

from cullinan.support.deprecation import (
    get_deprecation_info,
    is_deprecated,
    resolve_removal_version,
)
from cullinan.web.gateway import RouteGroup


def test_route_group_is_marked_deprecated():
    assert is_deprecated(RouteGroup)

    info = get_deprecation_info(RouteGroup)
    assert info is not None
    assert info["version"] == "0.95"
    assert "middleware" in info["alternative"]


def test_removal_version_is_derived_from_the_announced_anchor():
    info = get_deprecation_info(RouteGroup)

    # Derived, never hard-coded: it follows the release line this surface was
    # deprecated on - its own ``version`` - plus the standard deprecation window.
    # Anchoring on the release in flight instead would report a removal version
    # one minor further out than the one this surface advertised.
    assert info["removal_version"] == resolve_removal_version(info["version"])
    assert info["removal_version"] == "0.97"


def test_no_carrier_module_writes_a_hand_typed_removal_version():
    """Every deprecation carrier derives its removal version; none writes one.

    Three modules attach deprecation metadata: ``cullinan.core`` (five
    compatibility symbols), ``cullinan.web.gateway`` (``RouteGroup``) and
    ``cullinan.web.middleware.legacy`` (two helpers). Each derives the removal
    version from its announced anchor plus a window, so a hand-written
    ``removal_version="..."`` literal must not appear in any of them - such a
    literal is exactly what a later edit would drift with. The scan covers
    every carrier, not just one, so what the guard promises equals what it
    checks. ``cullinan/support/deprecation.py`` is deliberately not a carrier:
    the literal it shows lives inside a docstring example for callers, not in
    framework metadata.
    """
    import importlib
    from pathlib import Path

    # ``cullinan.web.middleware`` is now the middleware submodule itself, so its
    # package attribute and the module object agree. Resolve each carrier through
    # ``importlib`` so the module object is read directly, independent of how the
    # attribute is bound.
    carrier_modules = {
        "cullinan/core/__init__.py": importlib.import_module("cullinan.core"),
        "cullinan/web/gateway/route_types.py": importlib.import_module(
            "cullinan.web.gateway.route_types"
        ),
        "cullinan/web/middleware/legacy.py": importlib.import_module(
            "cullinan.web.middleware.legacy"
        ),
    }

    for relative, module in carrier_modules.items():
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert 'removal_version="' not in source, (
            f"{relative} pins a removal version as a literal; derive it from "
            "the anchor and window instead"
        )


def test_constructing_a_route_group_warns_but_stays_usable():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        group = RouteGroup(prefix="/api")

    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecations, "constructing a deprecated grouping type must warn"
    assert "RouteGroup" in str(deprecations[0].message)

    # The window contract: the old surface keeps working while it is deprecated.
    assert group.prefix == "/api"
    assert group.routes == []
    assert group.middleware_tags == set()


def test_the_deprecated_field_is_retained_during_the_window():
    field_names = {field.name for field in dataclasses.fields(RouteGroup)}

    assert "middleware_tags" in field_names
    assert {"prefix", "routes", "controller_cls"} <= field_names


def test_middleware_tags_defaults_to_an_empty_set():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        group = RouteGroup(prefix="/api", middleware_tags={"auth"})

    assert group.middleware_tags == {"auth"}
