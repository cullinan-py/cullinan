# -*- coding: utf-8 -*-
"""Core decorators for Cullinan framework.

This module provides the primary decorators for component registration:
- @Service(): Register a service component
- @Controller(): Register a controller with URL prefix
- @Component(): Register a generic component
- Inject/InjectByName/Lazy: Dependency injection markers

All decorators use the two-phase registration pattern:
1. Decorator execution: Collect metadata to PendingRegistry
2. ApplicationContext.refresh(): Process and register all components

Author: Cullinan
"""

import inspect
import weakref
from typing import Type, Optional, List, Any, Dict

from .pending import PendingRegistry, PendingRegistration, ComponentType


# =============================================================================
# Component Registration Decorators
# =============================================================================

_COMPONENT_REGISTRATION_ATTR = "__cullinan_component_registration__"


def _capture_component_registration(target_cls: Type, registration: PendingRegistration) -> None:
    setattr(target_cls, _COMPONENT_REGISTRATION_ATTR, {
        "name": registration.name,
        "component_type": registration.component_type,
        "scope": registration.scope,
        "url_prefix": registration.url_prefix,
        "routes": list(registration.routes),
        "dependencies": list(registration.dependencies or []),
        "conditions": list(registration.conditions),
        "source_module": registration.source_module,
        "source_file": registration.source_file,
        "source_line": registration.source_line,
        "source_qualname": registration.source_qualname,
        "is_top_level": registration.is_top_level,
    })


def get_component_registration_metadata(target_cls: Type) -> Optional[Dict[str, Any]]:
    metadata = getattr(target_cls, _COMPONENT_REGISTRATION_ATTR, None)
    if metadata is None:
        return None
    return {
        "name": metadata["name"],
        "component_type": metadata["component_type"],
        "scope": metadata["scope"],
        "url_prefix": metadata["url_prefix"],
        "routes": list(metadata["routes"]),
        "dependencies": list(metadata["dependencies"]),
        "conditions": list(metadata["conditions"]),
        "source_module": metadata["source_module"],
        "source_file": metadata["source_file"],
        "source_line": metadata["source_line"],
        "source_qualname": metadata["source_qualname"],
        "is_top_level": metadata["is_top_level"],
    }


_source_context_cache: Dict[tuple, Dict[str, Any]] = {}


def _build_source_context(target_cls: Type) -> Dict[str, Any]:
    # Use (module, qualname) as stable cache key — id() values are reused
    # after GC, causing cross-test contamination.
    cache_key = (target_cls.__module__, target_cls.__qualname__)
    cached = _source_context_cache.get(cache_key)
    if cached is not None:
        return cached

    source_file = None
    try:
        source_file = inspect.getfile(target_cls)
    except (TypeError, OSError):
        pass

    # source_line is intentionally omitted — source line inspection reads
    # and parses the entire source file, which is expensive during startup
    # and unnecessary for DI registration. The line number is available on
    # demand via the decorator metadata if needed for diagnostics.
    source_qualname = getattr(target_cls, "__qualname__", target_cls.__name__)
    result = {
        "source_file": source_file,
        "source_line": None,
        "source_qualname": source_qualname,
        "is_top_level": "<locals>" not in source_qualname,
    }
    _source_context_cache[cache_key] = result
    return result


def service(cls: Optional[Type] = None, *,
            name: Optional[str] = None,
            dependencies: Optional[List[str]] = None,
            scope: str = "singleton"):
    """Service decorator - marks a class as a service component.
    
    Services are singleton by default and participate in dependency injection.
    
    Usage:
        # Without parentheses (recommended for simple cases)
        @service
        class UserService:
            def get_user(self, id: int):
                return {"id": id}
        
        # With custom name
        @service(name="customEmailService")
        class EmailService:
            def send(self, to: str, content: str):
                pass

        # With dependencies (for ordering)
        @service(dependencies=["EmailService"])
        class NotificationService:
            email: EmailService = Inject()

    Args:
        cls: The class to decorate (when used without parentheses)
        name: Optional custom name (defaults to class name)
        dependencies: Optional explicit dependency names (for ordering)
        scope: Lifecycle scope - "singleton" (default), "prototype", or "request"
    
    Returns:
        Decorated class (unchanged, but registered in PendingRegistry)
    """
    def decorator(target_cls: Type) -> Type:
        source_context = _build_source_context(target_cls)

        # Collect conditions from class (set by @Conditional* decorators)
        from .conditions import get_class_conditions, clear_class_conditions
        conditions = get_class_conditions(target_cls)
        clear_class_conditions(target_cls)

        registration = PendingRegistration(
            cls=target_cls,
            name=name or target_cls.__name__,
            component_type=ComponentType.SERVICE,
            scope=scope,
            dependencies=dependencies,
            conditions=conditions,
            source_module=target_cls.__module__,
            source_file=source_context["source_file"],
            source_line=source_context["source_line"],
            source_qualname=source_context["source_qualname"],
            is_top_level=source_context["is_top_level"],
        )
        _capture_component_registration(target_cls, registration)
        PendingRegistry.get_instance().add(registration)
        return target_cls

    # Support both @service and @service(...)
    if cls is not None:
        # Called without parentheses: @service
        return decorator(cls)
    else:
        # Called with parentheses: @service(...) or @service()
        return decorator


# Alias for backward compatibility
Service = service


def controller(cls: Optional[Type] = None, *, url: str = ""):
    """Controller decorator - marks a class as a controller component.
    
    Controllers handle HTTP requests and are singleton by default.
    The URL prefix is applied to all route methods in the controller.
    Routes are registered during ApplicationContext.refresh().

    Usage:
        # Simple controller without URL prefix
        @controller
        class RootController:
            pass

        # Controller with URL prefix
        @controller(url='/api/users')
        class UserController:
            user_service: UserService = Inject()
            
            @get_api(url='')
            def list_users(self):
                return {"users": []}
            
            @get_api(url='/{id}')
            def get_user(self, url_params):
                user_id = url_params.get("id")
                return self.user_service.get_user(user_id)

    Args:
        cls: The class to decorate (when used without parentheses)
        url: URL prefix for all routes in this controller
    
    Returns:
        Decorated class (registered in PendingRegistry, routes processed on refresh)
    """
    def decorator(target_cls: Type) -> Type:
        source_context = _build_source_context(target_cls)

        # Collect conditions from class
        from .conditions import get_class_conditions, clear_class_conditions
        conditions = get_class_conditions(target_cls)
        clear_class_conditions(target_cls)

        registration = PendingRegistration(
            cls=target_cls,
            name=target_cls.__name__,
            component_type=ComponentType.CONTROLLER,
            scope="singleton",
            url_prefix=url,
            conditions=conditions,
            source_module=target_cls.__module__,
            source_file=source_context["source_file"],
            source_line=source_context["source_line"],
            source_qualname=source_context["source_qualname"],
            is_top_level=source_context["is_top_level"],
        )
        _capture_component_registration(target_cls, registration)
        PendingRegistry.get_instance().add(registration)
        return target_cls

    # Support both @controller and @controller(...)
    if cls is not None:
        # Called without parentheses: @controller
        return decorator(cls)
    else:
        # Called with parentheses: @controller(...) or @controller()
        return decorator


# Alias for backward compatibility
Controller = controller


def component(cls: Optional[Type] = None, *,
              name: Optional[str] = None,
              scope: str = "singleton"):
    """Generic component decorator - marks a class as a managed component.
    
    Use this for components that are neither services nor controllers.
    
    Usage:
        # Without parentheses
        @component
        class CacheManager:
            pass
        
        # With scope
        @component(scope="prototype")
        class RequestHandler:
            pass
    
    Args:
        cls: The class to decorate (when used without parentheses)
        name: Optional custom name (defaults to class name)
        scope: Lifecycle scope - "singleton" (default), "prototype", or "request"
    
    Returns:
        Decorated class (unchanged, but registered in PendingRegistry)
    """
    def decorator(target_cls: Type) -> Type:
        source_context = _build_source_context(target_cls)

        # Collect conditions from class
        from .conditions import get_class_conditions, clear_class_conditions
        conditions = get_class_conditions(target_cls)
        clear_class_conditions(target_cls)

        registration = PendingRegistration(
            cls=target_cls,
            name=name or target_cls.__name__,
            component_type=ComponentType.COMPONENT,
            scope=scope,
            conditions=conditions,
            source_module=target_cls.__module__,
            source_file=source_context["source_file"],
            source_line=source_context["source_line"],
            source_qualname=source_context["source_qualname"],
            is_top_level=source_context["is_top_level"],
        )
        _capture_component_registration(target_cls, registration)
        PendingRegistry.get_instance().add(registration)
        return target_cls

    # Support both @component and @component(...)
    if cls is not None:
        return decorator(cls)
    else:
        return decorator


# Alias for backward compatibility
Component = component


def provider(cls: Optional[Type] = None, *, name: Optional[str] = None):
    """Provider decorator - marks a class as a dependency provider.
    
    Providers are factories that create instances for dependency injection.
    
    Usage:
        @provider
        class DatabaseConnectionProvider:
            def get(self) -> Connection:
                return create_connection()

        @provider(name="customProvider")
        class CustomProvider:
            pass

    Args:
        cls: The class to decorate (when used without parentheses)
        name: Optional custom name (defaults to class name)
    
    Returns:
        Decorated class (unchanged, but registered in PendingRegistry)
    """
    def decorator(target_cls: Type) -> Type:
        source_context = _build_source_context(target_cls)

        # Collect conditions from class
        from .conditions import get_class_conditions, clear_class_conditions
        conditions = get_class_conditions(target_cls)
        clear_class_conditions(target_cls)

        registration = PendingRegistration(
            cls=target_cls,
            name=name or target_cls.__name__,
            component_type=ComponentType.PROVIDER,
            scope="singleton",
            conditions=conditions,
            source_module=target_cls.__module__,
            source_file=source_context["source_file"],
            source_line=source_context["source_line"],
            source_qualname=source_context["source_qualname"],
            is_top_level=source_context["is_top_level"],
        )
        _capture_component_registration(target_cls, registration)
        PendingRegistry.get_instance().add(registration)
        return target_cls

    # Support both @provider and @provider(...)
    if cls is not None:
        return decorator(cls)
    else:
        return decorator


# Alias for backward compatibility
Provider = provider


# =============================================================================
# Dependency Injection Markers
# =============================================================================

class Inject:
    """Dependency injection marker - inject by type annotation.
    
    Use as a class attribute default value to mark fields for injection.
    The dependency is resolved based on the type annotation.
    
    Usage:
        @Service()
        class UserService:
            email_service: EmailService = Inject()
            cache: Optional[CacheService] = Inject(required=False)
    
    Attributes:
        required: If True (default), raises error if dependency not found
    """
    
    def __init__(self, required: bool = True):
        """Initialize injection marker.
        
        Args:
            required: Whether the dependency is required (default True)
        """
        self.required = required
    
    def __repr__(self) -> str:
        return f"Inject(required={self.required})"


class InjectByName:
    """Dependency injection marker - inject by explicit name.
    
    Use when you need to inject a dependency by name rather than type,
    or when the type cannot be easily inferred.
    
    Usage:
        @Service()
        class UserService:
            # Explicit name
            email_service = InjectByName("EmailService")
            
            # Compatibility fallback: infer from attribute name
            email_service = InjectByName()
    
    Attributes:
        name: Explicit dependency name (None keeps compatibility fallback)
        required: If True (default), raises error if dependency not found
    """
    
    def __init__(self, name: Optional[str] = None, required: bool = True):
        """Initialize injection marker.
        
        Args:
            name: Explicit dependency name (None keeps compatibility fallback)
            required: Whether the dependency is required (default True)
        """
        self.name = name
        self.required = required
    
    def __repr__(self) -> str:
        if self.name:
            return f"InjectByName('{self.name}', required={self.required})"
        return f"InjectByName(required={self.required})"


class Lazy:
    """Lazy injection marker - resolve dependency on first access.
    
    Use to break circular dependencies or defer expensive initialization.
    The dependency is not resolved until the attribute is first accessed.
    
    Usage:
        @Service()
        class ServiceA:
            # Break circular dependency
            service_b: 'ServiceB' = Lazy()
        
        @Service()
        class ServiceB:
            service_a: 'ServiceA' = Lazy()
    
    Attributes:
        name: Optional explicit dependency name
    """
    
    def __init__(self, name: Optional[str] = None):
        """Initialize lazy injection marker.
        
        Args:
            name: Optional explicit dependency name
        """
        self.name = name
    
    def __repr__(self) -> str:
        if self.name:
            return f"Lazy('{self.name}')"
        return "Lazy()"


# =============================================================================
# Utility Functions
# =============================================================================

# Module-level cache for injection markers extraction results.
# Mirrors ``_global_type_hints_cache``: ``dir(cls)`` results are stable for the
# lifetime of a class object. Uses a WeakKeyDictionary keyed by the class
# object itself (not ``id(cls)``) so that cache entries are automatically
# evicted when the class is garbage-collected, preventing stale results from
# ``id()`` reuse. This avoids re-scanning every node during transitive scope
# validation (A4 perf).
_injection_markers_cache: "weakref.WeakKeyDictionary[type, Dict[bool, dict]]" = (
    weakref.WeakKeyDictionary()
)


def get_injection_markers(cls: Type, *, skip_private: bool = False) -> dict:
    """Extract all injection markers from a class.
    
    Scans class attributes and type annotations for Inject, InjectByName,
    and Lazy markers.
    
    Args:
        cls: The class to scan
        skip_private: When ``True``, single-underscore-prefixed attributes
            (``_xxx``) are skipped, treating them as private injection
            points. Defaults to ``False`` to preserve the v0.93a11+ behavior
            where single-underscore attributes remain visible to the
            injection system. See A2 (strict_private_injection).
        
    Returns:
        Dict mapping attribute names to their injection markers
    """
    per_class = _injection_markers_cache.get(cls)
    if per_class is not None:
        cached = per_class.get(skip_private)
        if cached is not None:
            return cached

    markers = {}
    
    # Check class attributes for marker instances
    for attr_name in dir(cls):
        if attr_name.startswith('__') and attr_name.endswith('__'):
            continue
        if skip_private and attr_name.startswith('_'):
            continue
        try:
            attr_value = getattr(cls, attr_name, None)
            if isinstance(attr_value, (Inject, InjectByName, Lazy)):
                markers[attr_name] = attr_value
        except Exception:
            pass

    if per_class is None:
        per_class = {}
        _injection_markers_cache[cls] = per_class
    per_class[skip_private] = markers
    return markers


def invalidate_injection_markers_cache() -> None:
    """Clear the module-level injection markers cache.

    Use after dynamic class reloads (e.g., in test suites) to ensure
    stale cached markers are not reused.
    """
    _injection_markers_cache.clear()


def get_type_hints_safe(cls: Type) -> dict:
    """Safely get type hints for a class.
    
    Handles forward references and missing annotations gracefully.
    
    Args:
        cls: The class to get hints for
        
    Returns:
        Dict of type hints (may be empty on error)
    """
    try:
        import typing
        return typing.get_type_hints(cls)
    except Exception:
        # Fall back to raw annotations
        return getattr(cls, '__annotations__', {})
