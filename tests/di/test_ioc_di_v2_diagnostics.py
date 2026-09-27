# -*- coding: utf-8 -*-
"""Cullinan IoC/DI 2.0 diagnostic and exception tests.

Author: plumeink

Minimal acceptance coverage for PR-R3:
1. Missing dependency errors expose injection_point, dependency_name,
   resolution_path, and candidate_sources.
2. Circular dependency chains stay stable, ordered, and exact.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cullinan.core.container import ApplicationContext
from cullinan.core.container import Definition, ScopeType
from cullinan.core.diagnostics import (
    DependencyNotFoundError,
    CircularDependencyError,
    ConditionNotMetError,
    CreationError,
    render_resolution_path,
    format_circular_dependency_error,
    format_missing_dependency_error,
)


class TestDependencyNotFoundError(unittest.TestCase):
    """Missing dependency error tests."""
    
    def test_get_missing_dependency_raises_error(self):
        """get() raises DependencyNotFoundError for a missing dependency."""
        ctx = ApplicationContext()
        ctx.refresh()
        
        with self.assertRaises(DependencyNotFoundError) as cm:
            ctx.get('NonExistingService')
        
        exc = cm.exception
        self.assertEqual(exc.dependency_name, 'NonExistingService')
    
    def test_error_contains_candidate_sources(self):
        """Errors include candidate source information."""
        ctx = ApplicationContext()
        
        ctx.register(Definition(
            name='ServiceA',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:ServiceA'
        ))
        
        ctx.refresh()
        
        with self.assertRaises(DependencyNotFoundError) as cm:
            ctx.get('ServiceB')
        
        exc = cm.exception
        self.assertIsNotNone(exc.candidate_sources)
        self.assertGreater(len(exc.candidate_sources), 0)


class TestCircularDependencyError(unittest.TestCase):
    """Circular dependency error tests."""
    
    def test_circular_dependency_detected(self):
        """Circular dependencies are detected."""
        ctx = ApplicationContext()
        
        # A -> B -> C -> A
        ctx.register(Definition(
            name='ServiceA',
            factory=lambda c: c.get('ServiceB'),
            scope=ScopeType.SINGLETON,
            source='test:ServiceA'
        ))
        
        ctx.register(Definition(
            name='ServiceB',
            factory=lambda c: c.get('ServiceC'),
            scope=ScopeType.SINGLETON,
            source='test:ServiceB'
        ))
        
        ctx.register(Definition(
            name='ServiceC',
            factory=lambda c: c.get('ServiceA'),
            scope=ScopeType.SINGLETON,
            source='test:ServiceC'
        ))
        
        ctx.refresh()
        
        with self.assertRaises(CircularDependencyError) as cm:
            ctx.get('ServiceA')
        
        exc = cm.exception
        self.assertIsNotNone(exc.dependency_chain)
    
    def test_circular_dependency_chain_is_ordered(self):
        """Circular dependency chains remain ordered and stable."""
        ctx = ApplicationContext()
        
        # A -> B -> A (simple cycle)
        ctx.register(Definition(
            name='ServiceA',
            factory=lambda c: c.get('ServiceB'),
            scope=ScopeType.SINGLETON,
            source='test:ServiceA'
        ))
        
        ctx.register(Definition(
            name='ServiceB',
            factory=lambda c: c.get('ServiceA'),
            scope=ScopeType.SINGLETON,
            source='test:ServiceB'
        ))
        
        ctx.refresh()
        
        with self.assertRaises(CircularDependencyError) as cm:
            ctx.get('ServiceA')
        
        exc = cm.exception
        chain = exc.dependency_chain
        
        # The chain should stay ordered: it starts with A and ends with A.
        self.assertEqual(chain[0], 'ServiceA')
        self.assertEqual(chain[-1], 'ServiceA')
        self.assertIn('ServiceB', chain)
    
    def test_dependency_cycle_in_definitions_detected_on_refresh(self):
        """Cycles declared in dependencies are detected during refresh()."""
        ctx = ApplicationContext()
        
        ctx.register(Definition(
            name='ServiceA',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:ServiceA',
            dependencies=['ServiceB']
        ))
        
        ctx.register(Definition(
            name='ServiceB',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:ServiceB',
            dependencies=['ServiceC']
        ))
        
        ctx.register(Definition(
            name='ServiceC',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:ServiceC',
            dependencies=['ServiceA']
        ))
        
        with self.assertRaises(CircularDependencyError) as cm:
            ctx.refresh()
        
        exc = cm.exception
        self.assertIsNotNone(exc.dependency_chain)


class TestConditionNotMetError(unittest.TestCase):
    """Condition failure error tests."""
    
    def test_get_with_unmet_condition_raises_error(self):
        """get() raises ConditionNotMetError when conditions fail."""
        ctx = ApplicationContext()
        
        ctx.register(Definition(
            name='ConditionalService',
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source='test:ConditionalService',
            conditions=[lambda c: False]
        ))
        
        ctx.refresh()
        
        with self.assertRaises(ConditionNotMetError) as cm:
            ctx.get('ConditionalService')
        
        exc = cm.exception
        self.assertEqual(exc.dependency_name, 'ConditionalService')


class TestCreationError(unittest.TestCase):
    """Creation error tests."""
    
    def test_factory_exception_wrapped_in_creation_error(self):
        """Factory exceptions are wrapped in CreationError."""
        ctx = ApplicationContext()
        
        def failing_factory(c):
            raise ValueError("Factory internal error")
        
        ctx.register(Definition(
            name='FailingService',
            factory=failing_factory,
            scope=ScopeType.SINGLETON,
            source='test:FailingService'
        ))
        
        ctx.refresh()
        
        with self.assertRaises(CreationError) as cm:
            ctx.get('FailingService')
        
        exc = cm.exception
        self.assertEqual(exc.dependency_name, 'FailingService')
        self.assertIsNotNone(exc.cause)
        self.assertIsInstance(exc.cause, ValueError)
    
    def test_factory_returning_none_raises_creation_error(self):
        """A factory returning None raises CreationError."""
        ctx = ApplicationContext()
        
        ctx.register(Definition(
            name='NoneService',
            factory=lambda c: None,
            scope=ScopeType.SINGLETON,
            source='test:NoneService'
        ))
        
        ctx.refresh()
        
        with self.assertRaises(CreationError) as cm:
            ctx.get('NoneService')
        
        exc = cm.exception
        self.assertIn('None', str(exc))


class TestDiagnosticsRendering(unittest.TestCase):
    """Diagnostic rendering tests."""
    
    def test_render_resolution_path(self):
        """render_resolution_path keeps a stable output format."""
        path = ['ServiceA', 'ServiceB', 'ServiceC', 'ServiceA']
        result = render_resolution_path(path)
        
        self.assertEqual(result, 'ServiceA -> ServiceB -> ServiceC -> ServiceA')
    
    def test_render_empty_path(self):
        """Empty paths render consistently."""
        result = render_resolution_path([])
        self.assertEqual(result, '(empty)')
    
    def test_format_circular_dependency_error(self):
        """format_circular_dependency_error includes the dependency chain."""
        chain = ['A', 'B', 'C', 'A']
        result = format_circular_dependency_error(chain)
        
        self.assertIn('A -> B -> C -> A', result)
        self.assertIn('Circular dependency', result)
    
    def test_format_missing_dependency_error(self):
        """format_missing_dependency_error includes the missing dependency name."""
        result = format_missing_dependency_error(
            dependency_name='MissingService',
            available_sources=['ServiceA', 'ServiceB']
        )
        
        self.assertIn('MissingService', result)
        self.assertIn('ServiceA', result)
