# -*- coding: utf-8 -*-
"""A1: Deprecation flow for legacy compatibility symbols.

Verifies that the five legacy symbols exported from ``cullinan.core`` carry
the standard deprecation metadata and emit both a ``DeprecationWarning``
(tool-chain visible) and a ``CompatibilitySemanticWarning`` (semantic
reminder) when used.

Covered symbols (deprecated since v0.95, removed in v0.97):
    - injectable
    - inject_constructor
    - InjectionRegistry
    - get_injection_registry
    - reset_injection_registry
"""
import warnings

import pytest

import cullinan.core as core
from cullinan.support.deprecation import is_deprecated, get_deprecation_info
from cullinan.core.semantic_rules import CompatibilitySemanticWarning, reset_semantic_warnings


LEGACY_SYMBOLS = [
    "injectable",
    "inject_constructor",
    "InjectionRegistry",
    "get_injection_registry",
    "reset_injection_registry",
]


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
        assert info["removal_version"] == "0.97"
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
        assert "0.97" in msg

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
