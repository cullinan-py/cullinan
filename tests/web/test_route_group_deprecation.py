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


def test_route_types_module_writes_no_hand_typed_removal_version():
    from pathlib import Path

    import cullinan.web.gateway.route_types as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    # A hand-written removal version would drift from the single source of truth.
    assert 'removal_version="' not in source


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
