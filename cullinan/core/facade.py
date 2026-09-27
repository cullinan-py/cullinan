# -*- coding: utf-8 -*-
"""IoC/DI Facade - Unified dependency resolution interface.

Provides a simplified, unified API for dependency resolution that internally
coordinates ProviderRegistry, InjectionRegistry, and ServiceRegistry.

This facade reduces complexity for end users while maintaining the flexibility
of the underlying three-tier registry architecture.

Author: plumeink
"""

from typing import Type, TypeVar, Optional, Any, Dict, List
import logging
from threading import RLock

logger = logging.getLogger(__name__)

T = TypeVar('T')


class DependencyResolutionError(Exception):
    """Raised when dependency resolution fails."""
    pass


class IoCFacade:
    """Unified facade for IoC/DI dependency resolution.

    This class provides a simplified API for resolving dependencies,
    abstracting away the complexity of the three-tier registry system
    (ProviderRegistry, InjectionRegistry, ServiceRegistry).

    Key Features:
    - Simple resolve() method for all dependency types
    - Automatic type-based resolution
    - Name-based resolution support
    - Caching for performance
    - Clear error messages

    Example:
        >>> facade = IoCFacade()
        >>> # Type-based resolution
        >>> user_service = facade.resolve(UserService)
        >>> # Name-based resolution
        >>> config = facade.resolve_by_name('Config')
        >>> # Check if dependency exists
        >>> if facade.has_dependency(EmailService):
        ...     email_service = facade.resolve(EmailService)
    """

    def __init__(self):
        """Initialize the IoC facade."""
        self._lock = RLock()
        self._resolution_cache: Dict[str, Any] = {}
        self._injection_registry = None
        self._provider_registry = None
        self._service_registry = None
        self._initialized = False

    def initialize(self,
                   injection_registry=None,
                   provider_registry=None,
                   service_registry=None) -> None:
        """Initialize the facade with registry instances.

        Args:
            injection_registry: InjectionRegistry instance
            provider_registry: ProviderRegistry instance
            service_registry: ServiceRegistry instance
        """
        with self._lock:
            if injection_registry:
                self._injection_registry = injection_registry
            if provider_registry:
                self._provider_registry = provider_registry
            if service_registry:
                self._service_registry = service_registry

            # Auto-discover registries if not provided
            if not self._initialized:
                self._auto_discover_registries()

            self._initialized = True
            logger.debug("IoCFacade initialized")

    def _auto_discover_registries(self) -> None:
        """Auto-discover registry instances from the framework."""
        try:
            # In 0.93, injection_registry is no longer used
            # We keep this for compatibility but it returns None
            if not self._injection_registry:
                self._injection_registry = None

            if not self._service_registry:
                from cullinan.core.services import get_service_registry
                self._service_registry = get_service_registry()

            logger.debug("Auto-discovered registries successfully")
        except Exception as e:
            logger.warning(f"Auto-discovery failed: {e}")

    def resolve(self,
                service_type: Type[T],
                *,
                required: bool = True,
                use_cache: bool = True) -> Optional[T]:
        """Resolve a dependency by its type.

        This is the primary method for dependency resolution. It automatically
        determines the dependency name from the type and resolves it.

        Args:
            service_type: The type of the dependency to resolve
            required: If True, raises error when dependency not found
            use_cache: If True, uses cached instances for singletons

        Returns:
            The resolved dependency instance, or None if not found and not required

        Raises:
            DependencyResolutionError: If dependency not found and required=True

        Example:
            >>> user_service = facade.resolve(UserService)
            >>> # Optional dependency
            >>> cache = facade.resolve(CacheService, required=False)
            >>> if cache:
            ...     cache.clear()
        """
        if not self._initialized:
            self.initialize()

        # Get dependency name from type
        name = service_type.__name__

        # Try cache first (for singletons)
        if use_cache:
            cached = self._resolution_cache.get(name)
            if cached is not None:
                logger.debug(f"Resolved {name} from cache")
                return cached

        # Resolve from registries
        instance = self._resolve_from_registries(name, service_type)

        if instance is None and required:
            raise DependencyResolutionError(
                f"Cannot resolve dependency: {name}. "
                f"Make sure it's registered with @service or configured in providers."
            )

        # Cache singleton instances
        if instance is not None and use_cache:
            self._resolution_cache[name] = instance

        return instance

    def resolve_by_name(self,
                       name: str,
                       *,
                       required: bool = True,
                       use_cache: bool = True) -> Optional[Any]:
        """Resolve a dependency by its name.

        Useful when you don't have access to the type or need to resolve
        by a custom name.

        Args:
            name: The name of the dependency to resolve
            required: If True, raises error when dependency not found
            use_cache: If True, uses cached instances

        Returns:
            The resolved dependency instance, or None if not found

        Raises:
            DependencyResolutionError: If dependency not found and required=True

        Example:
            >>> config = facade.resolve_by_name('Config')
            >>> db = facade.resolve_by_name('DatabaseConnection')
        """
        if not self._initialized:
            self.initialize()

        # Try cache first
        if use_cache:
            cached = self._resolution_cache.get(name)
            if cached is not None:
                logger.debug(f"Resolved {name} from cache")
                return cached

        # Resolve from registries
        instance = self._resolve_from_registries(name, None)

        if instance is None and required:
            raise DependencyResolutionError(
                f"Cannot resolve dependency by name: {name}. "
                f"Available: {self.list_available_dependencies()}"
            )

        # Cache if found
        if instance is not None and use_cache:
            self._resolution_cache[name] = instance

        return instance

    def _resolve_from_registries(self,
                                 name: str,
                                 service_type: Optional[Type] = None) -> Optional[Any]:
        """Internal method to resolve from the three-tier registry system.

        Resolution order:
        1. ServiceRegistry (highest priority - framework services)
        2. ProviderRegistry (configured providers)
        3. InjectionRegistry (fallback - uses provider registries)

        Args:
            name: Dependency name
            service_type: Optional type hint for better resolution

        Returns:
            Resolved instance or None
        """
        # Try ServiceRegistry first (highest priority)
        if self._service_registry:
            try:
                instance = self._service_registry.get_instance(name)
                if instance is not None:
                    logger.debug(f"Resolved {name} from ServiceRegistry")
                    return instance
            except Exception as e:
                logger.debug(f"ServiceRegistry resolution failed for {name}: {e}")

        # Try ProviderRegistry
        if self._provider_registry:
            try:
                instance = self._provider_registry.get_instance(name)
                if instance is not None:
                    logger.debug(f"Resolved {name} from ProviderRegistry")
                    return instance
            except Exception as e:
                logger.debug(f"ProviderRegistry resolution failed for {name}: {e}")

        # Fallback to InjectionRegistry
        if self._injection_registry:
            try:
                instance = self._injection_registry._resolve_dependency(name)
                if instance is not None:
                    logger.debug(f"Resolved {name} from InjectionRegistry")
                    return instance
            except Exception as e:
                logger.debug(f"InjectionRegistry resolution failed for {name}: {e}")

        logger.warning(f"Failed to resolve dependency: {name}")
        return None

    def has_dependency(self, service_type: Type) -> bool:
        """Check if a dependency can be resolved.

        Args:
            service_type: The type to check

        Returns:
            True if the dependency can be resolved

        Example:
            >>> if facade.has_dependency(CacheService):
            ...     cache = facade.resolve(CacheService)
        """
        try:
            instance = self.resolve(service_type, required=False, use_cache=False)
            return instance is not None
        except Exception:
            return False

    def has_dependency_by_name(self, name: str) -> bool:
        """Check if a dependency can be resolved by name.

        Args:
            name: The dependency name to check

        Returns:
            True if the dependency can be resolved
        """
        try:
            instance = self.resolve_by_name(name, required=False, use_cache=False)
            return instance is not None
        except Exception:
            return False

    def list_available_dependencies(self) -> List[str]:
        """List all available dependency names.

        Returns:
            List of available dependency names

        Example:
            >>> deps = facade.list_available_dependencies()
            >>> print(f"Available: {', '.join(deps)}")
        """
        dependencies = set()

        # Collect from ServiceRegistry
        if self._service_registry:
            try:
                dependencies.update(self._service_registry._items.keys())
            except Exception as e:
                logger.debug(f"Failed to list from ServiceRegistry: {e}")

        # Collect from ProviderRegistry
        if self._provider_registry:
            try:
                dependencies.update(self._provider_registry._providers.keys())
            except Exception as e:
                logger.debug(f"Failed to list from ProviderRegistry: {e}")

        return sorted(list(dependencies))

    def clear_cache(self) -> None:
        """Clear the resolution cache.

        Use this when you need to force re-resolution of dependencies.

        Example:
            >>> facade.clear_cache()
            >>> # Next resolve() will fetch fresh instances
        """
        with self._lock:
            self._resolution_cache.clear()
            logger.info("Dependency resolution cache cleared")

    def reset(self) -> None:
        """Reset the facade to initial state.

        Clears cache and registry references. Mainly for testing.
        """
        with self._lock:
            self._resolution_cache.clear()
            self._injection_registry = None
            self._provider_registry = None
            self._service_registry = None
            self._initialized = False
            logger.info("IoCFacade reset")


# Global facade instance
_ioc_facade: Optional[IoCFacade] = None
_facade_lock = RLock()


def get_ioc_facade() -> IoCFacade:
    """Get the global IoC facade instance.

    Returns:
        The global IoCFacade instance

    Example:
        >>> from cullinan.core.facade import get_ioc_facade
        >>> facade = get_ioc_facade()
        >>> user_service = facade.resolve(UserService)
    """
    global _ioc_facade
    if _ioc_facade is None:
        with _facade_lock:
            if _ioc_facade is None:
                _ioc_facade = IoCFacade()
                _ioc_facade.initialize()
    return _ioc_facade


def reset_ioc_facade() -> None:
    """Reset the global IoC facade instance.

    Mainly for testing purposes.
    """
    global _ioc_facade
    with _facade_lock:
        if _ioc_facade:
            _ioc_facade.reset()
        _ioc_facade = None


# Convenience functions for common operations

def resolve_dependency(service_type: Type[T], *, required: bool = True) -> Optional[T]:
    """Convenience function to resolve a dependency by type.

    Args:
        service_type: The type of the dependency
        required: If True, raises error when not found

    Returns:
        The resolved dependency instance

    Raises:
        DependencyResolutionError: If not found and required=True

    Example:
        >>> from cullinan.core.facade import resolve_dependency
        >>> user_service = resolve_dependency(UserService)
    """
    facade = get_ioc_facade()
    return facade.resolve(service_type, required=required)


def resolve_dependency_by_name(name: str, *, required: bool = True) -> Optional[Any]:
    """Convenience function to resolve a dependency by name.

    Args:
        name: The dependency name
        required: If True, raises error when not found

    Returns:
        The resolved dependency instance

    Raises:
        DependencyResolutionError: If not found and required=True

    Example:
        >>> from cullinan.core.facade import resolve_dependency_by_name
        >>> config = resolve_dependency_by_name('Config')
    """
    facade = get_ioc_facade()
    return facade.resolve_by_name(name, required=required)


def has_dependency(service_type: Type) -> bool:
    """Check if a dependency exists.

    Args:
        service_type: The type to check

    Returns:
        True if the dependency can be resolved

    Example:
        >>> from cullinan.core.facade import has_dependency
        >>> if has_dependency(CacheService):
        ...     cache = resolve_dependency(CacheService)
    """
    facade = get_ioc_facade()
    return facade.has_dependency(service_type)

