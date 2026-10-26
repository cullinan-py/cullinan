# -*- coding: utf-8 -*-
"""Controller stateless validation for Cullinan framework.

Provides runtime validation to ensure Controllers are stateless (singleton-safe).
Detects instance variable assignments in __init__ that could cause concurrency issues.
"""

import logging
import inspect
import warnings
from typing import Type, Set
from functools import wraps

logger = logging.getLogger(__name__)


class StatefulControllerWarning(UserWarning):
    """Warning raised when a Controller appears to be stateful."""
    pass


class StatefulControllerError(Exception):
    """Exception raised when a Controller is detected as stateful in strict mode."""
    pass


def _get_allowed_instance_vars() -> Set[str]:
    """Get set of allowed instance variable names.

    These are framework-managed or injected attributes that are safe to assign.

    Returns:
        Set of allowed attribute names
    """
    return {
        'dependencies',  # ServiceRegistry legacy
        'service',       # Injected service dict
        'response',      # Response proxy
        'response_factory',  # Response factory
        # Add any other framework-managed attributes here
    }


def _is_injection_descriptor(cls: Type, attr_name: str) -> bool:
    """Check if an attribute is an injection descriptor (InjectByName, Inject, etc.).

    Args:
        cls: Controller class
        attr_name: Attribute name to check

    Returns:
        True if it's an injection descriptor
    """
    try:
        class_attr = getattr(cls, attr_name, None)
        # Check if it's an InjectByName or Inject descriptor
        if class_attr is not None:
            attr_type = type(class_attr).__name__
            if attr_type in ('InjectByName', 'Inject', 'InjectByType'):
                return True
    except Exception:
        pass
    return False


def validate_stateless_controller(cls: Type, strict: bool = False) -> Type:
    """Validate that a Controller class is stateless (singleton-safe).

    Wraps the __init__ method to detect instance variable assignments
    that could cause concurrency issues in singleton Controllers.

    Args:
        cls: Controller class to validate
        strict: If True, raise exception; if False, log warning (default)

    Returns:
        The wrapped class

    Raises:
        StatefulControllerError: If stateful code detected in strict mode

    Example:
        @controller(url='/api/users')
        class UserController:
            def __init__(self):
                self.current_user = None  # Will trigger warning/error
    """
    original_init = cls.__init__

    # Get allowed instance variables
    allowed_vars = _get_allowed_instance_vars()

    @wraps(original_init)
    def wrapped_init(self, *args, **kwargs):
        # Track initial instance variables
        initial_vars = set(self.__dict__.keys()) if hasattr(self, '__dict__') else set()

        # Call original __init__
        result = original_init(self, *args, **kwargs)

        # Check for new instance variables
        final_vars = set(self.__dict__.keys()) if hasattr(self, '__dict__') else set()
        new_vars = final_vars - initial_vars - allowed_vars

        # Filter out injection descriptors (these are safe)
        problematic_vars = {
            var for var in new_vars
            if not _is_injection_descriptor(cls, var)
        }

        if problematic_vars:
            var_list = ', '.join(f"'{v}'" for v in sorted(problematic_vars))
            message = (
                f"Controller '{cls.__name__}' appears to be STATEFUL. "
                f"Instance variables {var_list} assigned in __init__. "
                f"Controllers are SINGLETONS shared across all requests. "
                f"Storing request-specific data in instance variables will cause CONCURRENCY ISSUES. "
                f"Solution: Pass request data via method parameters instead."
            )

            if strict:
                raise StatefulControllerError(message)
            else:
                warnings.warn(message, StatefulControllerWarning, stacklevel=2)
                logger.warning(
                    f"[STATEFUL_CONTROLLER] {cls.__name__} has instance variables: {var_list}. "
                    f"This may cause concurrency issues in singleton mode."
                )

        return result

    cls.__init__ = wrapped_init
    return cls


def check_controller_init_source(cls: Type, strict: bool = False) -> None:
    """Check Controller __init__ source code for potential stateful patterns.

    Performs static analysis on the __init__ source code to detect:
    - self.xxx = ... assignments
    - Warns about potential stateful code

    Args:
        cls: Controller class to check
        strict: If True, raise exception; if False, log warning

    Raises:
        StatefulControllerError: If stateful patterns detected in strict mode
    """
    try:
        # Get __init__ method
        init_method = cls.__init__

        # Skip if __init__ is inherited from object
        if init_method is object.__init__:
            return

        # Get source code
        source = inspect.getsource(init_method)

        # Simple pattern matching for self.xxx = assignments
        # This is a heuristic check, not perfect but catches common cases
        import re
        pattern = r'self\.(\w+)\s*='
        matches = re.findall(pattern, source)

        if matches:
            # Filter out allowed variables and common patterns
            allowed_vars = _get_allowed_instance_vars()
            problematic = [m for m in matches if m not in allowed_vars and not m.startswith('_')]

            if problematic:
                var_list = ', '.join(f"'self.{v}'" for v in problematic)
                message = (
                    f"Controller '{cls.__name__}' __init__ contains assignments: {var_list}. "
                    f"Controllers are singletons. Ensure these are not request-specific data."
                )

                if strict:
                    raise StatefulControllerError(message)
                else:
                    logger.info(
                        f"[CONTROLLER_INIT_CHECK] {cls.__name__} has assignments in __init__: {var_list}. "
                        f"Verify these are not request-specific."
                    )

    except StatefulControllerError:
        # A refusal is the point of strict mode, not a failure to analyse the
        # source. Without this clause the generic handler below catches it and
        # downgrades a hard error to a debug line -- strict mode then reads as
        # "raises" in the docstring and behaves as "does nothing".
        raise
    except (OSError, TypeError):
        # Can't get source (built-in, dynamically created, etc.)
        # Skip validation
        pass
    except Exception as e:
        logger.debug(f"Failed to analyze {cls.__name__}.__init__ source: {e}")


__all__ = [
    'validate_stateless_controller',
    'check_controller_init_source',
    'StatefulControllerWarning',
    'StatefulControllerError',
]

