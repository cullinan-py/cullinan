# -*- coding: utf-8 -*-
"""Core exceptions for the Cullinan framework."""


from typing import Optional, List, Dict, Any


class CullinanCoreError(Exception):
    """Base exception for all core module errors."""
    pass


class RegistryError(CullinanCoreError):
    """Exception raised for registry-related errors."""
    pass


class RegistryFrozenError(RegistryError):
    """Exception raised when attempting to modify a frozen registry.

    Structural writes after ``refresh()`` must raise this error.
    """

    def __init__(self, message: str = "Registry is frozen and cannot be modified."):
        super().__init__(message)
        self.message = message


class DependencyResolutionError(CullinanCoreError):
    """Exception raised when dependencies cannot be resolved.

    Carries structured diagnostic fields.
    """

    def __init__(
        self,
        message: str,
        dependency_name: Optional[str] = None,
        injection_point: Optional[str] = None,
        resolution_path: Optional[List[str]] = None,
        candidate_sources: Optional[List[Dict[str, Any]]] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.dependency_name = dependency_name
        self.injection_point = injection_point
        self.resolution_path = resolution_path or []
        self.candidate_sources = candidate_sources or []
        self.cause = cause

        # Preserve the original exception chain.
        if cause is not None:
            self.__cause__ = cause


class DependencyNotFoundError(DependencyResolutionError):
    """Exception raised when a required dependency is not found.

    Explicit error type for missing dependencies.
    """
    pass


class DependencyTypeResolutionError(DependencyResolutionError):
    """Exception raised when a dependency type hint cannot be resolved safely."""

    def __init__(
        self,
        message: str,
        dependency_name: Optional[str] = None,
        injection_point: Optional[str] = None,
        expected_type_name: Optional[str] = None,
        fallback_candidate: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            message,
            dependency_name=dependency_name,
            injection_point=injection_point,
            **kwargs,
        )
        self.expected_type_name = expected_type_name
        self.fallback_candidate = fallback_candidate


class ConditionNotMetError(DependencyResolutionError):
    """Exception raised when dependency conditions are not met.

    Explicit error type for unmet conditions.
    """

    def __init__(
        self,
        message: str,
        dependency_name: Optional[str] = None,
        failed_conditions: Optional[List[str]] = None,
        **kwargs
    ):
        super().__init__(message, dependency_name=dependency_name, **kwargs)
        self.failed_conditions = failed_conditions or []


class CircularDependencyError(DependencyResolutionError):
    """Exception raised when circular dependencies are detected.

    The dependency chain must remain stable and ordered.
    """

    def __init__(
        self,
        message: str,
        dependency_chain: Optional[List[str]] = None,
        **kwargs
    ):
        # Mirror dependency_chain into resolution_path.
        super().__init__(
            message,
            resolution_path=dependency_chain,
            **kwargs
        )
        self.dependency_chain = dependency_chain or []


class ScopeNotActiveError(DependencyResolutionError):
    """Exception raised when required scope is not active.

    Raised when request scope is required but inactive.
    """

    def __init__(
        self,
        scope_type: str,
        dependency_name: Optional[str] = None,
        message: Optional[str] = None,
        **kwargs
    ):
        if message is None:
            message = (
                f"Scope '{scope_type}' is not active, so dependency "
                f"'{dependency_name}' cannot be resolved."
            )
        super().__init__(message, dependency_name=dependency_name, **kwargs)
        self.scope_type = scope_type


class CreationError(DependencyResolutionError):
    """Exception raised when instance creation fails.

    Raised when instance creation fails and must preserve the original error.
    """

    def __init__(
        self,
        message: str,
        dependency_name: Optional[str] = None,
        cause: Optional[Exception] = None,
        **kwargs
    ):
        super().__init__(message, dependency_name=dependency_name, cause=cause, **kwargs)


class AmbiguousDependencyError(DependencyResolutionError):
    """Exception raised when constructor injection matches multiple definitions.

    Raised during refresh() when a constructor-injected type has more than
    one matching Definition in the registry.
    """

    def __init__(
        self,
        attr_name: str,
        target_cls: type,
        candidates: List[str],
        **kwargs,
    ):
        type_name = getattr(target_cls, "__name__", str(target_cls))
        candidate_names = ", ".join(candidates)
        message = (
            f"Constructor dependency '{attr_name}' on '{type_name}' "
            f"matches {len(candidates)} definitions by type: [{candidate_names}]. "
            f"Use InjectByName() as a field injection to disambiguate."
        )
        super().__init__(
            message,
            dependency_name=attr_name,
            injection_point=f"{type_name}.__annotations__['{attr_name}']",
            candidate_sources=[{"name": c} for c in candidates],
            **kwargs,
        )
        self.attr_name = attr_name
        self.target_cls = target_cls
        self.candidates = candidates


class LifecycleError(CullinanCoreError):
    """Exception raised for lifecycle management errors."""
    pass


class ScopeViolationError(LifecycleError):
    """Exception raised when scope constraints are violated.

    A singleton/prototype component transitively depends on a request-scoped
    component. Carries the full dependency chain from the origin component to
    the violating request-scoped component, aligned with
    :class:`CircularDependencyError`.

    Inherits from :class:`LifecycleError` for backward compatibility
    (``isinstance(e, LifecycleError)`` remains ``True``).
    """

    def __init__(
        self,
        message: str,
        dependency_chain: Optional[List[str]] = None,
        origin_name: Optional[str] = None,
        violating_component: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message)
        self.message = message
        self.dependency_chain = dependency_chain or []
        self.origin_name = origin_name
        self.violating_component = violating_component
