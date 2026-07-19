# -*- coding: utf-8 -*-
"""WebSocket registry module for Cullinan framework.

Provides enhanced WebSocket support with:
- Registry pattern for WebSocket handlers (based on cullinan.core.Registry)
- Type-based dependency injection (same as @controller and @service)
- Lifecycle management
- Integration with service layer

Usage:
    from cullinan import websocket_handler
    from cullinan.core import Inject
    from cullinan.core.services import Service, service

    @service
    class NotificationService(Service):
        def send_notification(self, message):
            return f"Notification: {message}"

    @websocket_handler(url='/ws/chat')
    class ChatHandler:
        # Type injection - automatically resolved!
        notification_service: NotificationService = Inject()

        def on_open(self):
            # Use injected service directly
            self.notification_service.send_notification("User connected")

        def on_message(self, message):
            # Handle incoming message
            self.write_message(f"Echo: {message}")
        
        def on_close(self):
            # Called when WebSocket connection is closed
            pass
"""

import logging
from typing import Type, Optional, Dict, Any, Callable
from cullinan.core import Registry

logger = logging.getLogger(__name__)


class WebSocketRegistry(Registry['Type[Any]']):
    """Registry for WebSocket handlers.
    
    Manages WebSocket handler classes with support for:
    - URL-based registration
    - Lifecycle management
    - Metadata storage (dependencies, options, etc.)
    """
    
    def __init__(self):
        """Initialize the WebSocket registry."""
        super().__init__()
        self._url_mapping: Dict[str, str] = {}  # URL -> handler name
    
    def register(self, name: str, handler_class: Type[Any], 
                 url: Optional[str] = None, **metadata) -> None:
        """Register a WebSocket handler.
        
        Args:
            name: Unique identifier for the handler
            handler_class: The WebSocket handler class
            url: URL pattern for the WebSocket endpoint
            **metadata: Additional metadata (dependencies, etc.)
        
        Raises:
            RegistryError: If name or URL already registered
        """
        
        self._validate_name(name)
        
        if name in self._items:
            logger.warning(f"WebSocket handler already registered: {name}")
            return
        
        # Check URL uniqueness
        if url and url in self._url_mapping:
            existing_name = self._url_mapping[url]
            logger.warning(f"URL {url} already mapped to {existing_name}, skipping {name}")
            return
        
        # Store handler class
        self._items[name] = handler_class
        
        # Initialize metadata dict if needed (lazy initialization from parent class)
        if self._metadata is None:
            self._metadata = {}

        # Store metadata including URL
        handler_metadata = metadata.copy()
        if url:
            handler_metadata['url'] = url
            self._url_mapping[url] = name
        
        self._metadata[name] = handler_metadata
        
        logger.info(f"Registered WebSocket handler: {name}" + 
                   (f" at {url}" if url else ""))
        
        # Note: Lifecycle hooks (on_post_construct, on_startup, etc.) are called
        # by ApplicationContext during refresh(), not here.

    def get(self, name: str) -> Optional[Type[Any]]:
        """Retrieve a WebSocket handler class by name.
        
        Args:
            name: Identifier of the handler
        
        Returns:
            The handler class, or None if not found
        """
        return self._items.get(name)
    
    def get_by_url(self, url: str) -> Optional[Type[Any]]:
        """Retrieve a WebSocket handler class by URL pattern.
        
        Args:
            url: URL pattern to look up
        
        Returns:
            The handler class, or None if not found
        """
        name = self._url_mapping.get(url)
        if name:
            return self.get(name)
        return None
    
    def get_url(self, name: str) -> Optional[str]:
        """Get the URL pattern for a handler.
        
        Args:
            name: Identifier of the handler
        
        Returns:
            The URL pattern, or None if not found
        """
        metadata = self.get_metadata(name)
        if metadata:
            return metadata.get('url')
        return None
    
    def list_urls(self) -> Dict[str, str]:
        """Get all registered URL mappings.
        
        Returns:
            Dictionary mapping URLs to handler names
        """
        return self._url_mapping.copy()
    
    def unregister(self, name: str) -> bool:
        """Unregister a WebSocket handler.
        
        Args:
            name: Identifier of the handler to unregister
        
        Returns:
            True if handler was unregistered, False if not found
        """
        if name not in self._items:
            return False
        
        # Remove URL mapping
        metadata = self.get_metadata(name)
        if metadata and 'url' in metadata:
            url = metadata['url']
            if url in self._url_mapping:
                del self._url_mapping[url]
        
        # Remove handler and metadata
        del self._items[name]
        if name in self._metadata:
            del self._metadata[name]
        
        logger.debug(f"Unregistered WebSocket handler: {name}")
        return True


# Global WebSocket registry instance
_websocket_registry: Optional[WebSocketRegistry] = None


def get_websocket_registry() -> WebSocketRegistry:
    """Get the global WebSocket registry instance.
    
    Returns:
        The global WebSocketRegistry
    """
    global _websocket_registry
    if _websocket_registry is None:
        _websocket_registry = WebSocketRegistry()
    return _websocket_registry


def reset_websocket_registry() -> None:
    """Reset the global WebSocket registry.
    
    Useful for testing or application reinitialization.
    """
    global _websocket_registry
    if _websocket_registry:
        _websocket_registry.clear()
    _websocket_registry = None
    logger.debug("Reset WebSocket registry")


def websocket_handler(url: Optional[str] = None, **options) -> Callable:
    """Decorator for registering WebSocket handlers with dependency injection support.

    Supports type-based dependency injection using cullinan.core.Inject, providing
    the same developer experience as @controller and @service decorators.

    Args:
        url: URL pattern for the WebSocket endpoint (e.g., '/ws/chat')
        **options: Additional options (dependencies, etc.)
    
    Returns:
        Decorator function
    
    Example:
        from cullinan.core import Inject
        from cullinan.core.services import Service, service

        @service
        class NotificationService(Service):
            def send(self, message):
                return f"Sent: {message}"

        @websocket_handler(url='/ws/chat')
        class ChatHandler:
            # Type injection - automatically injected!
            notification_service: NotificationService = Inject()

            def on_open(self):
                # Use injected service directly
                self.notification_service.send("User connected")

            def on_message(self, message):
                result = self.notification_service.send(message)
                self.write_message(f"Echo: {result}")

            def on_close(self):
                pass
    """
    def decorator(handler_class: Type[Any]) -> Type[Any]:
        # injectable() was a no-op since v0.93 and is deprecated in v0.95.
        # Classes are automatically injectable; no marker needed here.

        # 1. Register to WebSocketRegistry
        registry = get_websocket_registry()
        name = handler_class.__name__
        registry.register(name, handler_class, url=url, **options)

        logger.debug(f"Registered WebSocket handler: {name}")
        return handler_class
    
    return decorator
