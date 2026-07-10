# -*- coding: utf-8 -*-
"""Cullinan IoC/DI 2.0 - Factory Integration Tests

Author: Cullinan

Minimal acceptance test set for PR-R4:
1. Real injection based on existing injection capabilities
2. Structured diagnostics on injection failure
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cullinan.core.container import ApplicationContext
from cullinan.core.container import Definition, ScopeType
from cullinan.core.container import Factory


class UserRepository:
    """Mock Repository"""

    def get_user(self, user_id: int) -> dict:
        return {'id': user_id, 'name': f'User{user_id}'}


class UserService:
    """Mock Service, depends on Repository"""

    def __init__(self, repo: UserRepository):
        self.repo = repo

    def find_user(self, user_id: int) -> dict:
        return self.repo.get_user(user_id)


class TestFactoryBasics(unittest.TestCase):
    """Factory basic functionality tests"""

    def test_factory_resolve_delegates_to_context(self):
        """Factory.resolve delegates to Context"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='UserRepository',
            factory=lambda c: UserRepository(),
            scope=ScopeType.SINGLETON,
            source='test:UserRepository'
        ))

        ctx.refresh()

        factory = Factory(ctx)
        instance = factory.resolve(ctx.get_definition('UserRepository'))

        self.assertIsInstance(instance, UserRepository)

    def test_factory_create_raw_bypasses_cache(self):
        """Factory.create_raw bypasses cache and creates new instance each time"""
        ctx = ApplicationContext()

        call_count = [0]

        def counting_factory(c):
            call_count[0] += 1
            return UserRepository()

        definition = Definition(
            name='UserRepository',
            factory=counting_factory,
            scope=ScopeType.SINGLETON,
            source='test:UserRepository'
        )

        ctx.register(definition)
        ctx.refresh()

        factory = Factory(ctx)

        # create_raw calls factory every time
        instance1 = factory.create_raw(definition)
        instance2 = factory.create_raw(definition)

        self.assertIsNot(instance1, instance2)
        self.assertEqual(call_count[0], 2)


class TestDependencyInjectionViaContext(unittest.TestCase):
    """Dependency injection via Context tests"""

    def test_manual_dependency_injection(self):
        """Manual dependency injection (calling ctx.get in factory)"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='UserRepository',
            factory=lambda c: UserRepository(),
            scope=ScopeType.SINGLETON,
            source='test:UserRepository'
        ))

        ctx.register(Definition(
            name='UserService',
            factory=lambda c: UserService(c.get('UserRepository')),
            scope=ScopeType.SINGLETON,
            source='test:UserService'
        ))

        ctx.refresh()

        service = ctx.get('UserService')

        self.assertIsInstance(service, UserService)
        self.assertIsInstance(service.repo, UserRepository)

        # Verify functionality works
        user = service.find_user(1)
        self.assertEqual(user['id'], 1)

    def test_dependency_chain_resolution(self):
        """Dependency chain resolution"""
        ctx = ApplicationContext()

        class Controller:
            def __init__(self, service: UserService):
                self.service = service

        ctx.register(Definition(
            name='UserRepository',
            factory=lambda c: UserRepository(),
            scope=ScopeType.SINGLETON,
            source='test:UserRepository'
        ))

        ctx.register(Definition(
            name='UserService',
            factory=lambda c: UserService(c.get('UserRepository')),
            scope=ScopeType.SINGLETON,
            source='test:UserService'
        ))

        ctx.register(Definition(
            name='UserController',
            factory=lambda c: Controller(c.get('UserService')),
            scope=ScopeType.SINGLETON,
            source='test:UserController'
        ))

        ctx.refresh()

        controller = ctx.get('UserController')

        self.assertIsInstance(controller.service, UserService)
        self.assertIsInstance(controller.service.repo, UserRepository)


class TestPostProcessors(unittest.TestCase):
    """Post-processor tests"""

    def test_post_processor_is_called(self):
        """Post-processor is called"""
        ctx = ApplicationContext()

        ctx.register(Definition(
            name='Service',
            factory=lambda c: UserRepository(),
            scope=ScopeType.SINGLETON,
            source='test:Service'
        ))

        ctx.refresh()

        factory = Factory(ctx)

        processed = []

        def track_processor(instance, definition):
            processed.append(definition.name)
            return instance

        factory.add_post_processor(track_processor)

        definition = ctx.get_definition('Service')
        factory.resolve(definition)

        self.assertIn('Service', processed)

