# -*- coding: utf-8 -*-
"""Cullinan DynamicBody

Dynamic body class, supports attribute-style access.

Author: Cullinan
"""

from typing import Any, Dict, Iterator, KeysView, ValuesView, ItemsView, List


class _Empty:
    """Empty sentinel class, used to distinguish None from a true empty"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return '<EMPTY>'

    def __bool__(self):
        return False


# Empty sentinel
EMPTY = _Empty()


class DynamicBody:
    """Dynamic request body class

    Provides JavaScript-like attribute access, avoiding frequent use of .get().

    Features:
    - Attribute access: body.name
    - Safe access: body.get('name', default)
    - Nested safe access: body.get_nested('user.address.city', 'Unknown')
    - Quick emptiness check: body.has('name'), body.is_empty(), body.is_not_empty()
    - Dict compatibility: body['name'], 'name' in body
    - Iteration support: for key in body
    - Mutability: body.new_field = value
    - Nested access: body.user.name (nested dicts auto-convert)
    - Chained safe access: body.safe.user.address.city (no exception thrown)

    Usage:
        # Recommended syntax (avoids non-default parameter issue)
        @post_api(url="/users")
        async def create_user(
            self,
            auth: str = Header(alias="Authorization"),
            body: DynamicBody = DynamicBody(),  # Use default value syntax
        ):
            print(body.name, body.age)

        # Simplified syntax (when no other parameters have defaults)
        @post_api(url="/users")
        async def create_user(self, body: DynamicBody):
            print(body.name, body.age)

    Example:
        body = DynamicBody({'name': 'test', 'age': 18, 'user': {'id': 1}})

        # Attribute access
        print(body.name)  # 'test'
        print(body.age)   # 18

        # Nested access
        print(body.user.id)  # 1

        # Safe access
        print(body.get('email', 'default@example.com'))

        # Nested safe access
        print(body.get_nested('user.address.city', 'Unknown'))

        # Quick emptiness check
        if body.has('name'):
            print('has name')
        if body.is_not_empty():
            print('body has data')

        # Chained safe access (no exception)
        city = body.safe.user.address.city.value_or('Unknown')

        # Check existence
        if 'name' in body:
            print('has name')

        # Set new field
        body.email = 'test@example.com'

        # Convert to dict
        data = body.to_dict()
    """

    __slots__ = ('_data',)

    def __init__(self, data: Dict[str, Any] = None):
        """Initialize dynamic body

        Args:
            data: Raw data dictionary
        """
        object.__setattr__(self, '_data', data if data is not None else {})

    def __getattr__(self, name: str) -> Any:
        """Attribute access

        Args:
            name: Attribute name

        Returns:
            Attribute value (nested dicts auto-convert to DynamicBody)

        Raises:
            AttributeError: Attribute does not exist
        """
        data = object.__getattribute__(self, '_data')
        if name in data:
            value = data[name]
            # Nested dicts auto-convert to DynamicBody
            if isinstance(value, dict):
                return DynamicBody(value)
            return value
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        """Set attribute

        Args:
            name: Attribute name
            value: Attribute value
        """
        if name == '_data':
            object.__setattr__(self, name, value)
        else:
            self._data[name] = value

    def __delattr__(self, name: str) -> None:
        """Delete attribute

        Args:
            name: Attribute name
        """
        data = object.__getattribute__(self, '_data')
        if name in data:
            del data[name]
        else:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __getitem__(self, key: str) -> Any:
        """Dict-style access

        Args:
            key: Key name

        Returns:
            Corresponding value
        """
        value = self._data[key]
        if isinstance(value, dict):
            return DynamicBody(value)
        return value

    def __setitem__(self, key: str, value: Any) -> None:
        """Dict-style set

        Args:
            key: Key name
            value: Value
        """
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        """Dict-style delete

        Args:
            key: Key name
        """
        del self._data[key]

    def __contains__(self, name: str) -> bool:
        """Check if key exists

        Args:
            name: Key name

        Returns:
            Whether exists
        """
        return name in self._data

    def __iter__(self) -> Iterator[str]:
        """Iterate over key names"""
        return iter(self._data)

    def __len__(self) -> int:
        """Return field count"""
        return len(self._data)

    def __bool__(self) -> bool:
        """Boolean evaluation (True if not empty)"""
        return bool(self._data)

    def __repr__(self) -> str:
        return f"DynamicBody({self._data!r})"

    def __str__(self) -> str:
        return str(self._data)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, DynamicBody):
            return self._data == other._data
        if isinstance(other, dict):
            return self._data == other
        return False

    # =========================================================================
    # Dict compatibility methods
    # =========================================================================

    def get(self, name: str, default: Any = None) -> Any:
        """Safely get attribute value

        Args:
            name: Attribute name
            default: Default value

        Returns:
            Attribute value or default

        Example:
            email = body.get('email', 'default@example.com')
        """
        value = self._data.get(name, default)
        if isinstance(value, dict):
            return DynamicBody(value)
        return value

    def keys(self) -> KeysView[str]:
        """Return all keys"""
        return self._data.keys()

    def values(self) -> ValuesView[Any]:
        """Return all values"""
        return self._data.values()

    def items(self) -> ItemsView[str, Any]:
        """Return all key-value pairs"""
        return self._data.items()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to plain dict

        Returns:
            A copy of the dict
        """
        return dict(self._data)

    def update(self, data: Dict[str, Any] = None, **kwargs) -> None:
        """Update data

        Args:
            data: Dict to merge
            **kwargs: Key-value pairs to set
        """
        if data:
            self._data.update(data)
        if kwargs:
            self._data.update(kwargs)

    def pop(self, name: str, *default) -> Any:
        """Pop and return value

        Args:
            name: Key name
            *default: Default value (optional)

        Returns:
            Popped value
        """
        return self._data.pop(name, *default)

    def setdefault(self, name: str, default: Any = None) -> Any:
        """Set default value and return

        Args:
            name: Key name
            default: Default value

        Returns:
            Existing value or the default that was set
        """
        return self._data.setdefault(name, default)

    def clear(self) -> None:
        """Clear all data"""
        self._data.clear()

    # =========================================================================
    # Quick emptiness check methods
    # =========================================================================

    def has(self, name: str) -> bool:
        """Check if attribute exists

        More semantic than 'name' in body.

        Args:
            name: Attribute name

        Returns:
            Whether the attribute exists

        Example:
            if body.has('email'):
                send_email(body.email)
        """
        return name in self._data

    def has_value(self, name: str) -> bool:
        """Check if attribute exists and has a non-empty value (not None, empty string, empty list, etc.)

        Args:
            name: Attribute name

        Returns:
            Whether the attribute exists and has a value

        Example:
            if body.has_value('email'):
                send_email(body.email)  # ensure email is not None or ''
        """
        if name not in self._data:
            return False
        value = self._data[name]
        # None, '', [], {}, 0, False etc. all return False
        return bool(value)

    def is_empty(self) -> bool:
        """Check if empty

        Returns:
            True if there is no data

        Example:
            if body.is_empty():
                return {'error': 'No data provided'}
        """
        return len(self._data) == 0

    def is_not_empty(self) -> bool:
        """Check if not empty

        Returns:
            True if there is data

        Example:
            if body.is_not_empty():
                process(body)
        """
        return len(self._data) > 0

    def is_null(self, name: str) -> bool:
        """Check if attribute value is None

        Args:
            name: Attribute name

        Returns:
            True if attribute does not exist or value is None

        Example:
            if body.is_null('optional_field'):
                body.optional_field = default_value
        """
        return self._data.get(name) is None

    def is_not_null(self, name: str) -> bool:
        """Check if attribute value is not None

        Args:
            name: Attribute name

        Returns:
            True if attribute exists and value is not None

        Example:
            if body.is_not_null('callback_url'):
                notify(body.callback_url)
        """
        return name in self._data and self._data[name] is not None

    # =========================================================================
    # Nested safe access methods
    # =========================================================================

    def get_nested(self, path: str, default: Any = None, separator: str = '.') -> Any:
        """Nested path safe access

        Safely accesses nested attributes via a dot-separated path, returning the default value if any level does not exist.

        Args:
            path: Dot-separated path, e.g. 'user.address.city'
            default: Default value
            separator: Path separator, default '.'

        Returns:
            Nested attribute value or default

        Example:
            city = body.get_nested('user.address.city', 'Unknown')
            # Equivalent to:
            # city = body.get('user', {}).get('address', {}).get('city', 'Unknown')
            # but more concise and safe
        """
        keys = path.split(separator)
        current = self._data

        for key in keys:
            if isinstance(current, dict):
                if key not in current:
                    return default
                current = current[key]
            elif isinstance(current, DynamicBody):
                if key not in current._data:
                    return default
                current = current._data[key]
            else:
                return default

        if isinstance(current, dict):
            return DynamicBody(current)
        return current

    def get_list(self, name: str, default: List = None) -> List:
        """Safely get list attribute

        Args:
            name: Attribute name
            default: Default value, defaults to empty list

        Returns:
            List value or default

        Example:
            tags = body.get_list('tags')  # Returns [] if tags does not exist
            for tag in tags:
                process(tag)
        """
        if default is None:
            default = []
        value = self._data.get(name)
        if value is None:
            return default
        if isinstance(value, list):
            return value
        return default

    def get_str(self, name: str, default: str = '') -> str:
        """Safely get string attribute

        Args:
            name: Attribute name
            default: Default value, defaults to empty string

        Returns:
            String value or default

        Example:
            name = body.get_str('name')  # Returns '' if name does not exist
        """
        value = self._data.get(name)
        if value is None:
            return default
        return str(value)

    def get_int(self, name: str, default: int = 0) -> int:
        """Safely get integer attribute

        Args:
            name: Attribute name
            default: Default value, defaults to 0

        Returns:
            Integer value or default

        Example:
            age = body.get_int('age')  # Returns 0 if age does not exist or cannot be converted
        """
        value = self._data.get(name)
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def get_float(self, name: str, default: float = 0.0) -> float:
        """Safely get float attribute

        Args:
            name: Attribute name
            default: Default value, defaults to 0.0

        Returns:
            Float value or default

        Example:
            price = body.get_float('price')  # Returns 0.0 if price does not exist
        """
        value = self._data.get(name)
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def get_bool(self, name: str, default: bool = False) -> bool:
        """Safely get boolean attribute

        Supports various boolean representations: True/False, 'true'/'false', 1/0, 'yes'/'no'

        Args:
            name: Attribute name
            default: Default value, defaults to False

        Returns:
            Boolean value or default

        Example:
            active = body.get_bool('active')  # Returns False if active does not exist
        """
        value = self._data.get(name)
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        if isinstance(value, (int, float)):
            return bool(value)
        return default

    # =========================================================================
    # Chained safe accessor
    # =========================================================================

    @property
    def safe(self) -> 'SafeAccessor':
        """Return a safe accessor that supports chained access without throwing exceptions

        Returns:
            SafeAccessor instance

        Example:
            # Traditional way may throw exceptions
            # city = body.user.address.city  # AttributeError if any level is missing

            # Using safe accessor
            city = body.safe.user.address.city.value_or('Unknown')

            # Or check existence
            if body.safe.user.address.city.exists:
                print(body.safe.user.address.city.value)
        """
        return SafeAccessor(self._data)

    def copy(self) -> 'DynamicBody':
        """Return a shallow copy

        Returns:
            New DynamicBody instance
        """
        return DynamicBody(self._data.copy())


class SafeAccessor:
    """Safe accessor

    Supports chained access without throwing AttributeError, safely handling any missing level.

    Example:
        body = DynamicBody({'user': {'name': 'John'}})

        # Safely access existing attribute
        name = body.safe.user.name.value  # 'John'

        # Safely access non-existing attribute
        city = body.safe.user.address.city.value_or('Unknown')  # 'Unknown'

        # Check existence
        if body.safe.user.email.exists:
            send_email(body.safe.user.email.value)
    """

    __slots__ = ('_data', '_exists')

    def __init__(self, data: Any, exists: bool = True):
        """Initialize safe accessor

        Args:
            data: Current data
            exists: Whether data exists
        """
        object.__setattr__(self, '_data', data)
        object.__setattr__(self, '_exists', exists)

    def __getattr__(self, name: str) -> 'SafeAccessor':
        """Safely get attribute without throwing exceptions

        Args:
            name: Attribute name

        Returns:
            New SafeAccessor instance
        """
        data = object.__getattribute__(self, '_data')
        exists = object.__getattribute__(self, '_exists')

        if not exists:
            return SafeAccessor(None, False)

        if isinstance(data, dict):
            if name in data:
                return SafeAccessor(data[name], True)
            return SafeAccessor(None, False)

        if isinstance(data, DynamicBody):
            if name in data._data:
                return SafeAccessor(data._data[name], True)
            return SafeAccessor(None, False)

        return SafeAccessor(None, False)

    @property
    def value(self) -> Any:
        """Get current value

        Returns:
            Current value, or None if not exists
        """
        if not self._exists:
            return None
        if isinstance(self._data, dict):
            return DynamicBody(self._data)
        return self._data

    def value_or(self, default: Any) -> Any:
        """Get value or default

        Args:
            default: Default value

        Returns:
            Current value or default
        """
        if not self._exists or self._data is None:
            return default
        if isinstance(self._data, dict):
            return DynamicBody(self._data)
        return self._data

    @property
    def exists(self) -> bool:
        """Check if value exists

        Returns:
            Whether exists
        """
        return self._exists

    @property
    def is_null(self) -> bool:
        """Check if value is None

        Returns:
            Whether None
        """
        return not self._exists or self._data is None

    @property
    def is_not_null(self) -> bool:
        """Check if value is not None

        Returns:
            Whether not None
        """
        return self._exists and self._data is not None

    def __bool__(self) -> bool:
        """Boolean evaluation"""
        return self._exists and bool(self._data)

    def __repr__(self) -> str:
        if self._exists:
            return f"SafeAccessor({self._data!r})"
        return "SafeAccessor(<missing>)"
