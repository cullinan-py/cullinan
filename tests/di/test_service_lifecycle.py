# -*- coding: utf-8 -*-
"""
Test Service lifecycle methods (using ApplicationContext)

Verify:
1. on_post_construct() is called
2. on_startup() is called
3. on_shutdown() is called
4. on_pre_destroy() is called
"""

import logging
import pytest

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

from cullinan.core import ApplicationContext, set_application_context, InjectByName
from cullinan.core.pending import PendingRegistry
from cullinan.core.services import service, Service

pytestmark = [
    pytest.mark.filterwarnings("ignore::cullinan.core.semantic_rules.ComponentDiscoveryWarning"),
    pytest.mark.filterwarnings("ignore::cullinan.core.semantic_rules.InjectionSemanticWarning"),
]


def test_service_lifecycle():
    # Reset state
    PendingRegistry.reset()

    # Record called methods
    lifecycle_calls = []

    @service
    class TestService(Service):
        def on_post_construct(self):
            """Called after construction"""
            lifecycle_calls.append('on_post_construct')

        def on_startup(self):
            """Called on startup"""
            lifecycle_calls.append('on_startup')

        def on_shutdown(self):
            """Called on shutdown"""
            lifecycle_calls.append('on_shutdown')

        def on_pre_destroy(self):
            """Called before destruction"""
            lifecycle_calls.append('on_pre_destroy')

    @service
    class DependentService(Service):
        """Service depending on TestService"""
        test_service = InjectByName('TestService')

        def on_post_construct(self):
            lifecycle_calls.append('DependentService.on_post_construct')

        def on_startup(self):
            lifecycle_calls.append('DependentService.on_startup')

    # Create ApplicationContext
    ctx = ApplicationContext()
    set_application_context(ctx)
    try:
        ctx.refresh()
        assert 'on_post_construct' in lifecycle_calls
        assert 'on_startup' in lifecycle_calls

        init_idx = lifecycle_calls.index('on_post_construct')
        startup_idx = lifecycle_calls.index('on_startup')
        assert init_idx < startup_idx

        test_idx = lifecycle_calls.index('on_post_construct')
        dep_idx = lifecycle_calls.index('DependentService.on_post_construct')
        assert test_idx < dep_idx
        lifecycle_calls.clear()
        ctx.shutdown()

        assert 'on_shutdown' in lifecycle_calls
        assert 'on_pre_destroy' in lifecycle_calls
    finally:
        set_application_context(None)
        PendingRegistry.reset()
