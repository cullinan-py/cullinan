# -*- coding: utf-8 -*-
"""Tests for Duck Typing lifecycle - no inheritance required.

Verifies that lifecycle methods are called even when classes
don't inherit from Service, SmartLifecycle, or LifecycleAware.
"""

import pytest

from cullinan.core import ApplicationContext, set_application_context
from cullinan.core.pending import PendingRegistry
from cullinan.core.decorators import service, component, controller

pytestmark = pytest.mark.filterwarnings(
    "ignore::cullinan.core.semantic_rules.ComponentDiscoveryWarning"
)


def test_service_without_inheritance():
    """Test @service without inheriting Service base class"""
    PendingRegistry.reset()

    lifecycle_calls = []

    # Define a service without inheriting any base class
    @service
    class PlainService:
        """A service that doesn't inherit from Service"""

        def on_post_construct(self):
            lifecycle_calls.append('PlainService.on_post_construct')

        def on_startup(self):
            lifecycle_calls.append('PlainService.on_startup')

        def on_shutdown(self):
            lifecycle_calls.append('PlainService.on_shutdown')

        def on_pre_destroy(self):
            lifecycle_calls.append('PlainService.on_pre_destroy')

        def do_something(self):
            return "working"

    # Create ApplicationContext
    ctx = ApplicationContext()
    set_application_context(ctx)
    ctx.refresh()

    # Verify startup lifecycle was called
    assert 'PlainService.on_post_construct' in lifecycle_calls, \
        f"on_post_construct not called. Calls: {lifecycle_calls}"
    assert 'PlainService.on_startup' in lifecycle_calls, \
        f"on_startup not called. Calls: {lifecycle_calls}"

    # Verify service works normally
    svc = ctx.get('PlainService')
    assert svc.do_something() == "working"

    # Shutdown
    lifecycle_calls.clear()
    ctx.shutdown()

    # Verify shutdown lifecycle was called
    assert 'PlainService.on_shutdown' in lifecycle_calls, \
        f"on_shutdown not called. Calls: {lifecycle_calls}"
    assert 'PlainService.on_pre_destroy' in lifecycle_calls, \
        f"on_pre_destroy not called. Calls: {lifecycle_calls}"

def test_component_without_inheritance():
    """Test @component without inheriting any base class"""
    PendingRegistry.reset()

    lifecycle_calls = []

    @component
    class CacheManager:
        """A component that doesn't inherit from anything"""

        def __init__(self):
            self._cache = {}

        def on_post_construct(self):
            lifecycle_calls.append('CacheManager.on_post_construct')
            self._cache['initialized'] = True

        def on_startup(self):
            lifecycle_calls.append('CacheManager.on_startup')

        def get(self, key):
            return self._cache.get(key)

        def set(self, key, value):
            self._cache[key] = value

    ctx = ApplicationContext()
    set_application_context(ctx)
    ctx.refresh()

    # Verify lifecycle was called
    assert 'CacheManager.on_post_construct' in lifecycle_calls
    assert 'CacheManager.on_startup' in lifecycle_calls

    # Verify component works normally
    cache = ctx.get('CacheManager')
    assert cache.get('initialized') == True
    cache.set('test', 'value')
    assert cache.get('test') == 'value'

    ctx.shutdown()


def test_controller_without_inheritance():
    """Test @controller without inheriting any base class"""
    PendingRegistry.reset()

    lifecycle_calls = []

    @controller(url='/api')
    class ApiController:
        """A controller that doesn't inherit from anything"""

        def on_startup(self):
            lifecycle_calls.append('ApiController.on_startup')

        def on_shutdown(self):
            lifecycle_calls.append('ApiController.on_shutdown')

    ctx = ApplicationContext()
    set_application_context(ctx)
    ctx.refresh()

    assert 'ApiController.on_startup' in lifecycle_calls

    lifecycle_calls.clear()
    ctx.shutdown()

    assert 'ApiController.on_shutdown' in lifecycle_calls

def test_get_phase_without_inheritance():
    """Test get_phase() works without inheriting SmartLifecycle"""
    PendingRegistry.reset()

    startup_order = []

    @service
    class EarlyService:
        """Should start first (phase = -100)"""

        def get_phase(self):
            return -100

        def on_startup(self):
            startup_order.append('EarlyService')

    @service
    class LateService:
        """Should start last (phase = 100)"""

        def get_phase(self):
            return 100

        def on_startup(self):
            startup_order.append('LateService')

    @service
    class DefaultService:
        """Default phase (0)"""

        def on_startup(self):
            startup_order.append('DefaultService')

    ctx = ApplicationContext()
    set_application_context(ctx)
    ctx.refresh()

    # Verify startup order: EarlyService (-100) -> DefaultService (0) -> LateService (100)
    assert startup_order == ['EarlyService', 'DefaultService', 'LateService'], \
        f"Wrong order: {startup_order}"

    ctx.shutdown()


def test_async_lifecycle_without_inheritance():
    """Test async lifecycle methods without inheritance"""
    import asyncio

    PendingRegistry.reset()

    lifecycle_calls = []

    @service
    class AsyncService:
        """Async lifecycle without inheritance"""

        async def on_startup_async(self):
            await asyncio.sleep(0.001)
            lifecycle_calls.append('AsyncService.on_startup_async')

        async def on_shutdown_async(self):
            await asyncio.sleep(0.001)
            lifecycle_calls.append('AsyncService.on_shutdown_async')

    ctx = ApplicationContext()
    set_application_context(ctx)
    ctx.refresh()

    assert 'AsyncService.on_startup_async' in lifecycle_calls

    lifecycle_calls.clear()
    ctx.shutdown()

    assert 'AsyncService.on_shutdown_async' in lifecycle_calls

def test_mixed_inheritance_and_plain():
    """Test mix of classes with and without inheritance"""
    from cullinan.core.services import Service

    PendingRegistry.reset()

    lifecycle_calls = []

    @service
    class PlainService:
        def on_startup(self):
            lifecycle_calls.append('PlainService')

    @service
    class InheritedService(Service):
        def on_startup(self):
            lifecycle_calls.append('InheritedService')

    ctx = ApplicationContext()
    set_application_context(ctx)
    ctx.refresh()

    # Both should be called
    assert 'PlainService' in lifecycle_calls
    assert 'InheritedService' in lifecycle_calls

    ctx.shutdown()
