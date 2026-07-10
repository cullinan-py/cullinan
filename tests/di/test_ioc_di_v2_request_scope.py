# -*- coding: utf-8 -*-
"""Cullinan IoC/DI 2.0 - Request Scope Tests

Author: Cullinan

Minimal acceptance test set for PR-R6:
1. Resolving request scope without RequestContext: raises ScopeNotActiveError
2. Instance isolation across different RequestContexts
"""

import unittest
import sys
import os
import threading
import concurrent.futures

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cullinan.core.container import ApplicationContext
from cullinan.core.container import Definition, ScopeType
from cullinan.core.diagnostics import ScopeNotActiveError


class RequestScopedService:
    """Request scope service for testing"""

    instance_count = 0

    def __init__(self):
        RequestScopedService.instance_count += 1
        self.id = RequestScopedService.instance_count


class TestRequestScopeBasics(unittest.TestCase):
    """Request Scope basic functionality tests"""

    def setUp(self):
        RequestScopedService.instance_count = 0

    def test_request_scope_without_context_raises_error(self):
        """Resolving request scope without RequestContext raises ScopeNotActiveError"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='RequestService',
            factory=lambda c: RequestScopedService(),
            scope=ScopeType.REQUEST,
            source='test:RequestService'
        ))

        ctx.refresh()

        # Without entering request context, should raise ScopeNotActiveError
        with self.assertRaises(ScopeNotActiveError) as cm:
            ctx.get('RequestService')

        exc = cm.exception
        self.assertEqual(exc.scope_type, 'REQUEST')
        self.assertEqual(exc.dependency_name, 'RequestService')

    def test_request_scope_with_context_succeeds(self):
        """With RequestContext, request scope resolves successfully"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='RequestService',
            factory=lambda c: RequestScopedService(),
            scope=ScopeType.REQUEST,
            source='test:RequestService'
        ))

        ctx.refresh()

        # Enter request context
        ctx.enter_request_context()
        try:
            instance = ctx.get('RequestService')
            self.assertIsNotNone(instance)
            self.assertIsInstance(instance, RequestScopedService)
        finally:
            ctx.exit_request_context()

    def test_same_request_context_returns_same_instance(self):
        """Same request context returns the same instance"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='RequestService',
            factory=lambda c: RequestScopedService(),
            scope=ScopeType.REQUEST,
            source='test:RequestService'
        ))

        ctx.refresh()

        ctx.enter_request_context()
        try:
            instance1 = ctx.get('RequestService')
            instance2 = ctx.get('RequestService')

            self.assertIs(instance1, instance2)
            self.assertEqual(RequestScopedService.instance_count, 1)
        finally:
            ctx.exit_request_context()

    def test_different_request_contexts_return_different_instances(self):
        """Different request contexts return different instances"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='RequestService',
            factory=lambda c: RequestScopedService(),
            scope=ScopeType.REQUEST,
            source='test:RequestService'
        ))

        ctx.refresh()

        # First request
        ctx.enter_request_context()
        try:
            instance1 = ctx.get('RequestService')
        finally:
            ctx.exit_request_context()

        # Second request
        ctx.enter_request_context()
        try:
            instance2 = ctx.get('RequestService')
        finally:
            ctx.exit_request_context()

        self.assertIsNot(instance1, instance2)
        self.assertNotEqual(instance1.id, instance2.id)
        self.assertEqual(RequestScopedService.instance_count, 2)

    def test_is_request_active_returns_correct_value(self):
        """is_request_active correctly reflects state"""
        ctx = ApplicationContext()
        ctx.refresh()

        self.assertFalse(ctx.is_request_active())

        ctx.enter_request_context()
        self.assertTrue(ctx.is_request_active())

        ctx.exit_request_context()
        self.assertFalse(ctx.is_request_active())


class TestRequestScopeConcurrency(unittest.TestCase):
    """Request Scope concurrency tests"""

    def setUp(self):
        RequestScopedService.instance_count = 0

    def test_concurrent_requests_are_isolated(self):
        """Concurrent requests isolate request scope instances"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='RequestService',
            factory=lambda c: RequestScopedService(),
            scope=ScopeType.REQUEST,
            source='test:RequestService'
        ))

        ctx.refresh()

        results = {}

        def make_request(request_id: int):
            ctx.enter_request_context()
            try:
                instance = ctx.get('RequestService')
                results[request_id] = instance.id
            finally:
                ctx.exit_request_context()

        # Use thread pool to simulate concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(5)]
            concurrent.futures.wait(futures)

        # Should have 5 different instances
        self.assertEqual(len(results), 5)
        self.assertEqual(len(set(results.values())), 5)


class TestTryGetWithRequestScope(unittest.TestCase):
    """try_get interaction with request scope tests"""

    def test_try_get_request_scope_without_context_raises_error(self):
        """try_get for request scope without context should still raise ScopeNotActiveError"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='RequestService',
            factory=lambda c: RequestScopedService(),
            scope=ScopeType.REQUEST,
            source='test:RequestService'
        ))

        ctx.refresh()

        # Per 2.6.3 Contract, system errors should still be raised
        with self.assertRaises(ScopeNotActiveError):
            ctx.try_get('RequestService')
