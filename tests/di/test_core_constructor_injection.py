# -*- coding: utf-8 -*-
"""Verify the current semantics of the legacy constructor injection compatibility API in 0.93."""

import pytest

from cullinan.core import (
    ApplicationContext,
    get_injection_registry,
    inject_constructor,
    injectable,
    reset_injection_registry,
    service,
    set_application_context,
)
from cullinan.core.pending import PendingRegistry

pytestmark = [
    pytest.mark.filterwarnings("ignore::cullinan.core.semantic_rules.CompatibilitySemanticWarning"),
    pytest.mark.filterwarnings("ignore::cullinan.core.semantic_rules.ComponentDiscoveryWarning"),
]


def test_injectable_is_no_op_compatibility_decorator():
    class PlainClass:
        pass

    assert injectable(PlainClass) is PlainClass


def test_inject_constructor_is_no_op_compatibility_decorator():
    class PlainClass:
        pass

    assert inject_constructor(PlainClass) is PlainClass


def test_legacy_injection_registry_accessor_returns_none():
    reset_injection_registry()
    assert get_injection_registry() is None


def test_legacy_injection_registry_reset_is_safe_no_op():
    reset_injection_registry()


def test_compatibility_decorators_do_not_block_application_context():
    PendingRegistry.reset()

    @inject_constructor
    @injectable
    @service
    class LegacyCompatibleService:
        def __init__(self):
            self.ready = True

    ctx = ApplicationContext()
    set_application_context(ctx)
    try:
        ctx.refresh()
        instance = ctx.get("LegacyCompatibleService")
        assert instance.ready is True
    finally:
        ctx.shutdown()
        set_application_context(None)
        PendingRegistry.reset()
