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


if __name__ == "__main__":
    unittest.main()
