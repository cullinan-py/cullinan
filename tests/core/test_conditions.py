# -*- coding: utf-8 -*-
"""Tests for conditional decorators.

Author: plumeink
"""

import pytest
from cullinan.core.pending import PendingRegistry
from cullinan.core.decorators import service
from cullinan.core.conditions import (
    ConditionalOnProperty,
    ConditionalOnClass,
    ConditionalOnMissingBean,
    ConditionalOnBean,
    Conditional,
)
from cullinan.core.application_context import ApplicationContext
from cullinan.core.definitions import Definition, ScopeType

pytestmark = pytest.mark.filterwarnings(
    "ignore::cullinan.core.semantic_rules.ComponentDiscoveryWarning"
)


class TestConditionalOnClass:
    """Tests for @ConditionalOnClass decorator."""

    def setup_method(self):
        PendingRegistry.reset()

    def teardown_method(self):
        PendingRegistry.reset()

    def test_condition_met_existing_module(self):
        """Test condition is met when module exists."""
        @service()
        @ConditionalOnClass("json")
        class JsonService:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        assert ctx.has("JsonService")
        svc = ctx.get("JsonService")
        assert svc is not None

    def test_condition_not_met_missing_module(self):
        """Test condition is not met when module is missing."""
        @service()
        @ConditionalOnClass("nonexistent_module_xyz")
        class NonExistentService:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        # The service should be registered but condition check happens on resolve
        assert ctx.has("NonExistentService")

        # try_get should return None when condition not met
        svc = ctx.try_get("NonExistentService")
        assert svc is None


class TestConditionalOnMissingBean:
    """Tests for @ConditionalOnMissingBean decorator."""

    def setup_method(self):
        PendingRegistry.reset()

    def teardown_method(self):
        PendingRegistry.reset()

    def test_registers_when_bean_missing(self):
        """Test component registers when specified bean is missing."""
        @service()
        @ConditionalOnMissingBean("CustomCache")
        class DefaultCache:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        assert ctx.has("DefaultCache")
        cache = ctx.get("DefaultCache")
        assert cache is not None

    def test_skips_when_bean_exists(self):
        """Test component is skipped when specified bean exists."""
        @service()
        class CustomCache:
            pass

        @service()
        @ConditionalOnMissingBean("CustomCache")
        class DefaultCache:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        # Both should be registered
        assert ctx.has("CustomCache")
        assert ctx.has("DefaultCache")

        # CustomCache should work
        custom = ctx.get("CustomCache")
        assert custom is not None

        # DefaultCache condition should fail (CustomCache exists)
        default = ctx.try_get("DefaultCache")
        assert default is None


class TestConditionalOnBean:
    """Tests for @ConditionalOnBean decorator."""

    def setup_method(self):
        PendingRegistry.reset()

    def teardown_method(self):
        PendingRegistry.reset()

    def test_registers_when_bean_exists(self):
        """Test component registers when specified bean exists."""
        @service()
        class Database:
            pass

        @service()
        @ConditionalOnBean("Database")
        class DatabaseService:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        assert ctx.has("Database")
        assert ctx.has("DatabaseService")

        svc = ctx.get("DatabaseService")
        assert svc is not None

    def test_skips_when_bean_missing(self):
        """Test component is skipped when specified bean is missing."""
        @service()
        @ConditionalOnBean("NonExistentBean")
        class DependentService:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        assert ctx.has("DependentService")

        # Condition should fail
        svc = ctx.try_get("DependentService")
        assert svc is None


class TestCustomConditional:
    """Tests for @Conditional decorator with custom function."""

    def setup_method(self):
        PendingRegistry.reset()

    def teardown_method(self):
        PendingRegistry.reset()

    def test_custom_condition_true(self):
        """Test custom condition that returns True."""
        def always_true(ctx):
            return True

        @service()
        @Conditional(always_true)
        class AlwaysService:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        svc = ctx.get("AlwaysService")
        assert svc is not None

    def test_custom_condition_false(self):
        """Test custom condition that returns False."""
        def always_false(ctx):
            return False

        @service()
        @Conditional(always_false)
        class NeverService:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        svc = ctx.try_get("NeverService")
        assert svc is None


class TestMultipleConditions:
    """Tests for multiple conditions on same component."""

    def setup_method(self):
        PendingRegistry.reset()

    def teardown_method(self):
        PendingRegistry.reset()

    def test_all_conditions_must_pass(self):
        """Test that all conditions must pass."""
        def condition1(ctx):
            return True

        def condition2(ctx):
            return True

        @service()
        @Conditional(condition1)
        @Conditional(condition2)
        class MultiConditionService:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        svc = ctx.get("MultiConditionService")
        assert svc is not None

    def test_fails_if_any_condition_fails(self):
        """Test that component fails if any condition fails."""
        def condition_pass(ctx):
            return True

        def condition_fail(ctx):
            return False

        @service()
        @Conditional(condition_pass)
        @Conditional(condition_fail)
        class PartialConditionService:
            pass

        ctx = ApplicationContext()
        ctx.refresh()

        svc = ctx.try_get("PartialConditionService")
        assert svc is None
