# -*- coding: utf-8 -*-
"""Application-first runtime model built on top of ApplicationContext."""

from __future__ import annotations

from dataclasses import dataclass, field
import functools
import importlib
import inspect
import logging
import threading
import uuid
from types import MappingProxyType
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Type

from cullinan.core.application_context import (
    ApplicationContext,
    ContainerState,
    _emit_report_fallback,
)
from cullinan.core.container_manager import get_container_manager
from cullinan.core.context import create_context, destroy_context, get_current_context
from cullinan.core.decorators import get_component_registration_metadata
from cullinan.core.pending import PendingRegistration, PendingRegistry
from cullinan._api_boundary import in_public_api_context
from cullinan.core.semantic_rules import (
    PublicAPISemanticWarning,
    format_semantic_message,
    warn_semantic_once,
)
from cullinan.support.diagnostics import application_not_installed
from cullinan.support.exceptions import ConfigurationError
from cullinan.web.gateway import (
    get_dispatcher,
    get_exception_handler,
    get_pipeline,
    get_router,
    reset_gateway,
)
from cullinan.web.gateway.globals import (
    _peek_dispatcher,
    _peek_exception_handler,
    _peek_pipeline,
    _peek_router,
)
from cullinan.web.gateway.runtime import WebRuntime, WebRuntimeConfig
from cullinan.runtime.module_scanner import list_submodules


_MODULE_ATTR = "__cullinan_module__"
_APPLICATION_ATTR = "__cullinan_application__"
_APPLICATION_PACKAGES_ATTR = "__cullinan_application_packages__"
_APPLICATION_MODULES_ATTR = "__cullinan_application_modules__"
_APP_CONTEXT_KEY = "cullinan.application"
_RUNTIME_CONTEXT_KEY = "cullinan.runtime"

# Dedicated error code for a pre-boot pipeline registration that the boot
# boundary refuses. It is not the generic ``CONFIG_ERROR``: this failure and any
# other misconfiguration must stay distinguishable in monitoring.
_PREBOOT_REGISTRATION_ERROR_CODE = "PREBOOT_REGISTRATION_ERROR"


@dataclass(frozen=True)
class ModuleMetadata:
    imports: Tuple[Type[Any], ...] = ()
    packages: Tuple[str, ...] = ()
    ownership_overrides: Dict[str, Type[Any]] = field(default_factory=dict)
    warmup_hooks: Tuple[Callable[["Application"], None], ...] = ()
    health_checks: Tuple[Callable[["Application"], None], ...] = ()


@dataclass(frozen=True)
class ApplicationMetadata:
    packages: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ModuleSpec:
    cls: Type[Any]
    metadata: ModuleMetadata
    packages: Tuple[str, ...]

    @property
    def name(self) -> str:
        return f"{self.cls.__module__}.{self.cls.__name__}"


@dataclass(frozen=True)
class ModuleGraph:
    root_module: Type[Any]
    modules: Tuple[ModuleSpec, ...]
    python_modules: Tuple[str, ...]
    component_owners: Dict[str, Type[Any]]


@dataclass(frozen=True)
class _DeclarationDiff:
    """Reconciliation between the declared and the assembled component sets.

    ``declared`` is the import-time declaration snapshot taken *before*
    ``PendingRegistry.reset()``; ``assembled`` is the set of components that
    actually made it into ``ModuleGraph.component_owners``; ``dropped`` is the
    difference (declared but not assembled).

    Module-private on purpose: this is a diagnostic view hanging off the
    existing ``Application`` object and must never enter any ``__all__`` (it is
    not a new top-level symbol).
    """

    declared: Tuple[str, ...] = ()
    assembled: Tuple[str, ...] = ()
    dropped: Tuple[str, ...] = ()

    @property
    def dropped_count(self) -> int:
        return len(self.dropped)


#: The four gateway globals that ``reset_gateway()`` rebuilds at the boot
#: boundary. Their names double as the ``gateway`` mapping keys of
#: :class:`_AssemblySnapshot`.
_GATEWAY_SURFACE_NAMES: Tuple[str, ...] = (
    "pipeline",
    "router",
    "dispatcher",
    "exception_handler",
)


@dataclass(frozen=True)
class _SurfaceHoldings:
    """Declared / assembled / dropped holdings of one assembly surface.

    ``declared`` is what the surface held *before* the boot boundary (the
    pre-boot registration snapshot taken while warming up); ``assembled`` is what
    it holds *after* the boundary (what this assembly actually carries); and
    ``dropped`` is ``declared - assembled`` -- the pre-boot entries the boundary
    discarded.

    Module-private on purpose: like :class:`_DeclarationDiff` this is a
    diagnostic view hanging off the existing ``Application`` object and must
    never enter any ``__all__`` (it is not a new top-level symbol).
    """

    declared: Tuple[str, ...] = ()
    assembled: Tuple[str, ...] = ()
    dropped: Tuple[str, ...] = ()


@dataclass(frozen=True)
class _AssemblySnapshot:
    """What one application assembly actually holds, surface by surface.

    ``gateway`` maps each of the four gateway surfaces -- ``pipeline`` /
    ``router`` / ``dispatcher`` / ``exception_handler`` -- to its
    :class:`_SurfaceHoldings`; ``container`` reports the declared-vs-assembled
    component reconciliation the container assembled. The snapshot is obtained in
    one call through :meth:`Application.get_assembly_snapshot`.

    Module-private on purpose: this is a read-only diagnostic view and must never
    enter any ``__all__`` (it is not a new top-level symbol).
    """

    gateway: Mapping[str, _SurfaceHoldings]
    container: _SurfaceHoldings


class Runtime:
    """Mutable runtime record for one Application candidate."""

    def __init__(self, application: "Application", *, context: ApplicationContext, web_runtime: WebRuntime):
        self.application = application
        self.context = context
        self.web_runtime = web_runtime
        self.phase = "assembled"

    def validate(self) -> None:
        self.phase = "validating"
        self.web_runtime.validate()

    def warmup(self) -> None:
        self.phase = "warming"
        # Snapshot *every* gateway surface before the reset, so the assembly
        # snapshot can name, side by side with the assembled set, exactly the
        # pre-boot registrations the boundary discards. Like the pipeline-only
        # read below, this must not create the objects it is about to see wiped:
        # every surface is read through a non-materializing ``_peek_*`` helper.
        self.application._gateway_declared = _read_gateway_surface_holdings()
        # Read the pre-boot registrations *before* the reset, so the report names
        # exactly the entries the reset discards. The read must not create the
        # pipeline it is about to see wiped.
        discarded_entries = _registered_pipeline_entry_names()
        reset_gateway()
        # Report first, then refuse: a deployment that swallows the exception
        # still saw the diagnostic. The refusal lands on the consequence of the
        # reset for a starting application, not inside ``reset_gateway`` itself
        # (which keeps its silent rebuild semantics for direct callers).
        _warn_pipeline_registrations_reset(discarded_entries)
        _reject_preboot_pipeline_registrations(discarded_entries)
        self.context.refresh()
        self.web_runtime.router = get_router()
        self.web_runtime.dispatcher = get_dispatcher()
        self.web_runtime.pipeline = get_pipeline()
        self.web_runtime.exception_handler = get_exception_handler()
        self.web_runtime.warmup()

    def activate(self) -> Optional[WebRuntime]:
        self.phase = "active"
        return WebRuntime.activate_runtime(self.web_runtime, prepare=False)

    def begin_draining(self) -> None:
        self.phase = "draining"
        self.context.begin_draining()
        self.web_runtime.begin_draining()


def _pipeline_entry_names(pipeline: Any) -> Tuple[str, ...]:
    """Names of a pipeline's entries, without resolving the declarative order.

    The raw entry list is the view that does not depend on the declarative
    ordering resolving, which can fail for declarations that were never
    completed.
    """
    names: List[str] = []
    for entry in pipeline._entries:
        middleware = entry.middleware
        names.append(getattr(middleware, "display_name", None) or type(middleware).__name__)
    return tuple(names)


def _registered_pipeline_entry_names() -> Tuple[str, ...]:
    """Names of the gateway pipeline entries registered so far, without creating it.

    ``get_pipeline()`` is lazy, so calling it here would materialize a pipeline
    as a side effect of taking a reading -- a diagnostic must not change the
    state it reports on, least of all at the boundary where that state is about
    to be thrown away. The raw entry list is read instead; it is also the view
    that does not depend on the declarative ordering resolving, which can fail
    for declarations that were never completed.
    """
    pipeline = _peek_pipeline()
    if pipeline is None:
        return ()
    return _pipeline_entry_names(pipeline)


def _read_gateway_surface_holdings() -> Dict[str, Tuple[str, ...]]:
    """Read every gateway surface as it currently stands, without creating any.

    Each read goes through the module-private ``_peek_*`` helpers rather than the
    lazy ``get_*()`` accessors: the accessors materialize their object as a side
    effect, and an observer must not change what it observes -- least of all the
    boot boundary, which reads the surfaces immediately before it discards them.
    A surface that has not been materialized yet reads as empty.

    Returns one entry per :data:`_GATEWAY_SURFACE_NAMES`, each a tuple of the
    labels that surface holds in its own read-only projection.
    """
    pipeline = _peek_pipeline()
    router = _peek_router()
    dispatcher = _peek_dispatcher()
    exception_handler = _peek_exception_handler()

    pipeline_names: Tuple[str, ...] = ()
    if pipeline is not None:
        pipeline_names = _pipeline_entry_names(pipeline)

    router_names: Tuple[str, ...] = ()
    if router is not None:
        router_names = tuple(
            f"{entry.method} {entry.path}" for entry in router.get_all_routes()
        )

    dispatcher_names: Tuple[str, ...] = ()
    if dispatcher is not None:
        dispatcher_names = tuple(
            descriptor["name"] for descriptor in dispatcher.list_wired_components()
        )

    handler_names: Tuple[str, ...] = ()
    if exception_handler is not None:
        handler_names = tuple(
            descriptor["name"] for descriptor in exception_handler.list_registered_handlers()
        )

    return {
        "pipeline": pipeline_names,
        "router": router_names,
        "dispatcher": dispatcher_names,
        "exception_handler": handler_names,
    }


def _build_surface_holdings(
    declared: Tuple[str, ...],
    assembled: Tuple[str, ...],
) -> _SurfaceHoldings:
    """Pair a pre-boot reading with the current one, deriving ``dropped``."""
    assembled_set = set(assembled)
    dropped = tuple(name for name in declared if name not in assembled_set)
    return _SurfaceHoldings(declared=declared, assembled=assembled, dropped=dropped)


def _warn_pipeline_registrations_reset(names: Tuple[str, ...]) -> None:
    """Report the pipeline entries that the boot-time gateway reset discards.

    This belongs to the boot boundary only. ``reset_gateway()`` keeps its plain
    rebuild-everything semantics and stays silent -- it is a public entry point
    that tests call directly, so a report from inside it would be noise. What is
    announced here is the consequence of that reset for a starting application:
    entries registered imperatively before startup do not survive it.

    With nothing registered there is nothing to say, and no channel is used.
    """
    if not names:
        return
    joined = ", ".join(names)
    problem = (
        "[gateway-pipeline-reset] "
        f"{len(names)} gateway pipeline entry(ies) registered before startup were reset at "
        f"the boot boundary and will not take part in request handling: {joined}."
    )
    guidance = (
        "Declare middleware where the startup assembly reads it -- "
        "configure(middlewares=[...]) or the @middleware decorator. "
        "get_pipeline().add(...) is an imperative pre-boot entry point: its entries are "
        "discarded when the gateway globals are rebuilt."
    )
    _logger.warning(
        "Gateway pipeline entries registered before startup were reset: %d (%s). "
        "Declare middleware with configure(middlewares=[...]) or @middleware instead.",
        len(names),
        joined,
    )
    warn_semantic_once(
        key=f"gateway-pipeline-reset:{joined}",
        rule_key="gateway-pipeline-reset",
        problem=problem,
        guidance=guidance,
        category=PublicAPISemanticWarning,
        stacklevel=3,
    )
    _emit_report_fallback(problem, guidance)


def _reject_preboot_pipeline_registrations(names: Tuple[str, ...]) -> None:
    """Refuse a start when the pre-boot pipeline still held registrations.

    ``reset_gateway()`` rebuilds the gateway globals and discards whatever was
    added imperatively beforehand. Reporting that discard is not enough: the
    declarations the application made and the pipeline it will actually run
    would disagree, and the affected middleware would simply never run. The boot
    boundary therefore refuses to start instead, so the mismatch fails loudly at
    startup rather than turning into missing middleware at request time.

    The report is emitted first (see ``_warn_pipeline_registrations_reset``), so
    even a caller that catches the exception has already seen the diagnostic.
    """
    if not names:
        return
    joined = ", ".join(names)
    problem = (
        f"The pre-boot registrations reported above are rejected at the startup boundary: "
        f"{len(names)} gateway pipeline entry(ies) added before startup ({joined}) would not "
        "take part in request handling."
    )
    guidance = (
        "Declare middleware where the startup assembly reads it -- "
        "configure(middlewares=[...]) or the @middleware decorator. "
        "get_pipeline().add(...) registers on a pipeline that is rebuilt at the boot boundary, "
        "so pre-boot entries are refused instead of being silently discarded."
    )
    _logger.error(
        "Refusing to start: %d gateway pipeline entry(ies) were registered before startup (%s). "
        "Declare middleware with configure(middlewares=[...]) or @middleware instead.",
        len(names),
        joined,
    )
    raise ConfigurationError(
        message=format_semantic_message(
            "preboot-registration-rejected",
            problem=problem,
            guidance=guidance,
        ),
        error_code=_PREBOOT_REGISTRATION_ERROR_CODE,
    )


def _normalize_iterable(value: Optional[Iterable[Any]]) -> Tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return tuple(value)


def _infer_default_packages(module_cls: Type[Any]) -> Tuple[str, ...]:
    python_module = importlib.import_module(module_cls.__module__)
    if hasattr(python_module, "__path__"):
        return (python_module.__name__,)
    if "." in python_module.__name__:
        return (python_module.__name__.rsplit(".", 1)[0],)
    return (python_module.__name__,)


def module(
    cls: Optional[Type[Any]] = None,
    *,
    imports: Optional[Sequence[Type[Any]]] = None,
    packages: Optional[Sequence[str]] = None,
    ownership_overrides: Optional[Dict[str, Type[Any]]] = None,
    warmup: Optional[Sequence[Callable[["Application"], None]]] = None,
    health_checks: Optional[Sequence[Callable[["Application"], None]]] = None,
):
    """Declare a Cullinan application module."""

    def decorator(target_cls: Type[Any]) -> Type[Any]:
        metadata = ModuleMetadata(
            imports=tuple(imports or ()),
            packages=tuple(packages or _infer_default_packages(target_cls)),
            ownership_overrides=dict(ownership_overrides or {}),
            warmup_hooks=tuple(warmup or ()),
            health_checks=tuple(health_checks or ()),
        )
        setattr(target_cls, _MODULE_ATTR, metadata)
        return target_cls

    if cls is not None:
        return decorator(cls)
    return decorator


Module = module


def has_module_metadata(target: Any) -> bool:
    return getattr(target, _MODULE_ATTR, None) is not None


def application(
    fn: Optional[Callable[..., Any]] = None,
    *,
    packages: Optional[Sequence[str]] = None,
    modules: Optional[Sequence[Any]] = None,
):
    """Declare a Cullinan entry method for the default public startup path."""

    def decorator(target_fn: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.isclass(target_fn):
            from cullinan.support.diagnostics import application_decorator_requires_function

            raise TypeError(application_decorator_requires_function(target_fn))
        if not inspect.isfunction(target_fn):
            from cullinan.support.diagnostics import application_decorator_requires_function

            raise TypeError(application_decorator_requires_function(target_fn))

        @functools.wraps(target_fn)
        def entry_method(*args: Any, **kwargs: Any):
            if args or kwargs:
                from cullinan.support.diagnostics import application_entry_method_takes_no_arguments

                raise TypeError(application_entry_method_takes_no_arguments(entry_method))
            return entry_method.run()

        setattr(entry_method, _APPLICATION_PACKAGES_ATTR, tuple(packages or ()))
        setattr(entry_method, _APPLICATION_MODULES_ATTR, tuple(modules or ()))
        setattr(entry_method, _APPLICATION_ATTR, ApplicationMetadata())

        from cullinan.application import public as public_api
        from cullinan.support.config import get_class_config, set_class_config

        existing_config = get_class_config(target_fn)
        if existing_config is not None:
            set_class_config(entry_method, existing_config)
        else:
            refresh_application_entry(entry_method)

        entry_method.run = lambda **kwargs: public_api.run(entry_method, **kwargs)
        entry_method.get_asgi_app = lambda **kwargs: public_api.get_asgi_app(entry_method, **kwargs)
        entry_method.entry_kind = "method"
        return entry_method

    if fn is not None:
        return decorator(fn)
    return decorator


def refresh_application_entry(target: Any) -> None:
    if not has_application_metadata(target):
        return
    from cullinan.support.config import get_class_config

    config_values = get_class_config(target) or {}
    explicit_packages = tuple(getattr(target, _APPLICATION_PACKAGES_ATTR, ()) or ())
    configured_packages = tuple(config_values.get("user_packages") or ())
    explicit_modules = tuple(getattr(target, _APPLICATION_MODULES_ATTR, ()) or ())
    if explicit_modules and not explicit_packages:
        resolved_packages = ()
    else:
        resolved_packages = explicit_packages or configured_packages or _infer_default_packages(target)
    setattr(target, _APPLICATION_ATTR, ApplicationMetadata(packages=tuple(resolved_packages)))
    setattr(
        target,
        _MODULE_ATTR,
        ModuleMetadata(
            imports=explicit_modules,
            packages=tuple(resolved_packages),
        ),
    )
    target.packages = tuple(resolved_packages)


def has_application_metadata(target: Any) -> bool:
    return getattr(target, _APPLICATION_ATTR, None) is not None


def get_application_metadata(application_target: Any) -> ApplicationMetadata:
    metadata = getattr(application_target, _APPLICATION_ATTR, None)
    if metadata is None:
        raise TypeError(
            f"{application_target.__module__}.{application_target.__name__} is not a Cullinan application. "
            "Decorate it with @application."
        )
    return metadata


def get_module_metadata(module_target: Any) -> ModuleMetadata:
    metadata = getattr(module_target, _MODULE_ATTR, None)
    if metadata is None:
        raise TypeError(
            f"{module_target.__module__}.{module_target.__name__} is not a Cullinan module. "
            "Decorate it with @module."
        )
    return metadata


def bind_runtime_request_context(runtime: Optional[WebRuntime]) -> Dict[str, Any]:
    request_context = get_current_context()
    created_context = False
    if request_context is None:
        request_context = create_context()
        created_context = True

    app = getattr(runtime, "application", None) if runtime is not None else None
    entered_request_scope = False
    previous_app = request_context.get_metadata(_APP_CONTEXT_KEY)
    previous_runtime = request_context.get_metadata(_RUNTIME_CONTEXT_KEY)

    if app is not None and app.runtime is not None:
        app.context.enter_request_context()
        entered_request_scope = True
        request_context.set_metadata(_APP_CONTEXT_KEY, app)
        request_context.set_metadata(_RUNTIME_CONTEXT_KEY, runtime)

    return {
        "created_context": created_context,
        "entered_request_scope": entered_request_scope,
        "previous_app": previous_app,
        "previous_runtime": previous_runtime,
    }


def release_runtime_request_context(runtime: Optional[WebRuntime], binding: Optional[Dict[str, Any]]) -> None:
    if binding is None:
        return

    request_context = get_current_context()
    if request_context is not None:
        request_context.set_metadata(_APP_CONTEXT_KEY, binding.get("previous_app"))
        request_context.set_metadata(_RUNTIME_CONTEXT_KEY, binding.get("previous_runtime"))

    app = getattr(runtime, "application", None) if runtime is not None else None
    if binding.get("entered_request_scope") and app is not None and app.runtime is not None:
        app.context.exit_request_context()

    if binding.get("created_context"):
        destroy_context()


class Application:
    """Advanced runtime facade for module discovery and runtime switching.

    Regular business applications should prefer ``@application`` +
    ``@configure(...)`` and call the entry method directly.
    """

    _active_app: Optional["Application"] = None
    _active_lock = threading.RLock()

    def __init__(
        self,
        root_module: Type[Any] | Callable[..., Any],
        *,
        runtime_config: Optional[WebRuntimeConfig] = None,
    ) -> None:
        """Create an advanced runtime facade for one application entry.

        Regular business applications should prefer an ``@application`` entry
        method plus ``@configure(...)`` and call that method directly. Reach for
        ``Application`` only for explicit runtime orchestration, offline assembly
        inspection, or runtime switching.

        Args:
            root_module: The application entry. Positionally it accepts either a
                class declared with ``@module`` or an entry method declared with
                ``@application`` (the decorator attaches module metadata to the
                method, so both are valid entries here). The parameter name is
                kept for backward compatibility.
            runtime_config: Optional explicit ``WebRuntimeConfig``.
        """
        self.root_module = root_module
        self.runtime_config = runtime_config
        self.id = f"app-{uuid.uuid4().hex[:8]}"
        self.graph: Optional[ModuleGraph] = None
        self.runtime: Optional[Runtime] = None
        self.phase = "created"
        self._declaration_diff = _DeclarationDiff()
        # Pre-boot gateway readings, captured by ``Runtime.warmup()`` right before
        # the boot boundary resets the gateway globals. ``None`` means no start
        # has reached the boundary yet.
        self._gateway_declared: Optional[Mapping[str, Tuple[str, ...]]] = None

    @property
    def context(self) -> ApplicationContext:
        if self.runtime is None:
            raise RuntimeError(application_not_installed())
        return self.runtime.context

    @property
    def web_runtime(self) -> WebRuntime:
        if self.runtime is None:
            raise RuntimeError(application_not_installed())
        return self.runtime.web_runtime

    @property
    def is_active(self) -> bool:
        return self.__class__.current() is self

    @classmethod
    def current(cls, default: Optional["Application"] = None) -> Optional["Application"]:
        current = get_current_context()
        if current is not None:
            snapshot = current.get_metadata(_APP_CONTEXT_KEY)
            if snapshot is not None:
                return snapshot
        with cls._active_lock:
            return cls._active_app or default

    @classmethod
    def run(
        cls,
        root_module: Type[Any] | Callable[..., Any],
        *,
        runtime_config: Optional[WebRuntimeConfig] = None,
    ) -> "Application":
        """Build, install and activate an application from one entry (advanced).

        As with :meth:`__init__`, ``root_module`` positionally accepts either a
        ``@module`` class or an ``@application`` entry method. Regular
        applications should prefer an ``@application`` entry method plus
        ``@configure(...)`` and call that method directly; use
        ``Application.run()`` only for explicit runtime orchestration.
        """
        if not in_public_api_context():
            warn_semantic_once(
                key="public-api:application-model-run",
                rule_key="public-api-boundary",
                problem="Calling Application.run() directly uses an advanced runtime assembly entrypoint.",
                guidance=(
                    "Regular applications should prefer an `@application` entry method plus "
                    "`@configure(...)`, then call that entry method directly. "
                    "Call Application.run() directly only when you need explicit runtime orchestration."
                ),
                category=PublicAPISemanticWarning,
                stacklevel=2,
            )
        return cls(root_module, runtime_config=runtime_config).install()

    def discover(self) -> "Application":
        # Install the PEP 563 import hook so application modules are compiled
        # with CO_FUTURE_ANNOTATIONS.  This makes bare constructor-injection
        # annotations safe to use with TYPE_CHECKING imports.
        from cullinan.runtime.annotations_hook import (
            install_annotations_hook,
            uninstall_annotations_hook,
            _resolve_app_root_path,
        )

        root_path = _resolve_app_root_path(self.root_module)
        if root_path is not None:
            install_annotations_hook(root_path)
        try:
            specs = _collect_module_specs(self.root_module)
            python_modules = _discover_python_modules(specs)
        finally:
            if root_path is not None:
                uninstall_annotations_hook()

        registrations, declared_snapshot = _rebuild_pending_registry(python_modules)
        component_owners = _resolve_component_owners(specs, registrations)
        self.graph = ModuleGraph(
            root_module=self.root_module,
            modules=tuple(specs),
            python_modules=tuple(python_modules),
            component_owners=component_owners,
        )
        self._declaration_diff = _build_declaration_diff(declared_snapshot, component_owners)
        self.phase = "discovered"
        return self

    def assemble(self) -> "Application":
        if self.graph is None:
            self.discover()
        context = ApplicationContext(container_id=self.id)
        context._set_declared_not_assembled(self._declaration_diff.dropped)
        # The reconciliation policy is injected here, together with the
        # difference itself, so the report point performs no configuration
        # lookup of its own: it only acts on the values the assembly boundary
        # handed it. A failure this policy can arm therefore belongs to the
        # report point inside refresh(), never to assembly.
        from cullinan.support.config import get_config

        context._set_strict_assembly_policy(
            get_config().strict_assembly, get_config().strict_assembly_excludes
        )
        for hook in self._iter_health_checks():
            context.add_health_check(lambda _ctx, callback=hook: callback(self))
        runtime = Runtime(
            self,
            context=context,
            web_runtime=WebRuntime(config=_clone_runtime_config(self.runtime_config)),
        )
        runtime.web_runtime.application = self
        runtime.web_runtime.add_close_callback(lambda _runtime: self._finalize_drain())
        self.runtime = runtime
        self.phase = "assembled"
        return self

    def validate(self) -> "Application":
        if self.runtime is None:
            self.assemble()
        assert self.runtime is not None
        self.runtime.validate()
        self.phase = "validated"
        return self

    def warmup(self) -> "Application":
        if self.runtime is None:
            self.assemble()
        assert self.runtime is not None
        self.runtime.warmup()
        for hook in self._iter_warmup_hooks():
            hook(self)
        self.phase = "warmed"
        return self

    def build(self) -> "Application":
        if self.graph is None:
            self.discover()
        if self.runtime is None:
            self.assemble()
        self.validate()
        self.warmup()
        return self

    def install(self) -> "Application":
        previous_app: Optional[Application] = None
        previous_context: Optional[ApplicationContext] = None
        previous_runtime: Optional[WebRuntime] = None

        try:
            self.build()
            assert self.runtime is not None
            manager = get_container_manager()
            previous_context = manager.get_active_root()
            previous_runtime = WebRuntime.current()
            with self.__class__._active_lock:
                previous_app = self.__class__._active_app
                manager.bind(self.context)
                self.runtime.activate()
                self.__class__._active_app = self
                self.phase = "active"
        except Exception:
            if previous_context is not None:
                get_container_manager().bind(previous_context)
            if previous_runtime is not None or (self.runtime is not None and WebRuntime.current() is self.runtime.web_runtime):
                WebRuntime.bind_runtime(previous_runtime)
            if self.runtime is not None and self.context.state is not ContainerState.CLOSED:
                self.context.shutdown(timeout=self.web_runtime.config.drain_timeout)
            raise

        if previous_app is not None and previous_app is not self:
            previous_app._begin_draining()
            previous_app._finalize_drain()
        return self

    def reload(self) -> "Application":
        return self.__class__.run(self.root_module, runtime_config=self.runtime_config)

    def uninstall(self) -> None:
        manager = get_container_manager()
        with self.__class__._active_lock:
            if self.__class__._active_app is self:
                self.__class__._active_app = None
            if manager.get_active_root() is self.context:
                manager.bind(None)
            if WebRuntime.current() is self.web_runtime:
                WebRuntime.bind_runtime(None)
        self._begin_draining()
        self._finalize_drain()
        # ``_finalize_drain`` defers (without a retry of its own) while requests
        # are still in flight, which left the application stranded in
        # "draining" with its lifecycle instances un-released. uninstall() is a
        # teardown call, so drive the close to a terminal state here:
        # shutdown() waits on the authoritative request-scope count -- and, when
        # it is called from a live event loop, warns instead of blocking it.
        if self.context.state is not ContainerState.CLOSED:
            self.context.shutdown(timeout=self.web_runtime.config.drain_timeout)
        self.phase = "closed"
        if self.runtime is not None:
            self.runtime.phase = "closed"

    def get_component_owner(self, component: Type[Any]) -> Optional[Type[Any]]:
        if self.graph is None:
            return None
        key = f"{component.__module__}.{component.__name__}"
        return self.graph.component_owners.get(key)

    def get_declaration_diff(self) -> _DeclarationDiff:
        """Return the declared-vs-assembled reconciliation for this application.

        The declaration set is the import-time ``PendingRegistry`` snapshot
        taken just before assembly rebuilds it; the assembled set is
        ``ModuleGraph.component_owners``. ``dropped`` lists the components that
        were declared but never assembled (for example components living in a
        package that is missing from ``user_packages``, or components defined
        outside module top level).

        If the application has not been discovered yet, discovery is triggered
        first so the reconciliation is available. The return value is a
        module-private frozen dataclass and is not part of the public API
        surface.
        """
        if self.graph is None:
            self.discover()
        return self._declaration_diff

    def get_assembly_snapshot(self) -> _AssemblySnapshot:
        """Return what this assembly actually holds, surface by surface.

        One call reports every gateway surface -- ``pipeline`` / ``router`` /
        ``dispatcher`` / ``exception_handler`` -- plus the container, each as a
        ``declared`` / ``assembled`` / ``dropped`` triple. ``assembled`` is what
        the surface holds right now; ``declared`` is what it held *before* the
        boot boundary, captured in ``Runtime.warmup()``; and ``dropped`` is the
        pre-boot registrations the boundary discarded (``declared - assembled``),
        reported side by side with the assembled set so the two can be
        reconciled in one place.

        Every gateway surface is read through the module-private, non-creating
        ``_peek_*`` helpers, so querying never materializes a lazy global -- an
        observer must not change what it observes. The ``container`` sub-surface
        reports the same declared-vs-assembled component reconciliation that
        ``get_declaration_diff()`` exposes.

        This is the single query entry point promised by the registration-surface
        observability rule; the full per-entry detail lives here, while the boot
        boundary only reports a summary. The return value is a module-private
        frozen dataclass and is not part of the public API surface.
        """
        live = _read_gateway_surface_holdings()
        declared = self._gateway_declared if self._gateway_declared is not None else live
        gateway = {
            surface: _build_surface_holdings(
                tuple(declared.get(surface, ())),
                tuple(live.get(surface, ())),
            )
            for surface in _GATEWAY_SURFACE_NAMES
        }
        return _AssemblySnapshot(
            gateway=MappingProxyType(gateway),
            container=_SurfaceHoldings(
                declared=self._declaration_diff.declared,
                assembled=self._declaration_diff.assembled,
                dropped=self._declaration_diff.dropped,
            ),
        )

    def _iter_warmup_hooks(self) -> Iterable[Callable[["Application"], None]]:
        if self.graph is None:
            return ()
        hooks: List[Callable[["Application"], None]] = []
        for spec in self.graph.modules:
            hooks.extend(spec.metadata.warmup_hooks)
        return tuple(hooks)

    def _iter_health_checks(self) -> Iterable[Callable[["Application"], None]]:
        if self.graph is None:
            return ()
        checks: List[Callable[["Application"], None]] = []
        for spec in self.graph.modules:
            checks.extend(spec.metadata.health_checks)
        return tuple(checks)

    def _begin_draining(self) -> None:
        if self.runtime is None:
            return
        self.phase = "draining"
        self.runtime.begin_draining()

    def _finalize_drain(self) -> None:
        if self.runtime is None:
            return
        pending = self.web_runtime.request_count
        scopes = self.context.active_request_count
        if pending > 0 or scopes > 0:
            # This close trigger fires on the transport counter alone, so it can
            # run while request scopes are still active. Defer -- but never
            # silently: a deferral is only safe because a later trigger (or
            # ``uninstall``) re-enters here, and a silent one would strand the
            # application in "draining" with its instances un-released.
            _logger.warning(
                "Deferring drain finalisation: transport_requests=%s request_scopes=%s",
                pending,
                scopes,
            )
            return
        if self.context.state is not ContainerState.CLOSED:
            # The drain bound comes from the runtime configuration rather than a
            # hidden default: ``WebRuntimeConfig.drain_timeout`` (default 30.0,
            # the value ``ApplicationContext.shutdown`` used to hard-code) is now
            # the single timeout source for finalising the drain.
            self.context.shutdown(timeout=self.web_runtime.config.drain_timeout)
        self.phase = "closed"
        self.runtime.phase = "closed"


def _clone_runtime_config(config: Optional[WebRuntimeConfig]) -> WebRuntimeConfig:
    if config is None:
        return WebRuntimeConfig()
    return WebRuntimeConfig(
        warmup_checks=tuple(config.warmup_checks),
        health_checks=tuple(config.health_checks),
        drain_timeout=config.drain_timeout,
        trust_forwarded_headers=config.trust_forwarded_headers,
    )


def _collect_module_specs(root_module: Type[Any]) -> List[ModuleSpec]:
    discovered: Dict[Type[Any], ModuleSpec] = {}
    visiting: List[Type[Any]] = [root_module]

    while visiting:
        module_cls = visiting.pop()
        if module_cls in discovered:
            continue
        metadata = get_module_metadata(module_cls)
        spec = ModuleSpec(
            cls=module_cls,
            metadata=metadata,
            packages=tuple(metadata.packages)
            if metadata.packages != ()
            else (),
        )
        discovered[module_cls] = spec
        visiting.extend(reversed(metadata.imports))

    return list(discovered.values())


_logger = logging.getLogger(__name__)


def _discover_python_modules(specs: Sequence[ModuleSpec]) -> List[str]:
    discovered: List[str] = []
    seen = set()

    for spec in specs:
        for package_name in spec.packages:
            try:
                importlib.import_module(package_name)
            except Exception:
                _logger.warning(
                    "Skipping package %s during discovery — import failed",
                    package_name,
                    exc_info=True,
                )
                continue
            candidates = [package_name, *list_submodules(package_name)]
            for candidate in candidates:
                if candidate in seen:
                    continue
                try:
                    importlib.import_module(candidate)
                except Exception:
                    _logger.warning(
                        "Skipping module %s during discovery — import failed",
                        candidate,
                        exc_info=True,
                    )
                    continue
                seen.add(candidate)
                discovered.append(candidate)

    return discovered


def _component_identity(registration: PendingRegistration) -> str:
    source_module = registration.source_module or registration.cls.__module__
    return f"{source_module}.{registration.cls.__name__}"


def _build_declaration_diff(
    declared: Sequence[PendingRegistration],
    component_owners: Mapping[str, Type[Any]],
) -> _DeclarationDiff:
    declared_names = tuple(sorted({_component_identity(registration) for registration in declared}))
    assembled_names = tuple(sorted(component_owners.keys()))
    assembled_set = set(assembled_names)
    dropped = tuple(name for name in declared_names if name not in assembled_set)
    return _DeclarationDiff(
        declared=declared_names,
        assembled=assembled_names,
        dropped=dropped,
    )


def _rebuild_pending_registry(
    python_modules: Sequence[str],
) -> Tuple[List[PendingRegistration], List[PendingRegistration]]:
    # Snapshot the import-time declaration set *before* reset(). Without this,
    # the records of declarations that fall outside the discovered packages are
    # erased by reset() and the declared-vs-assembled difference can never be
    # reconciled afterwards (see Application.get_declaration_diff()).
    declared_snapshot = list(PendingRegistry.get_instance().get_all())
    PendingRegistry.reset()
    registry = PendingRegistry.get_instance()
    registrations: List[PendingRegistration] = []
    seen = set()

    for module_name in python_modules:
        module = importlib.import_module(module_name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ != module_name:
                continue
            metadata = get_component_registration_metadata(cls)
            if metadata is None:
                continue
            key = (cls, metadata["name"], metadata["component_type"].value)
            if key in seen:
                continue
            registration = PendingRegistration(
                cls=cls,
                name=metadata["name"],
                component_type=metadata["component_type"],
                scope=metadata["scope"],
                url_prefix=metadata["url_prefix"],
                routes=list(metadata["routes"]),
                dependencies=list(metadata["dependencies"]),
                conditions=list(metadata["conditions"]),
                source_module=metadata["source_module"],
                source_file=metadata["source_file"],
                source_line=metadata["source_line"],
            )
            registry.add(registration)
            registrations.append(registration)
            seen.add(key)

    return registrations, declared_snapshot


def _resolve_component_owners(
    specs: Sequence[ModuleSpec],
    registrations: Sequence[PendingRegistration],
) -> Dict[str, Type[Any]]:
    overrides = _collect_ownership_overrides(specs)
    spec_lookup = {spec.cls: spec for spec in specs}
    owners: Dict[str, Type[Any]] = {}

    for registration in registrations:
        source_module = registration.source_module or registration.cls.__module__
        component_path = f"{source_module}.{registration.cls.__name__}"

        override_owner = _match_ownership_override(overrides, source_module, component_path)
        if override_owner is not None:
            if override_owner not in spec_lookup:
                raise RuntimeError(
                    f"ownership_overrides for component {component_path} points to module "
                    f"{override_owner.__module__}.{override_owner.__name__}, but that module was not imported. "
                    "Add the module to imports first so the boundary declaration matches runtime ownership."
                )
            owners[component_path] = override_owner
            continue

        candidates = _matching_specs(specs, source_module)
        if not candidates:
            raise RuntimeError(
                f"Component {component_path} does not belong to any declared module package. "
                "Place it inside a package owned by some @module declaration, or declare the boundary explicitly "
                "with @module(packages=[...]). @module expresses runtime ownership and hot-pluggable boundaries, "
                "not explicit app registration."
            )

        top_prefix = max(prefix_length for _, prefix_length in candidates)
        top_specs = {spec.cls for spec, prefix_length in candidates if prefix_length == top_prefix}
        if len(top_specs) > 1:
            owner_names = ", ".join(
                sorted(f"{owner.__module__}.{owner.__name__}" for owner in top_specs)
            )
            raise RuntimeError(
                f"Component {component_path} matches multiple modules at the same time: {owner_names}. "
                "Use ownership_overrides to declare ownership explicitly and keep module boundaries, reload behavior, "
                "and hot-pluggable runtime semantics stable."
            )

        owners[component_path] = next(iter(top_specs))

    return owners


def _collect_ownership_overrides(specs: Sequence[ModuleSpec]) -> Dict[str, Type[Any]]:
    overrides: Dict[str, Type[Any]] = {}
    for spec in specs:
        for key, owner in spec.metadata.ownership_overrides.items():
            existing = overrides.get(key)
            if existing is not None and existing is not owner:
                raise RuntimeError(
                    f"ownership_overrides key {key} is declared by multiple modules. "
                    "A single boundary can have only one explicit owner."
                )
            overrides[key] = owner
    return overrides


def _match_ownership_override(
    overrides: Dict[str, Type[Any]],
    source_module: str,
    component_path: str,
) -> Optional[Type[Any]]:
    matched_key = None
    for key in overrides:
        if component_path == key or source_module == key or source_module.startswith(f"{key}."):
            if matched_key is None or len(key) > len(matched_key):
                matched_key = key
    if matched_key is None:
        return None
    return overrides[matched_key]


def _matching_specs(
    specs: Sequence[ModuleSpec],
    source_module: str,
) -> List[Tuple[ModuleSpec, int]]:
    matches: Dict[Type[Any], Tuple[ModuleSpec, int]] = {}
    for spec in specs:
        for package_name in spec.packages:
            if source_module == package_name or source_module.startswith(f"{package_name}."):
                previous = matches.get(spec.cls)
                score = len(package_name)
                if previous is None or score > previous[1]:
                    matches[spec.cls] = (spec, score)
    return list(matches.values())


__all__ = [
    "Application",
    "Module",
    "ModuleGraph",
    "ModuleMetadata",
    "ModuleSpec",
    "Runtime",
    "bind_runtime_request_context",
    "get_module_metadata",
    "module",
    "release_runtime_request_context",
]
