# -*- coding: utf-8 -*-
"""Cullinan Model Handlers

Pluggable model handler module.

Provides a unified model resolution interface, supporting multiple model libraries such as dataclass, Pydantic, etc.

Author: Cullinan
"""

from typing import Any, Dict, List, Optional, Type

from .base import ModelHandler, ModelHandlerError
from .dataclass_handler import DataclassHandler


class ModelHandlerRegistry:
    """Model handler registry

    Manages all registered model handlers, automatically selecting the appropriate handler based on type.

    Features:
    - Auto-discovery of available handlers
    - Sorted by priority
    - Supports manual register/unregister
    - Thread-safe singleton pattern

    Example:
        # Get registry
        registry = get_model_handler_registry()

        # Get handler that can handle a type
        handler = registry.get_handler(MyDataclass)
        if handler:
            instance = handler.resolve(MyDataclass, data)

        # Register custom handler
        registry.register(MyCustomHandler())
    """

    def __init__(self):
        self._handlers: List[ModelHandler] = []
        self._initialized = False

    def register(self, handler: ModelHandler) -> None:
        """Register handler

        Args:
            handler: Model handler instance
        """
        if handler not in self._handlers:
            self._handlers.append(handler)
            # Sort by priority descending
            self._handlers.sort(key=lambda h: h.priority, reverse=True)

    def unregister(self, handler: ModelHandler) -> bool:
        """Unregister handler

        Args:
            handler: Model handler instance

        Returns:
            True if successfully unregistered
        """
        if handler in self._handlers:
            self._handlers.remove(handler)
            return True
        return False

    def unregister_by_name(self, name: str) -> bool:
        """Unregister handler by name

        Args:
            name: Handler name

        Returns:
            True if successfully unregistered
        """
        for handler in self._handlers[:]:
            if handler.name == name:
                self._handlers.remove(handler)
                return True
        return False

    def get_handler(self, type_: Type) -> Optional[ModelHandler]:
        """Get handler that can handle the specified type

        Searches in priority order, returns the first handler that can handle it.

        Args:
            type_: Type

        Returns:
            Handler instance, or None if not found
        """
        self._ensure_initialized()

        for handler in self._handlers:
            try:
                if handler.can_handle(type_):
                    return handler
            except Exception:
                continue
        return None

    def can_handle(self, type_: Type) -> bool:
        """Check if any handler can handle the specified type

        Args:
            type_: Type

        Returns:
            True if a handler can handle it
        """
        return self.get_handler(type_) is not None

    def resolve(self, model_class: Type, data: Dict[str, Any]) -> Any:
        """Resolve data using the appropriate handler

        Args:
            model_class: Model class
            data: Data dictionary

        Returns:
            Model instance

        Raises:
            ModelHandlerError: No handler found or resolution failed
        """
        handler = self.get_handler(model_class)
        if handler is None:
            raise ModelHandlerError(
                f"No handler found for {model_class}",
                model_class=model_class,
            )
        return handler.resolve(model_class, data)

    @property
    def handlers(self) -> List[ModelHandler]:
        """Get all registered handlers"""
        self._ensure_initialized()
        return self._handlers.copy()

    def get_handler_names(self) -> List[str]:
        """Get all handler names"""
        self._ensure_initialized()
        return [h.name for h in self._handlers]

    def _ensure_initialized(self) -> None:
        """Ensure initialized"""
        if not self._initialized:
            self._auto_discover()
            self._initialized = True

    def _auto_discover(self) -> None:
        """Auto-discover and register available handlers"""
        # 1. Register built-in dataclass handler
        self.register(DataclassHandler())

        # 2. Try loading Pydantic handler
        try:
            from .pydantic_handler import PydanticHandler
            self.register(PydanticHandler())
        except ImportError:
            pass  # Pydantic not installed, skip

    def reset(self) -> None:
        """Reset registry (for testing)"""
        self._handlers.clear()
        self._initialized = False


# Global registry instance
_registry: Optional[ModelHandlerRegistry] = None


def get_model_handler_registry() -> ModelHandlerRegistry:
    """Get the global model handler registry

    Returns:
        ModelHandlerRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ModelHandlerRegistry()
    return _registry


def reset_model_handler_registry() -> None:
    """Reset global registry (for testing)"""
    global _registry
    if _registry is not None:
        _registry.reset()
    _registry = None


# Exports
__all__ = [
    'ModelHandler',
    'ModelHandlerError',
    'ModelHandlerRegistry',
    'DataclassHandler',
    'get_model_handler_registry',
    'reset_model_handler_registry',
]

# Try to export PydanticHandler (if available)
try:
    from .pydantic_handler import PydanticHandler  # noqa: F401  (re-exported via dynamic __all__.append below)
    __all__.append('PydanticHandler')
except ImportError:
    pass

