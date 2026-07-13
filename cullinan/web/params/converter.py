# -*- coding: utf-8 -*-
"""Cullinan Type Converter

Type converter, converts request parameters to target types.

Author: Cullinan
"""

import json
from typing import Any, Type


class ConversionError(Exception):
    """Type conversion error

    Attributes:
        message: Error message
        value: Original value
        target_type: Target type
    """

    def __init__(
        self,
        message: str,
        value: Any = None,
        target_type: Type = None
    ):
        super().__init__(message)
        self.message = message
        self.value = value
        self.target_type = target_type

    def __repr__(self) -> str:
        return f"ConversionError({self.message!r}, value={self.value!r}, target_type={self.target_type})"


class TypeConverter:
    """Type converter

    Converts raw values from requests to target types.

    Example:
        converter = TypeConverter()

        # Basic conversion
        result = converter.convert("123", int)  # -> 123
        result = converter.convert("true", bool)  # -> True
        result = converter.convert("1,2,3", list)  # -> ["1", "2", "3"]
    """

    # Boolean truthy strings
    TRUE_VALUES = frozenset({
        'true', 'True', 'TRUE',
        '1',
        'yes', 'Yes', 'YES',
        'on', 'On', 'ON'
    })

    FALSE_VALUES = frozenset({
        'false', 'False', 'FALSE',
        '0', '',
        'no', 'No', 'NO',
        'off', 'Off', 'OFF'
    })

    @classmethod
    def convert(cls, value: Any, target_type: Type) -> Any:
        """Convert value to target type

        Args:
            value: Original value
            target_type: Target type

        Returns:
            Converted value

        Raises:
            ConversionError: Conversion failed
        """
        if value is None:
            return None

        # If already the target type, return directly
        if isinstance(value, target_type):
            return value

        try:
            if target_type is str:
                return cls._to_str(value)
            elif target_type is int:
                return cls._to_int(value)
            elif target_type is float:
                return cls._to_float(value)
            elif target_type is bool:
                return cls._to_bool(value)
            elif target_type is list:
                return cls._to_list(value)
            elif target_type is dict:
                return cls._to_dict(value)
            elif target_type is bytes:
                return cls._to_bytes(value)
            else:
                # Try calling the target type constructor directly
                return target_type(value)
        except ConversionError:
            raise
        except Exception as e:
            raise ConversionError(
                f"Cannot convert {type(value).__name__} to {target_type.__name__}: {e}",
                value=value,
                target_type=target_type
            )

    @classmethod
    def _to_str(cls, value: Any) -> str:
        """Convert to string"""
        if isinstance(value, bytes):
            return value.decode('utf-8')
        return str(value)

    @classmethod
    def _to_int(cls, value: Any) -> int:
        """Convert to integer"""
        if isinstance(value, str):
            value = value.strip()
            # Handle float string
            if '.' in value:
                return int(float(value))
            # Handle empty string
            if not value:
                raise ConversionError(
                    "Cannot convert empty string to int",
                    value=value,
                    target_type=int
                )
            return int(value)
        if isinstance(value, float):
            return int(value)
        if isinstance(value, bool):
            return 1 if value else 0
        return int(value)

    @classmethod
    def _to_float(cls, value: Any) -> float:
        """Convert to float"""
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ConversionError(
                    "Cannot convert empty string to float",
                    value=value,
                    target_type=float
                )
        return float(value)

    @classmethod
    def _to_bool(cls, value: Any) -> bool:
        """Convert to boolean"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value in cls.TRUE_VALUES:
                return True
            if value in cls.FALSE_VALUES:
                return False
            raise ConversionError(
                f"Cannot convert '{value}' to bool",
                value=value,
                target_type=bool
            )
        if isinstance(value, (int, float)):
            return bool(value)
        return bool(value)

    @classmethod
    def _to_list(cls, value: Any) -> list:
        """Convert to list"""
        if isinstance(value, list):
            return value
        if isinstance(value, (tuple, set, frozenset)):
            return list(value)
        if isinstance(value, str):
            # Try parsing as JSON array
            value = value.strip()
            if value.startswith('[') and value.endswith(']'):
                try:
                    result = json.loads(value)
                    if isinstance(result, list):
                        return result
                except json.JSONDecodeError:
                    pass
            # Comma-separated
            if ',' in value:
                return [v.strip() for v in value.split(',')]
            # Single value
            if value:
                return [value]
            return []
        return [value]

    @classmethod
    def _to_dict(cls, value: Any) -> dict:
        """Convert to dict"""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            value = value.strip()
            if value.startswith('{') and value.endswith('}'):
                try:
                    result = json.loads(value)
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    pass
            raise ConversionError(
                f"Cannot parse '{value}' as JSON dict",
                value=value,
                target_type=dict
            )
        raise ConversionError(
            f"Cannot convert {type(value).__name__} to dict",
            value=value,
            target_type=dict
        )

    @classmethod
    def _to_bytes(cls, value: Any) -> bytes:
        """Convert to bytes"""
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode('utf-8')
        if isinstance(value, (bytearray, memoryview)):
            return bytes(value)
        raise ConversionError(
            f"Cannot convert {type(value).__name__} to bytes",
            value=value,
            target_type=bytes
        )

    @classmethod
    def can_convert(cls, value: Any, target_type: Type) -> bool:
        """Check if conversion is possible

        Args:
            value: Original value
            target_type: Target type

        Returns:
            Whether conversion is possible
        """
        try:
            cls.convert(value, target_type)
            return True
        except (ConversionError, Exception):
            return False

