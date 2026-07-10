# -*- coding: utf-8 -*-
"""Cullinan Parameter Validator

Parameter validator, validates whether parameter values satisfy constraints.

Author: Cullinan
"""

import re
from typing import Any, List, Tuple


class ValidationError(Exception):
    """Parameter validation error

    Attributes:
        message: Error message
        param_name: Parameter name
        value: Original value
        constraint: Constraint condition
    """

    def __init__(
        self,
        message: str,
        param_name: str = None,
        value: Any = None,
        constraint: str = None
    ):
        super().__init__(message)
        self.message = message
        self.param_name = param_name
        self.value = value
        self.constraint = constraint

    def __repr__(self) -> str:
        return f"ValidationError({self.message!r}, param={self.param_name!r})"

    def to_dict(self) -> dict:
        """Convert to dict format"""
        return {
            'message': self.message,
            'param': self.param_name,
            'value': self.value,
            'constraint': self.constraint,
        }


class ParamValidator:
    """Parameter validator

    Validates parameter values according to validation rules.

    Supported validation rules:
    - required: Required
    - ge: Greater than or equal
    - le: Less than or equal
    - gt: Greater than
    - lt: Less than
    - min_length: Minimum length
    - max_length: Maximum length
    - regex: Regular expression

    Example:
        validator = ParamValidator()

        # Single validation
        validator.validate_ge(10, 5, 'age')  # OK
        validator.validate_ge(3, 5, 'age')   # raises ValidationError

        # Batch validation
        validators = [('ge', 0), ('le', 100)]
        validator.validate(50, validators, 'score')  # OK
    """

    @classmethod
    def validate(
        cls,
        value: Any,
        validators: List[Tuple[str, Any]],
        param_name: str = None
    ) -> None:
        """Batch validate parameter value

        Args:
            value: Parameter value
            validators: List of validation rules, each item is (rule_name, rule_value)
            param_name: Parameter name (for error messages)

        Raises:
            ValidationError: Validation failed
        """
        for rule_name, rule_value in validators:
            method = getattr(cls, f'validate_{rule_name}', None)
            if method:
                method(value, rule_value, param_name)
            else:
                raise ValueError(f"Unknown validation rule: {rule_name}")

    @classmethod
    def validate_required(
        cls,
        value: Any,
        required: bool,
        param_name: str = None
    ) -> None:
        """Validate required

        Args:
            value: Parameter value
            required: Whether required
            param_name: Parameter name

        Raises:
            ValidationError: Value is None but required
        """
        if required and value is None:
            raise ValidationError(
                f"Parameter '{param_name}' is required",
                param_name=param_name,
                value=value,
                constraint='required'
            )

    @classmethod
    def validate_ge(
        cls,
        value: Any,
        min_value: float,
        param_name: str = None
    ) -> None:
        """Validate greater than or equal

        Args:
            value: Parameter value
            min_value: Minimum value
            param_name: Parameter name
        """
        if value is None:
            return
        if value < min_value:
            raise ValidationError(
                f"Parameter '{param_name}' must be >= {min_value}, got {value}",
                param_name=param_name,
                value=value,
                constraint=f'ge:{min_value}'
            )

    @classmethod
    def validate_le(
        cls,
        value: Any,
        max_value: float,
        param_name: str = None
    ) -> None:
        """Validate less than or equal

        Args:
            value: Parameter value
            max_value: Maximum value
            param_name: Parameter name
        """
        if value is None:
            return
        if value > max_value:
            raise ValidationError(
                f"Parameter '{param_name}' must be <= {max_value}, got {value}",
                param_name=param_name,
                value=value,
                constraint=f'le:{max_value}'
            )

    @classmethod
    def validate_gt(
        cls,
        value: Any,
        min_value: float,
        param_name: str = None
    ) -> None:
        """Validate greater than

        Args:
            value: Parameter value
            min_value: Minimum value (exclusive)
            param_name: Parameter name
        """
        if value is None:
            return
        if value <= min_value:
            raise ValidationError(
                f"Parameter '{param_name}' must be > {min_value}, got {value}",
                param_name=param_name,
                value=value,
                constraint=f'gt:{min_value}'
            )

    @classmethod
    def validate_lt(
        cls,
        value: Any,
        max_value: float,
        param_name: str = None
    ) -> None:
        """Validate less than

        Args:
            value: Parameter value
            max_value: Maximum value (exclusive)
            param_name: Parameter name
        """
        if value is None:
            return
        if value >= max_value:
            raise ValidationError(
                f"Parameter '{param_name}' must be < {max_value}, got {value}",
                param_name=param_name,
                value=value,
                constraint=f'lt:{max_value}'
            )

    @classmethod
    def validate_min_length(
        cls,
        value: Any,
        min_length: int,
        param_name: str = None
    ) -> None:
        """Validate minimum length

        Args:
            value: Parameter value (string or list)
            min_length: Minimum length
            param_name: Parameter name
        """
        if value is None:
            return
        if len(value) < min_length:
            raise ValidationError(
                f"Parameter '{param_name}' length must be >= {min_length}, got {len(value)}",
                param_name=param_name,
                value=value,
                constraint=f'min_length:{min_length}'
            )

    @classmethod
    def validate_max_length(
        cls,
        value: Any,
        max_length: int,
        param_name: str = None
    ) -> None:
        """Validate maximum length

        Args:
            value: Parameter value (string or list)
            max_length: Maximum length
            param_name: Parameter name
        """
        if value is None:
            return
        if len(value) > max_length:
            raise ValidationError(
                f"Parameter '{param_name}' length must be <= {max_length}, got {len(value)}",
                param_name=param_name,
                value=value,
                constraint=f'max_length:{max_length}'
            )

    @classmethod
    def validate_regex(
        cls,
        value: Any,
        pattern: str,
        param_name: str = None
    ) -> None:
        """Validate regex

        Args:
            value: Parameter value
            pattern: Regular expression
            param_name: Parameter name
        """
        if value is None:
            return
        if not isinstance(value, str):
            value = str(value)
        if not re.match(pattern, value):
            raise ValidationError(
                f"Parameter '{param_name}' does not match pattern '{pattern}'",
                param_name=param_name,
                value=value,
                constraint=f'regex:{pattern}'
            )

    @classmethod
    def validate_param(cls, param, value: Any, name: str = None) -> None:
        """Validate value based on a Param object

        Args:
            param: Param instance
            value: Parameter value
            name: Parameter name (overrides param.name)

        Raises:
            ValidationError: Validation failed
        """
        param_name = name or param.name

        # Required validation
        if param.required and value is None:
            raise ValidationError(
                f"Parameter '{param_name}' is required",
                param_name=param_name,
                value=value,
                constraint='required'
            )

        # Get and execute all validators
        validators = param.get_validators()
        if validators:
            cls.validate(value, validators, param_name)

