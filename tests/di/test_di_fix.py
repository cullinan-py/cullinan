# -*- coding: utf-8 -*-
"""Test ControllerRegistry dependency injection fix

Author: Cullinan
"""

import pytest

pytestmark = pytest.mark.filterwarnings(
    "ignore::cullinan.core.semantic_rules.ComponentDiscoveryWarning"
)


def reset_all_registries():
    """Reset all registries for independent testing"""
    from cullinan.web.controller.registry import reset_controller_registry
    from cullinan.core.pending import PendingRegistry
    from cullinan.core import set_application_context

    reset_controller_registry()
    PendingRegistry.reset()
    set_application_context(None)


def test_controller_di():
    """Test Controller dependency injection"""
    reset_all_registries()

    from cullinan.core import (
        ApplicationContext, 
        set_application_context, 
        get_application_context, 
        service, 
        controller, 
        Inject
    )

    # Create a test service
    @service
    class TestService:
        def get_message(self):
            return 'Hello from TestService'

    # Create a test controller
    @controller(url='/test')
    class TestController:
        test_service: TestService = Inject()
        
        def test_method(self):
            return self.test_service.get_message()

    # Create ApplicationContext and set global reference
    ctx = ApplicationContext()
    set_application_context(ctx)
    try:
        ctx.refresh()
        assert get_application_context() is not None
        assert ctx.is_refreshed is True

        from cullinan.web.controller.registry import get_controller_registry
        controller_registry = get_controller_registry()
        controller_registry.register('TestController', TestController, url_prefix='/test')

        instance = controller_registry.get_instance('TestController')

        assert isinstance(instance.test_service, Inject) is False
        assert hasattr(instance.test_service, 'get_message')
        assert instance.test_method() == 'Hello from TestService'
    finally:
        ctx.shutdown()
        reset_all_registries()


def test_multiple_services():
    """Test multiple services injection"""
    reset_all_registries()

    from cullinan.core import (
        ApplicationContext,
        set_application_context,
        service,
        controller,
        Inject
    )

    @service
    class ServiceA:
        def name(self):
            return 'ServiceA'

    @service
    class ServiceB:
        def name(self):
            return 'ServiceB'

    @controller(url='/multi')
    class MultiServiceController:
        service_a: ServiceA = Inject()
        service_b: ServiceB = Inject()

        def get_names(self):
            return f'{self.service_a.name()} + {self.service_b.name()}'

    # Create new ApplicationContext
    ctx = ApplicationContext()
    set_application_context(ctx)
    try:
        ctx.refresh()

        from cullinan.web.controller.registry import get_controller_registry
        controller_registry = get_controller_registry()
        controller_registry.register('MultiServiceController', MultiServiceController, url_prefix='/multi')

        instance = controller_registry.get_instance('MultiServiceController')
        assert hasattr(instance.service_a, 'name')
        assert hasattr(instance.service_b, 'name')
        assert instance.get_names() == 'ServiceA + ServiceB'
    finally:
        ctx.shutdown()
        reset_all_registries()


def test_optional_injection():
    """Test optional dependency injection"""
    reset_all_registries()

    from cullinan.core import (
        ApplicationContext,
        set_application_context,
        service,
        controller,
        Inject
    )

    @service
    class ExistingService:
        def exists(self):
            return True

    # Note: MissingService is not decorated with @service, so it won't be registered
    class MissingService:
        pass

    @controller(url='/optional')
    class OptionalController:
        existing: ExistingService = Inject()
        missing: MissingService = Inject(required=False)  # Optional dependency

    ctx = ApplicationContext()
    set_application_context(ctx)
    try:
        ctx.refresh()

        from cullinan.web.controller.registry import get_controller_registry
        controller_registry = get_controller_registry()
        controller_registry.register('OptionalController', OptionalController, url_prefix='/optional')

        instance = controller_registry.get_instance('OptionalController')
        assert hasattr(instance.existing, 'exists')
        assert instance.missing is None
    finally:
        ctx.shutdown()
        reset_all_registries()
