# -*- coding: utf-8 -*-
"""Core module for Cullinan framework.

This module provides foundational components for the Cullinan framework:
- ApplicationContext: Single entry point for IoC/DI (0.94a1)
- Decorators: @service, @controller, @component
- Dependency Injection: Inject, InjectByName, Lazy
- Unified lifecycle management (all components share same lifecycle)
- Core exceptions and types

Version: 0.94a1
"""

from cullinan._version import __version__ as _package_version
import warnings as _warnings
from cullinan.support.deprecation import deprecated as _deprecated
from .registry import Registry, SimpleRegistry
from .container_manager import ContainerManager, get_container_manager
# Import unified lifecycle from lifecycle_enhanced (the single source of truth)
from .lifecycle_enhanced import (
    LifecycleAware,
    SmartLifecycle,
    LifecyclePhase,
    LifecycleManager,
    get_lifecycle_manager,
    reset_lifecycle_manager,
)
# Keep LifecycleState for backward compatibility
from .types import LifecycleState
from .context import (
    RequestContext,
    get_current_context,
    set_current_context,
    create_context,
    destroy_context,
    ContextManager,
    get_context_value,
    set_context_value
)
from .exceptions import (
    CullinanCoreError,
    RegistryError,
    RegistryFrozenError,
    DependencyResolutionError,
    DependencyNotFoundError,
    DependencyTypeResolutionError,
    CircularDependencyError,
    ScopeNotActiveError,
    ConditionNotMetError,
    CreationError,
    LifecycleError,
    ScopeViolationError,
)

# ============================================================================
# IoC/DI 2.0 System
# ============================================================================

# ApplicationContext - Single Entry Point
from .application_context import ApplicationContext, ContainerState

# Definitions and Scope
from .definitions import Definition, ScopeType
from .scope_manager import ScopeManager
from .factory import Factory

# Diagnostics
from .diagnostics import (
    render_resolution_path,
    render_injection_point,
    render_candidate_sources,
    format_circular_dependency_error,
    format_missing_dependency_error,
    format_scope_violation_error,
)
from .injection_types import Provider
from .semantic_rules import (
    CompatibilitySemanticWarning,
    ComponentDiscoveryWarning,
    CullinanSemanticWarning,
    InjectionSemanticWarning,
    PublicAPISemanticWarning,
    warn_semantic_once,
)

# Decorators - Primary Registration API
from .decorators import (
    service as _service_decorator,
    controller as _controller_decorator,
    component as _component_decorator,
    provider as provider_decorator,
    Inject as _Inject_marker,
    InjectByName as _InjectByName_marker,
    Lazy as _Lazy_marker,
    get_injection_markers,
)

# Conditional Decorators
from .conditions import (
    ConditionalOnProperty,
    ConditionalOnClass,
    ConditionalOnMissingBean,
    ConditionalOnBean,
    Conditional,
)

# Pending Registry (for two-phase registration)
from .pending import PendingRegistry, PendingRegistration, ComponentType

# ============================================================================
# Compatibility Aliases (for backward compatibility)
# ============================================================================

# injectable is now a no-op, classes are automatically injectable
@_deprecated(
    version="0.95",
    alternative="@service / @component / @controller (classes are auto-injectable)",
    removal_version="0.97",
)
def injectable(cls):
    """Compatibility decorator - no longer needed in the v0.94 line.

    In the current public model, all classes decorated with @service,
    @controller, or @component
    are automatically injectable. This function is kept for backward compatibility.

    .. deprecated:: 0.95
        Use :func:`service`, :func:`component`, or :func:`controller` instead.
        This symbol will be removed in v0.97.
    """
    warn_semantic_once(
        key="compatibility:injectable",
        rule_key="compatibility-api",
        problem="@injectable is a compatibility-only entrypoint and no longer adds registration or injection semantics.",
        guidance="Use @service, @component, or @controller as the primary entrypoint.",
        category=CompatibilitySemanticWarning,
        stacklevel=2,
    )
    return cls

@_deprecated(
    version="0.95",
    alternative="ApplicationContext.refresh() (handles constructor injection uniformly)",
    removal_version="0.97",
)
def inject_constructor(cls):
    """Compatibility decorator - no longer needed in the v0.94 line.

    .. deprecated:: 0.95
        :meth:`ApplicationContext.refresh` now handles injection uniformly.
        This symbol will be removed in v0.97.
    """
    warn_semantic_once(
        key="compatibility:inject_constructor",
        rule_key="compatibility-api",
        problem="@inject_constructor is a compatibility-only entrypoint and no longer changes constructor injection behavior.",
        guidance="ApplicationContext.refresh() now handles injection uniformly, so no extra decorator is required.",
        category=CompatibilitySemanticWarning,
        stacklevel=2,
    )
    return cls

# ============================================================================
# Global ApplicationContext Access
# ============================================================================

def get_application_context():
    """Return the current active root container."""
    return get_container_manager().get_active_root()


def set_application_context(ctx) -> None:
    """Set or clear the global root container reference."""
    manager = get_container_manager()
    if ctx is None:
        manager.clear()
        return
    manager.bind(ctx)


# Provide dummy registry functions for compatibility
_dummy_registry = None

@_deprecated(
    version="0.95",
    alternative="ApplicationContext / get_application_context()",
    removal_version="0.97",
)
def get_injection_registry():
    """Compatibility function - returns None in the v0.94 line.

    Use ApplicationContext instead.

    .. deprecated:: 0.95
        Use :class:`ApplicationContext` or :func:`get_application_context`
        instead. This symbol will be removed in v0.97.
    """
    warn_semantic_once(
        key="compatibility:get_injection_registry",
        rule_key="compatibility-api",
        problem="get_injection_registry() keeps its compatibility shape only and does not return a usable registry.",
        guidance="Use ApplicationContext or get_application_context() instead.",
        category=CompatibilitySemanticWarning,
        stacklevel=2,
    )
    return _dummy_registry

@_deprecated(
    version="0.95",
    alternative="Create a new ApplicationContext explicitly",
    removal_version="0.97",
)
def reset_injection_registry():
    """Compatibility function - no-op in the v0.94 line.

    .. deprecated:: 0.95
        Create a new :class:`ApplicationContext` explicitly when you need a
        fresh container. This symbol will be removed in v0.97.
    """
    warn_semantic_once(
        key="compatibility:reset_injection_registry",
        rule_key="compatibility-api",
        problem="reset_injection_registry() no longer resets a real container in the v0.94 line.",
        guidance="Create a new ApplicationContext explicitly when you need a fresh container.",
        category=CompatibilitySemanticWarning,
        stacklevel=2,
    )

# InjectionRegistry compatibility class
@_deprecated(
    version="0.95",
    alternative="ApplicationContext / get_application_context()",
    removal_version="0.97",
)
class InjectionRegistry:
    """Compatibility class - use ApplicationContext instead.

    .. deprecated:: 0.95
        Use :class:`ApplicationContext` instead. This symbol will be removed
        in v0.97.
    """
    pass


# Rebind decorator markers from the public core facade.
service = _service_decorator
controller = _controller_decorator
component = _component_decorator
Inject = _Inject_marker
InjectByName = _InjectByName_marker
Lazy = _Lazy_marker
__version__ = _package_version

__all__ = [
    # ========================================================================
    # IoC/DI 2.0 System
    # ========================================================================

    # Application Context (Single Entry Point)
    'ApplicationContext',
    'ContainerState',
    'ContainerManager',
    'get_container_manager',
    'get_application_context',
    'set_application_context',
    'Definition',
    'ScopeType',
    'ScopeManager',
    'Factory',

    # Diagnostics
    'render_resolution_path',
    'render_injection_point',
    'render_candidate_sources',
    'format_circular_dependency_error',
    'format_missing_dependency_error',
    'format_scope_violation_error',

    # Exceptions
    'CullinanCoreError',
    'RegistryError',
    'RegistryFrozenError',
    'DependencyResolutionError',
    'DependencyNotFoundError',
    'DependencyTypeResolutionError',
    'CircularDependencyError',
    'ScopeNotActiveError',
    'ConditionNotMetError',
    'CreationError',
    'LifecycleError',
    'ScopeViolationError',

    # Decorators (Primary API)
    'service',
    'controller',
    'component',
    'provider_decorator',
    'Provider',
    'Inject',
    'InjectByName',
    'Lazy',
    'get_injection_markers',
    'CullinanSemanticWarning',
    'ComponentDiscoveryWarning',
    'CompatibilitySemanticWarning',
    'InjectionSemanticWarning',
    'PublicAPISemanticWarning',

    # Conditional Decorators
    'ConditionalOnProperty',
    'ConditionalOnClass',
    'ConditionalOnMissingBean',
    'ConditionalOnBean',
    'Conditional',

    # Pending Registry
    'PendingRegistry',
    'PendingRegistration',
    'ComponentType',

    # ========================================================================
    # Core Infrastructure
    # ========================================================================

    # Registry
    'Registry',
    'SimpleRegistry',

    # Lifecycle Management (Unified)
    'LifecycleManager',
    'LifecycleState',
    'LifecycleAware',
    'SmartLifecycle',
    'LifecyclePhase',
    'get_lifecycle_manager',
    'reset_lifecycle_manager',

    # Request Context
    'RequestContext',
    'get_current_context',
    'set_current_context',
    'create_context',
    'destroy_context',
    'ContextManager',
    'get_context_value',
    'set_context_value',

    # ========================================================================
    # Compatibility (kept for backward compatibility)
    # ========================================================================
    'injectable',
    'inject_constructor',
    'InjectionRegistry',
    'get_injection_registry',
    'reset_injection_registry',
]


# ----------------------------------------------------------------------------
# A1: One-time module-load deprecation notice for the legacy compatibility
# surface (PEP 562 style). Fires a single DeprecationWarning the first time
# `cullinan.core` is imported, so tooling (pytest -W error::DeprecationWarning,
# linters, IDEs) can surface the migration path without spamming callers.
# Per-call DeprecationWarning is still emitted by the @deprecated decorator
# wrapping each symbol; the CompatibilitySemanticWarning from
# warn_semantic_once remains deduplicated per key.
# ----------------------------------------------------------------------------
_DEPRECATED_LEGACY_SYMBOLS = (
    "injectable",
    "inject_constructor",
    "InjectionRegistry",
    "get_injection_registry",
    "reset_injection_registry",
)
_warnings.warn(
    "cullinan.core exports legacy compatibility symbols "
    f"({_DEPRECATED_LEGACY_SYMBOLS}) that are deprecated since v0.95 "
    "and will be removed in v0.97. See each symbol's __deprecated_info__ "
    "for the recommended replacement.",
    DeprecationWarning,
    stacklevel=2,
)
del _warnings
