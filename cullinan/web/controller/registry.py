# -*- coding: utf-8 -*-
"""Controller registry for Cullinan framework.

Uses the IoC/DI 2.0 system from cullinan.core.

Architecture design:
- ControllerRegistry stores Controller class definitions and routing information
- ApplicationContext handles dependency injection
- Supports route registration and HTTP method mapping

Performance optimizations:
- Fast O(1) controller and method lookup
- Lazy metadata and method storage initialization
- Memory-efficient with __slots__
- Batch method registration support
"""

from typing import Type, Any, Optional, Dict, List, Tuple
import logging
import threading

from cullinan.core import Registry
from cullinan.core.exceptions import RegistryError, DependencyResolutionError
from cullinan.core.provider_source import ProviderSource

logger = logging.getLogger(__name__)


class ControllerRegistry(Registry[Type[Any]], ProviderSource):
    """Controller registry

    Responsibilities:
    1. Store Controller class definitions
    2. Manage URL routing and HTTP method mapping
    3. Manage Controller singleton instances
    4. Provide Controller instance lookup interface

    Usage:
        # Auto-register via @controller decorator (recommended)
        @controller(url='/api/users')
        class UserController:
            user_service: UserService = Inject()

        # Or register manually
        registry = get_controller_registry()
        registry.register('UserController', UserController, url_prefix='/api/users')
        registry.register_method('UserController', '', 'get', handler_func)
    """

    __slots__ = ('_controller_methods', '_controller_instances', '_instance_lock')

    def __init__(self):
        """Initialize the Controller registry and register as a provider in the core DI system"""
        super().__init__()

        # Lazy init - only created on first method registration
        # Maps controller_name -> [(url, method, func), ...]
        self._controller_methods: Optional[Dict[str, List[Tuple[str, str, Any]]]] = None

        # Controller instance cache (singleton pattern)
        # Each Controller is created only once, shared across all requests
        # Note: Controllers must be designed stateless (thread-safe)
        self._controller_instances: Dict[str, Any] = {}

        # Thread lock (ensures singleton thread safety)
        self._instance_lock = threading.RLock()

        # In 0.93, we no longer auto-register to InjectionRegistry
        # ApplicationContext handles all dependency injection
        logger.debug("ControllerRegistry initialized")

    def register(self, name: str, controller_class: Type[Any],
                 url_prefix: str = '', **metadata) -> None:
        """Register a Controller class (O(1) operation)

        Note:
        - Controller classes should use the @controller decorator
        - Dependency injection is handled by ApplicationContext during refresh()
        - Controller instances are typically singletons, shared across all requests

        Args:
            name: Unique identifier for the Controller (usually the class name)
            controller_class: The Controller class
            url_prefix: URL prefix for all routes
            **metadata: Additional metadata (e.g., middleware, auth requirements)

        Raises:
            RegistryError: If name is already registered, invalid, or registry is frozen
        """
        self._check_frozen()
        self._validate_name(name)

        # Fast path: check if already registered
        if name in self._items:
            logger.warning(f"Controller already registered: {name}")
            return

        # Register Controller class (O(1))
        self._items[name] = controller_class

        # Lazy metadata initialization
        if url_prefix or metadata:
            if self._metadata is None:
                self._metadata = {}
            meta = metadata.copy()
            meta['url_prefix'] = url_prefix
            self._metadata[name] = meta
        elif self._metadata is not None or url_prefix == '':
            # Store empty prefix for consistency
            if self._metadata is None:
                self._metadata = {}
            self._metadata[name] = {'url_prefix': url_prefix}

        logger.debug(f"Registered controller: {name} with prefix: {url_prefix} (DI via core.injectable)")

    def register_method(self, controller_name: str, url: str,
                       http_method: str, handler_func: Any) -> None:
        """Register a method handler for a controller (O(1) operation).

        Args:
            controller_name: Name of the controller
            url: URL pattern for this method (relative to controller prefix)
            http_method: HTTP method (get, post, put, delete, etc.)
            handler_func: The handler function

        Raises:
            RegistryError: If controller not found or registry frozen
        """
        self._check_frozen()

        if controller_name not in self._items:
            raise RegistryError(f"Controller not found: {controller_name}")

        # Lazy init method storage
        if self._controller_methods is None:
            self._controller_methods = {}

        # Ensure list exists for this controller
        if controller_name not in self._controller_methods:
            self._controller_methods[controller_name] = []

        # Register method (O(1) append)
        method_info = (url, http_method, handler_func)
        self._controller_methods[controller_name].append(method_info)

        logger.debug(f"Registered method: {controller_name}.{http_method} {url}")

    def register_methods_batch(self, controller_name: str,
                               methods: List[Tuple[str, str, Any]]) -> int:
        """Register multiple methods for a controller in batch (optimized).

        More efficient than calling register_method multiple times.

        Args:
            controller_name: Name of the controller
            methods: List of (url, http_method, handler_func) tuples

        Returns:
            Number of methods successfully registered

        Raises:
            RegistryError: If controller not found or registry frozen
        """
        self._check_frozen()

        if controller_name not in self._items:
            raise RegistryError(f"Controller not found: {controller_name}")

        # Lazy init method storage
        if self._controller_methods is None:
            self._controller_methods = {}

        # Ensure list exists
        if controller_name not in self._controller_methods:
            self._controller_methods[controller_name] = []

        # Batch append (more efficient than multiple appends)
        self._controller_methods[controller_name].extend(methods)

        logger.debug(f"Registered {len(methods)} methods for controller: {controller_name}")
        return len(methods)

    def get(self, name: str) -> Optional[Type[Any]]:
        """Get a Controller class (O(1) operation)

        Args:
            name: Controller identifier

        Returns:
            Controller class, or None if not found
        """
        return self._items.get(name)

    def get_instance(self, name: str) -> Optional[Any]:
        """Get or create a Controller singleton instance (O(1) cache lookup, thread-safe)

        Workflow:
        1. Check cache, return immediately if exists (O(1))
        2. If not exists, create a new instance
        3. ApplicationContext handles dependency injection
        4. Cache the instance for all requests to share

        Note:
        - Controllers are singletons, shared across all requests
        - Controllers must be designed stateless (do not store request data in instance variables)
        - Request-related data is passed via method parameters

        Args:
            name: Controller identifier

        Returns:
            Controller instance, or None if not found

        Raises:
            DependencyResolutionError: If dependencies cannot be resolved
        """
        # Fast path: return cached instance (O(1)) - no lock needed for reads
        instance = self._controller_instances.get(name)
        if instance is not None:
            return instance

        # Check if Controller exists
        if name not in self._items:
            logger.debug(f"Controller not found: {name}")
            return None

        # Thread-safe singleton creation (Double-check locking pattern)
        with self._instance_lock:
            # Double-check: another thread may have already created it
            instance = self._controller_instances.get(name)
            if instance is not None:
                return instance

            try:
                controller_class = self._items[name]

                # [CRITICAL] Create instance via ApplicationContext and inject dependencies
                # Cannot instantiate directly, because @controller decorator does not include @injectable logic
                from cullinan.core import get_application_context
                ctx = get_application_context()

                if ctx is not None and ctx.is_refreshed:
                    # Prefer using ApplicationContext's dependency injection mechanism
                    instance = ctx._create_class_instance(controller_class)
                else:
                    # Fallback: instantiate directly (no dependency injection)
                    logger.warning(
                        f"ApplicationContext not available for controller {name}, "
                        f"dependencies will not be injected"
                    )
                    instance = controller_class()

                # Cache instance immediately (O(1))
                self._controller_instances[name] = instance

                logger.debug(f"Created controller singleton: {name} (dependencies injected via ApplicationContext)")
                return instance

            except Exception as e:
                logger.error(f"Failed to instantiate controller {name}: {e}", exc_info=True)
                raise DependencyResolutionError(f"Failed to create controller {name}: {e}") from e

    def get_methods(self, controller_name: str) -> List[Tuple[str, str, Any]]:
        """Get all registered methods for a controller (O(1) lookup + copy).

        Args:
            controller_name: Name of the controller

        Returns:
            List of (url, http_method, handler_func) tuples (copy for safety)
        """
        if self._controller_methods is None:
            return []
        return self._controller_methods.get(controller_name, []).copy()

    def has_methods(self, controller_name: str) -> bool:
        """Check if controller has any methods registered (O(1) operation).

        Args:
            controller_name: Name of the controller

        Returns:
            True if controller has methods, False otherwise
        """
        if self._controller_methods is None:
            return False
        return controller_name in self._controller_methods and \
               len(self._controller_methods[controller_name]) > 0

    def get_method_count(self, controller_name: str) -> int:
        """Get number of methods for a controller (O(1) operation).

        Args:
            controller_name: Name of the controller

        Returns:
            Number of registered methods
        """
        if self._controller_methods is None:
            return 0
        return len(self._controller_methods.get(controller_name, []))

    def get_url_prefix(self, controller_name: str) -> Optional[str]:
        """Get the URL prefix for a controller (O(1) operation).

        Args:
            controller_name: Name of the controller

        Returns:
            URL prefix string, or None if controller not found
        """
        if self._metadata is None:
            return None
        metadata = self._metadata.get(controller_name)
        if metadata:
            return metadata.get('url_prefix', '')
        return None

    def clear(self) -> None:
        """Clear all registered controllers and methods.

        Useful for testing or application reinitialization.
        """
        super().clear()
        if self._controller_methods is not None:
            self._controller_methods.clear()
        logger.debug("Cleared all registered controllers")

    def count(self) -> int:
        """Get the number of registered controllers (O(1) operation).

        Returns:
            Number of registered controllers
        """
        return len(self._items)

    def list_all_methods(self) -> Dict[str, List[Tuple[str, str, Any]]]:
        """Get all registered methods for all controllers.

        Returns:
            Dictionary mapping controller names to their method lists (copy)
        """
        if self._controller_methods is None:
            return {}
        return {name: methods.copy() for name, methods in self._controller_methods.items()}

    # ========================================================================
    # ProviderSource Interface Implementation
    # ========================================================================

    def can_provide(self, name: str) -> bool:
        """Check if this registry can provide the given controller.

        Args:
            name: Controller name

        Returns:
            True if controller is registered
        """
        return name in self._items

    def provide(self, name: str) -> Optional[Any]:
        """Provide a controller instance.

        Args:
            name: Controller name

        Returns:
            Controller instance or None if not found
        """
        return self.get_instance(name)

    def list_available(self) -> List[str]:
        """List all available controller names.

        Returns:
            List of controller names
        """
        return list(self._items.keys())

    def get_priority(self) -> int:
        """Get the priority of this provider source.

        Returns:
            Priority value (5 for controllers, lower than services)
        """
        return 5


# Global controller registry instance (singleton pattern)
_global_controller_registry = ControllerRegistry()


def get_controller_registry() -> ControllerRegistry:
    """Get the global controller registry instance.

    Returns:
        The global ControllerRegistry instance
    """
    return _global_controller_registry


def reset_controller_registry() -> None:
    """Reset the global controller registry.

    Useful for testing to ensure clean state between tests.
    """
    _global_controller_registry.clear()
    logger.debug("Reset global controller registry")
