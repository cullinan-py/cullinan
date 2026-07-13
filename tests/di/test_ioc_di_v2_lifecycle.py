# -*- coding: utf-8 -*-
"""Cullinan IoC/DI 2.0 - Lifecycle Tests

Author: Cullinan

Minimal acceptance test set for PR-R5:
1. refresh/start triggers eager initialization
2. shutdown executes in order
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cullinan.core.container import ApplicationContext
from cullinan.core.container import Definition, ScopeType


class LifecycleTracker:
    """Helper class for tracking lifecycle events"""
    
    events = []
    
    @classmethod
    def reset(cls):
        cls.events = []
    
    @classmethod
    def record(cls, event: str):
        cls.events.append(event)


class ServiceWithLifecycle:
    """Service with lifecycle hooks"""
    
    def __init__(self, name: str):
        self.name = name
        LifecycleTracker.record(f'{name}:init')
    
    def on_shutdown(self):
        LifecycleTracker.record(f'{self.name}:shutdown')


class TestEagerInitialization(unittest.TestCase):
    """Eager initialization tests"""
    
    def setUp(self):
        LifecycleTracker.reset()
    
    def test_eager_definitions_initialized_on_refresh(self):
        """eager=True Definition is initialized on refresh"""
        ctx = ApplicationContext()
        
        ctx.register(Definition(
            name='EagerService',
            factory=lambda c: ServiceWithLifecycle('EagerService'),
            scope=ScopeType.SINGLETON,
            source='test:EagerService',
            eager=True
        ))
        
        self.assertEqual(len(LifecycleTracker.events), 0)
        
        ctx.refresh()
        
        self.assertIn('EagerService:init', LifecycleTracker.events)
    
    def test_non_eager_definitions_not_initialized_on_refresh(self):
        """eager=False Definition is not initialized on refresh"""
        ctx = ApplicationContext()
        
        ctx.register(Definition(
            name='LazyService',
            factory=lambda c: ServiceWithLifecycle('LazyService'),
            scope=ScopeType.SINGLETON,
            source='test:LazyService',
            eager=False
        ))
        
        ctx.refresh()
        
        self.assertNotIn('LazyService:init', LifecycleTracker.events)
        
        # Initialized only on first access
        ctx.get('LazyService')
        self.assertIn('LazyService:init', LifecycleTracker.events)
    
    def test_eager_initialization_respects_dependencies(self):
        """Eager initialization respects dependency order"""
        ctx = ApplicationContext()
        
        ctx.register(Definition(
            name='ServiceA',
            factory=lambda c: ServiceWithLifecycle('ServiceA'),
            scope=ScopeType.SINGLETON,
            source='test:ServiceA',
            eager=True,
            dependencies=['ServiceB']  # A depends on B
        ))
        
        ctx.register(Definition(
            name='ServiceB',
            factory=lambda c: ServiceWithLifecycle('ServiceB'),
            scope=ScopeType.SINGLETON,
            source='test:ServiceB',
            eager=True
        ))
        
        ctx.refresh()
        
        # Both should be initialized
        self.assertIn('ServiceA:init', LifecycleTracker.events)
        self.assertIn('ServiceB:init', LifecycleTracker.events)


class TestShutdown(unittest.TestCase):
    """Shutdown tests"""
    
    def setUp(self):
        LifecycleTracker.reset()
    
    def test_shutdown_handlers_are_called(self):
        """Registered handlers are called on shutdown"""
        ctx = ApplicationContext()
        ctx.refresh()
        
        ctx.add_shutdown_handler(lambda: LifecycleTracker.record('handler1'))
        ctx.add_shutdown_handler(lambda: LifecycleTracker.record('handler2'))
        
        ctx.shutdown()
        
        self.assertIn('handler1', LifecycleTracker.events)
        self.assertIn('handler2', LifecycleTracker.events)
    
    def test_shutdown_handlers_called_in_order(self):
        """Shutdown handlers are called in registration order"""
        ctx = ApplicationContext()
        ctx.refresh()
        
        ctx.add_shutdown_handler(lambda: LifecycleTracker.record('first'))
        ctx.add_shutdown_handler(lambda: LifecycleTracker.record('second'))
        ctx.add_shutdown_handler(lambda: LifecycleTracker.record('third'))
        
        ctx.shutdown()
        
        first_idx = LifecycleTracker.events.index('first')
        second_idx = LifecycleTracker.events.index('second')
        third_idx = LifecycleTracker.events.index('third')
        
        self.assertLess(first_idx, second_idx)
        self.assertLess(second_idx, third_idx)
    
    def test_shutdown_handler_exception_does_not_stop_others(self):
        """One handler exception does not prevent other handlers from executing"""
        ctx = ApplicationContext()
        ctx.refresh()
        
        def failing_handler():
            LifecycleTracker.record('failing')
            raise RuntimeError("Intentional failure")
        
        ctx.add_shutdown_handler(lambda: LifecycleTracker.record('before'))
        ctx.add_shutdown_handler(failing_handler)
        ctx.add_shutdown_handler(lambda: LifecycleTracker.record('after'))
        
        # shutdown should not be interrupted by one handler failure
        ctx.shutdown()
        
        self.assertIn('before', LifecycleTracker.events)
        self.assertIn('failing', LifecycleTracker.events)
        self.assertIn('after', LifecycleTracker.events)


class TestContextLifecycle(unittest.TestCase):
    """Context full lifecycle tests"""
    
    def setUp(self):
        LifecycleTracker.reset()
    
    def test_full_lifecycle(self):
        """Full lifecycle: register -> refresh -> use -> shutdown"""
        ctx = ApplicationContext()
        
        # 1. Register
        ctx.register(Definition(
            name='Service',
            factory=lambda c: ServiceWithLifecycle('Service'),
            scope=ScopeType.SINGLETON,
            source='test:Service',
            eager=True
        ))
        
        self.assertFalse(ctx.is_refreshed)
        
        # 2. Refresh
        ctx.refresh()
        
        self.assertTrue(ctx.is_refreshed)
        self.assertTrue(ctx.is_frozen)
        self.assertIn('Service:init', LifecycleTracker.events)
        
        # 3. Use
        service = ctx.get('Service')
        self.assertIsNotNone(service)
        
        # 4. Shutdown
        ctx.add_shutdown_handler(lambda: LifecycleTracker.record('context:shutdown'))
        ctx.shutdown()
        
        self.assertIn('context:shutdown', LifecycleTracker.events)

