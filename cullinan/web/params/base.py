# -*- coding: utf-8 -*-
"""Cullinan Parameter Base Classes

Defines the infrastructure for parameter marker classes.

Author: Cullinan
"""

from typing import Any, List, Optional, Type, Union


class _UNSET:
    """Sentinel class representing an unset value

    Used to distinguish between "not set" and "set to None".
    Uses singleton pattern to ensure global uniqueness.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return '<UNSET>'

    def __bool__(self) -> bool:
        return False

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self


# Global UNSET singleton
UNSET = _UNSET()


class Param:
    """Parameter marker base class

    Base class for all parameter types (Path, Query, Body, Header, File).
    Used to mark the source and constraints of parameters in function signatures.

    Attributes:
        name: Parameter name (defaults to function parameter name)
        type_: Target type
        required: Whether required
        default: Default value
        description: Parameter description
        alias: Alias (key name used when reading from request)

    Validator Attributes:
        ge: Greater than or equal (numeric types)
        le: Less than or equal (numeric types)
        gt: Greater than (numeric types)
        lt: Less than (numeric types)
        min_length: Minimum length (string/list)
        max_length: Maximum length (string/list)
        regex: Regular expression (string)

    Example:
        # Used as type annotation
        @get_api(url="/users/{id}")
        async def get_user(self, id: Path(int), verbose: Query(bool, default=False)):
            pass

        # Direct instantiation
        param = Param(int, name='age', required=True, ge=0, le=150)
    """

    __slots__ = (
        'name', 'type_', 'required', 'default', 'description', 'alias',
        'ge', 'le', 'gt', 'lt', 'min_length', 'max_length', 'regex',
        '_validators'
    )

    # Parameter source identifier (overridden by subclasses)
    _source: str = 'unknown'

    def __init__(
        self,
        type_: Type = str,
        *,
        name: str = None,
        required: bool = True,
        default: Any = UNSET,
        description: str = '',
        alias: str = None,
        # Numeric constraints
        ge: Union[int, float, None] = None,
        le: Union[int, float, None] = None,
        gt: Union[int, float, None] = None,
        lt: Union[int, float, None] = None,
        # Length constraints
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        # Regex constraint
        regex: Optional[str] = None,
    ):
        """Initialize parameter marker

        Args:
            type_: Target type (default str)
            name: Parameter name (defaults to function parameter name)
            required: Whether required (automatically False when default value is provided)
            default: Default value
            description: Parameter description (for documentation generation)
            alias: Alias (key name used when reading from request)
            ge: Greater-than-or-equal constraint
            le: Less-than-or-equal constraint
            gt: Greater-than constraint
            lt: Less-than constraint
            min_length: Minimum length constraint
            max_length: Maximum length constraint
            regex: Regular expression constraint
        """
        self.name = name
        self.type_ = type_
        self.default = default
        self.description = description
        self.alias = alias

        # If has default value, not required
        if default is not UNSET:
            self.required = False
        else:
            self.required = required

        # Store constraints
        self.ge = ge
        self.le = le
        self.gt = gt
        self.lt = lt
        self.min_length = min_length
        self.max_length = max_length
        self.regex = regex

        # Lazy-build validators
        self._validators = None

    @property
    def source(self) -> str:
        """Return parameter source identifier"""
        return self._source

    def get_validators(self) -> List[tuple]:
        """Get validator list (lazy-built)

        Returns:
            List of validators, each as a (validator_name, value) tuple
        """
        if self._validators is None:
            self._validators = self._build_validators()
        return self._validators

    def _build_validators(self) -> List[tuple]:
        """Build validator list"""
        validators = []

        if self.ge is not None:
            validators.append(('ge', self.ge))
        if self.le is not None:
            validators.append(('le', self.le))
        if self.gt is not None:
            validators.append(('gt', self.gt))
        if self.lt is not None:
            validators.append(('lt', self.lt))
        if self.min_length is not None:
            validators.append(('min_length', self.min_length))
        if self.max_length is not None:
            validators.append(('max_length', self.max_length))
        if self.regex is not None:
            validators.append(('regex', self.regex))

        return validators

    def has_default(self) -> bool:
        """Check if has a default value"""
        return self.default is not UNSET

    def get_default(self) -> Any:
        """Get default value

        Returns:
            Default value, or None if not set
        """
        if self.default is UNSET:
            return None
        return self.default

    def __repr__(self) -> str:
        parts = [f"{self.__class__.__name__}({self.type_.__name__}"]
        if self.name:
            parts.append(f", name={self.name!r}")
        if not self.required:
            parts.append(", required=False")
        if self.default is not UNSET:
            parts.append(f", default={self.default!r}")
        if self.alias:
            parts.append(f", alias={self.alias!r}")
        parts.append(")")
        return "".join(parts)

    def __eq__(self, other) -> bool:
        if not isinstance(other, Param):
            return False
        return (
            self.name == other.name and
            self.type_ == other.type_ and
            self.required == other.required and
            self.default == other.default
        )

    def __hash__(self) -> int:
        return hash((self.name, self.type_, self.required))

    @classmethod
    def as_required(cls, type_: Type = str, **kwargs) -> 'Param':
        """Shortcut method to create a required parameter

        Example:
            # The following two forms are equivalent
            avatar: File = File.as_required(max_size=5*1024*1024)
            avatar: File = File(required=True, max_size=5*1024*1024)

        Args:
            type_: Target type (default str)
            **kwargs: Other parameter configuration

        Returns:
            Param instance with required=True
        """
        kwargs['required'] = True
        return cls(type_, **kwargs)

