# -*- coding: utf-8 -*-
"""Test ScopeViolationError dependency chain completeness and performance (A4).

Verifies:
- ScopeViolationError is raised (not plain LifecycleError) on scope violation.
- ScopeViolationError carries the full dependency_chain, origin_name, and
  violating_component fields (AC-A4-3).
- ScopeViolationError remains a LifecycleError subclass (backward compat).
- Existing keyword-based assertions (``assertIn("request-scoped", ...)``)
  continue to pass.
- Performance: a 100+ component dependency graph validates well under the
  5-second threshold (cross-origin memoization, O(N+E)).
"""

import time
import unittest

from cullinan.core.container import ApplicationContext, Definition, ScopeType
from cullinan.core.exceptions import LifecycleError, ScopeViolationError
from cullinan.core.decorators import InjectByName


class _RequestScoped:
    pass


class _SingletonLeaf:
    """Singleton that directly depends on a request-scoped component."""
    req = InjectByName("RequestScopedService")


class _SingletonMid:
    """Singleton depending on the leaf via explicit dependency."""
    def __init__(self):
        pass


class _SingletonRoot:
    """Singleton depending on the mid via explicit dependency."""
    def __init__(self):
        pass


def _build_chain_context():
    """Root -> Mid -> Leaf(InjectByName -> RequestScopedService).

    Components are registered origin-first so the transitive chain is
    reported starting from the root singleton.
    """
    ctx = ApplicationContext()
    ctx.register(Definition(
        name="RequestScopedService",
        factory=lambda c: _RequestScoped(),
        scope=ScopeType.REQUEST,
        source="test:RequestScopedService",
    ))
    ctx.register(Definition(
        name="SingletonRoot",
        factory=lambda c: _SingletonRoot(),
        scope=ScopeType.SINGLETON,
        dependencies=["SingletonMid"],
        source="test:SingletonRoot",
    ))
    ctx.register(Definition(
        name="SingletonMid",
        factory=lambda c: _SingletonMid(),
        scope=ScopeType.SINGLETON,
        dependencies=["SingletonLeaf"],
        source="test:SingletonMid",
    ))
    ctx.register(Definition(
        name="SingletonLeaf",
        factory=lambda c: _SingletonLeaf(),
        scope=ScopeType.SINGLETON,
        type_=_SingletonLeaf,
        source="test:SingletonLeaf",
    ))
    return ctx


class TestScopeViolationErrorChain(unittest.TestCase):
    """A4: ScopeViolationError carries the full dependency chain."""

    def test_scope_violation_raises_scope_violation_error(self):
        ctx = _build_chain_context()
        with self.assertRaises(ScopeViolationError) as cm:
            ctx.refresh()
        err = cm.exception
        self.assertEqual(err.origin_name, "SingletonRoot")
        self.assertEqual(err.violating_component, "RequestScopedService")

    def test_scope_violation_error_is_lifecycle_error_subclass(self):
        ctx = _build_chain_context()
        with self.assertRaises(LifecycleError) as cm:
            ctx.refresh()
        # The raised error must be both ScopeViolationError and LifecycleError.
        self.assertIsInstance(cm.exception, ScopeViolationError)
        self.assertIsInstance(cm.exception, LifecycleError)

    def test_dependency_chain_is_complete_and_ordered(self):
        ctx = _build_chain_context()
        with self.assertRaises(ScopeViolationError) as cm:
            ctx.refresh()
        chain = cm.exception.dependency_chain
        # The chain must run from the origin to the violating request-scoped
        # component, inclusive of both endpoints.
        self.assertEqual(chain[0], "SingletonRoot")
        self.assertEqual(chain[-1], "RequestScopedService")
        self.assertIn("SingletonMid", chain)
        self.assertIn("SingletonLeaf", chain)
        # Order: Root -> Mid -> Leaf -> RequestScopedService
        self.assertEqual(chain, ["SingletonRoot", "SingletonMid", "SingletonLeaf", "RequestScopedService"])

    def test_existing_keyword_assertions_still_hold(self):
        """Existing tests that assertIn key fragments must keep passing."""
        ctx = _build_chain_context()
        with self.assertRaises(LifecycleError) as cm:
            ctx.refresh()
        msg = str(cm.exception)
        self.assertIn("request-scoped", msg)
        self.assertIn("depends transitively", msg)
        self.assertIn("Dependency chain:", msg)

    def test_direct_dependency_chain_has_two_nodes(self):
        ctx = ApplicationContext()
        ctx.register(Definition(
            name="RequestService",
            factory=lambda c: _RequestScoped(),
            scope=ScopeType.REQUEST,
            source="test:RequestService",
        ))
        ctx.register(Definition(
            name="SingletonService",
            factory=lambda c: _SingletonRoot(),
            scope=ScopeType.SINGLETON,
            dependencies=["RequestService"],
            source="test:SingletonService",
        ))
        with self.assertRaises(ScopeViolationError) as cm:
            ctx.refresh()
        self.assertEqual(cm.exception.dependency_chain, ["SingletonService", "RequestService"])


class TestScopeValidationPerformance(unittest.TestCase):
    """A4: cross-origin memoization keeps validation O(N+E)."""

    def test_large_dependency_graph_validates_under_threshold(self):
        """A 120-component graph (no violations) validates in under 5 seconds.

        Without cross-origin memoization this graph triggers repeated
        traversals of the shared tail; the verified_safe memo ensures each
        node is fully visited only once.
        """
        ctx = ApplicationContext()

        # Build a chain of 100 singletons: S0 -> S1 -> ... -> S99, plus
        # 20 singletons that each depend on S99 (shared tail). All safe.
        for i in range(100):
            deps = [f"S{i + 1}"] if i < 99 else []
            ctx.register(Definition(
                name=f"S{i}",
                factory=lambda c, _i=i: type(f"Comp{_i}", (), {})(),
                scope=ScopeType.SINGLETON,
                dependencies=deps,
                source=f"test:S{i}",
            ))
        for j in range(20):
            ctx.register(Definition(
                name=f"T{j}",
                factory=lambda c, _j=j: type(f"Tail{_j}", (), {})(),
                scope=ScopeType.SINGLETON,
                dependencies=["S99"],
                source=f"test:T{j}",
            ))

        start = time.perf_counter()
        try:
            ctx.refresh()
        finally:
            ctx.shutdown()
        elapsed = time.perf_counter() - start
        # Threshold per ARCH: 5 seconds (QA confirms final value).
        self.assertLess(elapsed, 5.0, f"scope validation took {elapsed:.3f}s, exceeding 5s threshold")


class TestScopeViolationErrorFields(unittest.TestCase):
    """A4: ScopeViolationError fields default safely."""

    def test_defaults_when_fields_omitted(self):
        err = ScopeViolationError("plain message")
        self.assertEqual(err.dependency_chain, [])
        self.assertIsNone(err.origin_name)
        self.assertIsNone(err.violating_component)
        self.assertEqual(err.message, "plain message")
        self.assertIsInstance(err, LifecycleError)


if __name__ == "__main__":
    unittest.main()
