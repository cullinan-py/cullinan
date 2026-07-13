# -*- coding: utf-8 -*-
"""Cullinan Dataclass Model Handler

Built-in dataclass model handler.

Author: Cullinan
"""

import dataclasses
from typing import Any, Dict, Type, get_type_hints, Union

from .base import ModelHandler, ModelHandlerError


class DataclassHandler(ModelHandler):
    """Dataclass model handler

    Built-in handler for parsing Python dataclasses.

    Features:
    - Automatic type conversion
    - Supports nested dataclasses
    - Supports default values
    - Supports Optional types
    """

    priority = 10  # Lower than third-party libraries, serves as fallback
    name = "dataclass"

    def can_handle(self, type_: Type) -> bool:
        """Check if it is a dataclass"""
        if type_ is None:
            return False
        return dataclasses.is_dataclass(type_) and isinstance(type_, type)

    def resolve(self, model_class: Type, data: Dict[str, Any]) -> Any:
        """Parse data into a dataclass instance"""
        if not self.can_handle(model_class):
            raise ModelHandlerError(
                f"{model_class} is not a dataclass",
                model_class=model_class,
                handler_name=self.name,
            )

        if data is None:
            data = {}

        # Get field information
        fields = dataclasses.fields(model_class)
        type_hints = {}
        try:
            type_hints = get_type_hints(model_class)
        except Exception:
            pass

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
                    if self.can_handle(field_type):
                        if isinstance(raw_value, dict):
                            kwargs[field_name] = self.resolve(field_type, raw_value)
                        elif isinstance(raw_value, field_type):
                            kwargs[field_name] = raw_value
                        else:
                            raise ModelHandlerError(
                                f"Cannot convert {type(raw_value).__name__} to {field_type.__name__}"
                            )
                    else:
                        # Handle Optional types
                        actual_type = self._unwrap_optional(field_type)
                        if raw_value is None:
                            kwargs[field_name] = None
                        elif actual_type is not None:
                            kwargs[field_name] = self._convert_value(raw_value, actual_type)
                        else:
                            kwargs[field_name] = raw_value

                except ModelHandlerError as e:
                    field_errors.append({
                        'field': field_name,
                        'error': str(e),
                        'value': raw_value
                    })
                except Exception as e:
                    field_errors.append({
                        'field': field_name,
                        'error': str(e),
                        'value': raw_value
                    })
            else:
                # No value provided
                if field.default is not dataclasses.MISSING:
                    kwargs[field_name] = field.default
                elif field.default_factory is not dataclasses.MISSING:
                    kwargs[field_name] = field.default_factory()
                elif self._is_optional(field_type):
                    kwargs[field_name] = None
                else:
                    field_errors.append({
                        'field': field_name,
                        'error': f"Field '{field_name}' is required",
                        'value': None
                    })

        if field_errors:
            raise ModelHandlerError(
                f"Failed to resolve dataclass {model_class.__name__}",
                model_class=model_class,
                errors=field_errors,
                handler_name=self.name,
            )

        try:
            return model_class(**kwargs)
        except Exception as e:
            raise ModelHandlerError(
                f"Failed to create {model_class.__name__}: {e}",
                model_class=model_class,
                handler_name=self.name,
            )

    def to_dict(self, instance: Any) -> Dict[str, Any]:
        """Convert dataclass instance to dict"""
        if not dataclasses.is_dataclass(instance):
            raise ModelHandlerError(
                f"{type(instance)} is not a dataclass instance",
                handler_name=self.name,
            )

        result = {}
        for field in dataclasses.fields(instance):
            value = getattr(instance, field.name)
            if dataclasses.is_dataclass(value):
                result[field.name] = self.to_dict(value)
            else:
                result[field.name] = value
        return result

    def _is_optional(self, type_hint) -> bool:
        """Check if the type is Optional"""
        origin = getattr(type_hint, '__origin__', None)
        if origin is Union:
            args = getattr(type_hint, '__args__', ())
            return type(None) in args
        return False

    def _unwrap_optional(self, type_hint) -> Type:
        """Extract X from Optional[X]"""
        origin = getattr(type_hint, '__origin__', None)
        if origin is Union:
            args = getattr(type_hint, '__args__', ())
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return non_none[0]
        if isinstance(type_hint, type):
            return type_hint
        return None

    def _convert_value(self, value: Any, target_type: Type) -> Any:
        """Basic type conversion"""
        if value is None:
            return None
        if isinstance(value, target_type):
            return value

        try:
            if target_type is str:
                return str(value)
            elif target_type is int:
                return int(value)
            elif target_type is float:
                return float(value)
            elif target_type is bool:
                if isinstance(value, str):
                    return value.lower() in ('true', '1', 'yes', 'on')
                return bool(value)
            else:
                return target_type(value)
        except Exception:
            return value

