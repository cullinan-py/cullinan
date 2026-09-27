# -*- coding: utf-8 -*-
"""A1: Deprecation flow for legacy compatibility symbols.

Verifies that the five legacy symbols exported from ``cullinan.core`` carry
the standard deprecation metadata and emit both a ``DeprecationWarning``
(tool-chain visible) and a ``CompatibilitySemanticWarning`` (semantic
reminder) when used.

Covered symbols (deprecated since v0.95; the removal version is derived from
the framework version and the deprecation window):
    - injectable
    - inject_constructor
    - InjectionRegistry
    - get_injection_registry
    - reset_injection_registry
"""
import importlib
import warnings

import pytest

import cullinan.core as core
from cullinan.support.deprecation import (
    DEPRECATION_WINDOW_MINORS,
    EXTENDED_DEPRECATION_WINDOW_MINORS,
    _release_pair,
    current_version,
    deprecated,
    get_deprecation_info,
    is_deprecated,
    resolve_removal_version,
)
from cullinan.core.semantic_rules import CompatibilitySemanticWarning, reset_semantic_warnings


LEGACY_SYMBOLS = [
    "injectable",
    "inject_constructor",
    "InjectionRegistry",
    "get_injection_registry",
    "reset_injection_registry",
]


def _version_index(version: str) -> int:
    """Map a ``major.minor`` string onto the framework's linear release index."""
    major, minor = version.split(".")[:2]
    return int(major) * 100 + int(minor)


def _at_or_after(version: str, floor: str) -> bool:
    """True when ``version`` is the same as, or later than, ``floor``."""
    return _version_index(version) >= _version_index(floor)


@pytest.fixture(autouse=True)
def _restore_warning_filters():
    """Ensure each test starts with a clean warning filter state and
    resets the global semantic-warning dedupe set so CompatibilitySemanticWarning
    can be observed deterministically."""
    reset_semantic_warnings()
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        yield
    reset_semantic_warnings()


class TestDeprecationMetadata:
    """Each legacy symbol must carry __deprecated__ + __deprecated_info__."""

    @pytest.mark.parametrize("name", LEGACY_SYMBOLS)
    def test_symbol_is_marked_deprecated(self, name):
        obj = getattr(core, name)
        assert is_deprecated(obj), f"{name} should be marked deprecated"

    @pytest.mark.parametrize("name", LEGACY_SYMBOLS)
    def test_deprecation_info_has_required_fields(self, name):
        obj = getattr(core, name)
        info = get_deprecation_info(obj)
        assert info is not None, f"{name} missing __deprecated_info__"
        assert info["version"] == "0.95"
        # Derived, never hard-coded: ``removal_version`` follows the version in
        # ``cullinan._version`` plus the standard window, so pinning a literal
        # here would only move the per-release edit from the source into the
        # test (and drift the moment the framework version advances).
        assert info["removal_version"] == resolve_removal_version()
        assert info["alternative"], f"{name} alternative must not be empty"

    @pytest.mark.parametrize("name", LEGACY_SYMBOLS)
    def test_symbols_remain_in_all(self, name):
        """Deprecated symbols stay in __all__ during the deprecation window."""
        assert name in core.__all__


class TestDeprecationWarningOnUse:
    """Using a deprecated symbol must emit DeprecationWarning."""

    def test_injectable_emits_deprecation_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            core.injectable(object)
        deps = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deps) >= 1
        msg = str(deps[0].message)
        assert "deprecated" in msg
        assert "0.95" in msg
        # Derived, never hard-coded: the message quotes the SSOT-derived removal
        # version, so it must track the framework version automatically.
        assert resolve_removal_version() in msg

    def test_inject_constructor_emits_deprecation_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            core.inject_constructor(object)
        deps = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deps) >= 1

    def test_injection_registry_instantiation_emits_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            core.InjectionRegistry()
        deps = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deps) >= 1

    def test_get_injection_registry_emits_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = core.get_injection_registry()
        deps = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deps) >= 1
        # Behavior preserved: still returns the dummy registry.
        assert result is None or result is core._dummy_registry

    def test_reset_injection_registry_emits_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            core.reset_injection_registry()
        deps = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deps) >= 1


class TestDualWarningStrategy:
    """@deprecated emits DeprecationWarning; warn_semantic_once emits
    CompatibilitySemanticWarning (deduplicated)."""

    def test_injectable_emits_both_warning_types(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            core.injectable(object)
        has_dep = any(issubclass(w.category, DeprecationWarning) for w in caught)
        has_semantic = any(
            issubclass(w.category, CompatibilitySemanticWarning) for w in caught
        )
        assert has_dep, "DeprecationWarning should fire on each call"
        assert has_semantic, "CompatibilitySemanticWarning should fire on first call"

    def test_semantic_warning_is_deduplicated(self):
        """warn_semantic_once should only emit the semantic warning once."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            core.injectable(object)
            core.injectable(object)
            core.injectable(object)
        semantic = [
            w for w in caught
            if issubclass(w.category, CompatibilitySemanticWarning)
        ]
        assert len(semantic) == 1, "CompatibilitySemanticWarning must dedupe"

    def test_deprecation_warning_is_not_deduplicated_by_default(self):
        """DeprecationWarning is emitted on every call (standard Python
        semantics; deduplication is left to the caller's warning filter)."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            core.injectable(object)
            core.injectable(object)
        deps = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deps) == 2, "DeprecationWarning should fire on each call"


class TestBehaviorPreserved:
    """Deprecated symbols must keep their original behavior (no-op/None)."""

    def test_injectable_returns_class_unchanged(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            class Foo:
                pass
            assert core.injectable(Foo) is Foo

    def test_inject_constructor_returns_class_unchanged(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            class Bar:
                pass
            assert core.inject_constructor(Bar) is Bar

    def test_get_injection_registry_returns_none_or_dummy(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = core.get_injection_registry()
            assert result is None or result is core._dummy_registry

    def test_reset_injection_registry_is_noop(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # Should not raise.
            core.reset_injection_registry()

    def test_injection_registry_is_instantiable(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            instance = core.InjectionRegistry()
            assert instance is not None


class TestRuleBasedDeprecationWindow:
    """The removal version is derived from the version SSOT, never hard-coded.

    The rule-based refactor must not pull an existing deprecation forward: each
    surface's derived removal version must stay at or behind the value it
    advertised before the refactor (its ``floor``). Narrowing any window drops a
    surface below its floor and turns these guards red.
    """

    # Floors captured from the pre-refactor source: the core compatibility
    # aliases were announced for ``0.97``; the decorator's implicit default and
    # the legacy middleware helpers were announced for ``1.0``.
    CORE_REMOVAL_FLOOR = "0.97"
    COMPATIBILITY_REMOVAL_FLOOR = "1.0"

    def test_deprecation_windows_are_pinned_policy_values(self):
        # The two windows are policy *knobs*, not derived data: widening one
        # silently pushes every removal version further out, and the floor
        # guards in this class cannot catch that (they only reject narrowing).
        # Pin the exact values so a change to the policy can only land as a
        # deliberate, visible edit to this test - never as a silent drift.
        #
        # Both constants are an internal implementation detail rather than a
        # public compatibility commitment, so they are intentionally kept off
        # the published API surface and pinned here, on the test side, instead.
        assert DEPRECATION_WINDOW_MINORS == 2, (
            f"expected the standard window to be 2, got "
            f"{DEPRECATION_WINDOW_MINORS}; the window is a policy parameter and "
            f"any change must be a reviewed edit (it shifts every removal version)"
        )
        assert EXTENDED_DEPRECATION_WINDOW_MINORS == 5, (
            f"expected the extended window to be 5, got "
            f"{EXTENDED_DEPRECATION_WINDOW_MINORS}; the window is a policy "
            f"parameter and any change must be a reviewed edit (it shifts the "
            f"compatibility surface's removal version)"
        )

    def test_resolve_removal_version_is_current_minor_plus_window(self):
        # Parse with the module's own resolver instead of re-implementing the
        # arithmetic here: a hand-rolled ``split`` + ``int`` pair breaks on a
        # prerelease suffix (``0.96a1``), while the SSOT parser is suffix-aware.
        major, minor = _release_pair(current_version())
        total = major * 100 + minor + DEPRECATION_WINDOW_MINORS

        assert resolve_removal_version() == f"{total // 100}.{total % 100}"

    def test_resolve_removal_version_accepts_an_explicit_version_and_window(self):
        assert resolve_removal_version("0.96") == "0.98"
        assert resolve_removal_version("1.4", window=1) == "1.5"

    def test_resolve_removal_version_ignores_a_prerelease_suffix(self):
        assert resolve_removal_version("0.96a1") == "0.98"

    def test_resolve_removal_version_rejects_an_unparseable_version(self):
        with pytest.raises(ValueError):
            resolve_removal_version("not-a-version")

    def test_a_wide_window_rolls_over_into_the_next_major(self):
        # The framework numbers minors as a two-digit step, so a wide window has
        # to land on ``1.0`` rather than ``0.100``.
        assert resolve_removal_version("0.95", window=5) == "1.0"

    @pytest.mark.parametrize("name", LEGACY_SYMBOLS)
    def test_legacy_symbols_are_not_pulled_earlier_than_their_floor(self, name):
        version = get_deprecation_info(getattr(core, name))["removal_version"]
        assert _at_or_after(version, self.CORE_REMOVAL_FLOOR), (
            f"{name} removal version {version!r} is earlier than the value it "
            f"advertised before the refactor ({self.CORE_REMOVAL_FLOOR})"
        )

    def test_decorator_default_is_not_pulled_earlier_than_its_floor(self):
        @deprecated(version="0.95", alternative="the replacement helper")
        def _sample():
            return None

        version = get_deprecation_info(_sample)["removal_version"]
        assert _at_or_after(version, self.COMPATIBILITY_REMOVAL_FLOOR), (
            f"the decorator default removal version {version!r} is earlier than the "
            f"value it advertised before the refactor ({self.COMPATIBILITY_REMOVAL_FLOOR})"
        )

    def test_legacy_middleware_helpers_are_not_pulled_earlier_than_their_floor(self):
        legacy = importlib.import_module("cullinan.web.middleware.legacy")
        for name in ("register_middleware_manual", "get_registered_middlewares"):
            version = get_deprecation_info(getattr(legacy, name))["removal_version"]
            assert _at_or_after(version, self.COMPATIBILITY_REMOVAL_FLOOR), (
                f"{name} removal version {version!r} is earlier than the value it "
                f"advertised before the refactor ({self.COMPATIBILITY_REMOVAL_FLOOR})"
            )

    def test_core_aliases_derive_from_the_standard_window(self):
        expected = resolve_removal_version(window=DEPRECATION_WINDOW_MINORS)
        for name in LEGACY_SYMBOLS:
            assert get_deprecation_info(getattr(core, name))["removal_version"] == expected

    def test_compatibility_surface_derives_from_the_extended_window(self):
        expected = resolve_removal_version(window=EXTENDED_DEPRECATION_WINDOW_MINORS)
        legacy = importlib.import_module("cullinan.web.middleware.legacy")
        for name in ("register_middleware_manual", "get_registered_middlewares"):
            assert get_deprecation_info(getattr(legacy, name))["removal_version"] == expected
