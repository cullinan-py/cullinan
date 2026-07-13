# -*- coding: utf-8 -*-
"""Test SimpleRegistry duplicate registration policy

Verify behavior of error/warn/replace policies
"""

import pytest
from cullinan.core.registry import SimpleRegistry
from cullinan.core.exceptions import RegistryError


def test_duplicate_policy_error():
    """Test: error policy raises exception on duplicate registration"""

    registry = SimpleRegistry(duplicate_policy='error')

    registry.register('item1', 'value1')

    with pytest.raises(RegistryError) as exc_info:
        registry.register('item1', 'value2')

    assert 'already registered' in str(exc_info.value).lower()

    # Verify original value unchanged
    assert registry.get('item1') == 'value1'


def test_duplicate_policy_warn():
    """Test: warn policy logs warning and skips on duplicate registration"""

    registry = SimpleRegistry(duplicate_policy='warn')

    registry.register('item1', 'value1')

    # Should not raise exception
    registry.register('item1', 'value2')

    # Verify original value unchanged (keeps first registered value)
    assert registry.get('item1') == 'value1'


def test_duplicate_policy_replace():
    """Test: replace policy replaces existing item"""

    registry = SimpleRegistry(duplicate_policy='replace')

    registry.register('item1', 'value1')
    registry.register('item1', 'value2')

    # Verify value has been replaced
    assert registry.get('item1') == 'value2'


def test_default_policy_is_warn():
    """Test: default policy is warn (backward compatible)"""

    registry = SimpleRegistry()

    registry.register('item1', 'value1')
    registry.register('item1', 'value2')

    # Default should keep first registered value
    assert registry.get('item1') == 'value1'


def test_invalid_policy_raises_error():
    """Test: invalid policy parameter raises ValueError"""

    with pytest.raises(ValueError) as exc_info:
        SimpleRegistry(duplicate_policy='invalid')

    assert 'Invalid duplicate_policy' in str(exc_info.value)
    assert 'error' in str(exc_info.value)
    assert 'warn' in str(exc_info.value)
    assert 'replace' in str(exc_info.value)


def test_duplicate_policy_with_metadata():
    """Test: duplicate registration policy interaction with metadata"""

    # error policy
    registry_error = SimpleRegistry(duplicate_policy='error')
    registry_error.register('item1', 'value1', meta='old')

    with pytest.raises(RegistryError):
        registry_error.register('item1', 'value2', meta='new')

    assert registry_error.get_metadata('item1') == {'meta': 'old'}

    # replace policy
    registry_replace = SimpleRegistry(duplicate_policy='replace')
    registry_replace.register('item1', 'value1', meta='old')
    registry_replace.register('item1', 'value2', meta='new')

    assert registry_replace.get('item1') == 'value2'
    assert registry_replace.get_metadata('item1') == {'meta': 'new'}


def test_duplicate_policy_with_hooks():
    """Test: duplicate registration policy interaction with hooks"""

    pre_calls = []
    post_calls = []

    def pre_hook(name, item, metadata):
        pre_calls.append(name)

    def post_hook(name, item):
        post_calls.append(name)

    # warn policy: pre_hook will be called, but post_hook will not (because registration was skipped)
    registry = SimpleRegistry(duplicate_policy='warn')
    registry.add_hook('pre_register', pre_hook)
    registry.add_hook('post_register', post_hook)

    registry.register('item1', 'value1')
    registry.register('item1', 'value2')

    assert len(pre_calls) == 2  # pre_hook called both times
    assert len(post_calls) == 1  # post_hook only called the first time


def test_policy_error_mode_strict():
    """Test: error mode provides strict registration control"""

    registry = SimpleRegistry(duplicate_policy='error')

    # Successfully register multiple different items
    registry.register('item1', 'value1')
    registry.register('item2', 'value2')
    registry.register('item3', 'value3')

    assert registry.count() == 3

    # Attempting to duplicate-register any of them should fail
    with pytest.raises(RegistryError):
        registry.register('item1', 'new_value')

    with pytest.raises(RegistryError):
        registry.register('item2', 'new_value')

    # Verify all original values unchanged
    assert registry.get('item1') == 'value1'
    assert registry.get('item2') == 'value2'
    assert registry.get('item3') == 'value3'


def test_policy_replace_mode_override():
    """Test: replace mode allows override registration"""

    registry = SimpleRegistry(duplicate_policy='replace')

    # Register the same key multiple times
    registry.register('config', 'v1')
    registry.register('config', 'v2')
    registry.register('config', 'v3')

    # Last registration takes effect
    assert registry.get('config') == 'v3'
    assert registry.count() == 1

