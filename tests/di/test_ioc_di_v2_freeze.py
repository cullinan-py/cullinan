# -*- coding: utf-8 -*-
"""Cullinan IoC/DI 2.0 - Freeze Mechanism Tests

Author: Cullinan

Minimal acceptance test set for PR-R2:
1. register succeeds before refresh
2. register/clear raises RegistryFrozenError after refresh
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cullinan.core.container import ApplicationContext
from cullinan.core.container import Definition, ScopeType
from cullinan.core.diagnostics import RegistryFrozenError


class TestFreezeAfterRefresh(unittest.TestCase):
    """Freeze mechanism tests"""
    
    def test_register_before_refresh_succeeds(self):
        """register succeeds before refresh"""
        ctx = ApplicationContext()

        # Should not raise exception
        ctx.register(Definition(
            name='Service1',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:Service1'
        ))
        
        self.assertEqual(ctx.definition_count, 1)
        self.assertFalse(ctx.is_frozen)
    
    def test_register_after_refresh_raises_frozen_error(self):
        """register raises RegistryFrozenError after refresh"""
        ctx = ApplicationContext()
        
        ctx.register(Definition(
            name='ExistingService',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:ExistingService'
        ))
        
        ctx.refresh()
        
        # After refresh, registration should raise RegistryFrozenError
        with self.assertRaises(RegistryFrozenError) as cm:
            ctx.register(Definition(
                name='NewService',
                factory=lambda c: object(),
                scope=ScopeType.SINGLETON,
                source='test:NewService'
            ))
        
        self.assertIn('frozen', str(cm.exception))
        self.assertIn('NewService', str(cm.exception))
    
    def test_duplicate_registration_raises_error(self):
        """Duplicate registration of same Definition name raises ValueError"""
        ctx = ApplicationContext()
        
        ctx.register(Definition(
            name='Service',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:Service'
        ))
        
        with self.assertRaises(ValueError) as cm:
            ctx.register(Definition(
                name='Service',
                factory=lambda c: object(),
                scope=ScopeType.SINGLETON,
                source='test:Service'
            ))
        
        self.assertIn('already registered', str(cm.exception))
    
    def test_is_frozen_property(self):
        """is_frozen property correctly reflects state"""
        ctx = ApplicationContext()
        
        self.assertFalse(ctx.is_frozen)
        
        ctx.refresh()
        
        self.assertTrue(ctx.is_frozen)
    
    def test_multiple_refresh_calls_are_idempotent(self):
        """Multiple refresh calls are idempotent"""
        ctx = ApplicationContext()
        
        ctx.register(Definition(
            name='Service',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:Service'
        ))
        
        ctx.refresh()
        ctx.refresh()  # Second call should not raise
        ctx.refresh()  # Third call either
        
        self.assertTrue(ctx.is_frozen)
        self.assertTrue(ctx.is_refreshed)


class TestRegistryFrozenErrorDetails(unittest.TestCase):
    """RegistryFrozenError exception details tests"""
    
    def test_error_message_contains_definition_name(self):
        """Error message contains the Definition name that was attempted to register"""
        ctx = ApplicationContext()
        ctx.refresh()
        
        try:
            ctx.register(Definition(
                name='FailingService',
                factory=lambda c: object(),
                scope=ScopeType.SINGLETON,
                source='test:FailingService'
            ))
            self.fail("Should have raised RegistryFrozenError")
        except RegistryFrozenError as e:
            self.assertIn('FailingService', str(e))
    
    def test_error_is_registry_error_subclass(self):
        """RegistryFrozenError is a subclass of RegistryError"""
        from cullinan.core.diagnostics import RegistryError

        self.assertTrue(issubclass(RegistryFrozenError, RegistryError))
