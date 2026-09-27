# -*- coding: utf-8 -*-
"""Cullinan framework configuration."""

from contextlib import contextmanager
import os
import sys
from typing import Any, Dict, Iterator, List, Optional


_CLASS_CONFIG_ATTR = "__cullinan_config__"

class CullinanConfig:
    """Global configuration container for Cullinan."""

    def __init__(self):
        # User package directories, relative to the project root or absolute.
        self.user_packages: List[str] = []

        # Project root, either detected automatically or set explicitly.
        self.project_root: Optional[str] = None

        # Legacy root module field retained only for advanced compatibility internals.
        self.root_module: Optional[Any] = None

        # Whether verbose logging is enabled.
        self.verbose: bool = False

        # Whether automatic scanning is enabled.
        self.auto_scan: bool = True

        # Packages excluded from scanning.
        self.exclude_packages: List[str] = [
            # Testing
            'test', 'tests', '__pycache__', '.pytest_cache', '.tox',
            # Virtual environments
            'venv', 'env', '.venv', '.env', 'virtualenv',
            # Version control
            '.git', '.svn', '.hg',
            # IDEs
            '.vscode', '.idea', '.vs',
            # Build/Distribution
            'dist', 'build', 'eggs', '*.egg-info', 'htmlcov',
            # Documentation
            'docs', 'doc', 'site',
            # Node.js (for full-stack projects)
            'node_modules',
            # Python caches
            '__pypackages__', '.mypy_cache', '.ruff_cache',
        ]

        # Startup error policy:
        # 'strict': fail fast when a service cannot initialize
        # 'warn': log a warning and continue in degraded mode
        # 'ignore': ignore startup failures (debugging only)
        self.startup_error_policy: str = 'strict'

        # RequestContext feature flags (v0.81+).
        self.context_features = {
            # Whether request IDs are generated automatically.
            'auto_request_id': True,

            # Whether request timing is enabled.
            'timing': True,

            # Whether metadata storage is enabled.
            'metadata': True,

            # Whether cleanup callbacks are enabled.
            'cleanup_callbacks': True,

            # Whether RequestContext debug logging is enabled.
            'debug_logging': False,

            # Request ID format: 'uuid' (default), 'sequential', or 'custom'.
            'request_id_format': 'uuid',

            # Custom request ID generator used when request_id_format='custom'.
            'custom_request_id_generator': None,
        }

        # ====================================================================
        # v0.93: Server Engine Configuration
        # ====================================================================

        # Server engine: 'auto' (default), 'tornado', 'asgi'
        # Can also be set via env var CULLINAN_ENGINE
        self.server_engine: str = 'auto'

        # Default bind address for the top-level run() helper
        self.server_host: str = '0.0.0.0'
        self.server_port: int = 4080

        # ASGI server: 'uvicorn' (default), 'hypercorn'
        self.asgi_server: str = 'uvicorn'

        # Whether to enable the gateway middleware pipeline
        self.enable_middleware_pipeline: bool = True

        # Router configuration
        self.route_trailing_slash: bool = False
        self.route_case_sensitive: bool = True

        # Debug mode (enables stack traces in error responses)
        self.debug: bool = False

        # Explicit module list for packaged environments (Nuitka, PyInstaller, etc.).
        # When compiling with --standalone or --onefile, automatic module discovery
        # is limited. Populate this list with fully-qualified module names that
        # should be scanned, e.g.: ['myapp.services', 'myapp.controllers']
        self.explicit_modules: Optional[List[str]] = None

        # Declarative static-files / SPA mounts. Each entry may be a
        # ``cullinan.web.StaticFiles`` instance, a ``dict`` of kwargs, or a
        # ``(url, directory)`` tuple. Mounts are registered on the gateway
        # router at startup and served identically under Tornado and ASGI.
        self.static_files: List[Any] = []

        # Declarative gateway middleware. Each entry is either a
        # ``cullinan.web.gateway.GatewayMiddleware`` instance, or a
        # ``(instance, options)`` tuple. ``options`` accepts ``before`` /
        # ``after`` anchors and/or a ``priority`` global key (lower runs on a
        # more outer layer, default 100). Entries are consumed at the framework
        # assembly point (same place the built-in middleware are wired), so their
        # order never depends on registration timing.
        self.middlewares: List[Any] = []

        # The built-in gateway middleware layer. ``None`` (the default) installs
        # the framework default (the access-log middleware). Pass an empty list
        # to switch the built-in layer off, or a list of
        # ``GatewayMiddleware`` instances / classes / ``(instance, options)``
        # tuples to replace it. The built-in layer shares the declarative
        # ordering of ``middlewares``.
        self.builtin_middleware: Optional[List[Any]] = None

        # OpenAPI auto-generation
        # Set to True to auto-register /openapi.json and /openapi.yaml endpoints
        # Can also be set via env var CULLINAN_OPENAPI_ENABLED=1
        self.openapi_enabled: bool = True

        # OpenAPI metadata
        self.openapi_title: str = 'Cullinan API'
        self.openapi_version: str = '1.0.0'
        self.openapi_description: str = ''

        # ====================================================================
        # END v0.93
        # ====================================================================

    def add_user_package(self, package: str):
        """Add a user package to the scan list."""
        if package not in self.user_packages:
            self.user_packages.append(package)

    def set_project_root(self, root: str):
        """Set the project root."""
        self.project_root = os.path.abspath(root)

    def set_verbose(self, verbose: bool):
        """Enable or disable verbose logging."""
        self.verbose = verbose

    def _to_decorator_dict(self) -> Dict[str, Any]:
        """Return the config fields that may be attached to an entry method."""
        data = self.to_dict()
        data.pop('root_module', None)
        return data

    def __call__(self, target):
        """Allow configure(...) to act as a decorator."""
        set_class_config(target, self._to_decorator_dict())
        return target

    def from_dict(self, config: dict):
        """Load configuration from a dictionary."""
        if 'user_packages' in config:
            self.user_packages = config['user_packages']
        if 'project_root' in config:
            self.project_root = config['project_root']
        if 'root_module' in config:
            self.root_module = config['root_module']
        if 'verbose' in config:
            self.verbose = config['verbose']
        if 'auto_scan' in config:
            self.auto_scan = config['auto_scan']
        if 'exclude_packages' in config:
            self.exclude_packages = config['exclude_packages']
        if 'startup_error_policy' in config:
            self.startup_error_policy = config['startup_error_policy']
        if 'server_engine' in config:
            self.server_engine = config['server_engine']
        if 'asgi_server' in config:
            self.asgi_server = config['asgi_server']
        if 'server_host' in config:
            self.server_host = config['server_host']
        if 'server_port' in config:
            self.server_port = config['server_port']
        if 'explicit_modules' in config:
            self.explicit_modules = config['explicit_modules']
        if 'static_files' in config:
            value = config['static_files']
            self.static_files = list(value) if value else []
        if 'middlewares' in config:
            value = config['middlewares']
            self.middlewares = list(value) if value else []
        if 'builtin_middleware' in config:
            value = config['builtin_middleware']
            # ``None`` means "use the framework default"; an empty list means
            # "install no built-in middleware", so the two must not be conflated.
            self.builtin_middleware = list(value) if value is not None else None
        return self

    def to_dict(self) -> dict:
        """Export the configuration as a dictionary."""
        return {
            'user_packages': self.user_packages,
            'project_root': self.project_root,
            'root_module': self.root_module,
            'verbose': self.verbose,
            'auto_scan': self.auto_scan,
            'exclude_packages': self.exclude_packages,
            'startup_error_policy': self.startup_error_policy,
            'server_engine': self.server_engine,
            'asgi_server': self.asgi_server,
            'server_host': self.server_host,
            'server_port': self.server_port,
            'explicit_modules': self.explicit_modules,
            'static_files': list(self.static_files),
            'middlewares': list(self.middlewares),
            'builtin_middleware': (
                None if self.builtin_middleware is None else list(self.builtin_middleware)
            ),
        }


# Global configuration instance.
_config = CullinanConfig()


def get_config() -> CullinanConfig:
    """Return the global configuration instance."""
    return _config


def set_class_config(target: Any, config_values: Dict[str, Any]) -> None:
    setattr(target, _CLASS_CONFIG_ATTR, dict(config_values))
    try:
        from cullinan.application.model import refresh_application_entry

        refresh_application_entry(target)
    except Exception:
        pass


def get_class_config(target: Any) -> Optional[Dict[str, Any]]:
    config_values = getattr(target, _CLASS_CONFIG_ATTR, None)
    if config_values is None:
        return None
    return dict(config_values)


@contextmanager
def push_config_overrides(overrides: Optional[Dict[str, Any]]) -> Iterator[CullinanConfig]:
    """Temporarily apply entry-method config overrides to the global config."""
    if not overrides:
        yield _config
        return

    original = _config.to_dict()
    merged = dict(original)
    for key, value in overrides.items():
        if value is not None:
            merged[key] = value

    _config.from_dict(merged)
    try:
        yield _config
    finally:
        _config.from_dict(original)


def configure(
    root_module: Optional[Any] = None,
    user_packages: Optional[List[str]] = None,
    project_root: Optional[str] = None,
    verbose: bool = False,
    auto_scan: bool = True,
    exclude_packages: Optional[List[str]] = None,
    startup_error_policy: str = 'strict',
    server_engine: Optional[str] = None,
    asgi_server: Optional[str] = None,
    server_host: Optional[str] = None,
    server_port: Optional[int] = None,
    explicit_modules: Optional[List[str]] = None,
    static_files: Optional[List[Any]] = None,
    *,
    middlewares: Optional[List[Any]] = None,
    builtin_middleware: Optional[List[Any]] = None,
):
    """Configure the Cullinan framework.

    Args:
        root_module: Legacy root-module entrypoint. This default startup path has been removed.
        user_packages: User package list, for example ``['myapp', 'myapp.controllers']``.
        project_root: Project root directory. If omitted, it is inferred automatically.
        verbose: Whether to enable verbose logging.
        auto_scan: Whether to auto-scan packages. When ``False``, only the given
            user packages are imported.
        exclude_packages: Package names excluded from scanning.
        startup_error_policy: Startup error policy.
            - ``'strict'``: stop immediately when a service fails (default)
            - ``'warn'``: log a warning and continue in degraded mode
            - ``'ignore'``: ignore failures (not recommended outside debugging)
        server_engine: Backend used by the top-level ``run()`` helper:
            ``'auto'``, ``'tornado'``, or ``'asgi'``.
        asgi_server: Underlying ASGI server such as ``uvicorn`` or ``hypercorn``.
        server_host: Default bind host for the top-level ``run()`` helper.
        server_port: Default bind port for the top-level ``run()`` helper.
        static_files: Optional list of ``cullinan.web.StaticFiles`` mounts
            (also accepts dicts or ``(url, directory)`` tuples).
        middlewares: Optional list of gateway middleware to install on the
            onion pipeline. Each entry is either a
            ``cullinan.web.gateway.GatewayMiddleware`` instance, or a
            ``(instance, options)`` tuple. ``options`` accepts ``before`` /
            ``after`` anchors and/or a ``priority`` global key (a lower priority
            runs on a more outer layer; the default is 100). Declared middleware
            is assembled at the framework startup point, so the pipeline order
            follows the declaration rather than registration timing.
        builtin_middleware: Optional control for the **built-in** gateway
            middleware layer (the access-log middleware). ``None`` (the default)
            installs the framework default; an empty list switches the built-in
            layer off; a list of ``GatewayMiddleware`` instances / classes /
            ``(instance, options)`` tuples replaces it. The built-in layer is
            assembled at the same startup point and shares the declarative
            ordering of ``middlewares``.

    Example:
        >>> from cullinan import configure
        >>> @configure(user_packages=['your_app'], verbose=True)
        ... @application
        ... def main(): ...

    Example (declaring middleware)::

        from cullinan import configure, application

        @configure(user_packages=['your_app'], middlewares=[SecurityGate()])
        @application
        def main(): ...
    """
    global _config

    if root_module is not None:
        from cullinan.support.diagnostics import legacy_root_module_entry_removed

        raise ValueError(legacy_root_module_entry_removed())

    if user_packages is not None:
        _config.user_packages = user_packages

        # Infer the project root and add it to sys.path when needed.
        if project_root is None:
            project_root = _auto_detect_project_root(user_packages)

        if project_root and project_root not in sys.path:
            sys.path.insert(0, project_root)
            if verbose:
                print(f"Auto-added project root to sys.path: {project_root}")

    if project_root is not None:
        _config.set_project_root(project_root)

    _config.verbose = verbose
    _config.auto_scan = auto_scan

    if exclude_packages is not None:
        _config.exclude_packages = exclude_packages

    # Validate the startup error policy.
    valid_policies = ['strict', 'warn', 'ignore']
    if startup_error_policy not in valid_policies:
        raise ValueError(
            f"Invalid startup_error_policy: {startup_error_policy}. "
            f"Must be one of: {', '.join(valid_policies)}"
        )
    _config.startup_error_policy = startup_error_policy
    if server_engine is not None:
        _config.server_engine = server_engine
    if asgi_server is not None:
        _config.asgi_server = asgi_server
    if server_host is not None:
        _config.server_host = server_host
    if server_port is not None:
        _config.server_port = int(server_port)

    if explicit_modules is not None:
        _config.explicit_modules = explicit_modules

    if static_files is not None:
        from cullinan.web.static.spec import coerce_static_files

        _config.static_files = list(coerce_static_files(static_files))

    if middlewares is not None:
        _config.middlewares = list(middlewares)

    if builtin_middleware is not None:
        _config.builtin_middleware = list(builtin_middleware)

    return _config


def _auto_detect_project_root(user_packages: List[str]) -> Optional[str]:
    """Auto-detect the project root directory.

    Uses configured user package names to walk upward and find the project root.
    Example: ``user_packages=['club.fnep']`` looks for a directory containing
    ``club/fnep``. Works across development, Nuitka, and PyInstaller environments.
    """
    import inspect

    # In frozen/packaged environments, use path_utils for reliable path detection
    try:
        from cullinan.support.path_utils import get_base_path, is_frozen

        if is_frozen():
            # In frozen mode, return base path directly
            return str(get_base_path())
    except ImportError:
        pass  # Fallback to legacy inspection method
    except Exception:
        pass  # Handle any other errors gracefully

    # Get the file path of the configure() caller.
    frame = inspect.currentframe()
    if frame is None:
        return None

    try:
        # Walk up two stack frames: configure() -> caller.
        caller_frame = frame.f_back
        if caller_frame and caller_frame.f_back:
            caller_frame = caller_frame.f_back

        if caller_frame is None:
            return None

        caller_file = caller_frame.f_globals.get('__file__')
        if not caller_file:
            return None

        current_dir = os.path.dirname(os.path.abspath(caller_file))

        # If user_packages contain dotted package names, try to infer the root.
        for package in user_packages:
            if '.' in package:
                # Example: 'club.fnep' -> look for a parent directory containing 'club'.
                parts = package.split('.')
                top_package = parts[0]

                # Search upward from the current directory.
                search_dir = current_dir
                for _ in range(5):  # Search up to five directory levels.
                    # Check whether the top-level package directory exists here.
                    package_path = os.path.join(search_dir, top_package)
                    if os.path.isdir(package_path):
                        # Found it.
                        return search_dir

                    parent = os.path.dirname(search_dir)
                    if parent == search_dir:  # Reached the filesystem root.
                        break
                    search_dir = parent

        # If nothing was inferred, fall back to the caller file's grandparent.
        # This works for layouts such as project/app/main.py.
        return os.path.dirname(os.path.dirname(current_dir))

    finally:
        del frame
