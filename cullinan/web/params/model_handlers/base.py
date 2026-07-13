# -*- coding: utf-8 -*-
"""Cullinan Model Handler Base

Model handler base class, defines the pluggable model resolution interface.

Author: Cullinan
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Type


class ModelHandler(ABC):
    """Model handler base class

    All model handlers (e.g., dataclass, Pydantic, attrs, etc.) must inherit from this class.

    Handlers are managed via a registry, core code does not directly depend on concrete implementations.

    Attributes:
        priority: Priority, higher values are matched first (default 0)
        name: Handler name
    """

    priority: int = 0
    name: str = "base"

    @abstractmethod
    def can_handle(self, type_: Type) -> bool:
        """Check if this handler can handle the given type

        Args:
            type_: Type

        Returns:
            True if it can handle
        """
        pass

    @abstractmethod
    def resolve(self, model_class: Type, data: Dict[str, Any]) -> Any:
        """Resolve data into a model instance

        Args:
            model_class: Model class
            data: Request data dictionary

        Returns:
            Model instance

        Raises:
            ModelHandlerError: Resolution failed
        """
        pass

    @abstractmethod
    def to_dict(self, instance: Any) -> Dict[str, Any]:
        """Convert model instance to dict

        Args:
            instance: Model instance

        Returns:
            Dictionary
        """
        pass

    def get_source(self) -> str:
        """Get parameter source

        Returns 'body' by default, subclasses can override.

        Returns:
            Parameter source string
        """
        return 'body'

    def is_required_by_default(self) -> bool:
        """Whether required by default

        Returns:
            True if required by default
        """
        return True


class ModelHandlerError(Exception):
    """Model handler error

    Attributes:
        message: Error message
        model_class: Model class
        errors: List of error details
        handler_name: Handler name
    """

    def __init__(
        self,
        message: str,
        model_class: Type = None,
        errors: list = None,
        handler_name: str = None,
    ):
        super().__init__(message)
        self.message = message
        self.model_class = model_class
        self.errors = errors or []
        self.handler_name = handler_name

    def __repr__(self) -> str:
        return f"ModelHandlerError({self.message!r}, handler={self.handler_name})"

    def to_dict(self) -> dict:
        """Convert to dict format"""
        return {
            'message': self.message,
            'model': self.model_class.__name__ if self.model_class else None,
            'errors': self.errors,
            'handler': self.handler_name,
        }

