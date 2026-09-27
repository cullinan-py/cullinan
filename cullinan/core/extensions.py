# -*- coding: utf-8 -*-
"""Extension point registry and discovery for Cullinan framework.

Provides a unified way to register and discover framework extension points,
making it easier for users to extend the framework without deep knowledge
of internal implementation.

Author: Cullinan
"""

from typing import List, Dict, Optional, Any, Type
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ExtensionCategory(Enum):
    """Categories of extension points in the framework."""

    MIDDLEWARE = "middleware"
    LIFECYCLE = "lifecycle"
    INJECTION = "injection"
    ROUTING = "routing"
    CONFIGURATION = "configuration"
    HANDLER = "handler"


@dataclass
class ExtensionPoint:
    """Metadata about a framework extension point.

    Attributes:
        category: The category this extension point belongs to
        name: Unique name of the extension point
        description: Human-readable description
        interface: The interface/base class to implement (if any)
        example_url: URL to documentation or example
        required: Whether this extension point must be implemented
    """

    category: ExtensionCategory
    name: str
    description: str
    interface: Optional[Type] = None
    example_url: Optional[str] = None
    required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'category': self.category.value,
            'name': self.name,
            'description': self.description,
            'interface': self.interface.__name__ if self.interface else None,
            'example_url': self.example_url,
            'required': self.required,
        }


class ExtensionRegistry:
    """Central registry for all framework extension points.

    This registry serves two purposes:
    1. Document available extension points for users
    2. Provide a unified API for querying extension capabilities
    """

    def __init__(self):
        """Initialize the extension registry."""
        self._extension_points: List[ExtensionPoint] = []
        self._initialized = False

    def _ensure_initialized(self):
        """Lazily initialize extension points on first access."""
        if self._initialized:
            return

        self._register_builtin_extension_points()
        self._initialized = True

    def _register_builtin_extension_points(self):
        """Register all built-in extension points."""
        from cullinan.web.middleware import Middleware
        from cullinan.web.gateway import GatewayMiddleware
        from cullinan.core.services import Service

        # Middleware extension points.
        #
        # Two protocols coexist:
        #   * the legacy ``Middleware.process_request`` / ``process_response``
        #     pair, kept for backward compatibility (auto-bridged), and
        #   * the onion-model ``GatewayMiddleware.__call__`` protocol, which is
        #     the one the gateway pipeline actually runs and is the recommended
        #     protocol for new code.
        self._extension_points.extend([
            ExtensionPoint(
                category=ExtensionCategory.MIDDLEWARE,
                name='Middleware.process_request',
                description='Legacy protocol: intercept and process requests before they reach handlers',
                interface=Middleware,
            ),
            ExtensionPoint(
                category=ExtensionCategory.MIDDLEWARE,
                name='Middleware.process_response',
                description='Legacy protocol: intercept and process responses before they are sent',
                interface=Middleware,
            ),
            ExtensionPoint(
                category=ExtensionCategory.MIDDLEWARE,
                name='GatewayMiddleware.__call__',
                description=(
                    'Recommended protocol: onion-model middleware entry point '
                    'async def __call__(self, request, call_next)'
                ),
                interface=GatewayMiddleware,
            ),
        ])

        # Lifecycle extension points (unified lifecycle)
        self._extension_points.extend([
            ExtensionPoint(
                category=ExtensionCategory.LIFECYCLE,
                name='on_post_construct',
                description='Initialize component after dependency injection',
                interface=Service,
            ),
            ExtensionPoint(
                category=ExtensionCategory.LIFECYCLE,
                name='on_startup',
                description='Execute logic during application startup',
                interface=Service,
            ),
            ExtensionPoint(
                category=ExtensionCategory.LIFECYCLE,
                name='on_shutdown',
                description='Clean up resources during application shutdown',
                interface=Service,
            ),
            ExtensionPoint(
                category=ExtensionCategory.LIFECYCLE,
                name='on_pre_destroy',
                description='Final cleanup before component destruction',
                interface=Service,
            ),
        ])

        # Injection extension points
        self._extension_points.extend([
            ExtensionPoint(
                category=ExtensionCategory.INJECTION,
                name='custom_scope',
                description='Define custom dependency injection scopes',
            ),
            ExtensionPoint(
                category=ExtensionCategory.INJECTION,
                name='custom_provider',
                description='Define custom dependency providers',
            ),
        ])

        # Routing extension points
        self._extension_points.extend([
            ExtensionPoint(
                category=ExtensionCategory.ROUTING,
                name='custom_handler',
                description='Register custom route handlers',
            ),
        ])

        # Configuration extension points
        self._extension_points.extend([
            ExtensionPoint(
                category=ExtensionCategory.CONFIGURATION,
                name='config_provider',
                description='Provide custom configuration sources',
            ),
        ])

    def get_extension_points(self,
                            category: Optional[ExtensionCategory] = None) -> List[ExtensionPoint]:
        """Get all registered extension points, optionally filtered by category.

        Args:
            category: Optional category filter

        Returns:
            List of extension points matching the criteria

        Example:
            >>> registry = get_extension_registry()
            >>> middleware_points = registry.get_extension_points(
            ...     category=ExtensionCategory.MIDDLEWARE
            ... )
            >>> for point in middleware_points:
            ...     print(f"{point.name}: {point.description}")
        """
        self._ensure_initialized()

        if category is None:
            return self._extension_points.copy()

        return [ep for ep in self._extension_points if ep.category == category]

    def get_extension_point(self, name: str) -> Optional[ExtensionPoint]:
        """Get a specific extension point by name.

        Args:
            name: The name of the extension point

        Returns:
            The extension point if found, None otherwise
        """
        self._ensure_initialized()

        for ep in self._extension_points:
            if ep.name == name:
                return ep
        return None

    def list_categories(self) -> List[str]:
        """List all available extension categories.

        Returns:
            List of category names
        """
        self._ensure_initialized()
        return [cat.value for cat in ExtensionCategory]


# Global registry instance
_extension_registry: Optional[ExtensionRegistry] = None


def get_extension_registry() -> ExtensionRegistry:
    """Get the global extension registry instance.

    Returns:
        The global ExtensionRegistry instance
    """
    global _extension_registry
    if _extension_registry is None:
        _extension_registry = ExtensionRegistry()
    return _extension_registry


def reset_extension_registry():
    """Reset the global extension registry (mainly for testing)."""
    global _extension_registry
    _extension_registry = None


def list_extension_points(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Convenience function to list extension points as dictionaries.

    Args:
        category: Optional category name filter

    Returns:
        List of extension point dictionaries

    Example:
        >>> from cullinan.support.extensions import list_extension_points
        >>> points = list_extension_points(category='middleware')
        >>> for point in points:
        ...     print(f"{point['name']}: {point['description']}")
    """
    registry = get_extension_registry()

    cat_enum = None
    if category:
        try:
            cat_enum = ExtensionCategory(category)
        except ValueError:
            logger.warning(f"Unknown extension category: {category}")
            return []

    points = registry.get_extension_points(category=cat_enum)
    return [point.to_dict() for point in points]

