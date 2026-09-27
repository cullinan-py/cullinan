# -*- coding: utf-8 -*-
"""Lifecycle event hooks for Cullinan framework.

Provides an event-driven mechanism for lifecycle stages, allowing
extensions and applications to hook into critical points during
the application lifecycle.

Author: plumeink
"""

import logging
from typing import Callable, List, Optional, Any, Dict
from enum import Enum
from dataclasses import dataclass, field
import time

logger = logging.getLogger(__name__)


class LifecycleEvent(Enum):
    """Lifecycle event types."""

    # Application lifecycle events
    APP_BEFORE_INIT = "app_before_init"
    APP_AFTER_INIT = "app_after_init"
    APP_BEFORE_STARTUP = "app_before_startup"
    APP_AFTER_STARTUP = "app_after_startup"
    APP_BEFORE_SHUTDOWN = "app_before_shutdown"
    APP_AFTER_SHUTDOWN = "app_after_shutdown"

    # Service lifecycle events
    SERVICE_BEFORE_INIT = "service_before_init"
    SERVICE_AFTER_INIT = "service_after_init"
    SERVICE_INIT_FAILED = "service_init_failed"
    SERVICE_BEFORE_STARTUP = "service_before_startup"
    SERVICE_AFTER_STARTUP = "service_after_startup"
    SERVICE_BEFORE_SHUTDOWN = "service_before_shutdown"
    SERVICE_AFTER_SHUTDOWN = "service_after_shutdown"

    # Controller lifecycle events
    CONTROLLER_BEFORE_REGISTER = "controller_before_register"
    CONTROLLER_AFTER_REGISTER = "controller_after_register"
    CONTROLLER_REGISTER_FAILED = "controller_register_failed"

    # Middleware lifecycle events
    MIDDLEWARE_BEFORE_INIT = "middleware_before_init"
    MIDDLEWARE_AFTER_INIT = "middleware_after_init"

    # Request lifecycle events
    REQUEST_STARTED = "request_started"
    REQUEST_FINISHED = "request_finished"
    REQUEST_FAILED = "request_failed"


@dataclass
class LifecycleEventContext:
    """Context information for a lifecycle event.

    Attributes:
        event: The event type
        timestamp: Event timestamp
        component: Component name (e.g., service name, controller name)
        component_type: Component type (e.g., 'service', 'controller')
        data: Additional event-specific data
        error: Error information (if event is a failure event)
    """
    event: LifecycleEvent
    timestamp: float = field(default_factory=time.time)
    component: Optional[str] = None
    component_type: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Exception] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            'event': self.event.value,
            'timestamp': self.timestamp,
            'component': self.component,
            'component_type': self.component_type,
            'data': self.data,
            'error': str(self.error) if self.error else None,
        }


class LifecycleEventHook:
    """Represents a lifecycle event hook (callback function)."""

    def __init__(self,
                 event: LifecycleEvent,
                 callback: Callable[[LifecycleEventContext], None],
                 priority: int = 100,
                 name: Optional[str] = None):
        """Initialize a lifecycle event hook.

        Args:
            event: The event to hook into
            callback: The callback function
            priority: Hook priority (lower numbers execute first)
            name: Optional hook name for debugging
        """
        self.event = event
        self.callback = callback
        self.priority = priority
        self.name = name or f"{callback.__module__}.{callback.__name__}"

    def __call__(self, context: LifecycleEventContext):
        """Execute the hook."""
        try:
            logger.debug(f"Executing lifecycle hook: {self.name} for {self.event.value}")
            self.callback(context)
        except Exception as e:
            logger.error(f"Error in lifecycle hook {self.name}: {e}", exc_info=True)
            raise


class LifecycleEventManager:
    """Manages lifecycle event hooks.

    Provides registration, execution, and management of lifecycle event hooks.

    Example:
        >>> manager = LifecycleEventManager()
        >>>
        >>> def on_service_init(ctx):
        ...     print(f"Service {ctx.component} initialized")
        >>>
        >>> manager.register_hook(
        ...     LifecycleEvent.SERVICE_AFTER_INIT,
        ...     on_service_init
        ... )
        >>>
        >>> # Trigger event
        >>> ctx = LifecycleEventContext(
        ...     event=LifecycleEvent.SERVICE_AFTER_INIT,
        ...     component='UserService'
        ... )
        >>> manager.trigger_event(ctx)
    """

    def __init__(self):
        """Initialize the event manager."""
        self._hooks: Dict[LifecycleEvent, List[LifecycleEventHook]] = {}
        self._enabled = True
        self._event_log: List[LifecycleEventContext] = []
        self._max_log_size = 1000  # Keep last 1000 events

    def register_hook(self,
                     event: LifecycleEvent,
                     callback: Callable[[LifecycleEventContext], None],
                     priority: int = 100,
                     name: Optional[str] = None) -> LifecycleEventHook:
        """Register a lifecycle event hook.

        Args:
            event: The event to hook into
            callback: The callback function
            priority: Hook priority (lower numbers execute first)
            name: Optional hook name

        Returns:
            The created hook instance

        Example:
            >>> def my_hook(ctx):
            ...     print(f"Event: {ctx.event}")
            >>>
            >>> manager.register_hook(
            ...     LifecycleEvent.APP_AFTER_INIT,
            ...     my_hook,
            ...     priority=50
            ... )
        """
        hook = LifecycleEventHook(event, callback, priority, name)

        if event not in self._hooks:
            self._hooks[event] = []

        self._hooks[event].append(hook)

        # Sort by priority (lower priority executes first)
        self._hooks[event].sort(key=lambda h: h.priority)

        logger.debug(f"Registered lifecycle hook: {hook.name} for {event.value} (priority={priority})")

        return hook

    def unregister_hook(self, hook: LifecycleEventHook):
        """Unregister a lifecycle event hook.

        Args:
            hook: The hook to unregister
        """
        if hook.event in self._hooks:
            self._hooks[hook.event] = [h for h in self._hooks[hook.event] if h != hook]
            logger.debug(f"Unregistered lifecycle hook: {hook.name}")

    def trigger_event(self, context: LifecycleEventContext):
        """Trigger a lifecycle event.

        Args:
            context: The event context
        """
        if not self._enabled:
            return

        # Log the event
        self._log_event(context)

        # Get hooks for this event
        hooks = self._hooks.get(context.event, [])

        if not hooks:
            logger.debug(f"No hooks registered for {context.event.value}")
            return

        logger.debug(f"Triggering {len(hooks)} hook(s) for {context.event.value}")

        # Execute hooks in priority order
        for hook in hooks:
            try:
                hook(context)
            except Exception as e:
                logger.error(
                    f"Lifecycle hook {hook.name} failed for {context.event.value}: {e}",
                    extra={'context': context.to_dict()}
                )
                # Continue executing other hooks even if one fails

    def _log_event(self, context: LifecycleEventContext):
        """Log an event to the event log."""
        self._event_log.append(context)

        # Trim log if too large
        if len(self._event_log) > self._max_log_size:
            self._event_log = self._event_log[-self._max_log_size:]

    def get_event_log(self,
                     event: Optional[LifecycleEvent] = None,
                     limit: int = 100) -> List[LifecycleEventContext]:
        """Get the event log.

        Args:
            event: Optional event type to filter by
            limit: Maximum number of events to return

        Returns:
            List of event contexts
        """
        log = self._event_log

        if event:
            log = [ctx for ctx in log if ctx.event == event]

        return log[-limit:]

    def clear_event_log(self):
        """Clear the event log."""
        self._event_log.clear()
        logger.debug("Event log cleared")

    def enable(self):
        """Enable event triggering."""
        self._enabled = True
        logger.info("Lifecycle event manager enabled")

    def disable(self):
        """Disable event triggering."""
        self._enabled = False
        logger.info("Lifecycle event manager disabled")

    def is_enabled(self) -> bool:
        """Check if event manager is enabled."""
        return self._enabled

    def get_hooks(self, event: LifecycleEvent) -> List[LifecycleEventHook]:
        """Get all hooks for a specific event.

        Args:
            event: The event type

        Returns:
            List of hooks
        """
        return self._hooks.get(event, []).copy()

    def get_all_hooks(self) -> Dict[LifecycleEvent, List[LifecycleEventHook]]:
        """Get all registered hooks.

        Returns:
            Dictionary mapping events to hooks
        """
        return {
            event: hooks.copy()
            for event, hooks in self._hooks.items()
        }

    def clear_all_hooks(self):
        """Clear all registered hooks."""
        self._hooks.clear()
        logger.info("All lifecycle hooks cleared")


# Global lifecycle event manager
_lifecycle_event_manager: Optional[LifecycleEventManager] = None


def get_lifecycle_event_manager() -> LifecycleEventManager:
    """Get the global lifecycle event manager.

    Returns:
        The global LifecycleEventManager instance
    """
    global _lifecycle_event_manager
    if _lifecycle_event_manager is None:
        _lifecycle_event_manager = LifecycleEventManager()
    return _lifecycle_event_manager


def reset_lifecycle_event_manager():
    """Reset the global lifecycle event manager (for testing)."""
    global _lifecycle_event_manager
    _lifecycle_event_manager = None


# Decorator for registering lifecycle hooks
def lifecycle_hook(event: LifecycleEvent, priority: int = 100):
    """Decorator to register a function as a lifecycle hook.

    Args:
        event: The event to hook into
        priority: Hook priority

    Example:
        >>> @lifecycle_hook(LifecycleEvent.APP_AFTER_INIT, priority=50)
        ... def my_initialization_hook(ctx):
        ...     print("Application initialized!")
    """
    def decorator(func: Callable[[LifecycleEventContext], None]):
        manager = get_lifecycle_event_manager()
        manager.register_hook(event, func, priority, name=func.__name__)
        return func
    return decorator

