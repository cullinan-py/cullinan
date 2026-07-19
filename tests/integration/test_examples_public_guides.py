import asyncio
import importlib
import json
import sys
from pathlib import Path

import pytest

from cullinan import get_config
from cullinan.application import Application
from cullinan.web.controller import reset_controller_registry
from cullinan.core import PendingRegistry, set_application_context
from cullinan.core.semantic_rules import reset_semantic_warnings
from cullinan.web.gateway import WebRuntime, reset_gateway
from cullinan.web.middleware import reset_middleware_registry


def _clear_example_modules(prefix: str):
    for name in list(sys.modules):
        if name == prefix or name.startswith(f"{prefix}."):
            sys.modules.pop(name, None)


def _load_entry_method(module_path: str, name: str = "main"):
    prefix = module_path.rsplit(".", 1)[0]
    _clear_example_modules(prefix)
    module = importlib.import_module(module_path)
    return getattr(module, name)


def _read_example_file(*parts: str) -> str:
    return Path("examples", *parts).read_text(encoding="utf-8")


def _read_doc_file(*parts: str) -> str:
    return Path("docs", *parts).read_text(encoding="utf-8")


def _read_zh_doc_file(*parts: str) -> str:
    return Path("docs", "zh", *parts).read_text(encoding="utf-8")


async def _invoke_asgi_app(app, path: str, method: str = "GET", body: bytes = b"", query_string: bytes = b""):
    messages = []
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": query_string,
        "headers": [
            (b"host", b"example.test"),
            (b"content-type", b"application/json"),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("example.test", 80),
    }

    await app(scope, receive, send)

    start = next(message for message in messages if message["type"] == "http.response.start")
    body_message = next(message for message in messages if message["type"] == "http.response.body")
    payload = json.loads(body_message["body"].decode("utf-8"))
    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in start.get("headers", [])
    }
    return start["status"], headers, payload


async def _invoke_asgi_app_raw(app, path: str, method: str = "GET", body: bytes = b"", query_string: bytes = b""):
    """Same as ``_invoke_asgi_app`` but returns the raw body as text.

    Useful for non-JSON responses such as static files and SPA HTML.
    """
    messages = []
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": query_string,
        "headers": [(b"host", b"example.test")],
        "client": ("127.0.0.1", 12345),
        "server": ("example.test", 80),
    }

    await app(scope, receive, send)

    start = next(m for m in messages if m["type"] == "http.response.start")
    body_chunks = [m.get("body", b"") for m in messages if m["type"] == "http.response.body"]
    raw_body = b"".join(body_chunks).decode("utf-8", errors="replace")
    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in start.get("headers", [])
    }
    return start["status"], headers, raw_body


@pytest.fixture(autouse=True)
def _reset_runtime_state():
    cfg = get_config()
    original = cfg.to_dict()
    reset_semantic_warnings()
    PendingRegistry.reset()
    reset_controller_registry()
    reset_middleware_registry()
    WebRuntime.clear_active()
    reset_gateway()
    set_application_context(None)

    yield

    current = Application.current()
    if current is not None:
        current.uninstall()

    reset_semantic_warnings()
    PendingRegistry.reset()
    reset_controller_registry()
    reset_middleware_registry()
    WebRuntime.clear_active()
    reset_gateway()
    set_application_context(None)
    cfg.from_dict(original)


def test_minimal_app_example_serves_public_entrypoint():
    main = _load_entry_method("examples.minimal_app.root")
    app = main.get_asgi_app()

    status, _, payload = asyncio.run(_invoke_asgi_app(app, "/hello"))

    assert status == 200
    assert payload["entrypoint"] == "@application + @configure(...) + main()"


def test_controller_service_inject_example_uses_business_layers():
    main = _load_entry_method("examples.controller_service_inject.root")
    app = main.get_asgi_app()

    status, _, payload = asyncio.run(_invoke_asgi_app(app, "/users/2"))

    assert status == 200
    assert payload["name"] == "Linus"
    assert payload["role"] == "maintainer"


def test_middleware_and_module_example_marks_module_boundary():
    main = _load_entry_method("examples.middleware_and_module.root")
    app = main.get_asgi_app()

    status, headers, payload = asyncio.run(_invoke_asgi_app(app, "/inventory/summary"))

    assert status == 200
    assert payload["module_boundary"] == "examples.middleware_and_module"
    assert headers["x-cullinan-example"] == "middleware-and-module"
    assert headers["x-module-boundary"] == "examples.middleware_and_module"


def test_parameter_handling_example_maps_path_query_and_body():
    main = _load_entry_method("examples.parameter_handling.root")
    app = main.get_asgi_app()

    get_status, _, get_payload = asyncio.run(
        _invoke_asgi_app(
            app,
            "/catalog/items/7",
            query_string=b"include_meta=true&locale=zh-CN",
        )
    )
    post_status, _, post_payload = asyncio.run(
        _invoke_asgi_app(
            app,
            "/catalog/search",
            method="POST",
            body=json.dumps({"keyword": "cullinan", "page": 2, "limit": 5}).encode("utf-8"),
        )
    )

    assert get_status == 200
    assert get_payload["item_id"] == 7
    assert get_payload["include_meta"] is True
    assert get_payload["locale"] == "zh-CN"
    assert get_payload["meta"]["source"] == "parameter-system"

    assert post_status == 200
    assert post_payload["keyword"] == "cullinan"
    assert post_payload["page"] == 2
    assert post_payload["limit"] == 5


def test_testing_flow_example_stays_executable():
    _clear_example_modules("examples.testing_flow")
    module = importlib.import_module("examples.testing_flow.test_app")
    module.run_example_assertions()


def test_static_files_example_serves_assets_and_spa_fallback():
    main = _load_entry_method("examples.static_files_and_spa.root")
    app = main.get_asgi_app()

    # /api/health controller — must take priority over the root SPA mount.
    status, _, payload = asyncio.run(_invoke_asgi_app(app, "/api/health"))
    assert status == 200
    assert payload == {"status": "ok"}

    # SPA fallback — virtual path resolves to index.html.
    status, headers, body_text = asyncio.run(
        _invoke_asgi_app_raw(app, "/settings/profile")
    )
    assert status == 200
    assert "text/html" in headers.get("content-type", "")
    assert "Cullinan SPA Demo" in body_text

    # Real static asset under /public.
    status, headers, body_text = asyncio.run(
        _invoke_asgi_app_raw(app, "/public/robots.txt")
    )
    assert status == 200
    assert "User-agent" in body_text
    cache_control = headers.get("cache-control", "")
    assert "max-age=3600" in cache_control

    # Real static asset under /static — the prefix Tornado's native handler
    # used to shadow. Must resolve through the router on both engines.
    status, headers, body_text = asyncio.run(
        _invoke_asgi_app_raw(app, "/static/app.css")
    )
    assert status == 200
    assert "--cullinan-accent" in body_text
    assert "max-age=3600" in headers.get("cache-control", "")

    # Asset-looking miss under SPA must NOT fall back to index.html.
    status, _, _ = asyncio.run(_invoke_asgi_app_raw(app, "/assets/missing.js"))
    assert status == 404


def test_example_entrypoints_use_top_level_public_api():
    targets = [
        ("minimal_app", "root.py"),
        ("controller_service_inject", "root.py"),
        ("middleware_and_module", "root.py"),
        ("parameter_handling", "root.py"),
        ("testing_flow", "app.py"),
        ("static_files_and_spa", "root.py"),
    ]

    for parts in targets:
        source = _read_example_file(*parts)
        assert "from cullinan import application" in source
        assert "configure" in source
        assert "run(" not in source
        assert "from cullinan import get_asgi_app" not in source
        assert "configure_example(" not in source
        assert "from cullinan.application import configure, module, run" not in source
        assert "configure(root_module=" not in source


def test_examples_directory_keeps_legacy_demos_outside_default_path():
    examples_readme = Path("examples", "README.md").read_text(encoding="utf-8")

    assert "examples/legacy/" in examples_readme
    assert "examples/extension_registration_demo.py" in examples_readme
    assert Path("examples", "legacy", "decorator_demo_090.py").exists()
    assert not Path("examples", "decorator_demo_090.py").exists()
    # Expired legacy demos that referenced removed APIs (cullinan.run,
    # cullinan.core.provider) have been cleaned up.
    assert not Path("examples", "legacy", "custom_provider_demo.py").exists()
    assert not Path("examples", "legacy", "custom_auth_middleware.py").exists()
    assert not Path("examples", "legacy", "ioc_facade_demo.py").exists()
    assert not Path("examples", "custom_provider_demo.py").exists()
    assert not Path("examples", "custom_auth_middleware.py").exists()
    assert not Path("examples", "ioc_facade_demo.py").exists()


def test_docs_home_no_longer_exposes_fake_app_module():
    docs_home = _read_doc_file("README.md")
    zh_docs_home = _read_zh_doc_file("README.md")

    assert "Module Reference: app" not in docs_home
    assert "模块参考：app" not in zh_docs_home
    assert "modules/app.md" not in docs_home
    assert "modules/app.md" not in zh_docs_home
    assert not Path("docs", "modules", "application_lifecycle.md").exists()
    assert not Path("docs", "zh", "modules", "application_lifecycle.md").exists()
    assert not Path("docs", "modules", "app.md").exists()
    assert not Path("docs", "zh", "modules", "app.md").exists()
    assert "`cullinan.application + cullinan.web + cullinan.core`" not in docs_home
    assert "`cullinan.application + cullinan.web + cullinan.core`" not in zh_docs_home


def test_root_readme_keeps_default_path_on_top_level_api():
    readme = Path("README.MD").read_text(encoding="utf-8")

    assert "def create_app():" not in readme
    assert "create_app()" not in readme
    assert "- `cullinan.application` - application definition, configuration, and startup" not in readme
    assert "top-level `cullinan` API" in readme
    assert "**v0.95a1**" in readme


def test_getting_started_stays_on_business_first_onboarding_path():
    getting_started = _read_doc_file("getting_started.md")
    zh_getting_started = _read_zh_doc_file("getting_started.md")

    assert "ApplicationContext" not in getting_started
    assert "WebRuntime" not in getting_started
    assert "ApplicationContext" not in zh_getting_started
    assert "WebRuntime" not in zh_getting_started
    assert "Internals & Extensions" in getting_started
    assert "运行时与扩展" in zh_getting_started


def test_di_guides_prefer_public_core_and_top_level_startup():
    di_guide = _read_doc_file("dependency_injection_guide.md")
    zh_di_guide = _read_zh_doc_file("dependency_injection_guide.md")
    di_quick = _read_doc_file("quick_reference_di.md")
    zh_di_quick = _read_zh_doc_file("quick_reference_di.md")

    assert "from cullinan.core.services import service" not in di_guide
    assert "from cullinan.core.services import service" not in zh_di_guide
    assert "from cullinan.application import run" not in di_quick
    assert "from cullinan.application import run" not in zh_di_quick
    assert "from cullinan import application, configure" in di_quick
    assert "from cullinan import application, configure" in zh_di_quick


def test_api_reference_removes_compatibility_layer_from_current_surface():
    api_reference = _read_doc_file("api_reference.md")
    zh_api_reference = _read_zh_doc_file("api_reference.md")

    assert "explicit runtime assembly" not in api_reference
    assert "显式运行时装配" not in zh_api_reference
    assert "decorator-first business code" in api_reference
    assert "装饰器优先的业务代码" in zh_api_reference
    assert "Compatibility-oriented modules" not in api_reference
    assert "兼容保留模块" not in zh_api_reference
    assert "application.lifecycle" not in api_reference
    assert "application.lifecycle" not in zh_api_reference


def test_tornado_decoupling_docs_keep_top_level_startup_and_backend_neutral_terms():
    architecture = _read_doc_file("architecture.md")
    zh_architecture = _read_zh_doc_file("architecture.md")
    framework_semantics = _read_doc_file("framework_semantics.md")
    zh_framework_semantics = _read_zh_doc_file("framework_semantics.md")
    components = _read_doc_file("wiki", "components.md")
    zh_components = _read_zh_doc_file("wiki", "components.md")
    migration_v2 = _read_doc_file("migration_guide_v2.md")
    zh_migration_v2 = _read_zh_doc_file("migration_guide_v2.md")

    assert "cullinan.application -> Application, configure/run/get_asgi_app, @module" not in architecture
    assert "cullinan.application -> Application、configure/run/get_asgi_app、@module" not in zh_architecture
    assert "cullinan             -> @application, configure" in architecture
    assert "cullinan             -> @application、configure" in zh_architecture
    assert "configure/run/get_asgi_app" not in architecture
    assert "configure/run/get_asgi_app" not in zh_architecture

    assert "- `cullinan.application` for application configuration and startup" not in framework_semantics
    assert "- `cullinan.application` —— 应用配置与启动" not in zh_framework_semantics
    assert "- `cullinan` for application startup (`@application`, `configure`)" in framework_semantics
    assert "- `cullinan` —— 应用启动入口（`@application`、`configure`）" in zh_framework_semantics

    assert "`current_app`" not in components
    assert "`current_app`" not in zh_components
    assert "Application.current()" in components
    assert "Application.current()" in zh_components

    assert "from cullinan.application import run" not in migration_v2
    assert "from cullinan.application import run" not in zh_migration_v2
    assert "from cullinan import run" not in migration_v2
    assert "from cullinan import run" not in zh_migration_v2
    assert "@application" in migration_v2
    assert "@application" in zh_migration_v2


def test_current_version_markers_follow_v094a1_release_line():
    docs_home = _read_doc_file("README.md")
    zh_docs_home = _read_zh_doc_file("README.md")
    architecture = _read_doc_file("architecture.md")
    zh_architecture = _read_zh_doc_file("architecture.md")
    di_guide = _read_doc_file("dependency_injection_guide.md")
    zh_di_guide = _read_zh_doc_file("dependency_injection_guide.md")
    di_quick = _read_doc_file("quick_reference_di.md")
    zh_di_quick = _read_zh_doc_file("quick_reference_di.md")
    extension_guide = _read_doc_file("extension_development_guide.md")
    zh_extension_guide = _read_zh_doc_file("extension_development_guide.md")

    for content in (
        docs_home,
        zh_docs_home,
        architecture,
        zh_architecture,
        di_guide,
        zh_di_guide,
        di_quick,
        zh_di_quick,
        extension_guide,
        zh_extension_guide,
    ):
        assert "0.94a1" in content
        assert "0.93a13" not in content


def test_application_module_docs_prefer_entry_method_helpers_over_top_level_runtime_helpers():
    application_module = _read_doc_file("modules", "application.md")
    zh_application_module = _read_zh_doc_file("modules", "application.md")

    assert "top-level `run()` / `get_asgi_app()` are the shortest public startup path" not in application_module
    assert "顶层 `run()` / `get_asgi_app()` 才是最短公开启动路径" not in zh_application_module
    assert "main.run()" in application_module
    assert "main.get_asgi_app()" in application_module
    assert "main.run()" in zh_application_module
    assert "main.get_asgi_app()" in zh_application_module
