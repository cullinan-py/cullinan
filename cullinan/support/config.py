# -*- coding: utf-8 -*-
"""Cullinan framework configuration."""

from contextlib import contextmanager
import difflib
import logging
import os
import sys
from typing import Any, Dict, Iterator, List, Optional


logger = logging.getLogger(__name__)


_CLASS_CONFIG_ATTR = "__cullinan_config__"

# The logger level that was in place before ``verbose=True`` raised it, so that
# ``verbose=False`` can put it back. One slot is enough: the framework logger is
# process-global, and the last enable is the one whose level matters.
_VERBOSE_RESTORE_LEVEL: List[Optional[int]] = [None]

#: Defaults for :attr:`CullinanConfig.context_features`.
#:
#: Kept at module level rather than inline in ``__init__`` so that
#: ``from_dict`` can refill the keys a caller left out. Without that, a file
#: that names one flag would replace the whole mapping and every reader of
#: ``features['timing']`` would raise ``KeyError`` -- a failure nobody would
#: connect to the line they added.
_DEFAULT_CONTEXT_FEATURES: Dict[str, Any] = {
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

#: Words accepted as a truth value when a configuration value arrives as text.
#: JSON, TOML and YAML all hand back real booleans; this exists for the hand
#: edited file where someone writes ``"openapi_enabled": "false"``. Treating
#: that string as "true" (``bool("false")`` is ``True``) would reproduce the
#: very failure this module is being fixed for: a switch that is set, accepted
#: and ignored.
_TRUE_WORDS = frozenset({'1', 'true', 'yes', 'on'})
_FALSE_WORDS = frozenset({'0', 'false', 'no', 'off', ''})

#: ``(source, key)`` pairs already reported, so a configuration applied from
#: several entry points in one start-up logs each unknown key once. A reader who
#: sees the same warning three times stops reading it.
_REPORTED_UNKNOWN_KEYS: set = set()


def as_flag(key: str, value: Any) -> bool:
    """Read a configuration boolean, refusing a value it cannot interpret.

    ``bool()`` is not a parser: it maps every non-empty string to ``True``, so
    ``"false"`` becomes ``True`` and the switch silently does nothing. A value
    outside the vocabulary raises instead, naming the key, because a typo the
    framework guesses at is worse than one it reports.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        word = value.strip().lower()
        if word in _TRUE_WORDS:
            return True
        if word in _FALSE_WORDS:
            return False
    raise ValueError(
        f"configuration key '{key}' expects true/false, got {value!r}; "
        f"accepted: true/false (JSON, TOML, YAML), 1/0, yes/no, on/off"
    )


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
        self.context_features = dict(_DEFAULT_CONTEXT_FEATURES)

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

        # Largest request body the framework will read, in bytes. ``None``
        # (the default) keeps the historical behaviour of reading whatever the
        # client sends; a number turns an oversized upload into 413 before the
        # body reaches a handler.
        self.max_request_body_bytes: Optional[int] = None

        # How long a graceful shutdown may wait for in-flight requests before
        # cutting them. ``None`` means "leave the runtime default alone" (30s);
        # setting it here puts the knob on the same surface as the port and the
        # engine, instead of requiring the advanced Application entry.
        self.drain_timeout: Optional[float] = None

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

        # Declared-but-not-assembled policy.
        #
        # ``False`` (the default) keeps the always-on report: the difference
        # between the components declared at import time and the components the
        # assembly pass actually picked up is announced through the semantic
        # warning channel and startup continues.
        #
        # ``True`` requires that difference to be empty. The report is still
        # emitted -- the warning and the failure are not alternatives -- and
        # startup then fails with a ``ConfigurationError``.
        #
        # This is *not* ``startup_error_policy``: that one decides what happens
        # when a service cannot be initialised, while this one decides what
        # happens when a declared component was never assembled. The two names
        # resemble each other; the situations do not.
        self.strict_assembly: bool = False

        # Components that are intentionally left unassembled, written in the
        # same ``package.module.Component`` form the declaration report uses
        # (``Application.get_declaration_diff()``). A listed component is still
        # reported as declared-but-not-assembled; it simply no longer makes
        # ``strict_assembly`` fail, so intent is recorded instead of suppressed.
        # ``None`` (the default) means "no intentional exclusions"; an empty
        # list means the same thing and is accepted for symmetry.
        self.strict_assembly_excludes: Optional[List[str]] = None

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

    def from_dict(self, config: dict, *, source: Optional[str] = None):
        """Load configuration from a dictionary.

        Every declared field is accepted here -- :meth:`field_names` derives the
        accepted set from the instance itself, so a field added to ``__init__``
        is reachable without a second edit and a field that is *not* accepted is
        reported instead of dropped.

        Args:
            config: Key/value pairs to apply.
            source: Where the mapping came from, used in the report for a key
                this class does not accept (a file name, for example). Without
                it the report can only name the key, and the reader has to guess
                which of several sources produced it.

        Returns:
            CullinanConfig: ``self``, so callers can chain.
        """
        self._report_unknown_keys(config, source)

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
        if 'max_request_body_bytes' in config:
            value = config['max_request_body_bytes']
            self.max_request_body_bytes = int(value) if value is not None else None

        if 'drain_timeout' in config:
            value = config['drain_timeout']
            self.drain_timeout = float(value) if value is not None else None

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
        if 'strict_assembly' in config:
            self.strict_assembly = bool(config['strict_assembly'])
        if 'strict_assembly_excludes' in config:
            value = config['strict_assembly_excludes']
            # ``None`` and ``[]`` both mean "no intentional exclusions"; keep
            # whichever shape was supplied so ``to_dict``/``from_dict`` round
            # trips without silently rewriting the value.
            self.strict_assembly_excludes = list(value) if value is not None else None

        # -- The nine fields that had no branch until 0.96a11 ----------------
        #
        # They were declared, commented and readable from ``get_config()``, but
        # no entry point could set them: not ``configure()``, not the file. A
        # key written for one of them was accepted by the loader and dropped
        # here, in silence. ``openapi_enabled: false`` in a project file is the
        # case that was reported, and it is the worst shape of this defect --
        # the switch looks obeyed.
        if 'context_features' in config:
            value = config['context_features']
            # Merge over the defaults rather than replace: a file that names one
            # flag must not delete the other six, or every later reader of
            # ``features['timing']`` raises ``KeyError`` for a reason that points
            # nowhere near the line that was added.
            merged_features = dict(_DEFAULT_CONTEXT_FEATURES)
            if value:
                merged_features.update(dict(value))
            self.context_features = merged_features
        if 'enable_middleware_pipeline' in config:
            self.enable_middleware_pipeline = as_flag(
                'enable_middleware_pipeline', config['enable_middleware_pipeline']
            )
        if 'route_trailing_slash' in config:
            self.route_trailing_slash = as_flag(
                'route_trailing_slash', config['route_trailing_slash']
            )
        if 'route_case_sensitive' in config:
            self.route_case_sensitive = as_flag(
                'route_case_sensitive', config['route_case_sensitive']
            )
        if 'debug' in config:
            self.debug = as_flag('debug', config['debug'])
        if 'openapi_enabled' in config:
            self.openapi_enabled = as_flag('openapi_enabled', config['openapi_enabled'])
        if 'openapi_title' in config:
            value = config['openapi_title']
            self.openapi_title = 'Cullinan API' if value is None else str(value)
        if 'openapi_version' in config:
            value = config['openapi_version']
            self.openapi_version = '1.0.0' if value is None else str(value)
        if 'openapi_description' in config:
            value = config['openapi_description']
            self.openapi_description = '' if value is None else str(value)
        return self

    @classmethod
    def field_names(cls) -> frozenset:
        """Every key :meth:`from_dict` accepts, derived from the class itself.

        Derived rather than listed: a second list is a second truth, and the two
        drift the moment someone adds a field in a hurry. ``__init__`` is the
        single place a field is declared, so it is the single place this reads.
        """
        cached = cls.__dict__.get('_FIELD_NAMES_CACHE')
        if cached is None:
            cached = frozenset(
                name for name in vars(cls()) if not name.startswith('_')
            )
            setattr(cls, '_FIELD_NAMES_CACHE', cached)
        return cached

    def _report_unknown_keys(self, config: dict, source: Optional[str]) -> None:
        """Name every key that will not be applied, once per (source, key).

        Silence is the defect this replaces: a key that is read and discarded
        looks exactly like a key that took effect until someone measures the
        behaviour it was supposed to change.
        """
        unknown = sorted(set(config) - self.field_names())
        if not unknown:
            return
        where = source or 'configuration mapping'
        for key in unknown:
            marker = (where, key)
            if marker in _REPORTED_UNKNOWN_KEYS:
                continue
            _REPORTED_UNKNOWN_KEYS.add(marker)
            suggestion = difflib.get_close_matches(key, sorted(self.field_names()), n=1)
            hint = f" Did you mean '{suggestion[0]}'?" if suggestion else ''
            logger.warning(
                "Unknown configuration key '%s' in %s -- it is not applied.%s "
                "The accepted keys are CullinanConfig's field names "
                "(`CullinanConfig.field_names()`); 'configure(...)' takes its own, "
                "smaller set.",
                key,
                where,
                hint,
            )

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
            'drain_timeout': self.drain_timeout,
            'max_request_body_bytes': self.max_request_body_bytes,
            'explicit_modules': self.explicit_modules,
            'static_files': list(self.static_files),
            'middlewares': list(self.middlewares),
            'builtin_middleware': (
                None if self.builtin_middleware is None else list(self.builtin_middleware)
            ),
            'strict_assembly': self.strict_assembly,
            'strict_assembly_excludes': (
                None
                if self.strict_assembly_excludes is None
                else list(self.strict_assembly_excludes)
            ),
            # Exported for the same reason they are accepted: a field that
            # ``from_dict`` can set but ``to_dict`` cannot report makes
            # ``push_config_overrides`` restore an incomplete snapshot, so a
            # value set inside the block survives the exit. ``test_config_
            # reachability`` compares the two key sets for exactly this.
            'context_features': dict(self.context_features),
            'enable_middleware_pipeline': self.enable_middleware_pipeline,
            'route_trailing_slash': self.route_trailing_slash,
            'route_case_sensitive': self.route_case_sensitive,
            'debug': self.debug,
            'openapi_enabled': self.openapi_enabled,
            'openapi_title': self.openapi_title,
            'openapi_version': self.openapi_version,
            'openapi_description': self.openapi_description,
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
    drain_timeout: Optional[float] = None,
    max_request_body_bytes: Optional[int] = None,
    explicit_modules: Optional[List[str]] = None,
    static_files: Optional[List[Any]] = None,
    *,
    middlewares: Optional[List[Any]] = None,
    builtin_middleware: Optional[List[Any]] = None,
    strict_assembly: bool = False,
    strict_assembly_excludes: Optional[List[str]] = None,
):
    """Configure the Cullinan framework.

    Args:
        root_module: Legacy root-module entrypoint. This default startup path has been removed.
        user_packages: User package list, for example ``['myapp', 'myapp.controllers']``.
        project_root: Project root directory. If omitted, it is inferred automatically.
        verbose: Lower the ``cullinan`` logger to ``DEBUG`` so the scan and the route table
            report themselves. The level is process-wide and is not restored when the
            configuration is replaced, so treat it as a startup decision rather than a
            per-application flag. A logger with no handler still prints nothing.
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
            ``cullinan.web.gateway.GatewayMiddleware`` instance, a
            ``GatewayMiddleware`` class declared with ``@component``, or a
            ``(instance, options)`` tuple. ``options`` accepts ``before`` /
            ``after`` anchors and/or a ``priority`` global key (a lower priority
            runs on a more outer layer; the default is 100). Declared middleware
            is assembled at the framework startup point, so the pipeline order
            follows the declaration rather than registration timing.

            A **class** entry is container-owned: the framework container
            creates it, injects its dependencies and installs that same
            instance, so the pipeline and the container share one object. The
            class must be declared with ``@component``; a class without that
            declaration is refused at startup. An **instance** entry stays owned
            by the caller and is installed as-is.
        builtin_middleware: Optional control for the **built-in** gateway
            middleware layer (the access-log middleware). ``None`` (the default)
            installs the framework default; an empty list switches the built-in
            layer off; a list of ``GatewayMiddleware`` instances / classes /
            ``(instance, options)`` tuples replaces it. Class entries follow the
            same rule as ``middlewares``: they must be declared with
            ``@component`` and are installed as the container-owned instance.
            The built-in layer is assembled at the same startup point and shares
            the declarative ordering of ``middlewares``.
        strict_assembly: Declared-but-not-assembled policy. Components whose
            decorator ran during import but which the assembly pass never picked
            up (for example because their package is missing from
            ``user_packages``) are always reported. ``False`` (the default) keeps
            that report non-blocking -- behaviour is unchanged. ``True`` requires
            the difference to be empty: the report is emitted first, and startup
            then fails with a ``ConfigurationError``. Not to be confused with
            ``startup_error_policy``, which governs service *initialisation*
            failures rather than unassembled declarations.
        strict_assembly_excludes: Components that are intentionally left
            unassembled, written as ``package.module.Component`` -- the same form
            used by the declaration report (``Application.get_declaration_diff()``).
            Listed components are still reported as declared-but-not-assembled,
            but they no longer make ``strict_assembly`` fail. ``None`` (the
            default) means no intentional exclusions; pass an empty list for the
            same meaning explicitly.

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

    Example (requiring every declaration to be assembled)::

        from cullinan import configure, application

        @configure(
            user_packages=['your_app'],
            strict_assembly=True,
            # This one is deliberately not assembled.
            strict_assembly_excludes=['your_app.legacy.OptionalService'],
        )
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

    if max_request_body_bytes is not None:
        if max_request_body_bytes <= 0:
            raise ValueError("max_request_body_bytes must be greater than zero")
        _config.max_request_body_bytes = int(max_request_body_bytes)

    if drain_timeout is not None:
        if drain_timeout <= 0:
            raise ValueError("drain_timeout must be greater than zero")
        _config.drain_timeout = float(drain_timeout)

    if project_root is not None:
        _config.set_project_root(project_root)

    _config.verbose = verbose
    # ``verbose`` used to be stored and never read, so turning it on changed
    # nothing. It now lowers the framework's own logger to DEBUG, which is where
    # the scan reports what it imported and what it skipped -- and turning it off
    # restores the level that was in place before, because a switch that only
    # works in one direction is a switch nobody trusts twice.
    _framework_logger = logging.getLogger('cullinan')
    if verbose:
        if _framework_logger.level != logging.DEBUG:
            _VERBOSE_RESTORE_LEVEL[0] = _framework_logger.level
            _framework_logger.setLevel(logging.DEBUG)
    elif _VERBOSE_RESTORE_LEVEL[0] is not None:
        _framework_logger.setLevel(_VERBOSE_RESTORE_LEVEL[0])
        _VERBOSE_RESTORE_LEVEL[0] = None
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

    # ``strict_assembly`` has a real default (``False``), so it is assigned
    # unconditionally -- like ``verbose`` / ``auto_scan`` -- which keeps repeated
    # ``configure(...)`` calls predictable. The exclusion list keeps the
    # ``None``-means-unchanged convention shared by the other list options; pass
    # an empty list to clear it.
    _config.strict_assembly = bool(strict_assembly)
    if strict_assembly_excludes is not None:
        _config.strict_assembly_excludes = list(strict_assembly_excludes)

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
