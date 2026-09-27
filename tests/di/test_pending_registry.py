# -*- coding: utf-8 -*-
"""Tests for PendingRegistry.

Author: plumeink
"""

import pytest
import threading
from cullinan.core.pending import (
    PendingRegistry,
    PendingRegistration,
    ComponentType
)


class TestPendingRegistration:
    """Tests for PendingRegistration dataclass."""

    def test_basic_creation(self):
        """Test basic registration creation."""
        class MyService:
            pass

        reg = PendingRegistration(
            cls=MyService,
            name="MyService",
            component_type=ComponentType.SERVICE
        )

        assert reg.cls is MyService
        assert reg.name == "MyService"
        assert reg.component_type == ComponentType.SERVICE
        assert reg.scope == "singleton"
        assert reg.dependencies is None
        assert reg.conditions == []

    def test_controller_fields(self):
        """Test controller-specific fields."""
        class UserController:
            pass

        reg = PendingRegistration(
            cls=UserController,
            name="UserController",
            component_type=ComponentType.CONTROLLER,
            url_prefix="/api/users",
            routes=[{"path": "/", "method": "GET"}]
        )

        assert reg.url_prefix == "/api/users"
        assert len(reg.routes) == 1

    def test_source_location(self):
        """Test source location formatting."""
        class MyService:
            pass

        reg = PendingRegistration(
            cls=MyService,
            name="MyService",
            component_type=ComponentType.SERVICE,
            source_file="/path/to/service.py",
            source_line=42
        )

        assert reg.get_source_location() == "/path/to/service.py:42"

        # Test without line number
        reg2 = PendingRegistration(
            cls=MyService,
            name="MyService2",
            component_type=ComponentType.SERVICE,
            source_file="/path/to/service.py"
        )
        assert reg2.get_source_location() == "/path/to/service.py"

        # Test without source info
        reg3 = PendingRegistration(
            cls=MyService,
            name="MyService3",
            component_type=ComponentType.SERVICE
        )
        assert reg3.get_source_location() == "<unknown>"


class TestPendingRegistry:
    """Tests for PendingRegistry singleton."""

    def setup_method(self):
        """Reset registry before each test."""
        PendingRegistry.reset()

    def teardown_method(self):
        """Reset registry after each test."""
        PendingRegistry.reset()

    def test_singleton(self):
        """Test singleton pattern."""
        instance1 = PendingRegistry.get_instance()
        instance2 = PendingRegistry.get_instance()

        assert instance1 is instance2

    def test_add_and_get_all(self):
        """Test adding and retrieving registrations."""
        registry = PendingRegistry.get_instance()

        class ServiceA:
            pass

        class ServiceB:
            pass

        reg_a = PendingRegistration(
            cls=ServiceA,
            name="ServiceA",
            component_type=ComponentType.SERVICE
        )
        reg_b = PendingRegistration(
            cls=ServiceB,
            name="ServiceB",
            component_type=ComponentType.SERVICE
        )

        registry.add(reg_a)
        registry.add(reg_b)

        all_regs = registry.get_all()
        assert len(all_regs) == 2
        assert reg_a in all_regs
        assert reg_b in all_regs

    def test_get_by_type(self):
        """Test filtering by component type."""
        registry = PendingRegistry.get_instance()

        class MyService:
            pass

        class MyController:
            pass

        registry.add(PendingRegistration(
            cls=MyService,
            name="MyService",
            component_type=ComponentType.SERVICE
        ))
        registry.add(PendingRegistration(
            cls=MyController,
            name="MyController",
            component_type=ComponentType.CONTROLLER
        ))

        services = registry.get_by_type(ComponentType.SERVICE)
        controllers = registry.get_by_type(ComponentType.CONTROLLER)

        assert len(services) == 1
        assert services[0].name == "MyService"
        assert len(controllers) == 1
        assert controllers[0].name == "MyController"

    def test_get_by_name(self):
        """Test finding by name."""
        registry = PendingRegistry.get_instance()

        class MyService:
            pass

        registry.add(PendingRegistration(
            cls=MyService,
            name="MyService",
            component_type=ComponentType.SERVICE
        ))

        found = registry.get_by_name("MyService")
        assert found is not None
        assert found.cls is MyService

        not_found = registry.get_by_name("NotExists")
        assert not_found is None

    def test_contains(self):
        """Test contains check."""
        registry = PendingRegistry.get_instance()

        class MyService:
            pass

        registry.add(PendingRegistration(
            cls=MyService,
            name="MyService",
            component_type=ComponentType.SERVICE
        ))

        assert registry.contains("MyService") is True
        assert registry.contains("NotExists") is False

    def test_freeze(self):
        """Test freezing prevents further additions."""
        registry = PendingRegistry.get_instance()

        class ServiceA:
            pass

        class ServiceB:
            pass

        registry.add(PendingRegistration(
            cls=ServiceA,
            name="ServiceA",
            component_type=ComponentType.SERVICE
        ))

        registry.freeze()
        assert registry.is_frozen is True

        with pytest.raises(RuntimeError) as exc_info:
            registry.add(PendingRegistration(
                cls=ServiceB,
                name="ServiceB",
                component_type=ComponentType.SERVICE
            ))

        message = str(exc_info.value)
        assert "ServiceB" in message
        assert "ApplicationContext.refresh()" in message

    def test_clear(self):
        """Test clearing all registrations."""
        registry = PendingRegistry.get_instance()

        class MyService:
            pass

        registry.add(PendingRegistration(
            cls=MyService,
            name="MyService",
            component_type=ComponentType.SERVICE
        ))

        assert registry.count == 1

        registry.clear()
        assert registry.count == 0
        assert len(registry.get_all()) == 0

    def test_clear_frozen_raises(self):
        """clear() on frozen registry raises RuntimeError."""
        registry = PendingRegistry.get_instance()

        class MyService:
            pass

        registry.add(PendingRegistration(
            cls=MyService,
            name="MyService",
            component_type=ComponentType.SERVICE
        ))
        registry.freeze()

        with pytest.raises(RuntimeError, match=r"frozen|cannot clear"):
            registry.clear()

        # reset() should still work from class level
        PendingRegistry.reset()
        new_registry = PendingRegistry.get_instance()
        assert new_registry.count == 0

    def test_count_and_len(self):
        """Test count property and len()."""
        registry = PendingRegistry.get_instance()

        assert registry.count == 0
        assert len(registry) == 0

        class MyService:
            pass

        registry.add(PendingRegistration(
            cls=MyService,
            name="MyService",
            component_type=ComponentType.SERVICE
        ))

        assert registry.count == 1
        assert len(registry) == 1

    def test_reset(self):
        """Test reset clears and unfreezes."""
        registry = PendingRegistry.get_instance()

        class MyService:
            pass

        registry.add(PendingRegistration(
            cls=MyService,
            name="MyService",
            component_type=ComponentType.SERVICE
        ))
        registry.freeze()

        PendingRegistry.reset()

        new_registry = PendingRegistry.get_instance()
        assert new_registry.count == 0
        assert new_registry.is_frozen is False

    def test_thread_safety(self):
        """Test thread-safe additions."""
        registry = PendingRegistry.get_instance()

        def add_registrations(start_idx: int, count: int):
            for i in range(count):
                class DynamicClass:
                    pass
                DynamicClass.__name__ = f"Service_{start_idx}_{i}"

                registry.add(PendingRegistration(
                    cls=DynamicClass,
                    name=f"Service_{start_idx}_{i}",
                    component_type=ComponentType.SERVICE
                ))

        threads = []
        for i in range(5):
            t = threading.Thread(target=add_registrations, args=(i, 10))
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert registry.count == 50

    def test_repr(self):
        """Test string representation."""
        registry = PendingRegistry.get_instance()

        repr_str = repr(registry)
        assert "PendingRegistry" in repr_str
        assert "count=0" in repr_str
        assert "frozen=False" in repr_str
