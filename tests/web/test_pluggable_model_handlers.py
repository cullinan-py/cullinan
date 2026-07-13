# -*- coding: utf-8 -*-
"""Pluggable model handler tests"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass
from typing import Optional


def test_registry_basic():
    """Test registry basic functionality"""
    print("1. Testing registry basic functionality...")

    from cullinan.web.params.model_handlers import (
        get_model_handler_registry,
        reset_model_handler_registry,
        DataclassHandler,
    )

    # Reset registry
    reset_model_handler_registry()

    # Get registry
    registry = get_model_handler_registry()

    # Check auto-discovery
    handlers = registry.get_handler_names()
    assert 'dataclass' in handlers, f"Expected 'dataclass' in {handlers}"

    print(f"   Registered handlers: {handlers}")
    print("   Basic functionality test passed")


def test_dataclass_handler():
    """Test dataclass handler"""
    print("2. Testing dataclass handler...")

    from cullinan.web.params.model_handlers import (
        get_model_handler_registry,
        reset_model_handler_registry,
    )

    reset_model_handler_registry()
    registry = get_model_handler_registry()

    @dataclass
    class User:
        name: str
        age: int = 0
        email: Optional[str] = None

    # Check can handle
    handler = registry.get_handler(User)
    assert handler is not None
    assert handler.name == 'dataclass'

    # Test resolution
    data = {'name': 'John', 'age': '25', 'email': 'john@example.com'}
    user = handler.resolve(User, data)

    assert user.name == 'John'
    assert user.age == 25
    assert user.email == 'john@example.com'

    # Test to_dict
    result = handler.to_dict(user)
    assert result['name'] == 'John'
    assert result['age'] == 25

    print("   dataclass handler test passed")


def test_param_resolver_with_dataclass():
    """Test ParamResolver using registry"""
    print("3. Testing ParamResolver with model handlers...")

    from cullinan.web.params import ParamResolver
    from cullinan.web.params.model_handlers import reset_model_handler_registry

    reset_model_handler_registry()

    @dataclass
    class CreateUserRequest:
        name: str
        age: int = 0

    def handler(self, user: CreateUserRequest):
        pass

    # Analyze parameters
    config = ParamResolver.analyze_params(handler)

    assert 'user' in config
    assert config['user']['source'] == 'body'
    assert config['user'].get('model_handler') is not None
    assert config['user']['model_handler'].name == 'dataclass'

    print("   ParamResolver model handler integration test passed")


def test_custom_handler():
    """Test custom handler registration"""
    print("4. Testing custom handler registration...")

    from cullinan.web.params.model_handlers import (
        ModelHandler,
        ModelHandlerError,
        get_model_handler_registry,
        reset_model_handler_registry,
    )

    reset_model_handler_registry()

    # Create custom handler
    class CustomModel:
        """Custom model class"""
        def __init__(self, data):
            self.data = data

    class CustomHandler(ModelHandler):
        priority = 100  # High priority
        name = "custom"

        def can_handle(self, type_):
            return type_ is CustomModel

        def resolve(self, model_class, data):
            return CustomModel(data)

        def to_dict(self, instance):
            return instance.data

    # Register custom handler
    registry = get_model_handler_registry()
    registry.register(CustomHandler())

    # Check registration
    assert 'custom' in registry.get_handler_names()

    # Check priority (custom should be first)
    handlers = registry.handlers
    assert handlers[0].name == 'custom'

    # Test resolution
    handler = registry.get_handler(CustomModel)
    assert handler.name == 'custom'

    instance = handler.resolve(CustomModel, {'key': 'value'})
    assert instance.data == {'key': 'value'}

    print("   custom handler test passed")


def test_pydantic_handler_optional():
    """Test Pydantic handler (optional)"""
    print("5. Testing Pydantic handler...")

    from cullinan.web.params.model_handlers import (
        get_model_handler_registry,
        reset_model_handler_registry,
    )

    reset_model_handler_registry()
    registry = get_model_handler_registry()

    handlers = registry.get_handler_names()

    if 'pydantic' in handlers:
        print("   Pydantic is installed, testing Pydantic handler...")

        from pydantic import BaseModel

        class PydanticUser(BaseModel):
            name: str
            age: int = 0

        handler = registry.get_handler(PydanticUser)
        assert handler is not None
        assert handler.name == 'pydantic'

        # Test resolution
        data = {'name': 'Jane', 'age': 30}
        user = handler.resolve(PydanticUser, data)

        assert user.name == 'Jane'
        assert user.age == 30

        print("   Pydantic handler test passed")
    else:
        print("   Pydantic not installed, skipping Pydantic tests")

    return None


def test_handler_priority():
    """Test handler priority"""
    print("6. Testing handler priority...")

    from cullinan.web.params.model_handlers import (
        get_model_handler_registry,
        reset_model_handler_registry,
    )

    reset_model_handler_registry()
    registry = get_model_handler_registry()

    handlers = registry.handlers

    # Check priority sorting (descending)
    for i in range(len(handlers) - 1):
        assert handlers[i].priority >= handlers[i+1].priority, \
            f"Handler priority not sorted: {handlers[i].name}({handlers[i].priority}) < {handlers[i+1].name}({handlers[i+1].priority})"

    print(f"   Handler priority order: {[(h.name, h.priority) for h in handlers]}")
    print("   Handler priority test passed")
