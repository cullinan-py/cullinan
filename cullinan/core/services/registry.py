# -*- coding: utf-8 -*-
"""Service registry for Cullinan framework.

Uses the IoC/DI 2.0 system from cullinan.core.

Architecture:
- ServiceRegistry stores service class definitions
- ApplicationContext handles dependency injection and unified lifecycle management
- All lifecycle hooks are invoked centrally by ApplicationContext

Performance optimizations:
- Fast O(1) service lookup with direct dict access
- Lazy metadata initialization
- Memory-efficient with __slots__
- Singleton instance caching
"""

from typing import Type, Optional, List, Dict
import logging
import threading

from cullinan.core import Registry
from cullinan.core.exceptions import DependencyResolutionError
from cullinan.core.provider_source import ProviderSource
from .base import Service

logger = logging.getLogger(__name__)


class ServiceRegistry(Registry[Type[Service]], ProviderSource):
    """Service registry

    Responsibilities:
    1. Store service class definitions
    2. Create and cache singleton service instances
    3. Provide service instance lookup as a ProviderSource

    Note: Lifecycle management has been moved to ApplicationContext;
    this class no longer calls on_post_construct/on_startup/on_shutdown/on_pre_destroy.

    Usage:
        # Auto-register via @service decorator (recommended)
        @service
        class EmailService(Service):
            pass

        # Or register manually
        registry = get_service_registry()
        registry.register('EmailService', EmailService)

        # Get service instance
        email_service = registry.get_instance('EmailService')
    """
    
    __slots__ = ('_instances', '_instance_lock', '_priority')

    def __init__(self, priority: int = 10, auto_register: bool = True):
        """Initialize the service registry

        Args:
            priority: ProviderSource priority (default 10)
            auto_register: Whether to auto-register (default True)
        """
        super().__init__()

        # Service instance cache (O(1) lookup)
        self._instances: Dict[str, Service] = {}

        # Thread lock (ensures singleton thread safety)
        self._instance_lock = threading.RLock()

        # ProviderSource priority
        self._priority = priority

        if auto_register:
            logger.debug(f"ServiceRegistry initialized (priority={self._priority})")

    def register(self, name: str, service_class: Type[Service],
                 dependencies: Optional[List[str]] = None, **metadata) -> None:
        """Register a service class (O(1) operation)

        Args:
            name: Unique service identifier (typically the class name)
            service_class: Service class (not an instance)
            dependencies: List of dependency service names (optional, metadata only)
            **metadata: Additional metadata

        Raises:
            RegistryError: If name is already registered, invalid, or registry is frozen
        """
        self._check_frozen()
        self._validate_name(name)

        if name in self._items:
            logger.warning(f"Service already registered: {name}")
            return

        self._items[name] = service_class

        if dependencies or metadata:
            if self._metadata is None:
                self._metadata = {}
            meta = metadata.copy()
            meta['dependencies'] = dependencies or []
            self._metadata[name] = meta

        logger.debug(f"Registered service class: {name}")

    def get(self, name: str) -> Optional[Type[Service]]:
        """Get the service class (not instance) by name (O(1) operation).

        Args:
            name: Service identifier

        Returns:
            Service class, or None if not found
        """
        return self._items.get(name)

    def get_instance(self, name: str) -> Optional[Service]:
        """Get or create a service instance (O(1) cache lookup, thread-safe)

        Instances are created through ApplicationContext, which manages lifecycle.

        Args:
            name: Service identifier

        Returns:
            Service instance, or None if not found

        Raises:
            DependencyResolutionError: If dependencies cannot be resolved
        """
        instance = self._instances.get(name)
        if instance is not None:
            return instance

        if name not in self._items:
            logger.debug(f"Service not found: {name}")
            return None

        with self._instance_lock:
            instance = self._instances.get(name)
            if instance is not None:
                return instance

            try:
                service_class = self._items[name]

                # Create instance through ApplicationContext
                from cullinan.core import get_application_context
                ctx = get_application_context()

                if ctx is not None and ctx.is_refreshed:
                    instance = ctx._create_class_instance(service_class)
                else:
                    instance = service_class()

                self._instances[name] = instance
                logger.debug(f"Created service instance: {name}")
                return instance

            except Exception as e:
                logger.error(f"Failed to instantiate service {name}: {e}", exc_info=True)
                raise DependencyResolutionError(f"Failed to create {name}: {e}") from e

    def clear(self) -> None:
        """Clear all services and instances"""
        super().clear()
        self._instances.clear()
        logger.debug("Cleared service registry")

    def list_instances(self) -> Dict[str, Service]:
        """Get all service instances that have been created.

        Returns:
            Dictionary mapping service names to instances
        """
        return self._instances.copy()

    def has_instance(self, name: str) -> bool:
        """Check if a service instance has been created.

        Args:
            name: Service identifier

        Returns:
            True if instance exists, False otherwise
        """
        return name in self._instances

    # ========================================================================
    # ProviderSource Interface Implementation
    # ========================================================================

    def can_provide(self, name: str) -> bool:
        """Check whether a service with the given name can be provided"""
        return self.has(name)

    def provide(self, name: str) -> Optional[Service]:
        """Provide the service instance for the given name"""
        return self.get_instance(name)

    def list_available(self) -> List[str]:
        """List all available service names"""
        return list(self._items.keys())

    def get_priority(self) -> int:
        """Get the priority of this ProviderSource"""
        return self._priority


# Global service registry instance
_global_service_registry = ServiceRegistry()


def get_service_registry() -> ServiceRegistry:
    """Get the global service registry instance."""
    return _global_service_registry


def reset_service_registry() -> None:
    """Reset the global service registry."""
    _global_service_registry.clear()
    logger.debug("Reset global service registry")
