# -*- coding: utf-8 -*-
"""Middleware registry for Cullinan framework.

Provides centralized middleware registration and management with
decorator-based registration similar to @service and @controller.

Author: plumeink
"""

from typing import List, Optional, Dict, Type, Callable, Tuple
import logging
from cullinan.support.deprecation import resolve_removal_version
from .base import Middleware, MiddlewareChain

logger = logging.getLogger(__name__)

# A legacy ``@middleware`` class is now owned by the application container: the
# instance installed on the pipeline is the one the container creates and
# injects, instead of a second one built privately here. The declaration does not
# change -- ``@middleware(priority=...)`` keeps its syntax and its default. The
# removal version for the transition is derived from the release line it landed
# on plus the standard deprecation window, never written as a literal, so it
# cannot drift into a second, inconsistent value.
_LEGACY_OWNERSHIP_ANCHOR = "0.96"
_LEGACY_OWNERSHIP_REMOVAL_VERSION = resolve_removal_version(_LEGACY_OWNERSHIP_ANCHOR)


class MiddlewareRegistry:
    """Registry for managing middleware components.

    Provides:
    - Decorator-based middleware registration
    - Priority-based ordering
    - Lifecycle management (initialization and cleanup)

    Example:
        >>> from cullinan.web.middleware import middleware, Middleware
        >>>
        >>> @middleware(priority=100)
        >>> class LoggingMiddleware(Middleware):
        ...     def process_request(self, handler):
        ...         print(f"Request: {handler.request.uri}")
        ...         return None
    """

    def __init__(self):
        """Initialize the middleware registry."""
        self._middleware: List[tuple[int, Type[Middleware], Optional[Middleware]]] = []
        # Format: [(priority, middleware_class, instance), ...]
        self._initialized = False

    def register(self,
                 middleware_class: Type[Middleware],
                 priority: int = 100,
                 instance: Optional[Middleware] = None) -> None:
        """Register a middleware class or instance.

        Args:
            middleware_class: The middleware class to register
            priority: Priority for ordering (lower runs first, default 100)
            instance: Optional pre-instantiated middleware (for advanced use)

        Raises:
            TypeError: If middleware_class is not a Middleware subclass
        """
        if not issubclass(middleware_class, Middleware):
            raise TypeError(
                f"Expected Middleware subclass, got {middleware_class.__name__}"
            )

        self._middleware.append((priority, middleware_class, instance))
        logger.debug(
            f"Registered middleware: {middleware_class.__name__} "
            f"with priority {priority}"
        )

    def iter_ordered_middleware(self) -> List[Tuple[int, Middleware]]:
        """Return the registered middleware as ``(priority, instance)`` pairs.

        Middleware are ordered by priority (lower runs first) and instantiated
        on demand. This ordered, per-instance view is what lets the gateway
        bridge turn each legacy middleware into its own pipeline layer instead
        of one opaque wrapper, so a legacy middleware keeps the priority it
        declared through ``@middleware(priority=...)``.

        The instance is created by the application container (see
        ``_create_instance``), so a legacy middleware that declares dependencies
        gets them injected, the same way a declarative class entry does.
        """
        ordered: List[Tuple[int, Middleware]] = []
        for priority, middleware_class, instance in sorted(self._middleware, key=lambda x: x[0]):
            if instance is None:
                # Instantiate the middleware through the container
                try:
                    instance = self._create_instance(middleware_class)
                    logger.debug(
                        "Instantiated middleware: %s (container-owned; the "
                        "ownership transition window ends at v%s)",
                        middleware_class.__name__,
                        _LEGACY_OWNERSHIP_REMOVAL_VERSION,
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to instantiate {middleware_class.__name__}: {e}",
                        exc_info=True
                    )
                    raise
            ordered.append((priority, instance))
        return ordered

    @staticmethod
    def _create_instance(middleware_class: Type[Middleware]) -> Middleware:
        """Create a middleware through the application container, with DI.

        A legacy ``@middleware`` class used to be constructed with a bare
        ``middleware_class()`` call owned by no one, so a middleware that
        declared dependencies received none. The container creates it instead,
        so the instance installed on the pipeline is a container participant:
        its declared dependencies are injected, and an unresolvable dependency
        fails while the application is assembled rather than on the first
        request.

        The registry also works stand-alone -- ``get_middleware_chain()`` is
        called outside an assembled application -- so with no refreshed
        container available the plain construction is kept.
        """
        from cullinan.core import get_application_context

        context = get_application_context()
        if context is not None and context.is_refreshed:
            return context._create_class_instance(middleware_class)
        return middleware_class()

    def get_middleware_chain(self) -> MiddlewareChain:
        """Create a middleware chain with all registered middleware.

        Middleware are sorted by priority (lower values run first).

        Returns:
            Configured MiddlewareChain instance
        """
        chain = MiddlewareChain()

        for _priority, instance in self.iter_ordered_middleware():
            chain.add(instance)

        return chain

    def initialize_all(self) -> None:
        """Initialize all registered middleware.

        Calls unified lifecycle methods (on_post_construct, on_startup) on all middleware.
        """
        if self._initialized:
            logger.debug("Middleware already initialized")
            return

        chain = self.get_middleware_chain()
        chain.initialize_all()
        self._initialized = True
        logger.info("All middleware initialized")

    def get_registered_middleware(self) -> List[Dict[str, any]]:
        """Get information about all registered middleware.

        Returns:
            List of dictionaries with middleware information
        """
        return [
            {
                'name': middleware_class.__name__,
                'priority': priority,
                'class': middleware_class,
                'instantiated': instance is not None,
            }
            for priority, middleware_class, instance in self._middleware
        ]

    def clear(self) -> None:
        """Clear all registered middleware (mainly for testing)."""
        self._middleware.clear()
        self._initialized = False
        logger.debug("Middleware registry cleared")


# Global registry instance
_middleware_registry: Optional[MiddlewareRegistry] = None


def get_middleware_registry() -> MiddlewareRegistry:
    """Get the global middleware registry instance.

    Returns:
        The global MiddlewareRegistry instance
    """
    global _middleware_registry
    if _middleware_registry is None:
        _middleware_registry = MiddlewareRegistry()
    return _middleware_registry


def reset_middleware_registry():
    """Reset the global middleware registry (mainly for testing)."""
    global _middleware_registry
    _middleware_registry = None


def middleware(priority: int = 100) -> Callable:
    """Decorator for registering middleware classes.

    Similar to @service and @controller decorators, provides a unified
    way to register middleware components.

    Args:
        priority: Priority for middleware execution order (lower runs first)
                 Default: 100
                 Suggested ranges:
                 - 0-50: Critical (CORS, security)
                 - 51-100: Standard (logging, metrics)
                 - 101-200: Application-specific

    Returns:
        Decorator function

    Example:
        >>> from cullinan.web.middleware import middleware, Middleware
        >>>
        >>> @middleware(priority=50)
        >>> class SecurityMiddleware(Middleware):
        ...     def process_request(self, handler):
        ...         # Security checks
        ...         return None
        >>>
        >>> @middleware(priority=100)
        >>> class LoggingMiddleware(Middleware):
        ...     def process_request(self, handler):
        ...         print(f"Request: {handler.request.uri}")
        ...         return None
        >>>
        >>> # SecurityMiddleware runs before LoggingMiddleware
    """
    def decorator(middleware_class: Type[Middleware]) -> Type[Middleware]:
        """Inner decorator that performs the registration."""
        registry = get_middleware_registry()
        registry.register(middleware_class, priority=priority)
        logger.debug(
            f"Registered middleware via decorator: {middleware_class.__name__}"
        )
        return middleware_class

    return decorator

