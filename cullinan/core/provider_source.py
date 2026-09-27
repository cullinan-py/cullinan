# -*- coding: utf-8 -*-
"""Provider Source abstract interface — dependency provider for the IoC/DI system.

Defines a unified dependency-provider interface that all dependency-providing
registries should implement. This allows InjectionRegistry to depend only on
the abstract interface rather than concrete implementations.

Design principles:
- Dependency inversion: upper layers depend on abstractions, not concretions
- Interface segregation: only expose necessary methods
- Single responsibility: only responsible for providing dependencies, not lifecycle management

Author: plumeink
"""

from abc import ABC, abstractmethod
from typing import Optional, Any, List


class ProviderSource(ABC):
    """Abstract interface for dependency provider sources.

    All registries that provide dependency instances should implement this interface.
    This allows InjectionRegistry to depend only on the abstract interface rather
    than concrete implementations.

    Classes implementing this interface include:
    - ProviderRegistry: provides ClassProvider, InstanceProvider, FactoryProvider instances
    - ServiceRegistry: provides Service instances (with lifecycle management)
    - Other custom registries (extensions)

    Design points:
    1. Defines only the ability to "provide dependencies", not registration or lifecycle
    2. Supports priority so InjectionRegistry can query in priority order
    3. Interface methods should be efficient (O(1) or O(log n))

    Example:
        # Implement a custom ProviderSource
        class ConfigRegistry(ProviderSource):
            def can_provide(self, name: str) -> bool:
                return name in self._configs

            def provide(self, name: str) -> Optional[Any]:
                return self._configs.get(name)

            def list_available(self) -> List[str]:
                return list(self._configs.keys())

            def get_priority(self) -> int:
                return 50  # Higher priority than default

        # Register with InjectionRegistry
        injection_registry.add_provider_source(ConfigRegistry())
    """

    @abstractmethod
    def can_provide(self, name: str) -> bool:
        """Check whether a dependency with the given name can be provided.

        This method should be efficient (O(1)) as it will be called frequently.

        Args:
            name: dependency name (typically class name or service name)

        Returns:
            True if the dependency can be provided, False otherwise

        Example:
            >>> source.can_provide('UserService')
            True
            >>> source.can_provide('NonExistentService')
            False
        """
        pass

    @abstractmethod
    def provide(self, name: str) -> Optional[Any]:
        """Provide a dependency instance for the given name.

        Only called after can_provide() returns True.
        If the dependency exists but creation fails, raise an exception rather than
        returning None.

        Args:
            name: dependency name

        Returns:
            The dependency instance, or None if it cannot be provided

        Raises:
            DependencyResolutionError: if dependency resolution fails
            CircularDependencyError: if a circular dependency is detected

        Example:
            >>> instance = source.provide('UserService')
            >>> assert instance is not None
            >>> assert isinstance(instance, UserService)
        """
        pass

    @abstractmethod
    def list_available(self) -> List[str]:
        """List all available dependency names.

        Intended for debugging and diagnostics; does not need high performance.

        Returns:
            List of dependency names

        Example:
            >>> names = source.list_available()
            >>> print(names)
            ['UserService', 'EmailService', 'CacheService']
        """
        pass

    @abstractmethod
    def get_priority(self) -> int:
        """Get the priority of this ProviderSource.

        InjectionRegistry queries sources in descending priority order.
        Recommended priority ranges:
        - 100+: high priority (e.g., config, environment variables)
        - 10-99: normal priority (e.g., ServiceRegistry)
        - 1-9: low priority (e.g., defaults, fallback)
        - 0: lowest priority

        Returns:
            Priority value; higher values take precedence

        Example:
            >>> source.get_priority()
            10
        """
        pass

    def __repr__(self) -> str:
        """Return a human-readable string representation."""
        available_count = len(self.list_available()) if hasattr(self, 'list_available') else '?'
        return (
            f"{self.__class__.__name__}("
            f"priority={self.get_priority()}, "
            f"available={available_count})"
        )


class SimpleProviderSource(ProviderSource):
    """A simple ProviderSource implementation (for testing and examples).

    Dictionary-based simple implementation, suitable for:
    - Mocks in unit tests
    - Simple config provisioning
    - Example code

    Example:
        >>> source = SimpleProviderSource(priority=20)
        >>> source.register('config', {'debug': True})
        >>> source.register('version', '1.0.0')
        >>> source.can_provide('config')
        True
        >>> source.provide('config')
        {'debug': True}
    """

    __slots__ = ('_providers', '_priority')

    def __init__(self, priority: int = 5):
        """Initialize the simple provider source.

        Args:
            priority: priority level (default 5)
        """
        self._providers: dict[str, Any] = {}
        self._priority = priority

    def register(self, name: str, instance: Any) -> None:
        """Register a dependency instance.

        Args:
            name: dependency name
            instance: dependency instance
        """
        self._providers[name] = instance

    def can_provide(self, name: str) -> bool:
        """Check whether a dependency can be provided (O(1))."""
        return name in self._providers

    def provide(self, name: str) -> Optional[Any]:
        """Provide a dependency instance (O(1))."""
        return self._providers.get(name)

    def list_available(self) -> List[str]:
        """List all available dependencies."""
        return list(self._providers.keys())

    def get_priority(self) -> int:
        """Return the priority."""
        return self._priority


__all__ = [
    'ProviderSource',
    'SimpleProviderSource',
]

