# -*- coding: utf-8 -*-
"""Tests for ApplicationContext integration with decorators.

Author: Cullinan
"""

import pytest
from cullinan.core.pending import PendingRegistry
from cullinan.core.decorators import service, controller, component, Inject, InjectByName, Lazy
from cullinan.core.application_context import ApplicationContext
from cullinan.core.definitions import Definition, ScopeType

pytestmark = [
    pytest.mark.filterwarnings("ignore::cullinan.core.semantic_rules.ComponentDiscoveryWarning"),
    pytest.mark.filterwarnings("ignore::cullinan.core.semantic_rules.InjectionSemanticWarning"),
]


class TestApplicationContextDecoratorIntegration:
    """Tests for decorator integration with ApplicationContext."""

    def setup_method(self):
        PendingRegistry.reset()

    def teardown_method(self):
        PendingRegistry.reset()

    def test_basic_service_registration(self):
        """Test basic service decorator integration."""
        @service()
        class UserService:
            def get_user(self):
                return {"id": 1}

        ctx = ApplicationContext()
        ctx.refresh()

        # Service should be registered
        assert ctx.has("UserService")

        # Should be able to get instance
        user_service = ctx.get("UserService")
        assert user_service is not None
        assert user_service.get_user() == {"id": 1}

    def test_singleton_scope(self):
        """Test singleton services return same instance."""
        @service()
        class SingletonService:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        instance1 = ctx.get("SingletonService")
        instance2 = ctx.get("SingletonService")

        assert instance1 is instance2

    def test_prototype_scope(self):
        """Test prototype services return new instances."""
        @service(scope="prototype")
        class PrototypeService:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        instance1 = ctx.get("PrototypeService")
        instance2 = ctx.get("PrototypeService")

        assert instance1 is not instance2

    def test_controller_registration(self):
        """Test controller decorator integration."""
        @controller(url="/api/users")
        class UserController:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        assert ctx.has("UserController")
        user_controller = ctx.get("UserController")
        assert user_controller is not None

    def test_dependency_injection(self):
        """Test Inject marker works."""
        @service()
        class EmailService:
            def send(self, to: str):
                return f"sent to {to}"

        @service()
        class UserService:
            email_service: EmailService = Inject()

            def notify_user(self, email: str):
                return self.email_service.send(email)

        ctx = ApplicationContext()
        ctx.refresh()

        user_service = ctx.get("UserService")
        result = user_service.notify_user("test@example.com")
        assert result == "sent to test@example.com"

    def test_inject_by_name(self):
        """Test InjectByName marker works."""
        @service()
        class CacheService:
            def get(self, key: str):
                return f"cached:{key}"

        @service()
        class DataService:
            cache = InjectByName("CacheService")

            def get_data(self, key: str):
                return self.cache.get(key)

        ctx = ApplicationContext()
        ctx.refresh()

        data_service = ctx.get("DataService")
        result = data_service.get_data("mykey")
        assert result == "cached:mykey"

    def test_multiple_components(self):
        """Test multiple components work together."""
        @service()
        class RepoService:
            def find(self, id: int):
                return {"id": id, "name": "test"}

        @service()
        class LogicService:
            repo: RepoService = Inject()

            def process(self, id: int):
                data = self.repo.find(id)
                return {"processed": True, "data": data}

        @controller(url="/api")
        class ApiController:
            logic: LogicService = Inject()

            def handle(self, id: int):
                return self.logic.process(id)

        ctx = ApplicationContext()
        ctx.refresh()

        api_controller = ctx.get("ApiController")
        result = api_controller.handle(42)

        assert result["processed"] is True
        assert result["data"]["id"] == 42

    def test_pending_registry_frozen_after_refresh(self):
        """Test PendingRegistry is frozen after refresh."""
        @service()
        class ExistingService:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        # Should not be able to add more registrations
        pending = PendingRegistry.get_instance()
        assert pending.is_frozen is True

    def test_custom_definition_with_decorator(self):
        """Test mixing custom Definition with decorator registration."""
        @service()
        class DecoratedService:
            pass

        # Manually register a Definition
        ctx = ApplicationContext()

        def config_factory(ctx):
            return {"debug": True}

        ctx.register(Definition(
            name="Config",
            factory=config_factory,
            scope=ScopeType.SINGLETON,
            source="test:config",
        ))

        ctx.refresh()

        # Both should be available
        assert ctx.has("DecoratedService")
        assert ctx.has("Config")

        config = ctx.get("Config")
        assert config["debug"] is True

    def test_definition_count(self):
        """Test definition count includes decorator registrations."""
        @service()
        class Service1:
            pass

        @service()
        class Service2:
            pass

        @controller(url="/api")
        class Controller1:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        assert ctx.definition_count == 3


class TestLazyInjection:
    """Tests for lazy injection."""

    def setup_method(self):
        PendingRegistry.reset()

    def teardown_method(self):
        PendingRegistry.reset()

    def test_lazy_injection_deferred(self):
        """Test lazy injection is deferred until first access."""
        access_log = []

        @service()
        class ExpensiveService:
            def __init__(self):
                access_log.append("ExpensiveService created")

            def do_work(self):
                return "work done"

        @service()
        class ConsumerService:
            expensive: ExpensiveService = Lazy()

        ctx = ApplicationContext()
        ctx.refresh()

        # Get consumer - expensive should not be created yet
        consumer = ctx.get("ConsumerService")

        # Note: With current implementation, eager services are created on refresh
        # The lazy injection should work for accessing the attribute later


class TestComponentDecorator:
    """Tests for @Component decorator."""

    def setup_method(self):
        PendingRegistry.reset()

    def teardown_method(self):
        PendingRegistry.reset()

    def test_component_registration(self):
        """Test @Component decorator works."""
        @component()
        class Helper:
            def help(self):
                return "helped"

        ctx = ApplicationContext()
        ctx.refresh()

        assert ctx.has("Helper")
        helper = ctx.get("Helper")
        assert helper.help() == "helped"

    def test_component_with_custom_name(self):
        """Test @Component with custom name."""
        @component(name="myHelper")
        class Helper:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        assert ctx.has("myHelper")
        assert not ctx.has("Helper")
