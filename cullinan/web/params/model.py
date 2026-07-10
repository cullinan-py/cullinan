# -*- coding: utf-8 -*-
"""Cullinan Model Resolver

Dataclass model resolver, maps request data to dataclass instances.

Author: Cullinan
"""

import dataclasses
from typing import Any, Dict, Type, get_type_hints, Union

from .converter import TypeConverter, ConversionError


class ModelError(Exception):
    """Model resolution error

    Attributes:
        message: Error message
        model_class: Model class
        field_errors: List of field errors
    """

    def __init__(
        self,
        message: str,
        model_class: Type = None,
        field_errors: list = None
    ):
        super().__init__(message)
        self.message = message
        self.model_class = model_class
        self.field_errors = field_errors or []

    def __repr__(self) -> str:
        return f"ModelError({self.message!r}, model={self.model_class})"

    def to_dict(self) -> dict:
        """Convert to dict format"""
        return {
            'message': self.message,
            'model': self.model_class.__name__ if self.model_class else None,
            'field_errors': self.field_errors,
        }


class ModelResolver:
    """Model resolver

    Maps request data (dict) to dataclass instances.

    Features:
    - Automatic type conversion
    - Supports nested dataclasses
    - Supports default values
    - Supports optional fields (Optional)

    Example:
        from dataclasses import dataclass

        @dataclass
        class CreateUserRequest:
            name: str
            age: int = 0

        resolver = ModelResolver()
        data = {'name': 'test', 'age': '25'}
        user = resolver.resolve(CreateUserRequest, data)
        # user.name = 'test', user.age = 25
    """

    @classmethod
    def is_dataclass(cls, obj: Any) -> bool:
        """Check if it is a dataclass type

        Args:
            obj: Object to check

        Returns:
            Whether it is a dataclass
        """
        return dataclasses.is_dataclass(obj) and isinstance(obj, type)

    @classmethod
    def resolve(cls, model_class: Type, data: Dict[str, Any]) -> Any:
        """Parse dict data into a model instance

        Args:
            model_class: dataclass class
            data: Request data dict

        Returns:
            dataclass instance

        Raises:
            ModelError: Resolution failed
        """
        if not cls.is_dataclass(model_class):
            raise ModelError(
                f"{model_class} is not a dataclass",
                model_class=model_class
            )

        if data is None:
            data = {}

        # Get field information
        fields = dataclasses.fields(model_class)
        type_hints = get_type_hints(model_class)

        # Build kwargs
        kwargs = {}
        field_errors = []

        for field in fields:
            field_name = field.name
            field_type = type_hints.get(field_name, field.type)

            # Check if a value was provided
            if field_name in data:
                raw_value = data[field_name]

                try:
                    # Resolve nested dataclass
                    if cls.is_dataclass(field_type):
                        if isinstance(raw_value, dict):
                            kwargs[field_name] = cls.resolve(field_type, raw_value)
                        elif isinstance(raw_value, field_type):
                            kwargs[field_name] = raw_value
                        else:
                            raise ModelError(
                                f"Cannot convert {type(raw_value).__name__} to {field_type.__name__}"
                            )
                    else:
                        # Handle Optional types
                        actual_type = cls._unwrap_optional(field_type)
                        if raw_value is None:
                            kwargs[field_name] = None
                        elif actual_type is not None:
                            kwargs[field_name] = TypeConverter.convert(raw_value, actual_type)
                        else:
                            kwargs[field_name] = raw_value

                except (ConversionError, ModelError) as e:
                    field_errors.append({
                        'field': field_name,
                        'error': str(e),
                        'value': raw_value
                    })
            else:
                # No value provided
                if field.default is not dataclasses.MISSING:
                    # Has default value, use default
                    kwargs[field_name] = field.default
                elif field.default_factory is not dataclasses.MISSING:
                    # Has default factory, call factory
                    kwargs[field_name] = field.default_factory()
                elif cls._is_optional(field_type):
                    # Optional type, set to None
                    kwargs[field_name] = None
                else:
                    # Required field is missing
                    field_errors.append({
                        'field': field_name,
                        'error': f"Field '{field_name}' is required",
                        'value': None
                    })

        if field_errors:
            raise ModelError(
                f"Failed to resolve model {model_class.__name__}",
                model_class=model_class,
                field_errors=field_errors
            )

        try:
            return model_class(**kwargs)
        except Exception as e:
            raise ModelError(
                f"Failed to create {model_class.__name__}: {e}",
                model_class=model_class
            )

    @classmethod
    def _is_optional(cls, type_hint) -> bool:
        """Check if the type is Optional

        Args:
            type_hint: Type hint

        Returns:
            Whether it is Optional
        """
        # Optional[X] is equivalent to Union[X, None]
        origin = getattr(type_hint, '__origin__', None)
        if origin is Union:
            args = getattr(type_hint, '__args__', ())
            return type(None) in args
        return False

    @classmethod
    def _unwrap_optional(cls, type_hint) -> Type:
        """Extract X from Optional[X]

        Args:
            type_hint: Type hint

        Returns:
            The inner type, or the original type if not Optional
        """
        origin = getattr(type_hint, '__origin__', None)
        if origin is Union:
            args = getattr(type_hint, '__args__', ())
            # Filter out NoneType
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return non_none[0]
        # Not Optional, return the original type (if it is a basic type)
        if isinstance(type_hint, type):
            return type_hint
        return None

    @classmethod
    def to_dict(cls, instance: Any) -> Dict[str, Any]:
        """Convert dataclass instance to dict

        Args:
            instance: dataclass instance

        Returns:
            dict
        """
        if not dataclasses.is_dataclass(instance):
            raise ModelError(f"{type(instance)} is not a dataclass instance")

        result = {}
        for field in dataclasses.fields(instance):
            value = getattr(instance, field.name)
            if dataclasses.is_dataclass(value):
                result[field.name] = cls.to_dict(value)
            else:
                result[field.name] = value
        return result

