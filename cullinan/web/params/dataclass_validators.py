# -*- coding: utf-8 -*-
"""Cullinan Dataclass Validators

Provides field-level validation decorators for dataclasses.

Author: Cullinan
"""

from typing import Any, Callable, Dict, List, Type
import dataclasses


# Store field validators for each dataclass
_field_validators: Dict[Type, Dict[str, List[Callable]]] = {}


class FieldValidationError(Exception):
    """Field validation error

    Attributes:
        field: Field name
        value: Field value
        message: Error message
    """

    def __init__(self, field: str, value: Any, message: str):
        self.field = field
        self.value = value
        self.message = message
        super().__init__(f"Field '{field}' validation failed: {message}")

    def to_dict(self) -> dict:
        return {
            'field': self.field,
            'value': self.value,
            'message': self.message,
        }


def field_validator(*fields: str, mode: str = 'after'):
    """Field validator decorator

    Used to define field-level validation logic in a dataclass.

    Args:
        *fields: List of field names to validate
        mode: Validation mode
            - 'after': Validate after type conversion (default)
            - 'before': Validate before type conversion

    Example:
        from dataclasses import dataclass
        from cullinan.web.params import field_validator

        @dataclass
        class CreateUserRequest:
            name: str
            email: str
            age: int = 0

            @field_validator('email')
            @classmethod
            def validate_email(cls, v):
                if '@' not in v:
                    raise ValueError('Invalid email format')
                return v

            @field_validator('age')
            @classmethod
            def validate_age(cls, v):
                if v < 0 or v > 150:
                    raise ValueError('Age must be between 0 and 150')
                return v

            @field_validator('name', 'email')
            @classmethod
            def strip_strings(cls, v):
                if isinstance(v, str):
                    return v.strip()
                return v
    """
    def decorator(func: Callable) -> Callable:
        # Check if it's a classmethod
        if isinstance(func, classmethod):
            # Get the actual function
            actual_func = func.__func__
            # Mark validator attributes
            actual_func._is_field_validator = True
            actual_func._validator_fields = fields
            actual_func._validator_mode = mode
            # Return the original classmethod, preserving its type
            return func
        else:
            # Regular function
            func._is_field_validator = True
            func._validator_fields = fields
            func._validator_mode = mode
            return func

    return decorator


def register_validators(cls: Type) -> None:
    """Register all field validators for a dataclass

    Args:
        cls: dataclass class
    """
    if not dataclasses.is_dataclass(cls):
        return

    validators = {}

    # Scan validator methods in the class
    for name in dir(cls):
        if name.startswith('_'):
            continue

        try:
            # Use __dict__ to get directly, avoiding descriptor protocol
            if name in cls.__dict__:
                method = cls.__dict__[name]
            else:
                method = getattr(cls, name, None)
        except Exception:
            continue

        if method is None:
            continue

        # Handle classmethod wrapping
        actual_method = method
        if isinstance(method, classmethod):
            actual_method = method.__func__

        # Check if it's a validator
        if hasattr(actual_method, '_is_field_validator') and actual_method._is_field_validator:
            for field in actual_method._validator_fields:
                if field not in validators:
                    validators[field] = []
                validators[field].append({
                    'func': actual_method,
                    'mode': actual_method._validator_mode,
                })

    if validators:
        _field_validators[cls] = validators


def get_validators(cls: Type) -> Dict[str, List[dict]]:
    """Get field validators for a dataclass

    Args:
        cls: dataclass class

    Returns:
        Mapping of field names to validator lists
    """
    if cls not in _field_validators:
        register_validators(cls)
    return _field_validators.get(cls, {})


def validate_field(cls: Type, field: str, value: Any, mode: str = 'after') -> Any:
    """Validate a field value

    Args:
        cls: dataclass class
        field: Field name
        value: Field value
        mode: Validation mode

    Returns:
        Validated/converted value

    Raises:
        FieldValidationError: Validation failed
    """
    validators = get_validators(cls)
    field_validators = validators.get(field, [])

    for validator in field_validators:
        if validator['mode'] != mode:
            continue

        try:
            value = validator['func'](cls, value)
        except ValueError as e:
            raise FieldValidationError(field, value, str(e))
        except Exception as e:
            raise FieldValidationError(field, value, str(e))

    return value


def validate_dataclass(instance) -> None:
    """Validate an entire dataclass instance

    Args:
        instance: dataclass instance

    Raises:
        FieldValidationError: Validation failed
    """
    cls = type(instance)

    if not dataclasses.is_dataclass(cls):
        return

    validators = get_validators(cls)

    for field in dataclasses.fields(instance):
        field_name = field.name
        value = getattr(instance, field_name)

        # Execute after-mode validators
        if field_name in validators:
            for validator in validators[field_name]:
                if validator['mode'] == 'after':
                    try:
                        func = validator['func']
                        # Handle classmethod - need to use the class as the first argument
                        if isinstance(func, classmethod):
                            new_value = func.__func__(cls, value)
                        else:
                            # Regular function/method
                            new_value = func(cls, value)
                        setattr(instance, field_name, new_value)
                    except ValueError as e:
                        raise FieldValidationError(field_name, value, str(e))


class validated_dataclass:
    """Dataclass decorator with automatic validation

    Wraps @dataclass, automatically executes field validation after instantiation.

    Example:
        from cullinan.web.params import validated_dataclass, field_validator

        @validated_dataclass
        class CreateUserRequest:
            name: str
            email: str
            age: int = 0

            @field_validator('email')
            @classmethod
            def validate_email(cls, v):
                if '@' not in v:
                    raise ValueError('Invalid email format')
                return v
    """

    def __new__(cls, wrapped_cls=None, **kwargs):
        """Supports both @validated_dataclass and @validated_dataclass() usage"""
        if wrapped_cls is not None:
            # @validated_dataclass without parentheses
            return cls._wrap_class(wrapped_cls, kwargs)
        else:
            # @validated_dataclass() with parentheses
            def decorator(c):
                return cls._wrap_class(c, kwargs)
            return decorator

    @staticmethod
    def _wrap_class(cls, kwargs=None):
        """Wrap class"""
        if kwargs is None:
            kwargs = {}

        # Apply @dataclass
        if not dataclasses.is_dataclass(cls):
            cls = dataclasses.dataclass(cls, **kwargs)

        # Register validators (after @dataclass)
        register_validators(cls)

        # Save original __init__
        original_init = cls.__init__

        def new_init(self, *args, **kw):
            # Call original __init__
            original_init(self, *args, **kw)
            # Execute validation
            validate_dataclass(self)

        cls.__init__ = new_init

        return cls


def clear_validators():
    """Clear all registered validators (for testing)"""
    _field_validators.clear()

