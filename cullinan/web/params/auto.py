# -*- coding: utf-8 -*-
"""Cullinan Auto Type Inference

Auto type inference, automatically determines type based on value content.

Author: Cullinan
"""

import json
import re
from typing import Any, Type


class Auto:
    """Auto type inference

    Automatically infers and converts to the appropriate type based on the content of the input value.

    Type inference priority:
    1. None / null -> None
    2. Boolean string -> bool
    3. Integer string -> int
    4. Float string -> float
    5. JSON object/array -> dict/list
    6. Other -> keep original type (usually str)

    Example:
        Auto.infer("123")      # -> 123 (int)
        Auto.infer("12.5")     # -> 12.5 (float)
        Auto.infer("true")     # -> True (bool)
        Auto.infer('{"a":1}')  # -> {"a": 1} (dict)
        Auto.infer("hello")    # -> "hello" (str)
    """

    # Boolean value mapping
    BOOL_MAP = {
        'true': True, 'True': True, 'TRUE': True,
        'false': False, 'False': False, 'FALSE': False,
        'yes': True, 'Yes': True, 'YES': True,
        'no': False, 'No': False, 'NO': False,
        'on': True, 'On': True, 'ON': True,
        'off': False, 'Off': False, 'OFF': False,
    }

    # Numeric patterns
    INT_PATTERN = re.compile(r'^-?\d+$')
    FLOAT_PATTERN = re.compile(r'^-?\d+\.\d+$')
    SCIENTIFIC_PATTERN = re.compile(r'^-?\d+\.?\d*[eE][+-]?\d+$')

    @classmethod
    def infer(cls, value: Any) -> Any:
        """Infer and convert type based on value content

        Args:
            value: Original value

        Returns:
            Converted value
        """
        if value is None:
            return None

        # If already a non-string type, return directly
        if not isinstance(value, str):
            return value

        # Empty string
        if value == '':
            return ''

        # Infer after stripping leading/trailing whitespace
        stripped = value.strip()

        # null / None
        if stripped.lower() in ('null', 'none'):
            return None

        # Boolean value
        if stripped in cls.BOOL_MAP:
            return cls.BOOL_MAP[stripped]

        # Integer
        if cls.INT_PATTERN.match(stripped):
            try:
                return int(stripped)
            except ValueError:
                pass

        # Float
        if cls.FLOAT_PATTERN.match(stripped) or cls.SCIENTIFIC_PATTERN.match(stripped):
            try:
                return float(stripped)
            except ValueError:
                pass

        # JSON object
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass

        # JSON array
        if stripped.startswith('[') and stripped.endswith(']'):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass

        # Keep original string
        return value

    @classmethod
    def infer_type(cls, value: Any) -> Type:
        """Infer the target type of a value (without conversion)

        Args:
            value: Original value

        Returns:
            Inferred type
        """
        if value is None:
            return type(None)

        if not isinstance(value, str):
            return type(value)

        stripped = value.strip()

        # null / None
        if stripped.lower() in ('null', 'none'):
            return type(None)

        # Boolean value
        if stripped in cls.BOOL_MAP:
            return bool

        # Integer
        if cls.INT_PATTERN.match(stripped):
            return int

        # Float
        if cls.FLOAT_PATTERN.match(stripped) or cls.SCIENTIFIC_PATTERN.match(stripped):
            return float

        # JSON object
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                result = json.loads(stripped)
                if isinstance(result, dict):
                    return dict
            except json.JSONDecodeError:
                pass

        # JSON array
        if stripped.startswith('[') and stripped.endswith(']'):
            try:
                result = json.loads(stripped)
                if isinstance(result, list):
                    return list
            except json.JSONDecodeError:
                pass

        return str


class AutoType:
    """Auto type marker

    Used in parameter declarations to indicate automatic type inference.

    Example:
        @get_api(url="/search")
        async def search(self, limit: Query(AutoType, default=10)):
            # limit will have its type automatically inferred
            pass
    """
    pass

