# -*- coding: utf-8 -*-
"""Test transitive scope constraint validation (Issue 3 fix verification)

Verifies that singleton/prototype -> request-scoped transitive dependency chains are caught during refresh.
"""

import unittest
from cullinan.core.container import ApplicationContext
from cullinan.core.container import Definition, ScopeType
from cullinan.core.exceptions import LifecycleError
from cullinan.core.decorators import Inject, InjectByName


# ---- Test components ----

class RequestScopedService:
    """Mock request-scoped component"""
    def __init__(self):
        self.value = "request"


class SingletonB:
    """singleton B, depends on RequestScopedService via field injection"""
    req = InjectByName("RequestScopedService")

    def __init__(self):
        pass


class SingletonA:
    """singleton A, explicitly depends on SingletonB"""

    def __init__(self):
        pass


class PrototypeB:
    """prototype B, depends on RequestScopedService via field injection"""
    req = InjectByName("RequestScopedService")

    def __init__(self):
        pass


class PrototypeA:
    """prototype A, explicitly depends on PrototypeB"""

    def __init__(self):
        pass


class SingletonWithPrivateDI:
    """singleton, uses underscore-prefixed Inject to depend on request scoped (verifies Issue 5 linkage)"""
    _req = InjectByName("RequestScopedService")

    def __init__(self):
        pass


# ---- Direct dependency tests (ensure existing checks don't regress) ----

class TestDirectScopeViolation(unittest.TestCase):
    """Test: singleton directly depending on request scoped is still detected"""

    def test_singleton_directly_depends_on_request(self):
        ctx = ApplicationContext()

        ctx.register(Definition(
            name="RequestService",
            factory=lambda c: RequestScopedService(),
            scope=ScopeType.REQUEST,
            source="test:RequestService",
        ))
        ctx.register(Definition(
            name="SingletonService",
            factory=lambda c: RequestScopedService(),
            scope=ScopeType.SINGLETON,
            dependencies=["RequestService"],
            source="test:SingletonService",
        ))

        with self.assertRaises(LifecycleError) as cm:
            ctx.refresh()
        self.assertIn("request-scoped", str(cm.exception))


# ---- Transitive dependency tests ----

class TestTransitiveScopeViolation(unittest.TestCase):
    """Test: singleton transitive dependency on request scoped is detected"""

    def test_singleton_transitive_via_explicit_deps(self):
        """SingletonA → SingletonB → RequestC (explicit dependency chain)"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name="RequestScopedService",
            factory=lambda c: RequestScopedService(),
            scope=ScopeType.REQUEST,
            source="test:RequestScopedService",
        ))
        ctx.register(Definition(
            name="SingletonB",
            factory=lambda c: SingletonB(),
            scope=ScopeType.SINGLETON,
            type_=SingletonB,
            dependencies=["RequestScopedService"],
            source="test:SingletonB",
        ))
        ctx.register(Definition(
            name="SingletonA",
            factory=lambda c: SingletonA(),
            scope=ScopeType.SINGLETON,
            type_=SingletonA,
            dependencies=["SingletonB"],
            source="test:SingletonA",
        ))

        with self.assertRaises(LifecycleError) as cm:
            ctx.refresh()
        self.assertIn("request-scoped", str(cm.exception))
        self.assertIn("SingletonB", str(cm.exception))

    def test_singleton_transitive_via_field_injection(self):
        """SingletonA → SingletonB(Inject→RequestC) (implicit field injection chain)"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name="RequestScopedService",
            factory=lambda c: RequestScopedService(),
            scope=ScopeType.REQUEST,
            source="test:RequestScopedService",
        ))
        ctx.register(Definition(
            name="SingletonB",
            factory=lambda c: SingletonB(),
            scope=ScopeType.SINGLETON,
            type_=SingletonB,
            source="test:SingletonB",
        ))
        ctx.register(Definition(
            name="SingletonA",
            factory=lambda c: SingletonA(),
            scope=ScopeType.SINGLETON,
            dependencies=["SingletonB"],
            source="test:SingletonA",
        ))

        with self.assertRaises(LifecycleError) as cm:
            ctx.refresh()
        self.assertIn("RequestScopedService", str(cm.exception))
        self.assertIn("field", str(cm.exception).lower())

    def test_prototype_transitive_via_field_injection(self):
        """PrototypeA → PrototypeB(Inject→RequestC) (prototype transitive dependency)"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name="RequestScopedService",
            factory=lambda c: RequestScopedService(),
            scope=ScopeType.REQUEST,
            source="test:RequestScopedService",
        ))
        ctx.register(Definition(
            name="PrototypeB",
            factory=lambda c: PrototypeB(),
            scope=ScopeType.PROTOTYPE,
            type_=PrototypeB,
            source="test:PrototypeB",
        ))
        ctx.register(Definition(
            name="PrototypeA",
            factory=lambda c: PrototypeA(),
            scope=ScopeType.PROTOTYPE,
            dependencies=["PrototypeB"],
            source="test:PrototypeA",
        ))

        with self.assertRaises(LifecycleError) as cm:
            ctx.refresh()
        self.assertIn("RequestScopedService", str(cm.exception))

    def test_underscore_prefixed_injection_also_checked(self):
        """Underscore-prefixed field injection also subject to scope validation (Issue 5 linkage)"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name="RequestScopedService",
            factory=lambda c: RequestScopedService(),
            scope=ScopeType.REQUEST,
            source="test:RequestScopedService",
        ))
        ctx.register(Definition(
            name="SingletonWithPrivateDI",
            factory=lambda c: SingletonWithPrivateDI(),
            scope=ScopeType.SINGLETON,
            type_=SingletonWithPrivateDI,
            source="test:SingletonWithPrivateDI",
        ))

        with self.assertRaises(LifecycleError) as cm:
            ctx.refresh()
        self.assertIn("RequestScopedService", str(cm.exception))

    def test_request_to_singleton_is_allowed(self):
        """request -> singleton dependency is valid (reverse does not error)"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name="SingletonService",
            factory=lambda c: SingletonA(),
            scope=ScopeType.SINGLETON,
            source="test:SingletonService",
        ))
        ctx.register(Definition(
            name="RequestService",
            factory=lambda c: RequestScopedService(),
            scope=ScopeType.REQUEST,
            dependencies=["SingletonService"],
            source="test:RequestService",
        ))

        # Should not raise LifecycleError
        try:
            ctx.refresh()
        except LifecycleError:
            self.fail("request -> singleton dependency should not trigger LifecycleError")
