# -*- coding: utf-8 -*-

import importlib
import json
import os
import subprocess
import sys
import textwrap
import warnings
from importlib import resources
from pathlib import Path

import pytest

import cullinan
import cullinan._version as version_api
import cullinan.core as core_api
import cullinan.web as web_api
from cullinan import application, configure, get_config
from cullinan.application import Application
from cullinan.application import public as public_api
from cullinan.web.controller import reset_controller_registry
from cullinan.web.params import FileInfo
from cullinan.core import PendingRegistry, set_application_context
from cullinan.core.semantic_rules import PublicAPISemanticWarning, reset_semantic_warnings
from cullinan.web.gateway import WebRuntime, reset_gateway


EXPECTED_TOP_LEVEL_EXPORTS = [
    "Auto",
    "AutoType",
    "Body",
    "BodyDecoderMiddleware",
    "CullinanConfig",
    "DynamicBody",
    "File",
    "Header",
    "Inject",
    "InjectByName",
    "Lazy",
    "Middleware",
    "Param",
    "ParamResolver",
    "ParamValidator",
    "Path",
    "Provider",
    "Query",
    "ResolveError",
    "StaticFiles",
    "TypeConverter",
    "UNSET",
    "ValidationError",
    "WebRequest",
    "WebResponse",
    "application",
    "component",
    "configure",
    "controller",
    "delete_api",
    "get_api",
    "get_config",
    "get_decoded_body",
    "get_missing_header_handler",
    "middleware",
    "module",
    "patch_api",
    "post_api",
    "put_api",
    "response",
    "service",
    "set_decoded_body",
    "set_missing_header_handler",
    "websocket_handler",
]

EXPECTED_PACKAGE_VERSION = "0.95"

# ---------------------------------------------------------------------------
# 1.0 public API freeze contract (symbol-name granularity).
#
# Scope: exactly four package ``__all__`` lists -- ``cullinan`` /
# ``cullinan.application`` / ``cullinan.web`` / ``cullinan.core``.  The
# ``cullinan.web.gateway`` facade is deliberately *outside* the contract.
# ``FROZEN_PUBLIC_API_CONTRACT`` is bound below, after the ``EXPECTED_*``
# snapshots it references are declared.
# ---------------------------------------------------------------------------
FROZEN_PUBLIC_API_SYMBOL_COUNTS = {
    "cullinan": 44,
    "cullinan.application": 26,
    "cullinan.web": 34,
    "cullinan.core": 72,
}

# Explicitly excluded from the 1.0 freeze (layered gateway facade).
FROZEN_PUBLIC_API_EXCLUDED_MODULES = ("cullinan.web.gateway",)

EXPECTED_APPLICATION_EXPORTS = [
    "Application",
    "ApplicationMetadata",
    "Module",
    "ModuleGraph",
    "ModuleMetadata",
    "ModuleReflectionResult",
    "ModuleSpec",
    "Runtime",
    "CullinanConfig",
    "_collect_module_specs",
    "_resolve_component_owners",
    "application",
    "bind_runtime_request_context",
    "configure",
    "get_asgi_app",
    "get_application_metadata",
    "get_config",
    "has_application_metadata",
    "get_module_metadata",
    "module",
    "reflect_module",
    "release_runtime_request_context",
    "run",
    "scan_controller",
    "scan_service",
    "_validate_component_scan_results",
]

EXPECTED_WEB_EXPORTS = [
    "Auto",
    "AutoType",
    "Body",
    "BodyDecoderMiddleware",
    "DynamicBody",
    "File",
    "Handler",
    "Header",
    "Middleware",
    "Param",
    "ParamResolver",
    "ParamValidator",
    "Path",
    "Query",
    "ResolveError",
    "StaticFiles",
    "TypeConverter",
    "UNSET",
    "ValidationError",
    "WebRequest",
    "WebResponse",
    "controller",
    "delete_api",
    "get_api",
    "get_decoded_body",
    "get_missing_header_handler",
    "middleware",
    "patch_api",
    "post_api",
    "put_api",
    "response",
    "set_decoded_body",
    "set_missing_header_handler",
    "websocket_handler",
]

EXPECTED_CORE_EXPORTS = [
    "ApplicationContext",
    "ContainerState",
    "ContainerManager",
    "get_container_manager",
    "get_application_context",
    "set_application_context",
    "Definition",
    "ScopeType",
    "ScopeManager",
    "Factory",
    "render_resolution_path",
    "render_injection_point",
    "render_candidate_sources",
    "format_circular_dependency_error",
    "format_missing_dependency_error",
    "format_scope_violation_error",
    "CullinanCoreError",
    "RegistryError",
    "RegistryFrozenError",
    "DependencyResolutionError",
    "DependencyNotFoundError",
    "DependencyTypeResolutionError",
    "CircularDependencyError",
    "ScopeNotActiveError",
    "ConditionNotMetError",
    "CreationError",
    "LifecycleError",
    "ScopeViolationError",
    "service",
    "controller",
    "component",
    "provider_decorator",
    "Provider",
    "Inject",
    "InjectByName",
    "Lazy",
    "get_injection_markers",
    "CullinanSemanticWarning",
    "ComponentDiscoveryWarning",
    "CompatibilitySemanticWarning",
    "InjectionSemanticWarning",
    "PublicAPISemanticWarning",
    "ConditionalOnProperty",
    "ConditionalOnClass",
    "ConditionalOnMissingBean",
    "ConditionalOnBean",
    "Conditional",
    "PendingRegistry",
    "PendingRegistration",
    "ComponentType",
    "Registry",
    "SimpleRegistry",
    "LifecycleManager",
    "LifecycleState",
    "LifecycleAware",
    "SmartLifecycle",
    "LifecyclePhase",
    "get_lifecycle_manager",
    "reset_lifecycle_manager",
    "RequestContext",
    "get_current_context",
    "set_current_context",
    "create_context",
    "destroy_context",
    "ContextManager",
    "get_context_value",
    "set_context_value",
    "injectable",
    "inject_constructor",
    "InjectionRegistry",
    "get_injection_registry",
    "reset_injection_registry",
]

# The four frozen contracts, bound to their checked-in snapshots.  Kept as a
# mapping so the runtime check (M-1 ~ M-4) and the static snapshot stay tied
# to one source of truth.
FROZEN_PUBLIC_API_CONTRACT = {
    "cullinan": EXPECTED_TOP_LEVEL_EXPORTS,
    "cullinan.application": EXPECTED_APPLICATION_EXPORTS,
    "cullinan.web": EXPECTED_WEB_EXPORTS,
    "cullinan.core": EXPECTED_CORE_EXPORTS,
}


def _check_frozen_export_contract(contract: dict[str, list[str]]) -> None:
    """Apply the frozen-contract checks to ``contract`` (M-1 ~ M-3).

    Kept as a helper so the falsifiability test can run the *exact same*
    checks against a synthetic package.

    * M-1 -- ``__all__`` is read at runtime through ``importlib`` (never an
      AST literal), so dynamically appended exports are covered.
    * M-2 -- every listed name is resolved for real: ``getattr`` must succeed
      and must not be ``None`` (a module-level ``__getattr__`` may legally
      return ``None`` for an import that failed).
    * M-3 -- the symbol-name set *and* the count must match the snapshot.
    """
    for module_name, expected in contract.items():
        module = importlib.import_module(module_name)  # M-1
        names = list(module.__all__)  # M-1
        assert len(names) == len(expected), module_name  # M-3
        assert names == list(expected), module_name  # M-3
        for symbol in names:
            resolved = getattr(module, symbol)  # M-2
            assert resolved is not None, f"{module_name}.{symbol} resolves to None"


def _write_package(tmp_path: Path, package_name: str, files: dict[str, str]) -> str:
    root = tmp_path / package_name
    for relative_path, content in files.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    return package_name


def _clear_modules(prefix: str) -> None:
    for module_name in list(sys.modules):
        if module_name == prefix or module_name.startswith(f"{prefix}."):
            sys.modules.pop(module_name, None)


@pytest.fixture(autouse=True)
def _reset_semantic_once_and_config():
    cfg = get_config()
    original = cfg.to_dict()
    reset_semantic_warnings()
    set_application_context(None)
    PendingRegistry.reset()
    WebRuntime.clear_active()
    reset_gateway()
    reset_controller_registry()
    yield
    reset_semantic_warnings()
    set_application_context(None)
    PendingRegistry.reset()
    WebRuntime.clear_active()
    reset_gateway()
    reset_controller_registry()
    cfg.from_dict(original)


def test_top_level_public_api_hides_advanced_runtime_symbols():
    public_exports = set(cullinan.__all__)

    assert "application" in public_exports
    assert "run" not in public_exports
    assert "get_asgi_app" not in public_exports
    assert "create_app" not in public_exports
    assert "current_app" not in public_exports
    assert "Application" not in public_exports
    assert "ApplicationContext" not in public_exports
    assert "TornadoAdapter" not in public_exports
    assert "reset_controller_registry" not in public_exports


def test_public_api_export_lists_are_frozen_for_1_0():
    """Static snapshot: the checked-in contract must equal the live lists."""
    assert cullinan.__all__ == EXPECTED_TOP_LEVEL_EXPORTS
    assert application.__all__ == EXPECTED_APPLICATION_EXPORTS
    assert web_api.__all__ == EXPECTED_WEB_EXPORTS
    assert core_api.__all__ == EXPECTED_CORE_EXPORTS


def test_public_api_frozen_contract_is_resolvable_at_runtime():
    """1.0 freeze contract, verified by real execution (M-1 ~ M-4).

    The static snapshot above cannot see a name whose ``__all__`` entry
    resolves to ``None`` through a module-level ``__getattr__`` (PEP 562);
    importing and resolving each name for real can.
    """
    _check_frozen_export_contract(FROZEN_PUBLIC_API_CONTRACT)  # M-1 ~ M-3

    for module_name, expected_count in FROZEN_PUBLIC_API_SYMBOL_COUNTS.items():
        module = importlib.import_module(module_name)
        assert len(module.__all__) == expected_count, module_name

    for module_name in FROZEN_PUBLIC_API_EXCLUDED_MODULES:  # M-4
        assert module_name not in FROZEN_PUBLIC_API_CONTRACT
        gateway = importlib.import_module(module_name)
        assert list(gateway.__all__) not in [
            list(expected) for expected in FROZEN_PUBLIC_API_CONTRACT.values()
        ]


def test_frozen_contract_check_rejects_none_resolving_symbol(tmp_path, monkeypatch):
    """Falsifiability of M-2: a symbol that resolves to ``None`` must fail.

    Mirrors the ``cullinan.transport.adapter`` shape, where ``__all__``
    lists names that the module-level ``__getattr__`` can return as
    ``None``.  A static literal comparison would pass; this check must not.
    """
    package_name = "frozen_contract_none_probe"
    _write_package(
        tmp_path,
        package_name,
        {
            "__init__.py": """
                __all__ = ["Real", "Ghost"]

                class Real:
                    pass

                def __getattr__(name):
                    if name == "Ghost":
                        return None
                    raise AttributeError(name)
            """,
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package_name)

    try:
        with pytest.raises(AssertionError):
            _check_frozen_export_contract({package_name: ["Real", "Ghost"]})
    finally:
        _clear_modules(package_name)


def test_typed_marker_is_present_in_the_package_tree():
    assert resources.files("cullinan").joinpath("py.typed").is_file()


def test_version_single_source_is_shared_by_public_modules_and_pyproject():
    pyproject_text = Path("pyproject.toml").read_text(encoding="utf-8")

    assert version_api.__version__ == EXPECTED_PACKAGE_VERSION
    assert cullinan.__version__ == EXPECTED_PACKAGE_VERSION
    assert core_api.__version__ == EXPECTED_PACKAGE_VERSION
    assert 'dynamic = ["version"]' in pyproject_text
    assert 'version = { attr = "cullinan._version.__version__" }' in pyproject_text
    assert '"0.93.post1"' not in pyproject_text
    assert '"0.93.post1"' not in Path("cullinan/__init__.py").read_text(encoding="utf-8")
    assert '"0.93.post1"' not in Path("cullinan/core/__init__.py").read_text(encoding="utf-8")


def test_package_discovery_excludes_generated_build_trees():
    pyproject_text = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '"build*"' in pyproject_text
    assert '"dist*"' in pyproject_text


def test_top_level_does_not_expose_advanced_runtime_symbols():
    module = importlib.reload(cullinan)
    with pytest.raises(AttributeError):
        getattr(module, "run")
    with pytest.raises(AttributeError):
        getattr(module, "get_asgi_app")
    with pytest.raises(AttributeError):
        getattr(module, "Application")
    with pytest.raises(AttributeError):
        getattr(module, "create_app")
    with pytest.raises(AttributeError):
        getattr(module, "current_app")


def test_web_fileinfo_keeps_backend_neutral_upload_factory():
    assert hasattr(FileInfo, "from_upload_payload")
    assert not hasattr(FileInfo, "from_tornado_file")


def test_top_level_import_does_not_eagerly_load_tornado(monkeypatch):
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import importlib, sys; importlib.import_module('cullinan'); "
            "print(any(name.startswith('tornado') for name in sys.modules))",
        ],
        text=True,
        cwd=os.getcwd(),
    ).strip()

    assert output == "False"


def test_application_import_does_not_eagerly_load_tornado(monkeypatch):
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import importlib, sys; importlib.import_module('cullinan.application'); "
            "print(any(name.startswith('tornado') for name in sys.modules))",
        ],
        text=True,
        cwd=os.getcwd(),
    ).strip()

    assert output == "False"


def test_direct_application_run_stays_explicit_runtime_api(tmp_path, monkeypatch):
    package_name = "boundary_application_run"
    _write_package(
        tmp_path,
        package_name,
        {
            "__init__.py": "",
            "root.py": """
                from cullinan import module

                @module
                class RootModule:
                    pass
            """,
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package_name)

    root_module = importlib.import_module(f"{package_name}.root").RootModule
    app = Application.run(root_module)

    try:
        assert app.root_module is root_module
    finally:
        app.uninstall()
        _clear_modules(package_name)


def test_public_run_requires_application_entry_method():
    get_config().root_module = None

    with pytest.raises(RuntimeError, match=r"cullinan\.run\(\) requires an @application entry method"):
        public_api.run()

    with pytest.raises(RuntimeError) as exc_info:
        public_api.run()

    message = str(exc_info.value)
    assert "@application" in message
    assert "entry method" in message


def test_public_get_asgi_app_requires_application_entry_method():
    get_config().root_module = None

    with pytest.raises(RuntimeError, match=r"cullinan\.get_asgi_app\(\) requires an @application entry method"):
        public_api.get_asgi_app()

    with pytest.raises(RuntimeError) as exc_info:
        public_api.get_asgi_app()

    message = str(exc_info.value)
    assert "@application" in message
    assert "entry method" in message


def test_application_entry_method_runs_without_boundary_warning(tmp_path, monkeypatch):
    package_name = "boundary_public_application_method"
    _write_package(
        tmp_path,
        package_name,
        {
            "__init__.py": "",
            "root.py": """
                from cullinan import Inject, application, configure, controller, get_api, service

                @service
                class GreetingService:
                    def greet(self):
                        return "hello"

                @controller(url="/api")
                class GreetingController:
                    greeting_service: GreetingService = Inject()

                    @get_api(url="/ping")
                    def ping(self):
                        return {"message": self.greeting_service.greet()}

                @configure(
                    user_packages=["boundary_public_application_method"],
                    server_engine="tornado",
                    server_host="127.0.0.1",
                    server_port=5091,
                )
                @application
                def main(): ...
            """,
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package_name)
    entry_method = importlib.import_module(f"{package_name}.root").main

    captured: dict[str, object] = {}

    class DummyTornadoAdapter:
        def __init__(self, dispatcher, settings=None, global_headers=None, runtime=None):
            captured["dispatcher"] = dispatcher
            captured["settings"] = settings
            captured["global_headers"] = global_headers
            captured["runtime"] = runtime

        def run(self, host="0.0.0.0", port=4080, **kwargs):
            captured["host"] = host
            captured["port"] = port
            captured["kwargs"] = kwargs

    monkeypatch.setattr(public_api, "_load_tornado_adapter", lambda: DummyTornadoAdapter)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        app = entry_method()

    try:
        assert app is not None
        assert app.root_module is entry_method
        assert captured["host"] == "127.0.0.1"
        assert captured["port"] == 5091
        assert captured["settings"]["template_path"].endswith("templates")
        # static_path must NOT be injected: it would make Tornado auto-register
        # its native StaticFileHandler at /static/, shadowing router-based
        # StaticFiles mounts (engine-neutral router registration).
        assert "static_path" not in captured["settings"]
        assert isinstance(captured["global_headers"], list)
        assert not any(isinstance(item.message, PublicAPISemanticWarning) for item in caught)
    finally:
        if app is not None:
            app.uninstall()
        _clear_modules(package_name)


def test_configure_rejects_legacy_root_module_path():
    class RootModule:
        pass

    with pytest.raises(ValueError) as exc_info:
        configure(root_module=RootModule)

    message = str(exc_info.value)
    assert "configure(root_module=...)" in message
    assert "@application" in message


def test_public_run_rejects_legacy_startup_class(tmp_path, monkeypatch):
    package_name = "boundary_public_legacy_class"
    _write_package(
        tmp_path,
        package_name,
        {
            "__init__.py": "",
            "root.py": """
                from cullinan import application

                @application
                def main(): ...

                class LegacyApp:
                    pass
            """,
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package_name)
    legacy_app = importlib.import_module(f"{package_name}.root").LegacyApp

    with pytest.raises(RuntimeError) as exc_info:
        public_api.run(legacy_app)

    message = str(exc_info.value)
    assert "no longer accepts startup classes" in message


def test_entry_method_prefers_neutral_auto_engine_resolution(tmp_path, monkeypatch):
    package_name = "boundary_public_method_auto"
    _write_package(
        tmp_path,
        package_name,
        {
            "__init__.py": "",
            "root.py": """
                from cullinan import application, configure, controller, get_api

                @controller(url="/api")
                class GreetingController:
                    @get_api(url="/ping")
                    def ping(self):
                        return {"message": "hello"}

                @configure(
                    user_packages=["boundary_public_method_auto"],
                    server_host="127.0.0.1",
                    server_port=5092,
                    asgi_server="uvicorn",
                )
                @application
                def main(): ...
            """,
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package_name)
    entry_method = importlib.import_module(f"{package_name}.root").main

    captured: dict[str, object] = {}

    class DummyASGIAdapter:
        def __init__(self, dispatcher, global_headers=None, runtime=None):
            captured["dispatcher"] = dispatcher
            captured["global_headers"] = global_headers
            captured["runtime"] = runtime

        def run(self, host="0.0.0.0", port=4080, **kwargs):
            captured["host"] = host
            captured["port"] = port
            captured["kwargs"] = kwargs

    monkeypatch.setattr(public_api, "ASGIAdapter", DummyASGIAdapter)
    monkeypatch.setattr(public_api, "resolve_runtime_engine", lambda engine, asgi_server="uvicorn": "asgi")

    app = entry_method.run()

    try:
        assert app is not None
        assert app.root_module is entry_method
        assert captured["host"] == "127.0.0.1"
        assert captured["port"] == 5092
        assert captured["kwargs"]["server"] == "uvicorn"
        assert isinstance(captured["global_headers"], list)
    finally:
        if app is not None:
            app.uninstall()
        _clear_modules(package_name)


def test_entry_method_exposes_get_asgi_app(tmp_path, monkeypatch):
    package_name = "boundary_public_asgi_method"
    _write_package(
        tmp_path,
        package_name,
        {
            "__init__.py": "",
            "root.py": """
                from cullinan import application, configure, get_api, controller

                @controller(url="/api")
                class GreetingController:
                    @get_api(url="/ping")
                    def ping(self):
                        return {"message": "hello"}

                @configure(user_packages=["boundary_public_asgi_method"])
                @application
                def main(): ...
            """,
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package_name)
    entry_method = importlib.import_module(f"{package_name}.root").main

    app = entry_method.get_asgi_app()

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent = []

    async def send(message):
        sent.append(message)

    import asyncio

    try:
        asyncio.run(
            app(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/api/ping",
                    "headers": [],
                    "query_string": b"",
                    "client": ("127.0.0.1", 9000),
                    "server": ("localhost", 4080),
                    "scheme": "http",
                },
                receive,
                send,
            )
        )
        body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
        assert sent[0]["status"] == 200
        assert json.loads(body) == {"message": "hello"}
    finally:
        current_app = Application.current()
        if current_app is not None:
            current_app.uninstall()
        _clear_modules(package_name)


def test_entry_method_finalizes_middleware_and_openapi(tmp_path, monkeypatch):
    package_name = "boundary_public_asgi_finalize"
    _write_package(
        tmp_path,
        package_name,
        {
            "__init__.py": "",
            "root.py": """
                from cullinan import Middleware, application, configure, controller, get_api, middleware

                @middleware(priority=50)
                class AddExampleHeader(Middleware):
                    def process_response(self, request, response):
                        response.set_header("X-Boundary-Test", "ready")
                        return response

                @controller(url="/api")
                class GreetingController:
                    @get_api(url="/ping")
                    def ping(self):
                        return {"message": "hello"}

                @configure(user_packages=["boundary_public_asgi_finalize"])
                @application
                def main(): ...
            """,
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package_name)
    entry_method = importlib.import_module(f"{package_name}.root").main

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def dispatch(path: str):
        sent = []

        async def send(message):
            sent.append(message)

        await app(
            {
                "type": "http",
                "method": "GET",
                "path": path,
                "headers": [],
                "query_string": b"",
                "client": ("127.0.0.1", 9000),
                "server": ("localhost", 4080),
                "scheme": "http",
            },
            receive,
            send,
        )
        return sent

    app = entry_method.get_asgi_app()

    import asyncio

    try:
        ping_messages = asyncio.run(dispatch("/api/ping"))
        ping_body = b"".join(
            message.get("body", b"") for message in ping_messages if message["type"] == "http.response.body"
        )
        ping_headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in ping_messages[0].get("headers", [])
        }
        assert ping_messages[0]["status"] == 200
        assert json.loads(ping_body) == {"message": "hello"}
        assert ping_headers["x-boundary-test"] == "ready"

        openapi_messages = asyncio.run(dispatch("/openapi.json"))
        openapi_body = b"".join(
            message.get("body", b"") for message in openapi_messages if message["type"] == "http.response.body"
        )
        assert openapi_messages[0]["status"] == 200
        assert json.loads(openapi_body)["openapi"] == "3.0.3"
    finally:
        current_app = Application.current()
        if current_app is not None:
            current_app.uninstall()
        _clear_modules(package_name)
pytestmark = pytest.mark.filterwarnings(
    "ignore::cullinan.core.semantic_rules.PublicAPISemanticWarning"
)
