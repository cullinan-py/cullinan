# -*- coding: utf-8 -*-
"""Unified root container implementation for Cullinan IoC/DI."""

from __future__ import annotations

import ast
import asyncio
import inspect
import logging
import threading
import time
import types
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .definition_registry import DefinitionRegistry
from .definitions import Definition, ScopeType
from .exceptions import (
    AmbiguousDependencyError,
    CircularDependencyError,
    ConditionNotMetError,
    CreationError,
    DependencyNotFoundError,
    DependencyTypeResolutionError,
    LifecycleError,
    RegistryFrozenError,
    ScopeViolationError,
)
from .diagnostics import (
    format_circular_dependency_error,
    format_missing_dependency_error,
    format_scope_violation_error,
)
from .injection_types import Provider
from .lifecycle_enhanced import LifecyclePhase
from .semantic_rules import (
    ComponentDiscoveryWarning,
    InjectionSemanticWarning,
    format_semantic_message,
    warn_semantic_once,
)
from .scope_manager import ScopeManager
from cullinan.support.diagnostics import (
    collection_requires_one_element_type,
    collection_single_dependency_only,
    container_requires_one_element_type,
    duplicate_definition,
    invalid_annotation_expression,
    missing_inner_type,
    optional_single_dependency_only,
    provider_requires_single_type_argument,
    provider_single_dependency_only,
    tuple_injection_form,
    union_single_candidates_only,
    unsupported_annotation_container,
    unsupported_annotation_expression,
    unsupported_annotation_type,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _InjectionTarget:
    display_name: str
    lookup_names: Tuple[str, ...]
    runtime_type: Optional[type] = None


@dataclass(frozen=True)
class _NormalizedInjectionAnnotation:
    kind: str
    annotation_repr: str
    targets: Tuple[_InjectionTarget, ...]
    optional: bool = False
    collection_kind: Optional[str] = None


@dataclass(frozen=True)
class _ResolvedInjectionBinding:
    kind: str
    annotation_repr: str
    target_labels: Tuple[str, ...]
    required: bool
    candidate_names: Tuple[str, ...] = ()
    collection_kind: Optional[str] = None


class ContainerState(Enum):
    """State of the root container."""

    CREATED = "created"
    REGISTERING = "registering"
    VALIDATING = "validating"
    WARMING_UP = "warming_up"
    ACTIVE = "active"
    DRAINING = "draining"
    CLOSED = "closed"


# Module-level global cache for type hints resolution results.
# Previously an instance attribute on ApplicationContext, which caused
# typing.get_type_hints() to be called twice per class (once during
# registration and once during injection resolution). Moving to module
# level ensures the cache is shared across context instances and persists
# for the lifetime of the process.
_global_type_hints_cache: Dict[int, Tuple[Dict, Dict, Optional[Exception]]] = {}


def _normalize_string_annotation(value: Any) -> Any:
    """Strip spurious wrapping quotes from :pep:`563` string annotations.

    When ``CO_FUTURE_ANNOTATIONS`` is active and the source already contains
    a quoted forward reference like ``user_directory: "UserDirectoryService"``,
    Python stores the annotation expression as ``"'UserDirectoryService'"``
    (the inner quotes become part of the stored string).  This helper strips
    the outer quotes so downstream ``find_by_type_name`` can match the bare
    class name.
    """
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    # Repeatedly unwrap matching quote pairs, so "'UserService'" becomes
    # "UserService" then UserService.
    while (
        len(stripped) >= 2
        and stripped[0] in ('"', "'")
        and stripped[0] == stripped[-1]
    ):
        stripped = stripped[1:-1]
    return stripped


def invalidate_type_hints_cache() -> None:
    """Clear the module-level type hints cache.

    Use after dynamic class reloads (e.g., in test suites) to ensure
    stale cached annotations are not reused.
    """
    _global_type_hints_cache.clear()


class ApplicationContext:
    """Unified root container.

    Preserves the historical ``ApplicationContext`` API while using a single-root-container
    implementation internally.
    """

    __slots__ = (
        "_definition_registry",
        "_scope_manager",
        "_lock",
        "_resolving_stack",
        "_shutdown_handlers",
        "_lifecycle_instances",
        "_lifecycle_phases",
        "_startup_order",
        "_state",
        "_id",
        "_health_checks",
        "_strict_private_injection",
        "_strict_lifecycle",
    )

    def __init__(self, container_id: Optional[str] = None, *,
                 strict_private_injection: bool = False,
                 strict_lifecycle: bool = False):
        self._definition_registry = DefinitionRegistry()
        self._scope_manager = ScopeManager(root_id=container_id or hex(id(self)))
        self._lock = threading.RLock()
        self._resolving_stack: List[str] = []
        self._shutdown_handlers: List[Any] = []
        self._lifecycle_instances: Dict[str, Any] = {}
        self._lifecycle_phases: Dict[str, LifecyclePhase] = {}
        self._startup_order: List[str] = []
        self._state = ContainerState.CREATED
        self._id = self._scope_manager.root_id
        self._health_checks: List[Any] = []
        # A2: strict_private_injection - when True, single-underscore (_xxx)
        # attributes are skipped by the injection marker scanner. Default
        # False preserves the v0.93a11+ behavior where _xxx is visible to
        # the injection system. CULLINAN_STRICT_PRIVATE_INJECTION=1 env var
        # provides a global opt-in for CI / strict projects.
        self._strict_private_injection = strict_private_injection or (
            __import__("os").environ.get(
                "CULLINAN_STRICT_PRIVATE_INJECTION", ""
            ).lower() in ("1", "true", "yes")
        )
        # A3: strict_lifecycle - when True, non-critical lifecycle exceptions
        # are re-raised instead of being logged and swallowed. Default False
        # preserves the existing ApplicationContext behavior where only
        # critical lifecycle methods propagate.
        self._strict_lifecycle = strict_lifecycle

    # ========================================================================
    # Registration API
    # ========================================================================

    def register(self, definition: Definition) -> None:
        with self._lock:
            if self._definition_registry.is_frozen:
                raise RegistryFrozenError(
                    format_semantic_message(
                        "refresh-freeze",
                        f"Component '{definition.name}' attempted to register after refresh().",
                        "Complete all structural registrations before application startup reaches refresh().",
                    )
                )
            if self._state == ContainerState.CREATED:
                self._state = ContainerState.REGISTERING
            self._definition_registry.register(definition)

    def register_all(self, definitions: List[Definition]) -> None:
        for definition in definitions:
            self.register(definition)

    def add_health_check(self, callback) -> None:
        self._health_checks.append(callback)

    # ========================================================================
    # Lifecycle API
    # ========================================================================

    def refresh(self) -> None:
        with self._lock:
            if self._state == ContainerState.ACTIVE:
                logger.warning("ApplicationContext.refresh() was already called; skipping.")
                return
            if self._state == ContainerState.CLOSED:
                raise LifecycleError(
                    format_semantic_message(
                        "refresh-freeze",
                        "A closed ApplicationContext cannot be refreshed again.",
                        "Create a new ApplicationContext instance when you need to rebuild the application.",
                    )
                )

            if self._state == ContainerState.CREATED:
                self._state = ContainerState.REGISTERING

            logger.info("ApplicationContext.refresh() started.")
            self._process_pending_registrations()
            self._state = ContainerState.VALIDATING
            self._validate_definitions()
            self._state = ContainerState.WARMING_UP
            self._warm_up()
            self._definition_registry.freeze()
            self._run_health_checks()
            self._state = ContainerState.ACTIVE
            logger.info(
                "ApplicationContext.refresh() completed with %s registered definitions.",
                self.definition_count,
            )

    def begin_draining(self) -> None:
        with self._lock:
            if self._state == ContainerState.CLOSED:
                return
            self._state = ContainerState.DRAINING
            self._scope_manager.begin_drain()

    def shutdown(self, timeout: float = 30.0) -> None:
        with self._lock:
            if self._state == ContainerState.CLOSED:
                return
            self.begin_draining()

        self._await_request_drained(timeout)
        self._execute_lifecycle_shutdown()

        for handler in self._shutdown_handlers:
            try:
                result = handler()
                if inspect.iscoroutine(result):
                    self._run_coroutine(result)
            except Exception as exc:
                logger.error("Shutdown handler failed: %s", exc)

        self._scope_manager.clear_all()
        self._lifecycle_instances.clear()
        self._lifecycle_phases.clear()
        self._startup_order.clear()
        self._state = ContainerState.CLOSED
        logger.info("ApplicationContext.shutdown() completed.")

    def add_shutdown_handler(self, handler) -> None:
        self._shutdown_handlers.append(handler)

    # ========================================================================
    # Resolution API
    # ========================================================================

    def get(self, name: str) -> Any:
        definition = self._definition_registry.get(name)
        if definition is None:
            raise DependencyNotFoundError(
                message=format_missing_dependency_error(
                    dependency_name=name,
                    available_sources=self.list_definitions(),
                ),
                dependency_name=name,
                candidate_sources=[
                    {"source": definition_name, "reason": "name_mismatch"}
                    for definition_name in self.list_definitions()
                ],
            )
        return self._resolve(definition)

    def try_get(self, name: str) -> Optional[Any]:
        definition = self._definition_registry.get(name)
        if definition is None:
            return None
        if not definition.check_conditions(self):
            logger.debug("try_get('%s'): conditions were not met; returning None.", name)
            return None
        return self._resolve(definition)

    def has(self, name: str) -> bool:
        return self._definition_registry.has(name)

    def get_definition(self, name: str) -> Optional[Definition]:
        return self._definition_registry.get(name)

    def list_definitions(self) -> List[str]:
        return self._definition_registry.list_names()

    # ========================================================================
    # Request context proxy
    # ========================================================================

    def enter_request_context(self):
        if self._state != ContainerState.ACTIVE:
            raise LifecycleError(
                f"Container state is {self._state.value}; new request scopes are not accepted right now."
            )
        return self._scope_manager.enter_request_context()

    def exit_request_context(self) -> None:
        self._scope_manager.exit_request_context()

    def is_request_active(self) -> bool:
        return self._scope_manager.is_request_active()

    # ========================================================================
    # State inspection
    # ========================================================================

    @property
    def id(self) -> str:
        return self._id

    @property
    def state(self) -> ContainerState:
        return self._state

    @property
    def is_frozen(self) -> bool:
        return self._definition_registry.is_frozen

    @property
    def is_refreshed(self) -> bool:
        return self._state in {
            ContainerState.WARMING_UP,
            ContainerState.ACTIVE,
            ContainerState.DRAINING,
            ContainerState.CLOSED,
        }

    @property
    def definition_count(self) -> int:
        return self._definition_registry.count

    @property
    def active_request_count(self) -> int:
        return self._scope_manager.active_request_count

    # ========================================================================
    # Internal helpers
    # ========================================================================

    def _resolve(self, definition: Definition) -> Any:
        name = definition.name
        if name in self._resolving_stack:
            cycle_start = self._resolving_stack.index(name)
            chain = self._resolving_stack[cycle_start:] + [name]
            raise CircularDependencyError(
                message=format_circular_dependency_error(chain),
                dependency_chain=chain,
                dependency_name=name,
            )

        if not definition.check_conditions(self):
            raise ConditionNotMetError(
                message=f"Conditions were not met for dependency '{name}'.",
                dependency_name=name,
                failed_conditions=[f"condition_{index}" for index, _ in enumerate(definition.conditions)],
            )

        if (
            definition.scope == ScopeType.REQUEST
            and any(
                self._definition_registry.get(parent_name)
                and self._definition_registry.get(parent_name).scope == ScopeType.SINGLETON
                for parent_name in self._resolving_stack
            )
        ):
            raise CreationError(
                message=format_semantic_message(
                    "lifecycle-request-scope",
                    f"A singleton component attempted to resolve request-scoped component '{name}'.",
                    "Resolve the dependency lazily inside a request context, or adjust the two scopes.",
                ),
                dependency_name=name,
            )

        self._resolving_stack.append(name)
        try:
            return self._scope_manager.get(
                scope_type=definition.scope,
                name=name,
                factory=lambda: self._create_instance(definition),
            )
        finally:
            self._resolving_stack.pop()

    def _create_instance(self, definition: Definition) -> Any:
        try:
            instance = definition.factory(self)
            if instance is None:
                raise CreationError(
                    message=f"The factory for dependency '{definition.name}' returned None.",
                    dependency_name=definition.name,
                )
            return instance
        except (CreationError, CircularDependencyError, ConditionNotMetError):
            raise
        except Exception as exc:
            raise CreationError(
                message=f"Failed to create dependency '{definition.name}': {exc}",
                dependency_name=definition.name,
                cause=exc,
            ) from exc

    def _validate_definitions(self) -> None:
        self._validate_injection_contracts()
        self._validate_dependencies()
        self._validate_scope_constraints()

    def _validate_injection_contracts(self) -> None:
        from .decorators import get_injection_markers

        skip_private = self._strict_private_injection
        for definition in self._definition_registry.values():
            target_cls = definition.type_
            if target_cls is None or not inspect.isclass(target_cls):
                continue

            markers = get_injection_markers(target_cls, skip_private=skip_private)

            type_hints, raw_annotations, type_hint_error = self._get_class_type_hints(target_cls)

            for attr_name, marker in markers.items():
                self._resolve_marker_binding(
                    owner_cls=target_cls,
                    attr_name=attr_name,
                    marker=marker,
                    type_hints=type_hints,
                    raw_annotations=raw_annotations,
                    type_hint_error=type_hint_error,
                )

            # ── Validate constructor-injection dependencies ──────────
            self._validate_constructor_dependencies(
                target_cls, type_hints, markers
            )

    def _validate_constructor_dependencies(
        self,
        cls: type,
        type_hints: Dict[str, Any],
        markers: Dict[str, Any],
    ) -> None:
        """Pre-validate constructor-injected types at refresh time.

        Raises ``DependencyNotFoundError`` or ``AmbiguousDependencyError``
        before the container goes active.
        """
        annotations = dict(getattr(cls, "__annotations__", {}) or {})
        if not annotations:
            return

        class_dict = cls.__dict__

        for attr_name, annotation in annotations.items():
            if attr_name in markers:
                continue
            if attr_name in class_dict and class_dict[attr_name] is not None:
                continue

            required = attr_name not in class_dict
            runtime_type = type_hints.get(attr_name, _normalize_string_annotation(annotation))
            candidates = self._definition_registry.find_by_type(runtime_type)

            # Fallback: string forward reference → name-based lookup
            if not candidates and isinstance(runtime_type, str):
                candidates = self._definition_registry.find_by_type_name(runtime_type)

            if len(candidates) > 1:
                raise AmbiguousDependencyError(
                    attr_name=attr_name,
                    target_cls=cls,
                    candidates=[d.name for d in candidates],
                )
            if len(candidates) == 0 and required:
                type_name = getattr(runtime_type, "__name__", str(runtime_type))
                raise DependencyNotFoundError(
                    message=format_semantic_message(
                        "inject-unique-binding",
                        f"Constructor dependency '{attr_name}' ({type_name}) on "
                        f"'{cls.__name__}' has no registered definition.",
                        "Register a component of this type before refresh().",
                    ),
                    dependency_name=attr_name,
                    injection_point=f"{cls.__name__}.__annotations__['{attr_name}']",
                    candidate_sources=[],
                )

    def _validate_dependencies(self) -> None:
        visited: Set[str] = set()
        path: List[str] = []

        def visit(name: str) -> None:
            if name in path:
                cycle_start = path.index(name)
                chain = path[cycle_start:] + [name]
                raise CircularDependencyError(
                    message=format_circular_dependency_error(chain),
                    dependency_chain=chain,
                    dependency_name=name,
                )
            if name in visited:
                return

            definition = self._definition_registry.get(name)
            if definition is None:
                return

            path.append(name)
            for dep_name in definition.dependencies:
                if not self._definition_registry.has(dep_name):
                    raise DependencyNotFoundError(
                        message=format_semantic_message(
                            "inject-unique-binding",
                            f"Component '{definition.name}' declares an unregistered dependency '{dep_name}'.",
                            "Check whether the decorator ran, whether the module was imported before refresh(), and whether the dependency name is correct.",
                        ),
                        dependency_name=dep_name,
                        candidate_sources=[],
                    )
                visit(dep_name)
            path.pop()
            visited.add(name)

        for name in self._definition_registry.list_names():
            visit(name)

    def _validate_scope_constraints(self) -> None:
        """Validate scope constraints: singleton/prototype must not depend
        on request-scoped components, either directly or transitively.

        Recursively traverses each singleton/prototype component's explicit
        dependencies and implicit dependencies (field injection markers),
        detecting request-scoped beans in the full transitive closure.

        Performance (A4): uses a cross-origin ``verified_safe`` memo so each
        component subgraph is fully traversed at most once across all origins,
        reducing worst-case complexity from O(N^2 * M) to O(N + E).

        A2: when ``self._strict_private_injection`` is True, the injection
        marker scanner skips single-underscore (_xxx) attributes, treating
        them as strictly private (opt-out from the v0.93a11+ default where
        _xxx is visible to the injection system).
        """
        from .decorators import get_injection_markers

        skip_private = self._strict_private_injection

        def _scan_markers(cls):
            return get_injection_markers(cls, skip_private=skip_private)

        # Cross-origin cache: components whose transitive closure has been
        # confirmed not to reach a request-scoped component. Subsequent
        # origins that reach one of these nodes can short-circuit.
        verified_safe: Set[str] = set()

        for definition in self._definition_registry.values():
            if definition.scope not in (ScopeType.SINGLETON, ScopeType.PROTOTYPE):
                continue
            if definition.name in verified_safe:
                continue
            self._check_transitive_scope(
                definition.name, set(), definition.name, definition.scope,
                _scan_markers,
                path=[definition.name],
                verified_safe=verified_safe,
            )

    def _check_transitive_scope(self, name, visited, origin_name, origin_scope,
                                get_injection_markers, path=None, verified_safe=None):
        """Recursively check transitive scope constraints.

        Args:
            path: Ordered dependency chain from the origin component to the
                current node (inclusive). Used to build ``ScopeViolationError.
                dependency_chain`` on violation (A4).
            verified_safe: Cross-origin memo of components confirmed safe.
                When a node is in this set, its subgraph has already been
                validated and can be skipped (A4 perf).
        """
        if path is None:
            path = [name]
        if verified_safe is None:
            verified_safe = set()

        if name in visited:
            return
        if name in verified_safe:
            # Cross-origin cache hit: this subgraph was already validated.
            return
        visited.add(name)

        definition = self._definition_registry.get(name)
        if definition is None:
            return

        # Check explicit dependencies
        for dep_name in definition.dependencies:
            dep_def = self._definition_registry.get(dep_name)
            if dep_def is None:
                self._check_transitive_scope(
                    dep_name, visited, origin_name, origin_scope,
                    get_injection_markers,
                    path=path + [dep_name],
                    verified_safe=verified_safe,
                )
                continue
            if dep_def.scope == ScopeType.REQUEST:
                full_chain = path + [dep_name]
                raise ScopeViolationError(
                    message=format_semantic_message(
                        "lifecycle-request-scope",
                        f"{origin_scope.name.title()} component '{origin_name}' "
                        f"depends transitively on request-scoped component '{dep_name}' "
                        f"(dependency path includes '{name}'). "
                        f"Dependency chain: {' -> '.join(full_chain)}",
                        "Resolve that dependency inside a request context, "
                        "or adjust the component scopes.",
                    ),
                    dependency_chain=full_chain,
                    origin_name=origin_name,
                    violating_component=dep_name,
                )
            self._check_transitive_scope(
                dep_name, visited, origin_name, origin_scope,
                get_injection_markers,
                path=path + [dep_name],
                verified_safe=verified_safe,
            )

        # Check field injection implicit dependencies
        target_cls = definition.type_
        if target_cls is not None and inspect.isclass(target_cls):
            markers = get_injection_markers(target_cls)
            if markers:
                type_hints, raw_annotations, _ = self._get_class_type_hints(target_cls)
                for attr_name, marker in markers.items():
                    dep_names = self._resolve_marker_to_dependency_names(
                        marker, attr_name, type_hints, raw_annotations,
                    )
                    for dep_name in dep_names:
                        dep_def = self._definition_registry.get(dep_name)
                        if dep_def is None:
                            self._check_transitive_scope(
                                dep_name, visited, origin_name, origin_scope,
                                get_injection_markers,
                                path=path + [dep_name],
                                verified_safe=verified_safe,
                            )
                            continue
                        if dep_def.scope == ScopeType.REQUEST:
                            full_chain = path + [dep_name]
                            raise ScopeViolationError(
                                message=format_semantic_message(
                                    "lifecycle-request-scope",
                                    f"{origin_scope.name.title()} component '{origin_name}' "
                                    f"depends transitively on request-scoped component "
                                    f"'{dep_name}' via field '{attr_name}' on '{name}'. "
                                    f"Dependency chain: {' -> '.join(full_chain)}",
                                    "Resolve that dependency inside a request context, "
                                    "or adjust the component scopes.",
                                ),
                                dependency_chain=full_chain,
                                origin_name=origin_name,
                                violating_component=dep_name,
                            )
                        self._check_transitive_scope(
                            dep_name, visited, origin_name, origin_scope,
                            get_injection_markers,
                            path=path + [dep_name],
                            verified_safe=verified_safe,
                        )

            # Check constructor injection implicit dependencies
            type_hints_ci, _, _ = self._get_class_type_hints(target_cls)
            constructor_deps = self._resolve_constructor_dependency_names(
                target_cls, markers, type_hints_ci,
            )
            for dep_name in constructor_deps:
                dep_def = self._definition_registry.get(dep_name)
                if dep_def is None:
                    self._check_transitive_scope(
                        dep_name, visited, origin_name, origin_scope,
                        get_injection_markers,
                        path=path + [dep_name],
                        verified_safe=verified_safe,
                    )
                    continue
                if dep_def.scope == ScopeType.REQUEST:
                    cls_name = getattr(target_cls, "__name__", str(target_cls))
                    full_chain = path + [dep_name]
                    raise ScopeViolationError(
                        message=format_semantic_message(
                            "lifecycle-request-scope",
                            f"{origin_scope.name.title()} component '{origin_name}' "
                            f"depends transitively on request-scoped component "
                            f"'{dep_name}' via constructor injection on '{cls_name}'. "
                            f"Dependency chain: {' -> '.join(full_chain)}",
                            "Resolve that dependency inside a request context, "
                            "or adjust the component scopes.",
                        ),
                        dependency_chain=full_chain,
                        origin_name=origin_name,
                        violating_component=dep_name,
                    )
                self._check_transitive_scope(
                    dep_name, visited, origin_name, origin_scope,
                    get_injection_markers,
                    path=path + [dep_name],
                    verified_safe=verified_safe,
                )

        # Subgraph fully traversed without violation: memoize as safe.
        verified_safe.add(name)

    def _resolve_constructor_dependency_names(
        self, cls, markers, type_hints,
    ) -> List[str]:
        """Return *definition names* of constructor-injected dependencies on *cls*."""
        annotations = dict(getattr(cls, "__annotations__", {}) or {})
        if not annotations:
            return []
        class_dict = cls.__dict__
        result: List[str] = []
        for attr_name in annotations:
            if attr_name in markers:
                continue
            if attr_name in class_dict and class_dict[attr_name] is not None:
                continue
            runtime_type = type_hints.get(attr_name)
            if runtime_type is None:
                continue
            candidates = self._definition_registry.find_by_type(runtime_type)
            if len(candidates) == 1:
                result.append(candidates[0].name)
            elif len(candidates) > 1:
                # Will be caught by _validate_constructor_dependencies
                result.extend(d.name for d in candidates)
        return result
    @staticmethod
    def _resolve_marker_to_dependency_names(marker, attr_name, type_hints, raw_annotations):
        """Extract candidate dependency name list from an injection marker."""
        from .decorators import InjectByName

        names = []
        explicit_name = getattr(marker, 'name', None)
        if isinstance(marker, InjectByName) or (isinstance(explicit_name, str) and explicit_name):
            names.append(explicit_name or getattr(marker, 'name', None) or attr_name)
        else:
            # Type-hint based resolution: try the type hint name
            hint = type_hints.get(attr_name)
            if hint is not None and not isinstance(hint, str):
                if inspect.isclass(hint):
                    names.append(hint.__name__)
            # Also try raw annotation string
            raw = raw_annotations.get(attr_name)
            if isinstance(raw, str):
                names.append(raw)
        return [n for n in names if n is not None]

    def _warm_up(self) -> None:
        for definition_name in self._ordered_definition_names(self._warmup_candidates()):
            definition = self._definition_registry.get(definition_name)
            if definition is None:
                continue
            self._resolve(definition)
        self._execute_lifecycle_startup()

    def _warmup_candidates(self) -> List[str]:
        candidates: List[str] = []
        for definition in self._definition_registry.values():
            if definition.scope != ScopeType.SINGLETON:
                continue
            if definition.eager or definition.healthcheck is not None or self._definition_has_lifecycle(definition):
                candidates.append(definition.name)
        return candidates

    def _ordered_definition_names(self, names: List[str]) -> List[str]:
        selected = set(names)
        ordered: List[str] = []
        temporary: Set[str] = set()
        permanent: Set[str] = set()

        def visit(name: str) -> None:
            if name in permanent:
                return
            if name in temporary:
                cycle = list(temporary) + [name]
                raise CircularDependencyError(
                    message=format_circular_dependency_error(cycle),
                    dependency_chain=cycle,
                    dependency_name=name,
                )
            temporary.add(name)
            definition = self._definition_registry.get(name)
            if definition is not None:
                for dep_name in definition.dependencies:
                    if dep_name in selected:
                        visit(dep_name)
            temporary.remove(name)
            permanent.add(name)
            ordered.append(name)

        for name in names:
            visit(name)
        return ordered

    def _process_pending_registrations(self) -> None:
        from .pending import PendingRegistry

        pending = PendingRegistry.get_instance()
        registrations = pending.drain()
        if not registrations:
            pending.freeze()
            return

        for registration in registrations:
            try:
                scope = ScopeType[registration.scope.upper()]
            except KeyError:
                logger.warning("Unknown scope '%s'; falling back to SINGLETON.", registration.scope)
                scope = ScopeType.SINGLETON

            if not registration.is_top_level:
                warn_semantic_once(
                    key=(
                        f"component-local:{registration.source_module}:{registration.source_qualname}:{registration.name}"
                    ),
                    rule_key="component-top-level",
                    problem=(
                        f"Component '{registration.name}' is defined in a local scope "
                        f"({registration.source_qualname}). It is only registered when that block executes."
                    ),
                    guidance=(
                        "Move the component to module top level. If it must be created dynamically, "
                        "do not rely on the stability guarantees of automatic scanning and assembly. "
                        "When you need stronger ownership and hot-pluggable semantics, declare the boundary with @module."
                    ),
                    category=ComponentDiscoveryWarning,
                    stacklevel=3,
                )

            cls = registration.cls
            definition = Definition(
                name=registration.name,
                type_=cls,
                scope=scope,
                factory=self._build_class_factory(cls),
                source=registration.get_source_location(),
                dependencies=registration.dependencies or (),
                conditions=registration.conditions,
                tags={"component_type": registration.component_type.value},
            )

            if self._definition_registry.has(registration.name):
                raise ValueError(duplicate_definition(registration.name))

            self._definition_registry.register(definition)

            if registration.component_type.value == "controller":
                self._register_controller_routes(cls, registration.url_prefix or "")

        pending.freeze()

    def _build_class_factory(self, target_cls):
        def factory(ctx: "ApplicationContext") -> object:
            return ctx._create_class_instance(target_cls)

        return factory

    @staticmethod
    def _unwrap_route_func(method_func):
        original = getattr(method_func, "__cullinan_original_func__", None)
        if original is not None:
            return original
        wrapped = getattr(method_func, "__wrapped__", None)
        if wrapped is not None:
            return wrapped
        return method_func

    def _register_controller_routes(self, cls: type, url_prefix: str) -> None:
        try:
            from cullinan.web.controller.core import _controller_decoration_context
            from cullinan.web.controller.registry import get_controller_registry
            from cullinan.web.gateway import get_router
            from cullinan.web.handler import get_handler_registry

            gateway_router = get_router()
            handler_registry = get_handler_registry()
            func_list = _controller_decoration_context.get() or []
            _controller_decoration_context.set([])

            if not func_list:
                for attr_name in dir(cls):
                    if attr_name.startswith("__") and attr_name.endswith("__"):
                        continue
                    attr = getattr(cls, attr_name, None)
                    if not callable(attr):
                        continue
                    route_url = getattr(attr, "__cullinan_url__", None)
                    route_type = getattr(attr, "__cullinan_method__", None)
                    if route_url is None or route_type is None:
                        inner = getattr(attr, "__cullinan_original_func__", None) or getattr(attr, "__wrapped__", None)
                        if inner is not None:
                            route_url = getattr(inner, "__cullinan_url__", route_url)
                            route_type = getattr(inner, "__cullinan_method__", route_type)
                    if route_url is not None and route_type is not None:
                        func_list.append((route_url, attr, route_type))

            if not func_list:
                return

            controller_registry = get_controller_registry()
            controller_name = cls.__name__
            controller_registry.register(controller_name, cls, url_prefix=url_prefix)

            for method_url, method_func, http_method in func_list:
                original_func = self._unwrap_route_func(method_func)
                original_url = getattr(original_func, "__cullinan_url__", None)
                full_url = url_prefix + (original_url if original_url is not None else method_url)

                controller_registry.register_method(
                    controller_name,
                    method_url,
                    http_method,
                    method_func,
                )

                gateway_router.add_route(
                    method=http_method.upper(),
                    path=full_url,
                    handler=original_func,
                    controller_cls=cls,
                    controller_method_name=getattr(original_func, "__name__", ""),
                )
                handler_registry.register(full_url, original_func)
        except Exception as exc:
            logger.warning("Failed to register controller routes for %s: %s", cls.__name__, exc)
            raise LifecycleError(
                f"Controller '{cls.__name__}' route registration failed: {exc}"
            ) from exc

    def _create_class_instance(self, cls: type) -> object:
        from .decorators import Lazy, get_injection_markers

        # ── Constructor injection (resolve deps first, set via setattr) ──
        init_kwargs = self._resolve_constructor_dependencies(cls)
        instance = cls()
        for attr_name, value in init_kwargs.items():
            setattr(instance, attr_name, value)

        # ── Field injection (skips properties already set by constructor) ──
        markers = get_injection_markers(cls, skip_private=self._strict_private_injection)
        type_hints, raw_annotations, type_hint_error = self._get_class_type_hints(cls)

        for attr_name, marker in markers.items():
            if attr_name in instance.__dict__:
                continue
            binding = self._resolve_marker_binding(
                owner_cls=cls,
                attr_name=attr_name,
                marker=marker,
                type_hints=type_hints,
                raw_annotations=raw_annotations,
                type_hint_error=type_hint_error,
            )
            if isinstance(marker, Lazy):
                setattr(instance, attr_name, _LazyProxy(lambda binding=binding: self._materialize_binding(binding)))
                continue
            setattr(instance, attr_name, self._materialize_binding(binding))

        # ── Freeze: all injected attributes immutable after DI ──
        injected = list(init_kwargs.keys()) + [
            n for n in markers
            if n in instance.__dict__
            and n not in init_kwargs  # constructor already included
        ]
        _freeze_dependencies(instance, injected)

        return instance

    # ── Constructor-injection resolution ────────────────────────────

    def _resolve_constructor_dependencies(self, cls: type) -> Dict[str, Any]:
        """Scan class-level annotations for DI dependencies and resolve them.

        Rules (see spec §4.2):
        * ``name: SomeType`` (no default) → required DI, resolve by type.
        * ``name: SomeType = None`` → optional DI; skip if not found.
        * ``name: SomeType = Inject()`` or ``= Lazy()`` → handled by field injection.
        * ``name: SomeType = literal`` → framework ignores.
        """
        from .decorators import get_injection_markers

        annotations = dict(getattr(cls, "__annotations__", {}) or {})
        if not annotations:
            return {}

        markers = get_injection_markers(cls, skip_private=self._strict_private_injection)
        class_dict = cls.__dict__
        type_hints, _raw, _err = self._get_class_type_hints(cls)

        result: Dict[str, Any] = {}
        for attr_name, annotation in annotations.items():
            # Skip field-injection markers — those are handled separately.
            if attr_name in markers:
                continue
            # Skip literal defaults, e.g. ``timeout: int = 5``.
            if attr_name in class_dict and class_dict[attr_name] is not None:
                continue

            required = attr_name not in class_dict  # no default at all
            runtime_type = type_hints.get(attr_name, _normalize_string_annotation(annotation))
            candidates = self._definition_registry.find_by_type(runtime_type)

            # Fallback: string forward reference → name-based lookup
            if not candidates and isinstance(runtime_type, str):
                candidates = self._definition_registry.find_by_type_name(runtime_type)

            if len(candidates) == 1:
                result[attr_name] = self._resolve(candidates[0])
            elif len(candidates) > 1:
                raise AmbiguousDependencyError(
                    attr_name=attr_name,
                    target_cls=cls,
                    candidates=[d.name for d in candidates],
                )
            elif required:
                type_name = getattr(runtime_type, "__name__", str(runtime_type))
                raise DependencyNotFoundError(
                    message=format_semantic_message(
                        "inject-unique-binding",
                        f"Constructor dependency '{attr_name}' ({type_name}) on "
                        f"'{cls.__name__}' has no registered definition.",
                        "Register a component of this type before refresh().",
                    ),
                    dependency_name=attr_name,
                    injection_point=f"{cls.__name__}.__annotations__['{attr_name}']",
                    candidate_sources=[],
                )
            # else: optional, no candidate → skip

        return result

    def _get_class_type_hints(self, cls: type):
        import typing

        cache_key = id(cls)
        cached = _global_type_hints_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            raw_annotations = dict(inspect.get_annotations(cls, eval_str=False))
        except Exception:
            raw_annotations = dict(getattr(cls, "__annotations__", {}) or {})

        # Normalize: when CO_FUTURE_ANNOTATIONS wraps an already-quoted
        # annotation (e.g. `"UserDirectoryService"` → `"'UserDirectoryService'"`),
        # strip the outer quotes so fallback lookups succeed.
        raw_annotations = {k: _normalize_string_annotation(v) for k, v in raw_annotations.items()}

        try:
            result = (typing.get_type_hints(cls, include_extras=True), raw_annotations, None)
        except Exception as exc:
            result = ({}, raw_annotations, exc)

        _global_type_hints_cache[cache_key] = result
        return result

    @staticmethod
    def _format_annotation_repr(annotation: Any) -> str:
        if isinstance(annotation, str):
            return annotation
        if hasattr(annotation, "__forward_arg__"):
            return str(annotation.__forward_arg__)
        if annotation is None:
            return "<unknown>"
        if hasattr(annotation, "__module__") and hasattr(annotation, "__qualname__"):
            return f"{annotation.__module__}.{annotation.__qualname__}"
        return repr(annotation)

    @staticmethod
    def _annotation_expr(node: ast.AST) -> str:
        return ast.unparse(node) if hasattr(ast, "unparse") else node.__class__.__name__

    @staticmethod
    def _flatten_union_ast(node: ast.AST) -> List[ast.AST]:
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return (
                ApplicationContext._flatten_union_ast(node.left)
                + ApplicationContext._flatten_union_ast(node.right)
            )
        return [node]

    @staticmethod
    def _extract_ast_name(node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = ApplicationContext._extract_ast_name(node.value)
            if parent:
                return f"{parent}.{node.attr}"
            return node.attr
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    @staticmethod
    def _make_target_from_name(name: str) -> _InjectionTarget:
        lookup_names = []
        if name:
            lookup_names.append(name)
            if "." in name:
                lookup_names.append(name.rsplit(".", 1)[-1])
        deduped = []
        for item in lookup_names:
            if item not in deduped:
                deduped.append(item)
        return _InjectionTarget(
            display_name=name,
            lookup_names=tuple(deduped),
        )

    @staticmethod
    def _make_target_from_type(type_hint: type) -> _InjectionTarget:
        lookup_names = [type_hint.__name__]
        qualified_name = f"{type_hint.__module__}.{type_hint.__qualname__}"
        if qualified_name not in lookup_names:
            lookup_names.append(qualified_name)
        if type_hint.__qualname__ not in lookup_names:
            lookup_names.append(type_hint.__qualname__)
        return _InjectionTarget(
            display_name=type_hint.__name__,
            lookup_names=tuple(lookup_names),
            runtime_type=type_hint,
        )

    @staticmethod
    def _make_single_annotation(target: _InjectionTarget, annotation_repr: str, *, optional: bool = False) -> _NormalizedInjectionAnnotation:
        return _NormalizedInjectionAnnotation(
            kind="single",
            annotation_repr=annotation_repr,
            targets=(target,),
            optional=optional,
        )

    @staticmethod
    def _parse_runtime_annotation(annotation: Any) -> _NormalizedInjectionAnnotation:
        import typing

        annotation_repr = ApplicationContext._format_annotation_repr(annotation)
        if isinstance(annotation, str):
            return ApplicationContext._parse_string_annotation(annotation)
        if hasattr(annotation, "__forward_arg__"):
            return ApplicationContext._parse_string_annotation(annotation.__forward_arg__)

        # ── Generic‑alias aware detection ──────────────────────────
        # Must run *before* inspect.isclass because some GenericAlias
        # objects (e.g. list['Hook'] on Python 3.9) may accidentally
        # pass the isclass check.
        origin_raw = None
        args_raw = ()
        if hasattr(annotation, "__origin__") and hasattr(annotation, "__args__"):
            origin_raw = getattr(annotation, "__origin__", None)
            args_raw = getattr(annotation, "__args__", ())
        origin = typing.get_origin(annotation)
        args = typing.get_args(annotation)

        # Use origin_raw / args_raw as fallback when stdlib returns None/empty
        _origin = origin if origin is not None else origin_raw
        _args = args if args else args_raw

        if _origin is typing.Annotated:
            if not _args:
                raise ValueError(missing_inner_type("Annotated"))
            return ApplicationContext._parse_runtime_annotation(_args[0])
        if _origin is typing.Final:
            if not _args:
                raise ValueError(missing_inner_type("Final"))
            return ApplicationContext._parse_runtime_annotation(_args[0])
        if origin in (typing.Union, getattr(types, "UnionType", ())):
            non_none_args = [arg for arg in args if arg is not type(None)]
            has_none = len(non_none_args) != len(args)
            if has_none and len(non_none_args) == 1:
                normalized = ApplicationContext._parse_runtime_annotation(non_none_args[0])
                if normalized.kind != "single":
                    raise ValueError(optional_single_dependency_only())
                return _NormalizedInjectionAnnotation(
                    kind="single",
                    annotation_repr=annotation_repr,
                    targets=normalized.targets,
                    optional=True,
                )
            targets: List[_InjectionTarget] = []
            for arg in args:
                normalized = ApplicationContext._parse_runtime_annotation(arg)
                if normalized.kind != "single" or normalized.optional:
                    raise ValueError(union_single_candidates_only())
                targets.extend(normalized.targets)
            return _NormalizedInjectionAnnotation(
                kind="union",
                annotation_repr=annotation_repr,
                targets=tuple(targets),
            )
        if origin is Provider:
            if len(args) != 1:
                raise ValueError(provider_requires_single_type_argument())
            normalized = ApplicationContext._parse_runtime_annotation(args[0])
            if normalized.kind != "single" or normalized.optional:
                raise ValueError(provider_single_dependency_only())
            return _NormalizedInjectionAnnotation(
                kind="provider",
                annotation_repr=annotation_repr,
                targets=normalized.targets,
            )
        # Collection handling: support both PEP 585 builtins (list, set, tuple)
        # and their typing counterparts (typing.List, typing.Set, typing.Tuple).
        # On Python 3.9, typing.get_origin may behave inconsistently for
        # PEP 585 generics with forward-reference string arguments; we also
        # inspect __origin__ directly as a fallback.
        _collection_origins = (list, set, tuple, typing.List, typing.Set, typing.Tuple)
        if origin in _collection_origins or (
            origin is None
            and hasattr(annotation, "__origin__")
            and annotation.__origin__ in _collection_origins
        ):
            _origin = origin if origin is not None else annotation.__origin__
            _args = args if args else getattr(annotation, "__args__", ())
            if _origin is tuple or _origin is typing.Tuple:
                if len(_args) != 2 or _args[1] is not Ellipsis:
                    raise ValueError(tuple_injection_form())
                element_annotation = _args[0]
                collection_kind = "tuple"
            else:
                if len(_args) != 1:
                    raise ValueError(collection_requires_one_element_type())
                element_annotation = _args[0]
                collection_kind = getattr(_origin, "__name__", str(_origin))
            normalized = ApplicationContext._parse_runtime_annotation(element_annotation)
            if normalized.kind != "single" or normalized.optional:
                raise ValueError(collection_single_dependency_only())
            return _NormalizedInjectionAnnotation(
                kind="collection",
                annotation_repr=annotation_repr,
                targets=normalized.targets,
                collection_kind=collection_kind,
            )

        # ── Bare class (single-dependency reference) ─────────────
        if inspect.isclass(annotation):
            return ApplicationContext._make_single_annotation(
                ApplicationContext._make_target_from_type(annotation),
                annotation_repr,
            )

        raise ValueError(unsupported_annotation_type(annotation_repr))

    @staticmethod
    def _parse_string_annotation(annotation_text: str) -> _NormalizedInjectionAnnotation:
        try:
            expr = ast.parse(annotation_text, mode="eval").body
        except SyntaxError as exc:
            raise ValueError(invalid_annotation_expression(annotation_text)) from exc
        return ApplicationContext._parse_annotation_ast(expr, annotation_text)

    @staticmethod
    def _parse_annotation_ast(node: ast.AST, annotation_repr: str) -> _NormalizedInjectionAnnotation:
        base_name = ApplicationContext._extract_ast_name(node)
        if base_name:
            return ApplicationContext._make_single_annotation(
                ApplicationContext._make_target_from_name(base_name),
                annotation_repr,
            )

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            parts = ApplicationContext._flatten_union_ast(node)
            normalized_targets: List[_InjectionTarget] = []
            optional = False
            for part in parts:
                part_name = ApplicationContext._extract_ast_name(part)
                if part_name in {"None", "NoneType"}:
                    optional = True
                    continue
                normalized = ApplicationContext._parse_annotation_ast(part, ApplicationContext._annotation_expr(part))
                if normalized.kind != "single" or normalized.optional:
                    raise ValueError(union_single_candidates_only())
                normalized_targets.extend(normalized.targets)
            if optional and len(normalized_targets) == 1:
                return _NormalizedInjectionAnnotation(
                    kind="single",
                    annotation_repr=annotation_repr,
                    targets=tuple(normalized_targets),
                    optional=True,
                )
            return _NormalizedInjectionAnnotation(
                kind="union",
                annotation_repr=annotation_repr,
                targets=tuple(normalized_targets),
            )

        if not isinstance(node, ast.Subscript):
            raise ValueError(unsupported_annotation_expression(annotation_repr))

        container_name = ApplicationContext._extract_ast_name(node.value)
        if container_name is None:
            raise ValueError(unsupported_annotation_container(annotation_repr))
        container_name = container_name.rsplit(".", 1)[-1]

        if container_name in {"Annotated", "Final"}:
            elements = ApplicationContext._subscript_elements(node.slice)
            if not elements:
                raise ValueError(missing_inner_type(container_name))
            normalized = ApplicationContext._parse_annotation_ast(elements[0], ApplicationContext._annotation_expr(elements[0]))
            return _NormalizedInjectionAnnotation(
                kind=normalized.kind,
                annotation_repr=annotation_repr,
                targets=normalized.targets,
                optional=normalized.optional,
                collection_kind=normalized.collection_kind,
            )
        if container_name == "Optional":
            elements = ApplicationContext._subscript_elements(node.slice)
            if len(elements) != 1:
                raise ValueError("Optional[T] requires exactly one type argument.")
            normalized = ApplicationContext._parse_annotation_ast(elements[0], ApplicationContext._annotation_expr(elements[0]))
            if normalized.kind != "single":
                raise ValueError(optional_single_dependency_only())
            return _NormalizedInjectionAnnotation(
                kind="single",
                annotation_repr=annotation_repr,
                targets=normalized.targets,
                optional=True,
            )
        if container_name == "Provider":
            elements = ApplicationContext._subscript_elements(node.slice)
            if len(elements) != 1:
                raise ValueError(provider_requires_single_type_argument())
            normalized = ApplicationContext._parse_annotation_ast(elements[0], ApplicationContext._annotation_expr(elements[0]))
            if normalized.kind != "single" or normalized.optional:
                raise ValueError(provider_single_dependency_only())
            return _NormalizedInjectionAnnotation(
                kind="provider",
                annotation_repr=annotation_repr,
                targets=normalized.targets,
            )
        if container_name in {"list", "set"}:
            elements = ApplicationContext._subscript_elements(node.slice)
            if len(elements) != 1:
                raise ValueError(container_requires_one_element_type(container_name))
            normalized = ApplicationContext._parse_annotation_ast(elements[0], ApplicationContext._annotation_expr(elements[0]))
            if normalized.kind != "single" or normalized.optional:
                raise ValueError(collection_single_dependency_only())
            return _NormalizedInjectionAnnotation(
                kind="collection",
                annotation_repr=annotation_repr,
                targets=normalized.targets,
                collection_kind=container_name,
            )
        if container_name == "tuple":
            elements = ApplicationContext._subscript_elements(node.slice)
            if len(elements) != 2 or not isinstance(elements[1], ast.Constant) or elements[1].value is not Ellipsis:
                raise ValueError(tuple_injection_form())
            normalized = ApplicationContext._parse_annotation_ast(elements[0], ApplicationContext._annotation_expr(elements[0]))
            if normalized.kind != "single" or normalized.optional:
                raise ValueError(collection_single_dependency_only())
            return _NormalizedInjectionAnnotation(
                kind="collection",
                annotation_repr=annotation_repr,
                targets=normalized.targets,
                collection_kind="tuple",
            )
        if container_name == "Union":
            elements = ApplicationContext._subscript_elements(node.slice)
            normalized_targets: List[_InjectionTarget] = []
            optional = False
            for element in elements:
                element_name = ApplicationContext._extract_ast_name(element)
                if element_name in {"None", "NoneType"}:
                    optional = True
                    continue
                normalized = ApplicationContext._parse_annotation_ast(element, ApplicationContext._annotation_expr(element))
                if normalized.kind != "single" or normalized.optional:
                    raise ValueError(union_single_candidates_only())
                normalized_targets.extend(normalized.targets)
            if optional and len(normalized_targets) == 1:
                return _NormalizedInjectionAnnotation(
                    kind="single",
                    annotation_repr=annotation_repr,
                    targets=tuple(normalized_targets),
                    optional=True,
                )
            return _NormalizedInjectionAnnotation(
                kind="union",
                annotation_repr=annotation_repr,
                targets=tuple(normalized_targets),
            )

        raise ValueError(unsupported_annotation_container(annotation_repr))

    @staticmethod
    def _subscript_elements(node: ast.AST) -> List[ast.AST]:
        if isinstance(node, ast.Tuple):
            return list(node.elts)
        return [node]

    def _normalize_marker_annotation(
        self,
        *,
        owner_cls: type,
        attr_name: str,
        type_hints: Dict[str, Any],
        raw_annotations: Dict[str, Any],
        type_hint_error: Optional[Exception],
    ) -> _NormalizedInjectionAnnotation:
        type_hint = type_hints.get(attr_name)
        raw_annotation = raw_annotations.get(attr_name)
        try:
            if type_hint is not None:
                return self._parse_runtime_annotation(type_hint)
            if raw_annotation is not None:
                return self._parse_runtime_annotation(raw_annotation)
        except Exception as exc:
            cause = exc
        else:
            cause = type_hint_error

        message = format_semantic_message(
            "inject-unique-binding",
            (
                f"Failed to resolve the type for dependency field '{attr_name}' on component "
                f"'{owner_cls.__name__}'. Original annotation: "
                f"'{self._format_annotation_repr(raw_annotation)}'."
            ),
            "Provide a type annotation that Inject() can resolve stably. For complex cases, use InjectByName('ExplicitName').",
        )
        if cause is not None:
            message = f"{message} Original error: {type(cause).__name__}: {cause}"

        raise DependencyTypeResolutionError(
            message=message,
            dependency_name=attr_name,
            injection_point=f"{owner_cls.__module__}.{owner_cls.__name__}.{attr_name}",
            expected_type_name=self._format_annotation_repr(raw_annotation),
            candidate_sources=[],
            cause=cause,
        )

    def _resolve_marker_binding(
        self,
        *,
        owner_cls: type,
        attr_name: str,
        marker,
        type_hints: Dict[str, Any],
        raw_annotations: Dict[str, Any],
        type_hint_error: Optional[Exception],
    ) -> _ResolvedInjectionBinding:
        from .decorators import InjectByName

        injection_point = f"{owner_cls.__module__}.{owner_cls.__name__}.{attr_name}"
        required = getattr(marker, "required", True)
        explicit_name = getattr(marker, "name", None)

        if isinstance(marker, InjectByName) or explicit_name:
            self._warn_name_based_injection_semantics(
                owner_cls=owner_cls,
                attr_name=attr_name,
                explicit_name=explicit_name,
                raw_annotation=raw_annotations.get(attr_name),
            )
            dependency_name = explicit_name or marker.name or attr_name
            candidate_names = (dependency_name,) if self._definition_registry.has(dependency_name) else ()
            if required and not candidate_names:
                raise DependencyNotFoundError(
                    message=format_semantic_message(
                        "inject-by-name",
                        (
                            f"Dependency field '{attr_name}' on component '{owner_cls.__name__}' requires "
                            f"explicit component '{dependency_name}', but that component is not registered."
                        ),
                        "Make sure the InjectByName() name matches the registration name. If needed, switch to Inject() with an explicit type.",
                    ),
                    dependency_name=dependency_name,
                    injection_point=injection_point,
                    candidate_sources=[
                        {"source": candidate, "reason": "name_mismatch"}
                        for candidate in self.list_definitions()
                    ],
                )
            return _ResolvedInjectionBinding(
                kind="single",
                annotation_repr=dependency_name,
                target_labels=(dependency_name,),
                required=required,
                candidate_names=candidate_names,
            )

        normalized = self._normalize_marker_annotation(
            owner_cls=owner_cls,
            attr_name=attr_name,
            type_hints=type_hints,
            raw_annotations=raw_annotations,
            type_hint_error=type_hint_error,
        )
        return self._resolve_normalized_binding(
            normalized=normalized,
            injection_point=injection_point,
            dependency_name=attr_name,
            required=required,
        )

    def _warn_name_based_injection_semantics(
        self,
        *,
        owner_cls: type,
        attr_name: str,
        explicit_name: Optional[str],
        raw_annotation: Any,
    ) -> None:
        point = f"{owner_cls.__module__}.{owner_cls.__name__}.{attr_name}"
        if not explicit_name:
            warn_semantic_once(
                key=f"inject-by-name-implicit:{point}",
                rule_key="inject-by-name",
                problem=(
                    f"Injection point '{point}' uses InjectByName() without an explicit name, so it currently falls back to attribute name '{attr_name}'."
                ),
                guidance="Prefer InjectByName('ExactComponentName') to avoid drift between attribute names and registration names.",
                category=InjectionSemanticWarning,
                stacklevel=4,
            )

        if raw_annotation in (None, Any):
            warn_semantic_once(
                key=f"inject-by-name-annotation:{point}",
                rule_key="inject-by-name",
                problem=(
                    f"Injection point '{point}' uses InjectByName() without an explicit type annotation."
                ),
                guidance="Even for name-based resolution, add an accurate type annotation to express intent and help static analysis.",
                category=InjectionSemanticWarning,
                stacklevel=4,
            )

    def _resolve_normalized_binding(
        self,
        *,
        normalized: _NormalizedInjectionAnnotation,
        injection_point: str,
        dependency_name: str,
        required: bool,
    ) -> _ResolvedInjectionBinding:
        allow_missing = normalized.optional or not required

        if normalized.kind == "single":
            candidate_name = self._select_single_candidate(
                target=normalized.targets[0],
                injection_point=injection_point,
                dependency_name=dependency_name,
                normalized=normalized,
                allow_missing=allow_missing,
            )
            return _ResolvedInjectionBinding(
                kind="single",
                annotation_repr=normalized.annotation_repr,
                target_labels=tuple(target.display_name for target in normalized.targets),
                required=required,
                candidate_names=(candidate_name,) if candidate_name else (),
            )

        if normalized.kind == "provider":
            candidate_name = self._select_single_candidate(
                target=normalized.targets[0],
                injection_point=injection_point,
                dependency_name=dependency_name,
                normalized=normalized,
                allow_missing=not required,
            )
            return _ResolvedInjectionBinding(
                kind="provider",
                annotation_repr=normalized.annotation_repr,
                target_labels=tuple(target.display_name for target in normalized.targets),
                required=required,
                candidate_names=(candidate_name,) if candidate_name else (),
            )

        if normalized.kind == "collection":
            candidate_names = tuple(
                definition.name for definition in self._find_matching_definitions(normalized.targets[0])
            )
            if required and not candidate_names:
                self._raise_missing_binding(
                    dependency_name=dependency_name,
                    injection_point=injection_point,
                    normalized=normalized,
                )
            return _ResolvedInjectionBinding(
                kind="collection",
                annotation_repr=normalized.annotation_repr,
                target_labels=tuple(target.display_name for target in normalized.targets),
                required=required,
                candidate_names=candidate_names,
                collection_kind=normalized.collection_kind,
            )

        if normalized.kind == "union":
            viable_candidates = []
            ambiguous_targets = []
            for target in normalized.targets:
                matches = self._find_matching_definitions(target)
                if len(matches) > 1:
                    ambiguous_targets.append((target, matches))
                elif len(matches) == 1:
                    viable_candidates.append((target, matches[0]))
            if ambiguous_targets:
                target, matches = ambiguous_targets[0]
                self._raise_ambiguous_binding(
                    dependency_name=dependency_name,
                    injection_point=injection_point,
                    normalized=normalized,
                    candidates=matches,
                    extra_reason=f"Union candidate '{target.display_name}' matched multiple components.",
                )
            unique_names = {definition.name for _, definition in viable_candidates}
            if len(unique_names) == 1 and viable_candidates:
                chosen = viable_candidates[0][1].name
                return _ResolvedInjectionBinding(
                    kind="single",
                    annotation_repr=normalized.annotation_repr,
                    target_labels=tuple(target.display_name for target in normalized.targets),
                    required=required,
                    candidate_names=(chosen,),
                )
            if len(unique_names) > 1:
                self._raise_ambiguous_binding(
                    dependency_name=dependency_name,
                    injection_point=injection_point,
                    normalized=normalized,
                    candidates=[definition for _, definition in viable_candidates],
                    extra_reason="Multiple Union candidates can be bound at the same time.",
                )
            if allow_missing:
                return _ResolvedInjectionBinding(
                    kind="single",
                    annotation_repr=normalized.annotation_repr,
                    target_labels=tuple(target.display_name for target in normalized.targets),
                    required=False,
                    candidate_names=(),
                )
            self._raise_missing_binding(
                dependency_name=dependency_name,
                injection_point=injection_point,
                normalized=normalized,
            )

        raise DependencyTypeResolutionError(
            message=format_semantic_message(
                "inject-unique-binding",
                f"Injection point '{injection_point}' uses unsupported injection semantics '{normalized.kind}'.",
                "Use InjectByName('ExplicitName'), or narrow the annotation to a single type contract that can bind uniquely.",
            ),
            dependency_name=dependency_name,
            injection_point=injection_point,
            expected_type_name=normalized.annotation_repr,
            candidate_sources=[],
        )

    def _select_single_candidate(
        self,
        *,
        target: _InjectionTarget,
        injection_point: str,
        dependency_name: str,
        normalized: _NormalizedInjectionAnnotation,
        allow_missing: bool,
    ) -> Optional[str]:
        matches = self._find_matching_definitions(target)
        if len(matches) == 1:
            return matches[0].name
        if not matches and allow_missing:
            return None
        if len(matches) > 1:
            self._raise_ambiguous_binding(
                dependency_name=dependency_name,
                injection_point=injection_point,
                normalized=normalized,
                candidates=matches,
            )
        self._raise_missing_binding(
            dependency_name=dependency_name,
            injection_point=injection_point,
            normalized=normalized,
        )

    def _find_matching_definitions(self, target: _InjectionTarget) -> List[Definition]:
        matches: List[Definition] = []
        for definition in self._definition_registry.values():
            if self._definition_matches_target(definition, target):
                matches.append(definition)
        return matches

    @staticmethod
    def _definition_matches_target(definition: Definition, target: _InjectionTarget) -> bool:
        if target.runtime_type is not None and definition.type_ is not None:
            try:
                if issubclass(definition.type_, target.runtime_type):
                    return True
            except TypeError:
                pass
        if definition.name in target.lookup_names:
            return True
        if definition.type_ is None:
            return False
        for candidate_type in getattr(definition.type_, "__mro__", (definition.type_,)):
            qualified_name = f"{candidate_type.__module__}.{candidate_type.__qualname__}"
            if (
                candidate_type.__name__ in target.lookup_names
                or candidate_type.__qualname__ in target.lookup_names
                or qualified_name in target.lookup_names
            ):
                return True
        return False

    def _raise_missing_binding(
        self,
        *,
        dependency_name: str,
        injection_point: str,
        normalized: _NormalizedInjectionAnnotation,
    ) -> None:
        raise DependencyNotFoundError(
            message=format_semantic_message(
                "inject-unique-binding",
                (
                    f"Injection point '{injection_point}' could not find a bindable component. "
                    f"Original annotation: '{normalized.annotation_repr}', "
                    f"normalized semantics: '{self._describe_normalized_kind(normalized)}'."
                ),
                "Make sure the target component is registered and imported before refresh(). Use InjectByName('ExplicitName') when the dependency cannot be expressed uniquely.",
            ),
            dependency_name=dependency_name,
            injection_point=injection_point,
            candidate_sources=[
                {"source": candidate, "reason": "name_mismatch"}
                for candidate in self.list_definitions()
            ],
        )

    def _raise_ambiguous_binding(
        self,
        *,
        dependency_name: str,
        injection_point: str,
        normalized: _NormalizedInjectionAnnotation,
        candidates: List[Definition],
        extra_reason: Optional[str] = None,
    ) -> None:
        reason = extra_reason or "Multiple candidates satisfy the injection contract."
        raise DependencyTypeResolutionError(
            message=format_semantic_message(
                "inject-unique-binding",
                (
                    f"Injection point '{injection_point}' resolved to multiple candidates. "
                    f"Original annotation: '{normalized.annotation_repr}', "
                    f"normalized semantics: '{self._describe_normalized_kind(normalized)}'. "
                    f"{reason}"
                ),
                "Use InjectByName('ExplicitName'), or narrow the type until only one component can be bound.",
            ),
            dependency_name=dependency_name,
            injection_point=injection_point,
            expected_type_name=normalized.annotation_repr,
            candidate_sources=[
                {"source": definition.name, "reason": "multiple_candidates"}
                for definition in candidates
            ],
        )

    @staticmethod
    def _describe_normalized_kind(normalized: _NormalizedInjectionAnnotation) -> str:
        if normalized.kind == "collection":
            return f"collection[{normalized.collection_kind}]"
        return normalized.kind

    def _materialize_binding(self, binding: _ResolvedInjectionBinding) -> Any:
        if binding.kind == "single":
            if not binding.candidate_names:
                return None
            dependency_name = binding.candidate_names[0]
            return self.get(dependency_name) if binding.required else self.try_get(dependency_name)

        if binding.kind == "provider":
            if not binding.candidate_names:
                return None
            dependency_name = binding.candidate_names[0]
            return Provider(lambda dependency_name=dependency_name: self.get(dependency_name))

        if binding.kind == "collection":
            values = [self.get(name) for name in binding.candidate_names]
            if binding.collection_kind == "set":
                return set(values)
            if binding.collection_kind == "tuple":
                return tuple(values)
            return list(values)

        raise DependencyTypeResolutionError(
            message=format_semantic_message(
                "inject-unique-binding",
                f"Internal binding resolution produced unknown kind '{binding.kind}'.",
                "This is an internal consistency error in the framework. Check the binding normalization flow.",
            ),
            dependency_name=",".join(binding.target_labels),
            candidate_sources=[],
        )

    def _definition_has_lifecycle(self, definition: Definition) -> bool:
        target_cls = definition.type_
        if target_cls is None:
            return False
        lifecycle_methods = (
            "on_post_construct",
            "on_post_construct_async",
            "on_startup",
            "on_startup_async",
            "on_shutdown",
            "on_shutdown_async",
            "on_pre_destroy",
            "on_pre_destroy_async",
        )
        for method_name in lifecycle_methods:
            if self._is_class_method_overridden(target_cls, method_name):
                return True
        return False

    @staticmethod
    def _is_class_method_overridden(target_cls: type, method_name: str) -> bool:
        for cls in target_cls.__mro__:
            if method_name not in cls.__dict__:
                continue
            if cls.__name__ in ("LifecycleAware", "SmartLifecycle", "object"):
                return False
            return True
        return False

    def _execute_lifecycle_startup(self) -> None:
        instances_with_phase = []
        for definition_name in self._ordered_definition_names(self._warmup_candidates()):
            definition = self._definition_registry.get(definition_name)
            if definition is None or definition.scope != ScopeType.SINGLETON:
                continue
            if not self._scope_manager.has(ScopeType.SINGLETON, definition_name):
                continue
            instance = self._scope_manager.get(
                scope_type=ScopeType.SINGLETON,
                name=definition_name,
                factory=lambda: self._create_instance(definition),
            )
            if not self._instance_has_lifecycle(instance):
                continue
            phase = 0
            if hasattr(instance, "get_phase") and callable(getattr(instance, "get_phase")):
                try:
                    phase = instance.get_phase()
                except Exception:
                    phase = 0
            instances_with_phase.append((definition_name, instance, phase))

        instances_with_phase.sort(key=lambda item: item[2])
        self._startup_order = [name for name, _, _ in instances_with_phase]

        for name, instance, _ in instances_with_phase:
            self._lifecycle_instances[name] = instance
            self._lifecycle_phases[name] = LifecyclePhase.POST_CONSTRUCT
            self._call_lifecycle_method(name, instance, "on_post_construct", "on_post_construct_async")

        for name, instance, _ in instances_with_phase:
            self._lifecycle_phases[name] = LifecyclePhase.STARTING
            self._call_lifecycle_method(name, instance, "on_startup", "on_startup_async")
            self._lifecycle_phases[name] = LifecyclePhase.RUNNING

    def _execute_lifecycle_shutdown(self) -> None:
        shutdown_order = list(reversed(self._startup_order))
        for name in shutdown_order:
            instance = self._lifecycle_instances.get(name)
            if instance is None:
                continue
            self._lifecycle_phases[name] = LifecyclePhase.STOPPING
            self._call_lifecycle_method(name, instance, "on_shutdown", "on_shutdown_async")

        for name in shutdown_order:
            instance = self._lifecycle_instances.get(name)
            if instance is None:
                continue
            self._lifecycle_phases[name] = LifecyclePhase.PRE_DESTROY
            self._call_lifecycle_method(name, instance, "on_pre_destroy", "on_pre_destroy_async")
            self._lifecycle_phases[name] = LifecyclePhase.DESTROYED

    def _call_lifecycle_method(self, name: str, instance: Any, sync_method: str, async_method: str) -> None:
        async_func = getattr(instance, async_method, None)
        if async_func and callable(async_func) and self._is_user_defined_method(instance, async_method):
            try:
                self._run_coroutine(async_func())
            except Exception as exc:
                logger.error("Lifecycle method %s.%s failed: %s", name, async_method, exc)
                if self._is_critical_lifecycle(sync_method, async_method):
                    raise LifecycleError(
                        f"Critical lifecycle method '{name}.{async_method}' failed: {exc}"
                    ) from exc

        sync_func = getattr(instance, sync_method, None)
        if sync_func and callable(sync_func) and self._is_user_defined_method(instance, sync_method):
            try:
                result = sync_func()
                if inspect.iscoroutine(result):
                    self._run_coroutine(result)
            except Exception as exc:
                logger.error("Lifecycle method %s.%s failed: %s", name, sync_method, exc)
                if self._is_critical_lifecycle(sync_method, async_method):
                    raise LifecycleError(
                        f"Critical lifecycle method '{name}.{sync_method}' failed: {exc}"
                    ) from exc

    @staticmethod
    def _is_critical_lifecycle(sync_method: str, async_method: str) -> bool:
        """Determine if a lifecycle method is critical (failure should propagate).
        
        on_post_construct and on_pre_destroy are critical — failure means the
        component is in an inconsistent state. on_startup/on_shutdown failures
        are logged but do not halt the container to avoid cascading failures.
        """
        critical = {
            "on_post_construct", "on_post_construct_async",
            "on_pre_destroy", "on_pre_destroy_async",
        }
        return sync_method in critical or async_method in critical

    def _is_user_defined_method(self, instance: Any, method_name: str) -> bool:
        return self._is_class_method_overridden(type(instance), method_name)

    @staticmethod
    def _instance_has_lifecycle(instance: Any) -> bool:
        for method_name in (
            "on_post_construct",
            "on_post_construct_async",
            "on_startup",
            "on_startup_async",
            "on_shutdown",
            "on_shutdown_async",
            "on_pre_destroy",
            "on_pre_destroy_async",
        ):
            method = getattr(instance, method_name, None)
            if method and callable(method):
                if type(instance).__name__ in ("LifecycleAware", "SmartLifecycle"):
                    continue
                return True
        return False

    @staticmethod
    def _run_coroutine(coro) -> None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(coro)
            else:
                loop.run_until_complete(coro)
        except RuntimeError:
            asyncio.run(coro)

    def _await_request_drained(self, timeout: float) -> None:
        deadline = time.monotonic() + max(timeout, 0)
        while self.active_request_count > 0:
            if time.monotonic() >= deadline:
                logger.warning(
                    "Timed out while waiting for request scopes to drain. root=%s remaining=%s",
                    self.id,
                    self.active_request_count,
                )
                break
            time.sleep(0.01)

    def _run_health_checks(self) -> None:
        for definition in self._definition_registry.values():
            callback = definition.healthcheck
            if callback is None:
                continue
            instance = self.get(definition.name)
            result = callback(self, instance)
            if inspect.iscoroutine(result):
                result = self._run_coroutine_safely(result)
            if result is False:
                raise LifecycleError(f"Health check failed for component '{definition.name}'.")

        for callback in self._health_checks:
            result = callback(self)
            if inspect.iscoroutine(result):
                result = self._run_coroutine_safely(result)
            if result is False:
                raise LifecycleError("Container health check failed.")

    @staticmethod
    def _run_coroutine_safely(coro) -> Any:
        """Run a coroutine, handling both running and non-running event loops.
        
        Uses asyncio.run() for fresh loops (normal case). Falls back to
        creating a new event loop in a separate thread when a loop is already
        running (e.g., inside a Jupyter notebook or async web server startup).
        """
        import concurrent.futures
        
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — safe to use asyncio.run()
            return asyncio.run(coro)
        
        # A loop is already running — run in a new loop on a new thread
        def _run_in_new_loop():
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_in_new_loop)
            return future.result(timeout=30)

    def get_lifecycle_phase(self, name: str) -> Optional[LifecyclePhase]:
        return self._lifecycle_phases.get(name)

    def is_component_running(self, name: str) -> bool:
        return self._lifecycle_phases.get(name) == LifecyclePhase.RUNNING


class _LazyProxy:
    __slots__ = ("_resolver", "_resolved", "_value", "_lock")

    def __init__(self, resolver: Callable[[], Any]):
        self._resolver = resolver
        self._resolved = False
        self._value = None
        self._lock = threading.Lock()

    def _resolve(self):
        if self._resolved:
            return self._value
        with self._lock:
            if not self._resolved:
                self._value = self._resolver()
                self._resolved = True
        return self._value

    def __getattr__(self, item):
        return getattr(self._resolve(), item)

    def __call__(self, *args, **kwargs):
        return self._resolve()(*args, **kwargs)


class _ImmutableAttributeError(AttributeError):
    """Raised when attempting to reassign a dependency after DI injection.

    Points developers to the TestContext API for testing scenarios.
    """

    def __init__(self, attr_name: str):
        super().__init__(
            f"Cannot reassign '{attr_name}': dependency already injected. "
            f"Use TestContext.mock(instance, '{attr_name}', mock_value) for testing."
        )


def _freeze_dependencies(instance, injected_names):
    """Make injected attributes read-only on a single instance.

    Creates a transient dynamic subclass that overrides ``__setattr__``
    to reject reassignment of frozen attributes.  Only *instance* is
    affected — other instances of the same class, including those
    created manually (outside of :meth:`_create_class_instance`), are
    completely unaffected.

    Args:
        instance: The freshly-injected instance.
        injected_names: Iterable of attribute names that were populated
            by DI (both constructor and field injection).

    Raises:
        _ImmutableAttributeError: When code tries to reassign a frozen
            attribute on *instance* after freeze.
    """
    frozen = frozenset(injected_names)
    cls = type(instance)

    class _Frozen(cls):
        def __setattr__(self, name, value):
            if name in frozen:
                raise _ImmutableAttributeError(name)
            super().__setattr__(name, value)

    _Frozen.__name__ = cls.__name__
    _Frozen.__qualname__ = cls.__qualname__
    _Frozen.__module__ = cls.__module__
    instance.__class__ = _Frozen


__all__ = ["ApplicationContext", "ContainerState"]
