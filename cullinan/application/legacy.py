# -*- coding: utf-8 -*-
import importlib
import inspect
import os
import importlib.util
import logging
from dataclasses import dataclass
import sys
import threading
from typing import List, Optional

from dotenv import load_dotenv
from pathlib import Path

# Tornado discovery is kept lazy so importing application-facing modules does not
# eagerly pull a concrete server framework into the semantic layer.
_tornado_available = importlib.util.find_spec("tornado") is not None

from cullinan.runtime.module_scanner import (
    is_pyinstaller_frozen,
    is_nuitka_compiled,
    file_list_func
)
from cullinan.core.semantic_rules import (
    CompatibilitySemanticWarning,
    describe_semantic_rule,
    format_semantic_message,
    warn_semantic_once,
)
from cullinan.support.exceptions import PackageDiscoveryError

# Module-level logger
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModuleReflectionResult:
    module_name: str
    func: str
    imported: bool
    strategy: str
    error: Optional[str] = None


def reflect_module(module_name: str, func: str) -> ModuleReflectionResult:
    """Import a module by dotted name and optionally call a function on it.

    - If `func` is 'nobody' or 'controller' we only import the module (decorators will run at import).
    - Otherwise, if the attribute named `func` exists and is callable, call it.

    Errors during import or call are logged but swallowed to keep scanning robust.
    
    Args:
        module_name: Dotted module name to import (e.g., 'myapp.controllers.user')
        func: Function name to call after import, or 'nobody'/'controller' to skip calling
    """
    if not module_name:
        return ModuleReflectionResult(
            module_name="",
            func=func,
            imported=False,
            strategy="invalid",
            error="empty module name",
        )

    # sanitize package-style paths that may come from file-system discovery
    if module_name.endswith('.py'):
        module_name = module_name[:-3]
    module_name = module_name.strip('.')

    if not module_name:
        return ModuleReflectionResult(
            module_name="",
            func=func,
            imported=False,
            strategy="invalid",
            error="empty module name",
        )

    logger.debug("Reflecting module: %s (func: %s)", module_name, func)

    mod = None
    strategy = "unknown"
    errors: List[str] = []

    def _record_error(stage: str, exc: Exception) -> None:
        errors.append(f"{stage}: {type(exc).__name__}: {exc}")

    # Strategy 0: prefer sys.modules first (modules are often already loaded under Nuitka).
    if module_name in sys.modules:
        mod = sys.modules[module_name]
        strategy = "sys.modules"
        logger.info("[OK] Found in sys.modules: %s", module_name)

        # For controller and service modules, already being loaded means decorators already ran.
        if func in ('nobody', 'controller'):
            logger.debug("[OK] Module already loaded (decorators executed): %s", module_name)
            return ModuleReflectionResult(
                module_name=module_name,
                func=func,
                imported=True,
                strategy=strategy,
            )

        # Continue with the callable if requested.
        if func not in ('nobody', 'controller'):
            try:
                fn = getattr(mod, func, None)
                if callable(fn):
                    fn()
                    logger.debug("[OK] Called function: %s.%s", module_name, func)
            except Exception as e:
                _record_error("call", e)
                logger.debug("[FAIL] Error calling %s.%s: %s", module_name, func, str(e))
        return ModuleReflectionResult(
            module_name=module_name,
            func=func,
            imported=True,
            strategy=strategy,
            error="; ".join(errors) if errors else None,
        )

    # Strategy 1: regular import (works across all environments).
    try:
        mod = importlib.import_module(module_name)
        strategy = "importlib"
        logger.info("[OK] Successfully imported: %s", module_name)

        # For controller and service modules, importing is enough because decorators run on import.
        if func in ('nobody', 'controller'):
            logger.debug("[OK] Module imported (decorators executed): %s", module_name)
            return ModuleReflectionResult(
                module_name=module_name,
                func=func,
                imported=True,
                strategy=strategy,
            )

    except ImportError as e:
        error_msg = str(e)
        _record_error("import", e)
        logger.warning("[FAIL] Import failed for %s: %s", module_name, error_msg)

        # Strategy 2: try relative imports (sometimes needed after Nuitka compilation).
        if is_nuitka_compiled() and '.' in module_name:
            # Try importing from the parent package.
            parts = module_name.rsplit('.', 1)
            if len(parts) == 2:
                parent_pkg, mod_part = parts
                try:
                    parent = importlib.import_module(parent_pkg)
                    if hasattr(parent, mod_part):
                        mod = getattr(parent, mod_part)
                        strategy = "parent-attribute"
                        logger.info("[OK] Imported as attribute: %s from %s", mod_part, parent_pkg)

                        if func in ('nobody', 'controller'):
                            return ModuleReflectionResult(
                                module_name=module_name,
                                func=func,
                                imported=True,
                                strategy=strategy,
                                error="; ".join(errors) if errors else None,
                            )
                    else:
                        # Try using __import__ with fromlist.
                        try:
                            mod = __import__(module_name, fromlist=[mod_part])
                            strategy = "__import__"
                            logger.info("[OK] Imported using __import__: %s", module_name)

                            if func in ('nobody', 'controller'):
                                return ModuleReflectionResult(
                                    module_name=module_name,
                                    func=func,
                                    imported=True,
                                    strategy=strategy,
                                    error="; ".join(errors) if errors else None,
                                )
                        except Exception as e2:
                            _record_error("__import__", e2)
                            logger.debug("[FAIL] __import__ also failed: %s", str(e2))
                except Exception as e3:
                    _record_error("relative-import", e3)
                    logger.debug("[FAIL] Relative import failed: %s", str(e3))

        # Strategy 3: reuse sys.modules (packaging tools may have preloaded the module).
        if module_name in sys.modules:
            mod = sys.modules[module_name]
            strategy = "sys.modules"
            logger.info("[OK] Found in sys.modules: %s", module_name)

            if func in ('nobody', 'controller'):
                return ModuleReflectionResult(
                    module_name=module_name,
                    func=func,
                    imported=True,
                    strategy=strategy,
                    error="; ".join(errors) if errors else None,
                )

        # Strategy 4: import from a file path as the last resort.
        elif is_pyinstaller_frozen() or is_nuitka_compiled():
            # Build likely file paths.
            base_dirs = []

            if is_pyinstaller_frozen():
                meipass = getattr(sys, '_MEIPASS', None)
                if meipass:
                    base_dirs.append(meipass)

            if is_nuitka_compiled():
                exe_dir = os.path.dirname(sys.executable)
                base_dirs.append(exe_dir)

            for base in base_dirs:
                module_path = os.path.join(base, module_name.replace('.', os.sep) + '.py')
                if os.path.exists(module_path):
                    try:
                        spec = importlib.util.spec_from_file_location(module_name, module_path)
                        if spec and spec.loader:
                            mod = importlib.util.module_from_spec(spec)
                            sys.modules[module_name] = mod  # Register the module in sys.modules.
                            spec.loader.exec_module(mod)
                            strategy = "file"
                            logger.info("[OK] Imported from file: %s", module_path)
                            break
                    except Exception as import_ex:
                        _record_error("file-import", import_ex)
                        logger.warning("[FAIL] Failed to import from file %s: %s", module_path, str(import_ex))
    except Exception as e:
        _record_error("unexpected-import", e)
        logger.warning("[FAIL] Unexpected error importing %s: %s", module_name, str(e))
        return ModuleReflectionResult(
            module_name=module_name,
            func=func,
            imported=False,
            strategy=strategy,
            error="; ".join(errors) if errors else str(e),
        )

    if mod is None:
        logger.warning("[FAIL] Could not import module: %s", module_name)
        return ModuleReflectionResult(
            module_name=module_name,
            func=func,
            imported=False,
            strategy=strategy,
            error="; ".join(errors) if errors else "Could not import module",
        )

    # For controller and service modules, importing is enough because decorators run on import.
    if func in ('nobody', 'controller'):
        logger.debug("[OK] Module imported (decorators executed): %s", module_name)
        return ModuleReflectionResult(
            module_name=module_name,
            func=func,
            imported=True,
            strategy=strategy,
            error="; ".join(errors) if errors else None,
        )

    # Call the requested function if it exists.
    try:
        fn = getattr(mod, func, None)
        if callable(fn):
            fn()
            logger.debug("[OK] Called function: %s.%s", module_name, func)
    except Exception as e:
        _record_error("call", e)
        logger.debug("[FAIL] Error calling %s.%s: %s", module_name, func, str(e))
        return ModuleReflectionResult(
            module_name=module_name,
            func=func,
            imported=True,
            strategy=strategy,
            error="; ".join(errors),
        )

    return ModuleReflectionResult(
        module_name=module_name,
        func=func,
        imported=True,
        strategy=strategy,
        error="; ".join(errors) if errors else None,
    )



def scan_controller(modules: list) -> List[ModuleReflectionResult]:
    """Scan and import controller modules to register their handlers.
    
    Args:
        modules: List of dotted module names to scan
    """
    return [reflect_module(mod, 'controller') for mod in modules]



def scan_service(modules: list) -> List[ModuleReflectionResult]:
    """Scan and import service modules to register their services.
    
    Args:
        modules: List of dotted module names to scan
    """
    return [reflect_module(mod, 'nobody') for mod in modules]


def _validate_component_scan_results(
    modules: List[str],
    scan_results: List[ModuleReflectionResult],
) -> None:
    from cullinan.core.decorators import get_component_registration_metadata
    from cullinan.core.pending import PendingRegistry

    import_failures = {}
    for result in scan_results:
        if not result.imported:
            import_failures[result.module_name] = result.error or "unknown import failure"

    pending = PendingRegistry.get_instance()
    registered_components = {
        (
            registration.source_module or registration.cls.__module__,
            registration.name,
            registration.component_type.value,
        )
        for registration in pending.get_all()
    }
    missing_registrations = []

    for module_name in {result.module_name for result in scan_results if result.imported}:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ != module_name:
                continue
            metadata = get_component_registration_metadata(cls)
            if metadata is None:
                continue
            component_key = (
                metadata["source_module"] or cls.__module__,
                metadata["name"],
                metadata["component_type"].value,
            )
            if component_key in registered_components:
                continue
            missing_registrations.append({
                "module": module_name,
                "component": metadata["name"],
                "class": cls.__name__,
                "component_type": metadata["component_type"].value,
            })

    if import_failures or missing_registrations:
        failure_lines = []
        if import_failures:
            failure_lines.append(
                format_semantic_message(
                    "component-import-execution",
                    "The following modules failed to import during component scanning, so decorator registration never ran.",
                    "Fix the import errors first, then run refresh() again. Cullinan auto-assembly depends on decorators running during import instead of explicit app registration.",
                )
            )
            for module_name, error in sorted(import_failures.items()):
                failure_lines.append(f"- {module_name}: {error}")
        if missing_registrations:
            failure_lines.append(
                format_semantic_message(
                    "component-top-level",
                    "The following decorated components expose registration metadata but never entered PendingRegistry.",
                    "Make sure the components are defined at module top level and that PendingRegistry was not frozen or replaced too early. If you need a stronger boundary, express runtime ownership with @module.",
                )
            )
            for item in missing_registrations:
                failure_lines.append(
                    f"- {item['module']}::{item['class']} ({item['component_type']}, registration={item['component']})"
                )
        raise PackageDiscoveryError(
            message=format_semantic_message(
                "component-top-level",
                "Component scan validation failed because some imports never executed or decorated registrations never reached PendingRegistry.",
                "Cullinan only guarantees automatic discovery and assembly for module-top-level components whose decorators ran during import.",
            ),
            details={
                "candidate_module_count": len(modules),
                "failed_module_count": len(import_failures),
                "missing_registration_count": len(missing_registrations),
                "diagnostics": " | ".join(failure_lines),
                "semantic_rules": {
                    "component-import-execution": describe_semantic_rule("component-import-execution"),
                    "component-top-level": describe_semantic_rule("component-top-level"),
                },
            },
        )




def is_started_directly() -> bool:
    """Return True if the process was started directly (a __main__ frame exists).

    We inspect the stack and check whether any frame's module name is '__main__'.
    This is a conservative heuristic: if the framework is imported by another
    application (e.g. tests, embedding, REPL), we won't auto-install console handlers.
    """
    try:
        for frame_info in inspect.stack():
            module = inspect.getmodule(frame_info[0])
            if module is None:
                continue
            if getattr(module, '__name__', '') == '__main__':
                return True
    except Exception:
        pass
    return False


# Thread-safety guard for _ensure_console_logging (legacy)
_legacy_logging_initialized = False
_legacy_logging_lock = threading.Lock()


def _ensure_console_logging():
    """Ensure framework logs appear on console when the application hasn't configured logging.

    Behavior:
    - If the root logger already has handlers, assume application configured logging and do nothing.
    - If the 'cullinan' package logger already has handlers, do nothing.
    - Otherwise add a StreamHandler to stdout on the 'cullinan' logger at INFO level.
    - Honor env var CULLINAN_DISABLE_AUTO_CONSOLE=1 to disable this behavior.

    Thread-safe: uses a module-level lock and flag to prevent duplicate handlers.
    """
    global _legacy_logging_initialized
    if _legacy_logging_initialized:
        return None
    with _legacy_logging_lock:
        if _legacy_logging_initialized:
            return None
        try:
            if os.getenv('CULLINAN_DISABLE_AUTO_CONSOLE', '0') == '1':
                _legacy_logging_initialized = True
                return None
            # Allow forcing console handler via env var (useful in tests/IDE runs)
            force = os.getenv('CULLINAN_FORCE_CONSOLE', '0').lower() in ('1', 'true', 'yes')
            # only auto-enable console logging when the process was started directly
            # unless forced via CULLINAN_FORCE_CONSOLE
            if not force and not is_started_directly():
                _legacy_logging_initialized = True
                return None
            root = logging.getLogger()
            # consider only "real" handlers (not NullHandler)
            root_has_real = any(not isinstance(h, logging.NullHandler) for h in getattr(root, 'handlers', []) if h is not None)
            if root_has_real:
                _legacy_logging_initialized = True
                return None
            pkg_logger = logging.getLogger('cullinan')
            pkg_has_real = any(not isinstance(h, logging.NullHandler) for h in getattr(pkg_logger, 'handlers', []) if h is not None)
            if pkg_has_real:
                _legacy_logging_initialized = True
                return None
            # add a console handler to the package logger
            console_handler = logging.StreamHandler(sys.stdout)
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            console_handler.setFormatter(fmt)
            # allow customizing console level via env var (e.g. DEBUG/INFO)
            lvl_name = os.getenv('CULLINAN_AUTO_CONSOLE_LEVEL', '').strip()
            if lvl_name:
                try:
                    level = int(lvl_name)
                except Exception:
                    level = getattr(logging, lvl_name.upper(), None)
                if isinstance(level, int):
                    console_handler.setLevel(level)
                else:
                    console_handler.setLevel(logging.INFO)
            else:
                console_handler.setLevel(logging.INFO)
            pkg_logger.addHandler(console_handler)
            pkg_logger.setLevel(logging.INFO)
            pkg_logger.propagate = False
            _legacy_logging_initialized = True
            return console_handler
        except Exception:
            # never raise from logging setup
            _legacy_logging_initialized = True
            return None


# ASCII banner used when the framework starts; backslashes are escaped so this
# compiles cleanly and prints exactly as intended.
BANNER = (
    "|||||||||||||||||||||||||||||||||||||||||||||||||\n"
    "|||                                           |||\n"
    "|||    _____      _ _ _                       |||\n"
    "|||   / ____|    | | (_)                      |||\n"
    "|||  | |    _   _| | |_ _ __   __ _ _ __      |||\n"
    "|||  | |   | | | | | | | '_ \\ / _` | '_ \\     |||\n"
    "|||  | |___| |_| | | | | | | | (_| | | | |    |||\n"
    "|||   \\_____\\__,_|_|_|_|_| |_|\\__,_|_| |_|    |||\n"
    "|||                                           |||\n"
    "|||||||||||||||||||||||||||||||||||||||||||||||||\n"
    "\t|||\n"
)


def _register_explicit_classes():
    """Legacy explicit registration mode has been removed."""


def _init_framework():
    """Common initialization logic shared by all engine modes.

    Returns:
        Tuple of (ctx, pending_count) — ApplicationContext and the count of
        processed pending registrations.
    """
    logger.info("loading env...")
    load_dotenv()
    load_dotenv(verbose=True)
    env_path = Path(os.getcwd()) / '.env'
    load_dotenv(dotenv_path=env_path)

    # ========== IoC/DI 2.0: use ApplicationContext as the single entrypoint ==========
    logger.info("└---initializing IoC/DI 2.0 ApplicationContext...")
    from cullinan.core import ApplicationContext, set_application_context
    from cullinan.core.pending import PendingRegistry

    ctx = ApplicationContext()
    set_application_context(ctx)

    _register_explicit_classes()

    logger.info("└---scanning modules...")
    modules = file_list_func()

    if not modules:
        logger.warning("[WARN] No modules found for scanning!")
        logger.warning("[WARN] Consider using cullinan.support.configure(user_packages=['your_app'])")
    else:
        logger.info("└---found %d modules to scan", len(modules))
        service_scan_results = scan_service(modules)
        controller_scan_results = scan_controller(modules)
        _validate_component_scan_results(
            modules,
            [*service_scan_results, *controller_scan_results],
        )

    logger.info("└---refreshing ApplicationContext...")
    ctx.refresh()

    pending_count = PendingRegistry.get_instance().count
    logger.info(f"[OK] ApplicationContext refreshed with {pending_count} components")
    logger.info("└---lifecycle hooks executed by ApplicationContext")

    return ctx, pending_count


def _setup_middleware_pipeline():
    """Wire legacy @middleware-registered middleware into the gateway pipeline."""
    try:
        from cullinan.web.gateway import get_pipeline, AccessLogMiddleware, LegacyMiddlewareBridge
        from cullinan.web.middleware import get_middleware_registry

        pipeline = get_pipeline()

        # Add built-in access log middleware
        pipeline.add(AccessLogMiddleware())

        # Bridge legacy middleware
        mw_registry = get_middleware_registry()
        registered = mw_registry.get_registered_middleware()
        if registered:
            chain = mw_registry.get_middleware_chain()
            pipeline.add(LegacyMiddlewareBridge(chain))
            logger.info("└---bridged %d legacy middleware into gateway pipeline", len(registered))
    except Exception as exc:
        logger.debug("Middleware pipeline setup skipped: %s", exc)


def _setup_openapi():
    """Auto-register OpenAPI spec endpoints if enabled.

    Reads configuration from CullinanConfig and environment variables:
    - CULLINAN_OPENAPI_ENABLED: '1'/'true' to enable (default: enabled)
    - CULLINAN_OPENAPI_TITLE: API title
    - CULLINAN_OPENAPI_VERSION: API version

    Registers /openapi.json and /openapi.yaml GET endpoints.
    """
    try:
        # Check config
        enabled = True
        title = 'Cullinan API'
        version = '1.0.0'
        description = ''

        try:
            from cullinan.support.config import get_config
            cfg = get_config()
            enabled = getattr(cfg, 'openapi_enabled', True)
            title = getattr(cfg, 'openapi_title', title)
            version = getattr(cfg, 'openapi_version', version)
            description = getattr(cfg, 'openapi_description', description)
        except Exception:
            pass

        # Environment variable override
        env_enabled = os.getenv('CULLINAN_OPENAPI_ENABLED', '').strip().lower()
        if env_enabled in ('0', 'false', 'no', 'off'):
            enabled = False
        elif env_enabled in ('1', 'true', 'yes', 'on'):
            enabled = True

        env_title = os.getenv('CULLINAN_OPENAPI_TITLE', '').strip()
        if env_title:
            title = env_title
        env_version = os.getenv('CULLINAN_OPENAPI_VERSION', '').strip()
        if env_version:
            version = env_version

        if not enabled:
            logger.debug("OpenAPI auto-generation disabled")
            return

        from cullinan.web.gateway.openapi import OpenAPIGenerator
        from cullinan.web.gateway import get_router

        generator = OpenAPIGenerator(
            router=get_router(),
            title=title,
            version=version,
            description=description,
        )
        generator.register_spec_routes()
        logger.info("└---OpenAPI endpoints registered: /openapi.json, /openapi.yaml")

    except Exception as exc:
        logger.debug("OpenAPI setup skipped: %s", exc)


def _setup_static_files():
    """Register declarative ``StaticFiles`` mounts on the gateway router."""
    try:
        from cullinan.support.config import get_config
        cfg = get_config()
        raw_specs = getattr(cfg, "static_files", None) or []
        if not raw_specs:
            return

        from cullinan.web.static.spec import coerce_static_files
        from cullinan.web.static.registry import install_static_files
        from cullinan.web.gateway import get_router

        specs = coerce_static_files(raw_specs)
        if not specs:
            return

        project_root = getattr(cfg, "project_root", None)
        installed = install_static_files(
            specs,
            router=get_router(),
            project_root=project_root,
        )
        logger.info(
            "└---static files registered: %d mount(s), %d route(s)",
            len(specs),
            installed,
        )
    except Exception as exc:
        logger.debug("Static files setup skipped: %s", exc)


def _finalize_runtime_setup():
    """Apply the standard post-initialization runtime setup steps."""
    _setup_middleware_pipeline()
    _setup_static_files()
    _setup_openapi()


def _collect_global_headers():
    """Collect global headers from the legacy HeaderRegistry if available."""
    global_headers = []
    try:
        from cullinan.web.controller.core import get_header_registry
        hr = get_header_registry()
        if hr.has_headers():
            global_headers = hr.get_headers()
    except Exception:
        pass
    return global_headers


def _build_tornado_settings():
    """Build the default Tornado settings.

    We deliberately do **not** inject ``static_path`` here. Passing
    ``static_path`` makes ``tornado.web.Application`` auto-register its built-in
    ``StaticFileHandler`` at ``static_url_prefix`` (default ``/static/``). That
    handler is matched before Cullinan's catch-all ``.*`` gateway handler, so it
    silently shadows any router-based :class:`~cullinan.web.StaticFiles` mount on
    the ``/static`` prefix — requests hit Tornado's native handler (pointing at
    ``cwd/static``) and return a Tornado 404 instead of reaching the dispatcher.

    Static files are an engine-neutral, router-registered capability per
    ADR-001 (declarative ``StaticFiles`` -> ``Router`` -> ``Dispatcher``), so the
    Tornado-native static handler must stay disabled to keep behaviour identical
    across the Tornado and ASGI backends. ``template_path`` registers no handler
    and is left in place for Tornado templating in custom handlers.
    """
    return dict(
        template_path=os.path.join(os.getcwd(), 'templates'),
    )


def _build_transport_settings():
    return _build_tornado_settings()


def run(handlers=None, engine=None):
    """Start the compatibility scanning application entrypoint.

    Args:
        handlers: Extra (url, handler_class) pairs for Tornado mode.
        engine: Server engine — ``'auto'`` (default), ``'tornado'``, or ``'asgi'``.
                Can also be set via env-var ``CULLINAN_ENGINE`` or
                ``CullinanConfig.server_engine``.
    """
    warn_semantic_once(
        key="public-api:legacy-application-run",
        rule_key="compatibility-api",
        problem="cullinan.application.run() is a compatibility scanning entrypoint.",
        guidance=(
            "Regular applications should declare an `@application` entry method, attach "
            "`@configure(...)`, and call that entry method directly. Use "
            "cullinan.application.run() only when maintaining older scan-based projects."
        ),
        category=CompatibilitySemanticWarning,
        stacklevel=2,
    )
    if handlers is None:
        handlers = []

    installed_handler = _ensure_console_logging()
    if installed_handler is not None:
        old_fmt = None
        try:
            old_fmt = getattr(installed_handler, 'formatter', None)
            installed_handler.setFormatter(logging.Formatter('%(message)s'))
            logger.info(BANNER)
        finally:
            try:
                installed_handler.setFormatter(old_fmt)
            except Exception:
                pass
    else:
        logger.info(BANNER)

    # Determine engine
    configured_asgi_server = 'uvicorn'
    if engine is None:
        engine = os.getenv('CULLINAN_ENGINE', '').strip().lower() or None
    if engine is None:
        try:
            from cullinan.support.config import get_config
            config = get_config()
            engine = getattr(config, 'server_engine', 'auto')
            configured_asgi_server = getattr(config, 'asgi_server', 'uvicorn')
        except Exception:
            engine = 'auto'

    from cullinan.transport.adapter.runtime_selection import resolve_runtime_engine
    engine = resolve_runtime_engine(engine, asgi_server=configured_asgi_server)

    ctx, pending_count = _init_framework()
    _finalize_runtime_setup()

    port = int(os.getenv("SERVER_PORT", 4080))
    host = os.getenv("SERVER_HOST", "0.0.0.0")

    if engine == 'asgi':
        _run_asgi(host, port)
    else:
        _run_tornado(host, port, handlers)


def _run_tornado(host: str, port: int, extra_handlers: list):
    """Start the server using the Tornado adapter (single-handler gateway mode)."""
    if not _tornado_available:
        raise ImportError(
            "Tornado is required for engine='tornado'. Install it with: pip install tornado"
        )

    from cullinan.web.gateway import get_dispatcher, get_router
    from cullinan.transport.adapter import TornadoAdapter

    # Collect global headers from legacy HeaderRegistry
    global_headers = _collect_global_headers()
    settings = _build_tornado_settings()

    dispatcher = get_dispatcher()
    router = get_router()

    logger.info("└---gateway router: %d routes registered", router.route_count())
    logger.info("└---starting Tornado (single-handler gateway mode)")

    adapter = TornadoAdapter(
        dispatcher=dispatcher,
        settings=settings,
        global_headers=global_headers,
        extra_handlers=extra_handlers,
    )

    logger.info("server is starting")
    logger.info("port is %s", str(port))

    adapter.run(host=host, port=port)


def _run_asgi(host: str, port: int):
    """Start the server using the ASGI adapter."""
    from cullinan.web.gateway import get_dispatcher
    from cullinan.transport.adapter import ASGIAdapter

    global_headers = _collect_global_headers()

    dispatcher = get_dispatcher()

    logger.info("└---starting ASGI server")

    adapter = ASGIAdapter(
        dispatcher=dispatcher,
        global_headers=global_headers,
    )

    adapter.run(host=host, port=port)


def get_asgi_app():
    """Create and return an ASGI application callable via the compatibility entrypoint.

    This function performs full framework initialization and returns an ASGI 3.0
    app that can be served by uvicorn, hypercorn, or any ASGI server::

        # myapp.py
        from cullinan.application import get_asgi_app
        app = get_asgi_app()

        # Then: uvicorn myapp:app
    """
    warn_semantic_once(
        key="public-api:legacy-application-get-asgi-app",
        rule_key="compatibility-api",
        problem="cullinan.application.get_asgi_app() is a compatibility scanning entrypoint.",
        guidance=(
            "Regular applications should declare an `@application` entry method and use "
            "`entry.get_asgi_app()` when they need an ASGI callable. Use "
            "cullinan.application.get_asgi_app() only when maintaining older scan-based deployments."
        ),
        category=CompatibilitySemanticWarning,
        stacklevel=2,
    )
    installed_handler = _ensure_console_logging()
    if installed_handler is not None:
        old_fmt = getattr(installed_handler, 'formatter', None)
        try:
            installed_handler.setFormatter(logging.Formatter('%(message)s'))
            logger.info(BANNER)
        finally:
            try:
                installed_handler.setFormatter(old_fmt)
            except Exception:
                pass
    else:
        logger.info(BANNER)

    _init_framework()
    _finalize_runtime_setup()

    from cullinan.web.gateway import get_dispatcher
    from cullinan.transport.adapter import ASGIAdapter

    global_headers = _collect_global_headers()

    adapter = ASGIAdapter(
        dispatcher=get_dispatcher(),
        global_headers=global_headers,
    )
    return adapter.create_app()


async def _run_shutdown_sequence(server, loop, timeout_seconds: int):
    """Wait for controller.active_request_count to drop to zero (or until timeout),
    then stop the server and close any remaining connections.

    This function is used by tests and by graceful shutdown logic to allow
    inflight requests to finish before the server is stopped.
    """
    try:
        import asyncio as _asyncio
        import cullinan.web.controller as _ctrl

        start = getattr(loop, 'time', _asyncio.get_event_loop().time)()
        deadline = start + (timeout_seconds or 0)

        # poll until active_request_count reaches 0 or timeout
        while getattr(_ctrl, 'active_request_count', 0) > 0:
            now = getattr(loop, 'time', _asyncio.get_event_loop().time)()
            if timeout_seconds and now >= deadline:
                break
            await _asyncio.sleep(0.1)

        # attempt to stop server and close connections
        try:
            if hasattr(server, 'stop') and callable(server.stop):
                server.stop()
        except Exception:
            pass
        try:
            if hasattr(server, 'close_all_connections') and callable(server.close_all_connections):
                server.close_all_connections()
        except Exception:
            pass
    except Exception:
        # be robust in tests or exotic environments
        try:
            if hasattr(server, 'stop') and callable(server.stop):
                server.stop()
        except Exception:
            pass
    return None
