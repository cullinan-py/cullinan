# -*- coding: utf-8 -*-
"""A2: strict_private_injection configuration switch.

Verifies that the ``strict_private_injection`` opt-out switch and the
``CULLINAN_STRICT_PRIVATE_INJECTION`` environment variable correctly cause
single-underscore (_xxx) attributes to be skipped by the injection marker
scanner, while the default behavior (v0.93a11+) keeps _xxx visible.

Context: commit c888738 (v0.93a11+) intentionally changed
``get_injection_markers`` to only skip dunder (``__xxx__``) attributes,
making single-underscore attributes visible to the injection system.
``strict_private_injection`` provides an opt-out for projects that want
strict private semantics per [[公共 API 暴露准则]] §3.
"""
import os
import unittest
from unittest.mock import patch

from cullinan.core.container import ApplicationContext, Definition, ScopeType
from cullinan.core.decorators import (
    InjectByName,
    get_injection_markers,
    invalidate_injection_markers_cache,
)
from cullinan.core.exceptions import ScopeViolationError


class _RequestScoped:
    pass


class _SingletonWithPrivateDI:
    _req = InjectByName("RequestScopedService")


class _SingletonWithPublicDI:
    req = InjectByName("RequestScopedService")


def _build_context_with_private_di(*, strict_private_injection=False):
    """Context with only the private-DI singleton."""
    ctx = ApplicationContext(strict_private_injection=strict_private_injection)
    ctx.register(Definition(
        name="RequestScopedService",
        factory=lambda c: _RequestScoped(),
        scope=ScopeType.REQUEST,
        source="test:RequestScopedService",
    ))
    ctx.register(Definition(
        name="SingletonWithPrivateDI",
        factory=lambda c: _SingletonWithPrivateDI(),
        scope=ScopeType.SINGLETON,
        type_=_SingletonWithPrivateDI,
        source="test:SingletonWithPrivateDI",
    ))
    return ctx


def _build_context_with_public_di(*, strict_private_injection=False):
    """Context with only the public-DI singleton."""
    ctx = ApplicationContext(strict_private_injection=strict_private_injection)
    ctx.register(Definition(
        name="RequestScopedService",
        factory=lambda c: _RequestScoped(),
        scope=ScopeType.REQUEST,
        source="test:RequestScopedService",
    ))
    ctx.register(Definition(
        name="SingletonWithPublicDI",
        factory=lambda c: _SingletonWithPublicDI(),
        scope=ScopeType.SINGLETON,
        type_=_SingletonWithPublicDI,
        source="test:SingletonWithPublicDI",
    ))
    return ctx


def _build_context(*, strict_private_injection=False):
    """Context with both private and public DI singletons."""
    ctx = ApplicationContext(strict_private_injection=strict_private_injection)
    ctx.register(Definition(
        name="RequestScopedService",
        factory=lambda c: _RequestScoped(),
        scope=ScopeType.REQUEST,
        source="test:RequestScopedService",
    ))
    ctx.register(Definition(
        name="SingletonWithPrivateDI",
        factory=lambda c: _SingletonWithPrivateDI(),
        scope=ScopeType.SINGLETON,
        type_=_SingletonWithPrivateDI,
        source="test:SingletonWithPrivateDI",
    ))
    ctx.register(Definition(
        name="SingletonWithPublicDI",
        factory=lambda c: _SingletonWithPublicDI(),
        scope=ScopeType.SINGLETON,
        type_=_SingletonWithPublicDI,
        source="test:SingletonWithPublicDI",
    ))
    return ctx


class TestStrictPrivateInjectionDefault(unittest.TestCase):
    """Default behavior (strict_private_injection=False): _xxx is visible."""

    def setUp(self):
        invalidate_injection_markers_cache()

    def test_default_has_strict_private_false(self):
        ctx = ApplicationContext()
        self.assertFalse(ctx._strict_private_injection)

    def test_default_sees_private_injection_markers(self):
        markers = get_injection_markers(_SingletonWithPrivateDI)
        self.assertIn("_req", markers)

    def test_default_detects_private_di_scope_violation(self):
        """Default: _req InjectByName is scanned and triggers scope violation."""
        invalidate_injection_markers_cache()
        ctx = _build_context_with_private_di(strict_private_injection=False)
        with self.assertRaises(ScopeViolationError):
            ctx.refresh()


class TestStrictPrivateInjectionEnabled(unittest.TestCase):
    """strict_private_injection=True: _xxx is skipped."""

    def setUp(self):
        invalidate_injection_markers_cache()

    def test_explicit_strict_private_true(self):
        ctx = ApplicationContext(strict_private_injection=True)
        self.assertTrue(ctx._strict_private_injection)

    def test_skip_private_hides_underscore_markers(self):
        markers = get_injection_markers(_SingletonWithPrivateDI, skip_private=True)
        self.assertNotIn("_req", markers)

    def test_skip_private_keeps_public_markers(self):
        markers = get_injection_markers(_SingletonWithPublicDI, skip_private=True)
        self.assertIn("req", markers)

    def test_strict_mode_skips_private_di_scope_violation(self):
        """strict_private_injection=True: _req is not scanned, so no violation."""
        invalidate_injection_markers_cache()
        ctx = _build_context_with_private_di(strict_private_injection=True)
        # Should NOT raise because _req is skipped.
        ctx.refresh()

    def test_strict_mode_still_detects_public_di_violation(self):
        """strict_private_injection=True: public `req` is still scanned."""
        invalidate_injection_markers_cache()
        ctx = _build_context_with_public_di(strict_private_injection=True)
        with self.assertRaises(ScopeViolationError):
            ctx.refresh()


class TestEnvironmentVariable(unittest.TestCase):
    """CULLINAN_STRICT_PRIVATE_INJECTION env var provides global opt-in."""

    def setUp(self):
        invalidate_injection_markers_cache()

    def test_env_var_enables_strict_mode(self):
        with patch.dict(os.environ, {"CULLINAN_STRICT_PRIVATE_INJECTION": "1"}):
            ctx = ApplicationContext()
            self.assertTrue(ctx._strict_private_injection)

    def test_env_var_true_enables_strict_mode(self):
        with patch.dict(os.environ, {"CULLINAN_STRICT_PRIVATE_INJECTION": "true"}):
            ctx = ApplicationContext()
            self.assertTrue(ctx._strict_private_injection)

    def test_env_var_yes_enables_strict_mode(self):
        with patch.dict(os.environ, {"CULLINAN_STRICT_PRIVATE_INJECTION": "yes"}):
            ctx = ApplicationContext()
            self.assertTrue(ctx._strict_private_injection)

    def test_env_var_empty_disables_strict_mode(self):
        with patch.dict(os.environ, {"CULLINAN_STRICT_PRIVATE_INJECTION": ""}):
            ctx = ApplicationContext()
            self.assertFalse(ctx._strict_private_injection)

    def test_env_var_zero_disables_strict_mode(self):
        with patch.dict(os.environ, {"CULLINAN_STRICT_PRIVATE_INJECTION": "0"}):
            ctx = ApplicationContext()
            self.assertFalse(ctx._strict_private_injection)

    def test_explicit_param_overrides_env_var(self):
        """explicit strict_private_injection=False with env=1 -> False? No:
        the OR logic means env var wins. But explicit True always wins."""
        with patch.dict(os.environ, {"CULLINAN_STRICT_PRIVATE_INJECTION": "1"}):
            ctx = ApplicationContext(strict_private_injection=False)
            # OR logic: False or True = True
            self.assertTrue(ctx._strict_private_injection)

    def test_explicit_true_with_no_env(self):
        with patch.dict(os.environ, {}, clear=True):
            ctx = ApplicationContext(strict_private_injection=True)
            self.assertTrue(ctx._strict_private_injection)


class TestCacheInvalidation(unittest.TestCase):
    """The injection markers cache must be invalidated when skip_private changes."""

    def setUp(self):
        invalidate_injection_markers_cache()

    def test_cache_keyed_by_skip_private(self):
        """get_injection_markers with skip_private=False and True return
        different results and are cached independently."""
        m_default = get_injection_markers(_SingletonWithPrivateDI, skip_private=False)
        m_strict = get_injection_markers(_SingletonWithPrivateDI, skip_private=True)
        self.assertIn("_req", m_default)
        self.assertNotIn("_req", m_strict)


# ── PM AC-A2-4 acceptance scenarios (TS-1 to TS-6) ─────────────────────
# PM-defined authoritative test scenarios for strict_private_injection.
# These map 1:1 to PM's table (msg_e95f8d797d1e, art_a78302c5d6c8).


class _DatabaseService:
    """Type used for bare-annotation constructor injection (TS-6)."""
    pass


class _SingletonWithPrivateBareAnnotation:
    """TS-6: _internal_db uses bare type annotation (constructor injection)."""
    _internal_db: _DatabaseService


class _SingletonWithPublicBareAnnotation:
    """TS-6 companion: public `db` bare type annotation (must still inject)."""
    db: _DatabaseService


def _build_context_private_bare_annotation(*, strict_private_injection=False):
    """Context with a request-scoped DatabaseService and a singleton that
    has a private bare-annotation ``_internal_db: _DatabaseService``."""
    ctx = ApplicationContext(strict_private_injection=strict_private_injection)
    ctx.register(Definition(
        name="DatabaseService",
        factory=lambda c: _DatabaseService(),
        scope=ScopeType.REQUEST,
        type_=_DatabaseService,
        source="test:DatabaseService",
    ))
    ctx.register(Definition(
        name="SingletonWithPrivateBareAnnotation",
        factory=lambda c: _SingletonWithPrivateBareAnnotation(),
        scope=ScopeType.SINGLETON,
        type_=_SingletonWithPrivateBareAnnotation,
        source="test:SingletonWithPrivateBareAnnotation",
    ))
    return ctx


def _build_context_public_bare_annotation(*, strict_private_injection=False):
    """Context with a request-scoped DatabaseService and a singleton that
    has a public bare-annotation ``db: _DatabaseService``."""
    ctx = ApplicationContext(strict_private_injection=strict_private_injection)
    ctx.register(Definition(
        name="DatabaseService",
        factory=lambda c: _DatabaseService(),
        scope=ScopeType.REQUEST,
        type_=_DatabaseService,
        source="test:DatabaseService",
    ))
    ctx.register(Definition(
        name="SingletonWithPublicBareAnnotation",
        factory=lambda c: _SingletonWithPublicBareAnnotation(),
        scope=ScopeType.SINGLETON,
        type_=_SingletonWithPublicBareAnnotation,
        source="test:SingletonWithPublicBareAnnotation",
    ))
    return ctx


class TestPMAcceptanceScenarios(unittest.TestCase):
    """PM AC-A2-4 authoritative test scenarios TS-1 through TS-6."""

    def setUp(self):
        invalidate_injection_markers_cache()

    # TS-1: default False, _req InjectByName -> scanned, scope violation raises
    def test_TS1_default_scans_private_injectbyname_and_raises(self):
        """TS-1: strict_private_injection=False (default), _req = InjectByName("X")
        is scanned and triggers scope violation (LifecycleError).
        Aligns with test_underscore_prefixed_injection_also_checked L183."""
        ctx = _build_context_with_private_di(strict_private_injection=False)
        with self.assertRaises(ScopeViolationError):
            ctx.refresh()

    # TS-2: strict=True, _req InjectByName -> skipped, no scope check
    def test_TS2_strict_skips_private_injectbyname_no_violation(self):
        """TS-2: strict_private_injection=True, _req = InjectByName("X") is
        skipped, stays as the unresolved InjectByName marker (not injected),
        no scope validation triggered."""
        invalidate_injection_markers_cache()
        ctx = _build_context_with_private_di(strict_private_injection=True)
        # Should NOT raise because _req is skipped.
        ctx.refresh()
        instance = ctx.get("SingletonWithPrivateDI")
        # _req was NOT injected: it still holds the InjectByName marker
        # (or is absent), but it is NOT the resolved _RequestScoped instance.
        value = getattr(instance, "_req", None)
        self.assertNotIsInstance(value, _RequestScoped)

    # TS-3: strict=True, req (no prefix) -> still injected
    def test_TS3_strict_keeps_public_injectbyname(self):
        """TS-3: strict_private_injection=True, req = InjectByName("X") (no
        underscore prefix) is still scanned normally."""
        invalidate_injection_markers_cache()
        # Use a valid singleton->singleton context so public req resolves.
        ctx = ApplicationContext(strict_private_injection=True)
        ctx.register(Definition(
            name="RequestScopedService",
            factory=lambda c: _RequestScoped(),
            scope=ScopeType.SINGLETON,
            source="test:RequestScopedService",
        ))
        ctx.register(Definition(
            name="SingletonWithPublicDI",
            factory=lambda c: _SingletonWithPublicDI(),
            scope=ScopeType.SINGLETON,
            type_=_SingletonWithPublicDI,
            source="test:SingletonWithPublicDI",
        ))
        ctx.refresh()
        instance = ctx.get("SingletonWithPublicDI")
        self.assertIsNotNone(getattr(instance, "req", None))

    # TS-4: CULLINAN_STRICT_PRIVATE_INJECTION=1, _req -> equivalent to TS-2
    def test_TS4_env_var_equivalent_to_strict_mode(self):
        """TS-4: CULLINAN_STRICT_PRIVATE_INJECTION=1, _req = InjectByName("X")
        is skipped (equivalent to TS-2 via env var fallback)."""
        invalidate_injection_markers_cache()
        with patch.dict(os.environ, {"CULLINAN_STRICT_PRIVATE_INJECTION": "1"}):
            ctx = _build_context_with_private_di()
            # Should NOT raise because _req is skipped via env var.
            ctx.refresh()
            instance = ctx.get("SingletonWithPrivateDI")
            value = getattr(instance, "_req", None)
            self.assertNotIsInstance(value, _RequestScoped)

    # TS-5: explicit False + env=1 -> OR logic, strict wins
    def test_TS5_explicit_false_with_env_one_still_strict(self):
        """TS-5: strict_private_injection=False + env=1 -> OR logic means env
        var wins (any True -> strict). Validates OR logic end-to-end."""
        invalidate_injection_markers_cache()
        with patch.dict(os.environ, {"CULLINAN_STRICT_PRIVATE_INJECTION": "1"}):
            ctx = _build_context_with_private_di(strict_private_injection=False)
            # OR logic: False or True = True -> _req skipped, no violation.
            ctx.refresh()
            instance = ctx.get("SingletonWithPrivateDI")
            value = getattr(instance, "_req", None)
            self.assertNotIsInstance(value, _RequestScoped)

    # TS-6: strict=True, _internal_db: DatabaseService (bare type annotation) -> skipped
    def test_TS6_strict_skips_private_bare_annotation_constructor(self):
        """TS-6: strict_private_injection=True, _internal_db: DatabaseService
        (bare type annotation, constructor injection path) is skipped.
        No scope violation, no DependencyNotFoundError, attr stays unset."""
        invalidate_injection_markers_cache()
        ctx = _build_context_private_bare_annotation(strict_private_injection=True)
        # Should NOT raise: _internal_db is skipped, so no scope check, no
        # DependencyNotFoundError for the unresolvable private annotation.
        ctx.refresh()
        instance = ctx.get("SingletonWithPrivateBareAnnotation")
        # _internal_db was skipped by strict mode, so it remains unset
        # (constructor injection did not set it).
        self.assertFalse(hasattr(instance, "_internal_db") and
                         getattr(instance, "_internal_db", None) is not None)

    def test_TS6_default_scans_private_bare_annotation_and_raises(self):
        """TS-6 companion: default (strict=False), _internal_db: DatabaseService
        (bare type annotation) IS scanned and triggers scope violation.
        Validates the default constructor-injection path is unaffected."""
        invalidate_injection_markers_cache()
        ctx = _build_context_private_bare_annotation(strict_private_injection=False)
        with self.assertRaises(ScopeViolationError):
            ctx.refresh()

    def test_TS6_strict_keeps_public_bare_annotation(self):
        """TS-6 companion: strict=True, db: DatabaseService (public bare type
        annotation) is still scanned and triggers scope violation."""
        invalidate_injection_markers_cache()
        ctx = _build_context_public_bare_annotation(strict_private_injection=True)
        with self.assertRaises(ScopeViolationError):
            ctx.refresh()


if __name__ == "__main__":
    unittest.main()
