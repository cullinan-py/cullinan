# -*- coding: utf-8 -*-
"""Deprecation utilities for Cullinan framework.

Provides tools for marking deprecated APIs and managing backward compatibility.

Author: plumeink
"""

import re
import warnings
import functools
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Deprecation windows, counted in minor releases. The concrete removal version
# is derived from the framework version (the single source of truth in
# ``cullinan._version``), so no version literal is written by hand anywhere in
# the codebase.
#
# Each surface picks the window that reproduces the removal version it already
# advertised. A window is an internal policy knob used to preserve that
# equivalence; it is not a fresh schedule commitment, and its final value is
# settled together with the release plan that owns the surrounding deprecations.
DEPRECATION_WINDOW_MINORS = 2

# The legacy middleware registration helpers and the decorator's implicit
# default were announced with a removal one major step further out; this wider
# window reproduces that announcement so the rule-based refactor never pulls
# them forward.
EXTENDED_DEPRECATION_WINDOW_MINORS = 5

# The framework numbers minors as a two-digit step (``0.95`` ... ``0.99``) before
# rolling into the next major (``1.0``); the removal arithmetic rolls over the
# same way so a wide window lands on the expected version instead of ``0.100``.
_MINORS_PER_MAJOR = 100


def _release_pair(version: str) -> Tuple[int, int]:
    """Return ``(major, minor)`` parsed from a version string like ``0.96a1``."""
    match = re.match(r"\s*(\d+)\.(\d+)", version)
    if match is None:
        raise ValueError(f"Unrecognised version string: {version!r}")
    return int(match.group(1)), int(match.group(2))


def current_version() -> str:
    """Return the framework version from its single source of truth."""
    from cullinan._version import __version__

    return __version__


def resolve_removal_version(
    version: Optional[str] = None,
    window: int = DEPRECATION_WINDOW_MINORS,
) -> str:
    """Derive a removal version as ``current minor + window``.

    The value is computed from the version in ``cullinan._version`` rather than
    hard-coded, so adding a new deprecation cannot introduce a further,
    inconsistent removal version. The minor field rolls over into the major
    field the same way the framework's release numbering does (``0.99`` + one
    minor becomes ``1.0``).

    Example:
        >>> resolve_removal_version("0.95")  # window defaults to 2
        '0.97'
        >>> resolve_removal_version("0.95", window=5)
        '1.0'
    """
    major, minor = _release_pair(version or current_version())
    total_minor = major * _MINORS_PER_MAJOR + minor + window
    new_major, new_minor = divmod(total_minor, _MINORS_PER_MAJOR)
    return f"{new_major}.{new_minor}"


def deprecated(version: str,
               alternative: str,
               removal_version: Optional[str] = None,
               category: type = DeprecationWarning):
    """Decorator to mark a function or class as deprecated.

    Args:
        version: Version in which the API was deprecated
        alternative: Description of the alternative API to use
        removal_version: Version in which the API will be removed. When omitted,
            it is derived from the framework version and the compatibility
            window (``current minor + EXTENDED_DEPRECATION_WINDOW_MINORS``)
            instead of being hard-coded - that window keeps the removal version
            this default already advertised.
        category: Warning category (default: DeprecationWarning)

    Example:
        >>> @deprecated(
        ...     version="0.8",
        ...     alternative="resolve_dependency()",
        ... )
        ... def get_service_by_name(name: str):
        ...     return registry.get_instance(name)
    """
    resolved_removal_version = removal_version or resolve_removal_version(
        window=EXTENDED_DEPRECATION_WINDOW_MINORS
    )

    def decorator(obj):
        # Handle both functions and classes
        if isinstance(obj, type):
            # For classes
            original_init = obj.__init__

            @functools.wraps(original_init)
            def new_init(self, *args, **kwargs):
                warnings.warn(
                    f"{obj.__name__} is deprecated since v{version} and will be removed in v{resolved_removal_version}. "
                    f"Use {alternative} instead.",
                    category=category,
                    stacklevel=2
                )
                original_init(self, *args, **kwargs)

            obj.__init__ = new_init

            # Add deprecation marker
            obj.__deprecated__ = True
            obj.__deprecated_info__ = {
                'version': version,
                'alternative': alternative,
                'removal_version': resolved_removal_version,
            }

            return obj
        else:
            # For functions
            @functools.wraps(obj)
            def wrapper(*args, **kwargs):
                warnings.warn(
                    f"{obj.__name__}() is deprecated since v{version} and will be removed in v{resolved_removal_version}. "
                    f"Use {alternative} instead.",
                    category=category,
                    stacklevel=2
                )
                return obj(*args, **kwargs)

            # Add deprecation marker
            wrapper.__deprecated__ = True
            wrapper.__deprecated_info__ = {
                'version': version,
                'alternative': alternative,
                'removal_version': resolved_removal_version,
            }

            return wrapper

    return decorator


def is_deprecated(obj) -> bool:
    """Check if an object is marked as deprecated.

    Args:
        obj: The object to check

    Returns:
        True if the object is deprecated
    """
    return getattr(obj, '__deprecated__', False)


def get_deprecation_info(obj) -> Optional[dict]:
    """Get deprecation information for an object.

    Args:
        obj: The object to check

    Returns:
        Dictionary with deprecation info, or None if not deprecated
    """
    if is_deprecated(obj):
        return getattr(obj, '__deprecated_info__', None)
    return None


class DeprecationManager:
    """Manages deprecation warnings and backward compatibility.

    Can be configured to control deprecation warning behavior.
    """

    def __init__(self):
        """Initialize the deprecation manager."""
        self._enabled = True
        self._strict_mode = False  # If True, raise errors instead of warnings
        self._logged_warnings = set()  # Track which warnings have been shown

    def enable(self):
        """Enable deprecation warnings."""
        self._enabled = True
        logger.info("Deprecation warnings enabled")

    def disable(self):
        """Disable deprecation warnings."""
        self._enabled = False
        logger.info("Deprecation warnings disabled")

    def is_enabled(self) -> bool:
        """Check if deprecation warnings are enabled."""
        return self._enabled

    def set_strict_mode(self, strict: bool = True):
        """Set strict mode.

        In strict mode, deprecated API usage raises errors instead of warnings.

        Args:
            strict: Whether to enable strict mode
        """
        self._strict_mode = strict
        logger.info(f"Strict mode {'enabled' if strict else 'disabled'}")

    def is_strict(self) -> bool:
        """Check if strict mode is enabled."""
        return self._strict_mode

    def warn_once(self, key: str, message: str, category: type = DeprecationWarning):
        """Issue a deprecation warning only once per key.

        Useful for avoiding spam when a deprecated API is called in a loop.

        Args:
            key: Unique key for this warning
            message: Warning message
            category: Warning category
        """
        if not self._enabled:
            return

        if key in self._logged_warnings:
            return

        if self._strict_mode:
            raise DeprecationError(message)

        warnings.warn(message, category=category, stacklevel=3)
        self._logged_warnings.add(key)
        logger.warning(f"Deprecation warning: {message}")

    def clear_logged_warnings(self):
        """Clear the set of logged warnings."""
        self._logged_warnings.clear()


class DeprecationError(Exception):
    """Raised when deprecated API is used in strict mode."""
    pass


# Global deprecation manager
_deprecation_manager: Optional[DeprecationManager] = None


def get_deprecation_manager() -> DeprecationManager:
    """Get the global deprecation manager.

    Returns:
        The global DeprecationManager instance
    """
    global _deprecation_manager
    if _deprecation_manager is None:
        _deprecation_manager = DeprecationManager()
    return _deprecation_manager


def reset_deprecation_manager():
    """Reset the global deprecation manager (for testing)."""
    global _deprecation_manager
    _deprecation_manager = None


# Convenience functions

def warn_deprecated(message: str, category: type = DeprecationWarning):
    """Issue a deprecation warning.

    Args:
        message: Warning message
        category: Warning category
    """
    manager = get_deprecation_manager()
    if manager.is_enabled():
        if manager.is_strict():
            raise DeprecationError(message)
        warnings.warn(message, category=category, stacklevel=2)
