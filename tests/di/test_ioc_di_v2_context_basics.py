# -*- coding: utf-8 -*-
"""Cullinan IoC/DI 2.0 - Context Basics Tests

Author: Cullinan

Minimal acceptance test set for PR-R1:
1. singleton: two get() calls with same name return the same object
2. prototype: two get() calls with same name return different objects
"""

import unittest
import sys
import os

# Ensure cullinan is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cullinan.core.container import ApplicationContext
from cullinan.core.container import Definition, ScopeType


class SimpleService:
    """Simple service class for testing"""

    instance_count = 0

    def __init__(self):
        SimpleService.instance_count += 1
        self.id = SimpleService.instance_count


class TestApplicationContextBasics(unittest.TestCase):
    """ApplicationContext basic functionality tests"""

    def setUp(self):
        """Reset counter before each test"""
        SimpleService.instance_count = 0

    def test_singleton_scope_returns_same_instance(self):
        """singleton: two get() calls with same name return the same object"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='SimpleService',
            factory=lambda c: SimpleService(),
            scope=ScopeType.SINGLETON,
            source='test:SimpleService'
        ))

        ctx.refresh()

        # Two get calls should return the same instance
        instance1 = ctx.get('SimpleService')
        instance2 = ctx.get('SimpleService')

        self.assertIs(instance1, instance2)
        self.assertEqual(instance1.id, instance2.id)
        # Should have created only once
        self.assertEqual(SimpleService.instance_count, 1)

    def test_prototype_scope_returns_different_instances(self):
        """prototype: two get() calls with same name return different objects"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='SimpleService',
            factory=lambda c: SimpleService(),
            scope=ScopeType.PROTOTYPE,
            source='test:SimpleService'
        ))

        ctx.refresh()

        # Two get calls should return different instances
        instance1 = ctx.get('SimpleService')
        instance2 = ctx.get('SimpleService')

        self.assertIsNot(instance1, instance2)
        self.assertNotEqual(instance1.id, instance2.id)
        # Should have created twice
        self.assertEqual(SimpleService.instance_count, 2)

    def test_register_before_refresh_succeeds(self):
        """Registration allowed before refresh"""
        ctx = ApplicationContext()

        # Should not raise exception
        ctx.register(Definition(
            name='Service1',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:Service1'
        ))

        ctx.register(Definition(
            name='Service2',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:Service2'
        ))

        self.assertEqual(ctx.definition_count, 2)
        self.assertFalse(ctx.is_frozen)

    def test_refresh_freezes_registry(self):
        """After refresh, registry is frozen"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='Service',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:Service'
        ))

        self.assertFalse(ctx.is_frozen)

        ctx.refresh()

        self.assertTrue(ctx.is_frozen)
        self.assertTrue(ctx.is_refreshed)

    def test_has_returns_correct_value(self):
        """has() correctly returns whether Definition exists"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='ExistingService',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:ExistingService'
        ))

        self.assertTrue(ctx.has('ExistingService'))
        self.assertFalse(ctx.has('NonExistingService'))

    def test_list_definitions(self):
        """list_definitions() returns all registered names"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='ServiceA',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:ServiceA'
        ))

        ctx.register(Definition(
            name='ServiceB',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:ServiceB'
        ))

        names = ctx.list_definitions()

        self.assertIn('ServiceA', names)
        self.assertIn('ServiceB', names)
        self.assertEqual(len(names), 2)

    def test_try_get_returns_none_for_missing(self):
        """try_get() returns None for non-existent dependency"""
        ctx = ApplicationContext()
        ctx.refresh()

        result = ctx.try_get('NonExisting')

        self.assertIsNone(result)

    def test_try_get_returns_instance_for_existing(self):
        """try_get() returns instance for existing dependency"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='Service',
            factory=lambda c: SimpleService(),
            scope=ScopeType.SINGLETON,
            source='test:Service'
        ))

        ctx.refresh()

        result = ctx.try_get('Service')

        self.assertIsNotNone(result)
        self.assertIsInstance(result, SimpleService)

    def test_eager_initialization(self):
        """eager=True Definition is pre-created on refresh"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='EagerService',
            factory=lambda c: SimpleService(),
            scope=ScopeType.SINGLETON,
            source='test:EagerService',
            eager=True
        ))

        self.assertEqual(SimpleService.instance_count, 0)

        ctx.refresh()

        # After refresh, should already be created
        self.assertEqual(SimpleService.instance_count, 1)

    def test_non_eager_not_initialized_on_refresh(self):
        """eager=False Definition is not created on refresh"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='LazyService',
            factory=lambda c: SimpleService(),
            scope=ScopeType.SINGLETON,
            source='test:LazyService',
            eager=False
        ))

        ctx.refresh()

        # After refresh, should not be created yet
        self.assertEqual(SimpleService.instance_count, 0)

        # Created only on first get
        ctx.get('LazyService')
        self.assertEqual(SimpleService.instance_count, 1)


class TestConditions(unittest.TestCase):
    """Conditional functionality tests"""

    def test_condition_satisfied_allows_resolution(self):
        """Resolution allowed when condition is satisfied"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='ConditionalService',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:ConditionalService',
            conditions=[lambda c: True]
        ))

        ctx.refresh()

        result = ctx.get('ConditionalService')
        self.assertIsNotNone(result)

    def test_try_get_returns_none_when_condition_not_met(self):
        """try_get returns None when condition is not met"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='ConditionalService',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:ConditionalService',
            conditions=[lambda c: False]
        ))

        ctx.refresh()

        result = ctx.try_get('ConditionalService')
        self.assertIsNone(result)

