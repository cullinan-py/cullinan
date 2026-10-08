import ast
import asyncio
import doctest
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import textwrap
import warnings
from pathlib import Path
from typing import NamedTuple

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


# ---------------------------------------------------------------------------
# Public-doc import resolvability gate
#
# Every import shown in the public guides must be resolvable. Two implementation
# constraints follow from the upstream ruling:
#   * the scan must be multi-line aware - a line-anchor scan silently skips
#     ``from cullinan import (`` blocks, so blocks are parsed with ``ast``;
#   * it must import for real - a static ``__all__`` / name-set comparison cannot
#     see PEP 562 module-level ``__getattr__`` re-exports.
#
# A third constraint is that the gate must be fail-closed: if a document's code
# fences cannot be paired reliably the scan must fail loudly (file name + fence
# count) rather than skip the rest of the file, because a silent skip turns the
# gate into a false guarantee.
# ---------------------------------------------------------------------------


class UnbalancedCodeFenceError(ValueError):
    """Raised when a document's code fences cannot be paired reliably."""

    def __init__(self, doc: str, fence_count: int, detail: str):
        self.doc = doc
        self.fence_count = fence_count
        super().__init__(
            f"{doc}: {fence_count} code-fence lines ({detail}); the fences do not "
            "pair up, so the document cannot be scanned reliably"
        )


class UnparseableCodeBlockError(ValueError):
    """Raised when a python code block cannot be parsed and is not registered.

    Parsing failures used to be swallowed, which turned the gate into a false
    guarantee for the skipped region. A block may only be skipped when it is
    listed in ``_UNPARSEABLE_PYTHON_BLOCK_REGISTRY``; anything else fails
    loudly with the document name and the block's start line.
    """

    def __init__(self, doc: str, line: int, detail: str):
        self.doc = doc
        self.line = line
        super().__init__(
            f"{doc}:{line}: python code block is not parseable ({detail}) and is "
            "not registered as a known non-parseable block"
        )


class _CodeBlock(NamedTuple):
    start_offset: int
    end_offset: int
    start_line: int
    info: str
    body: str


class _DocImport(NamedTuple):
    line: int
    node: ast.AST
    heading: str
    block_digest: str


# An opening fence is up to three leading spaces, then a run of at least three
# backticks or tildes, then an optional info string.
_FENCE_LINE = re.compile(r"^[ \t]{0,3}(?P<fence>`{3,}|~{3,})(?P<info>[^\n]*)$", re.M)
_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.M)

# A block is allowed to keep non-resolvable imports only when its nearest
# preceding heading marks it as deprecated / scheduled for removal, or as a
# pre-migration "v0.9x" example.
_STALE_BLOCK_HEADING_MARKERS = (
    "deprecated",
    "will be removed",
    "弃用",
    "移除",
    "v0.9x",
)

# The blocks that are allowed to keep stale imports. Compared for equality so a
# future edit cannot silently widen the exemption and absorb a real defect.
_EXPECTED_EXEMPT_BLOCK_HEADINGS = {
    "Legacy Imports (Deprecated)",
    "遗留导入（已弃用）",
    "v0.9x: Tornado only",
    "v0.9x：仅 Tornado",
}

# Python code blocks that cannot be parsed. These are shell transcripts and
# list-indented snippets, not runnable modules. Parsing failures are no longer
# skipped silently: a block must appear here (keyed by document and body digest)
# or the gate fails. The set is asserted for equality so it cannot drift.
_UNPARSEABLE_PYTHON_BLOCK_REGISTRY = {
    ("migration_guide.md", "ae21a01a6f41da35"): "exception transcript, not python",
    ("migration_guide.md", "6fe4e6d66b1407b3"): "exception transcript, not python",
    ("wiki/decorators.md", "48092db847348ed7"): "list-indented decorator snippet",
    ("wiki/decorators.md", "7339b6c7c292229d"): "list-indented method snippet",
    ("wiki/injection.md", "c0a8d61cc95caa59"): "list-indented class-body snippet",
    ("zh/migration_guide.md", "f9bfad16a7018de9"): "exception transcript, not python",
    ("zh/migration_guide.md", "6425d12359b2bd33"): "exception transcript, not python",
    ("zh/wiki/decorators.md", "212921b13424a2b0"): "list-indented decorator snippet",
    ("zh/wiki/decorators.md", "7339b6c7c292229d"): "list-indented method snippet",
    ("zh/wiki/injection.md", "fc0322cfe8f06542"): "list-indented class-body snippet",
}

# Code blocks whose cullinan imports are deliberately non-resolvable: they are
# explicitly labelled "before / old style" migration examples that demonstrate a
# path which has since been removed. This is the same situation the
# deprecated-block exemption covers for the legacy import walkthrough, so these
# blocks are exempt too. They are registered one by one (document + body digest)
# instead of being released by a heuristic such as "the file name contains
# migration"; the set is asserted for equality so it cannot silently widen.
_EXEMPT_LEGACY_IMPORT_BLOCKS = {
    ("migration_guide.md", "8dbbadbaf22519c2"): "'Before (1.x)' example: removed grouped registry helpers",
    ("migration_guide.md", "a69165a46a5a0ec7"): "'Old style' example: removed cullinan.app entrypoint",
    ("migration_to_final_semantic_layout.md", "4ff57b10c924a54b"): "'Before' example: removed cullinan.public_api",
    ("migration_to_final_semantic_layout.md", "c630f77e3d7d2c30"): "'Before' example: removed cullinan.application_model",
    ("migration_to_final_semantic_layout.md", "b620681f8fe9905b"): "'Before' example: removed cullinan.controller / cullinan.params",
    ("migration_to_final_semantic_layout.md", "c817df3ddebca627"): "'Before' example: removed cullinan.adapter",
    ("zh/migration_guide.md", "8dbbadbaf22519c2"): "'Before (1.x)' example: removed grouped registry helpers",
    ("zh/migration_guide.md", "0f481ec0a8c741b6"): "'Old style' example: removed cullinan.app entrypoint",
    ("zh/migration_to_final_semantic_layout.md", "4ff57b10c924a54b"): "'Before' example: removed cullinan.public_api",
    ("zh/migration_to_final_semantic_layout.md", "c630f77e3d7d2c30"): "'Before' example: removed cullinan.application_model",
    ("zh/migration_to_final_semantic_layout.md", "b620681f8fe9905b"): "'Before' example: removed cullinan.controller / cullinan.params",
    ("zh/migration_to_final_semantic_layout.md", "c817df3ddebca627"): "'Before' example: removed cullinan.adapter",
}

# Guides corrected by this iteration; every cullinan import in them must resolve.
_IMPORT_GATED_DOCS = (
    "import_migration_090.md",
    "zh/import_migration_090.md",
    "migration_guide_v2.md",
    "zh/migration_guide_v2.md",
    "getting_started.md",
    "zh/getting_started.md",
)


def _block_digest(body: str) -> str:
    """Stable short digest of a code block body, used to key the registries."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _is_python_block(block: "_CodeBlock") -> bool:
    return bool(block.info) and block.info.split()[0] in ("python", "py")


def _iter_public_docs():
    """Yield ``(relative_path, text)`` for every markdown file under ``docs``."""
    for doc in sorted(Path("docs").rglob("*.md")):
        yield doc.relative_to("docs").as_posix(), doc.read_text(encoding="utf-8")


def _iter_code_blocks(text: str, doc: str = ""):
    """Return the document's fenced code blocks as ``_CodeBlock`` records.

    Fences are paired strictly: an opening fence may carry an info string, but a
    closing fence must be made of the same fence character, be at least as long
    as the opener, and carry no info string. A fence-like line that still
    carries an info string (`` ```powershell ``) while a block is open is treated
    as block content, so it can never be mistaken for the closing fence and
    shift the pairing of every following block.

    When the fences cannot be paired - an odd number of fence lines, or a block
    that is never closed - ``UnbalancedCodeFenceError`` is raised instead of
    silently skipping the remainder of the document.
    """
    matches = list(_FENCE_LINE.finditer(text))
    if len(matches) % 2 != 0:
        raise UnbalancedCodeFenceError(doc, len(matches), "odd number of fences")
    blocks = []
    index = 0
    while index < len(matches):
        opener = matches[index]
        open_char = opener.group("fence")[0]
        open_len = len(opener.group("fence"))
        closer = None
        scan = index + 1
        while scan < len(matches):
            candidate = matches[scan]
            fence = candidate.group("fence")
            if (
                fence[0] == open_char
                and len(fence) >= open_len
                and candidate.group("info").strip() == ""
            ):
                closer = candidate
                break
            scan += 1
        if closer is None:
            raise UnbalancedCodeFenceError(doc, len(matches), "a block is never closed")
        blocks.append(
            _CodeBlock(
                start_offset=opener.start(),
                end_offset=closer.end(),
                start_line=text[: opener.start()].count("\n") + 1,
                info=opener.group("info").strip(),
                body=text[opener.end() + 1 : closer.start()],
            )
        )
        index = scan + 1
    return blocks


def _mask_code_fences(text: str, blocks) -> str:
    """Blank out fenced code so heading detection ignores ``#`` inside code."""
    chars = list(text)
    for block in blocks:
        for index in range(block.start_offset, block.end_offset):
            if chars[index] != "\n":
                chars[index] = " "
    return "".join(chars)


def _nearest_heading(masked: str, position: int) -> str:
    heading = ""
    for match in _MARKDOWN_HEADING.finditer(masked[:position]):
        heading = match.group(2).strip()
    return heading


def _iter_doc_imports(text: str, module_prefix: str = "", doc: str = ""):
    """Yield ``_DocImport`` records for imports inside python code blocks.

    Only fences whose info string marks them as python (``python`` / ``py``) are
    parsed; shell, ini and prose fences cannot carry python imports and are not
    scanned. ``UnbalancedCodeFenceError`` propagates when the document's fences
    cannot be paired reliably, so the caller can turn it into an explicit
    failure. A python block that cannot be parsed is reported as
    ``UnparseableCodeBlockError`` unless the block is registered in
    ``_UNPARSEABLE_PYTHON_BLOCK_REGISTRY``; nothing is skipped silently.
    """
    blocks = _iter_code_blocks(text, doc)
    masked = _mask_code_fences(text, blocks)
    for block in blocks:
        if not _is_python_block(block):
            continue
        digest = _block_digest(block.body)
        try:
            tree = ast.parse(block.body)
        except SyntaxError as error:
            if (doc, digest) in _UNPARSEABLE_PYTHON_BLOCK_REGISTRY:
                continue
            detail = str(error).splitlines()[0] if str(error) else "syntax error"
            raise UnparseableCodeBlockError(doc, block.start_line, detail) from error
        heading = _nearest_heading(masked, block.start_offset)
        base_line = block.start_line + 1
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.Import):
                module = ""
                names = [alias.name for alias in node.names]
            else:
                continue
            if module_prefix and not (
                module.startswith(module_prefix)
                or any(name.startswith(module_prefix) for name in names)
            ):
                continue
            yield _DocImport(
                line=base_line + node.lineno - 1,
                node=node,
                heading=heading,
                block_digest=digest,
            )


def _execute_import(node) -> None:
    """Import for real; raise if the module or any imported name is missing."""
    if isinstance(node, ast.ImportFrom):
        if node.module is None:
            return
        module = importlib.import_module(node.module)
        for alias in node.names:
            if alias.name == "*":
                continue
            getattr(module, alias.name)
    else:
        for alias in node.names:
            importlib.import_module(alias.name)


def _describe_import(node) -> str:
    return ast.unparse(node).splitlines()[0]


async def _invoke_asgi_app(
    app,
    path: str,
    method: str = "GET",
    body: bytes = b"",
    query_string: bytes = b"",
    extra_headers=None,
):
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
            *[
                (key.encode("latin-1"), value.encode("latin-1"))
                for key, value in (extra_headers or {}).items()
            ],
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


def test_middleware_pipeline_example_reflects_declared_order():
    main = _load_entry_method("examples.middleware_pipeline.root")
    app = main.get_asgi_app()

    # The declared gate sits on the outermost layer, so an unauthenticated
    # request is rejected before the endpoint body ever runs.
    status, _, payload = asyncio.run(_invoke_asgi_app(app, "/pipeline"))
    assert status == 403
    assert payload == {"error": "missing demo key"}

    # With the demo key, both declared middleware take effect and the installed
    # order matches the declaration (priority=0 gate stays outermost).
    status, headers, payload = asyncio.run(
        _invoke_asgi_app(
            app,
            "/pipeline",
            extra_headers={"x-demo-key": "let-me-in"},
        )
    )
    assert status == 200
    assert headers["x-demo-gate"] == "passed"
    assert headers["x-demo-marker"] == "middleware-pipeline"
    assert payload["order"][:2] == [
        "ApiKeyGateMiddleware",
        "RequestMarkerMiddleware",
    ]
    # The framework's built-in layer is still present in the same pipeline.
    assert "AccessLogMiddleware" in payload["order"]

    # The protected endpoint is equally gated.
    guarded_status, _, _ = asyncio.run(_invoke_asgi_app(app, "/pipeline/echo"))
    assert guarded_status == 403


def test_middleware_ownership_example_marks_the_two_forms():
    main = _load_entry_method("examples.middleware_ownership.root")
    app = main.get_asgi_app()

    status, headers, payload = asyncio.run(_invoke_asgi_app(app, "/ownership"))

    assert status == 200
    assert payload["order"][:2] == ["AuditMiddleware", "MarkerMiddleware"]
    assert payload["container_managed"] == "AuditMiddleware"
    assert payload["externally_owned"] == "MarkerMiddleware"
    # The container-owned middleware recorded into its injected dependency.
    assert payload["audit_log_entries"] == ["/ownership"]
    assert headers["x-audit-entries"] == "1"
    assert headers["x-marker"] == "externally-owned"


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


def test_component_discovery_boundary_example_reports_dropped_component():
    _clear_example_modules("examples.component_discovery_boundary")
    module = importlib.import_module("examples.component_discovery_boundary.demo")
    module.run_example_assertions()


def test_assembly_snapshot_example_reports_surface_holdings():
    _clear_example_modules("examples.assembly_snapshot")
    module = importlib.import_module("examples.assembly_snapshot.demo")
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
        ("middleware_pipeline", "root.py"),
        ("middleware_ownership", "root.py"),
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
    # Pin the *current* release line the README's "Current series" section
    # advertises; asserting the previous line would stay green forever once the
    # README keeps it as historical context, making the guard vacuous.
    assert "**v0.96a5**" in readme


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


def _is_cullinan_import(node) -> bool:
    """True for ``from cullinan[...] import ...`` / ``import cullinan[...]``."""
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        return module == "cullinan" or module.startswith("cullinan.")
    if isinstance(node, ast.Import):
        return any(
            alias.name == "cullinan" or alias.name.startswith("cullinan.")
            for alias in node.names
        )
    return False


def _block_is_exempt(relative: str, item: "_DocImport") -> bool:
    """A block is exempt when its heading or an explicit registration marks it so."""
    if (relative, item.block_digest) in _EXEMPT_LEGACY_IMPORT_BLOCKS:
        return True
    return any(marker in item.heading.lower() for marker in _STALE_BLOCK_HEADING_MARKERS)


def test_public_guide_cullinan_imports_are_resolvable():
    """Every cullinan import shown in the public guides resolves.

    The gate covers both the top-level ``from cullinan import ...`` form and the
    submodule form (``from cullinan.<module> import ...`` and ``import
    cullinan.<module>``). Multi-line import blocks are parsed with ``ast`` (a
    line-anchor scan would skip them) and resolved by importing for real (a
    static ``__all__`` comparison would misjudge PEP 562 module-level
    ``__getattr__`` exports).

    Two situations keep a block out of the gate, and both are explicit and
    enumerable: a block under a heading that marks it deprecated / scheduled for
    removal, and the registered set of explicitly labelled "before / old style"
    migration examples. Nothing is released by a file-name heuristic. A document
    whose fences cannot be paired - or that holds a python block which cannot be
    parsed and is not registered - fails the gate explicitly.
    """
    failures = []
    scanned = 0
    for relative, text in _iter_public_docs():
        try:
            imports = list(_iter_doc_imports(text, doc=relative))
        except (UnbalancedCodeFenceError, UnparseableCodeBlockError) as error:
            failures.append(str(error))
            continue
        for item in imports:
            if not _is_cullinan_import(item.node):
                continue
            scanned += 1
            try:
                _execute_import(item.node)
            except Exception as error:
                if _block_is_exempt(relative, item):
                    continue
                failures.append(
                    f"{relative}:{item.line}: {_describe_import(item.node)} -> {error}"
                )

    assert scanned > 0, "the public-doc import gate matched no cullinan import statement"
    assert not failures, (
        "unresolvable or unscannable cullinan import content in the public docs:\n"
        + "\n".join(failures)
    )


def test_public_guide_exempt_legacy_blocks_are_enumerated():
    """Legacy blocks that keep non-resolvable imports are listed one by one.

    The gate never releases a non-resolvable block implicitly: whatever it lets
    through must equal ``_EXEMPT_LEGACY_IMPORT_BLOCKS`` (minus the heading-marked
    deprecated blocks). The equality assertion means a future edit cannot widen
    the exemption, and a stale entry cannot linger.
    """
    found = set()
    for relative, text in _iter_public_docs():
        try:
            imports = list(_iter_doc_imports(text, doc=relative))
        except (UnbalancedCodeFenceError, UnparseableCodeBlockError):
            continue
        for item in imports:
            if not _is_cullinan_import(item.node):
                continue
            try:
                _execute_import(item.node)
            except Exception:
                if any(
                    marker in item.heading.lower()
                    for marker in _STALE_BLOCK_HEADING_MARKERS
                ):
                    continue
                found.add((relative, item.block_digest))

    assert found == set(_EXEMPT_LEGACY_IMPORT_BLOCKS), (
        "the set of non-resolvable import blocks exempted from the gate changed; "
        f"expected {sorted(_EXEMPT_LEGACY_IMPORT_BLOCKS)}, got {sorted(found)}"
    )


def test_unparseable_python_blocks_are_enumerated():
    """Non-parseable python blocks are registered one by one, never skipped.

    Parsing failures used to be swallowed silently. The gate now reports them,
    so the only tolerated ones are those listed in
    ``_UNPARSEABLE_PYTHON_BLOCK_REGISTRY``; the equality assertion keeps that
    list exact in both directions.
    """
    found = set()
    for relative, text in _iter_public_docs():
        try:
            blocks = _iter_code_blocks(text, relative)
        except UnbalancedCodeFenceError:
            continue
        for block in blocks:
            if not _is_python_block(block):
                continue
            try:
                ast.parse(block.body)
            except SyntaxError:
                found.add((relative, _block_digest(block.body)))

    assert found == set(_UNPARSEABLE_PYTHON_BLOCK_REGISTRY), (
        "the set of non-parseable python blocks changed; expected "
        f"{sorted(_UNPARSEABLE_PYTHON_BLOCK_REGISTRY)}, got {sorted(found)}"
    )


def test_unparseable_python_block_is_not_silently_skipped():
    """A python block that cannot be parsed raises instead of being skipped."""
    text = "Intro\n\n" "```python\n" "from cullinan import (\n" "```\n"
    with pytest.raises(UnparseableCodeBlockError) as excinfo:
        list(_iter_doc_imports(text, doc="sample.md"))
    message = str(excinfo.value)
    assert "sample.md" in message


def test_unregistered_unresolvable_submodule_import_fails_the_gate():
    """An injected, unresolvable submodule import is reported (falsifiable)."""
    text = (
        "Intro\n\n"
        "```python\n"
        "from cullinan.web.does_not_exist import thing\n"
        "```\n"
    )
    imports = [item for item in _iter_doc_imports(text, doc="sample.md")]
    matched = [item for item in imports if _is_cullinan_import(item.node)]
    assert len(matched) == 1, "the injected submodule import must be scannable"
    with pytest.raises(Exception):
        _execute_import(matched[0].node)
    assert not _block_is_exempt("sample.md", matched[0])
    assert ("sample.md", matched[0].block_digest) not in _EXEMPT_LEGACY_IMPORT_BLOCKS


def test_import_gated_public_docs_keep_resolvable_cullinan_imports():
    """The guides corrected this iteration keep resolvable imports.

    ``(a)`` the corrected statements must execute; ``(b)`` the remaining
    statements must execute too, unless their block is explicitly marked
    deprecated / scheduled for removal - or is a pre-migration ``v0.9x`` example.
    A gated document whose fences cannot be paired fails the gate explicitly
    (file name + fence count) instead of being partially skipped.
    """
    failures = []
    exempt_headings = set()
    for relative in _IMPORT_GATED_DOCS:
        text = Path("docs", relative).read_text(encoding="utf-8")
        try:
            imports = list(_iter_doc_imports(text, module_prefix="cullinan", doc=relative))
        except (UnbalancedCodeFenceError, UnparseableCodeBlockError) as error:
            failures.append(str(error))
            continue
        for item in imports:
            try:
                _execute_import(item.node)
                continue
            except Exception as error:
                if any(
                    marker in item.heading.lower()
                    for marker in _STALE_BLOCK_HEADING_MARKERS
                ):
                    exempt_headings.add(item.heading)
                    continue
                failures.append(
                    f"{relative}:{item.line}: {_describe_import(item.node)} -> {error}"
                )

    assert not failures, (
        "unresolvable or unscannable cullinan imports in the import-gated guides:\n"
        + "\n".join(failures)
    )
    assert exempt_headings == _EXPECTED_EXEMPT_BLOCK_HEADINGS, (
        "the set of blocks whose imports are exempted from the gate changed; expected "
        f"{sorted(_EXPECTED_EXEMPT_BLOCK_HEADINGS)}, got {sorted(exempt_headings)}"
    )


def test_code_fence_scanner_fails_closed_on_unbalanced_fences():
    """An unbalanced document raises instead of being scanned silently."""
    malformed = (
        "Intro\n\n"
        "```python\n"
        "from cullinan import application\n"
        "\n"
        "```powershell\n"
        "python demo.py\n"
        "```\n"
    )
    with pytest.raises(UnbalancedCodeFenceError) as excinfo:
        _iter_code_blocks(malformed, "sample.md")
    message = str(excinfo.value)
    assert "sample.md" in message
    assert "3" in message


def test_code_fence_scanner_ignores_info_string_fences_inside_a_block():
    """```lang lines inside an open block are content, not a closing fence."""
    text = (
        "```python\n"
        "from cullinan import application\n"
        "```\n"
        "\n"
        "```powershell\n"
        "python demo.py\n"
        "```\n"
    )
    blocks = _iter_code_blocks(text, "sample.md")
    assert [block.info for block in blocks] == ["python", "powershell"]
    assert "from cullinan import application" in blocks[0].body
    assert "from cullinan import application" not in blocks[1].body


def test_migration_v2_available_import_block_is_not_exempt_from_the_gate():
    """The block that advertises new available imports is still scanned.

    That block self-claims the imports work, so it must not be silently absorbed
    by the deprecated-block exemption; every top-level ``from cullinan import``
    statement in the guide must resolve and must not sit under an exempt
    heading. (Submodule imports are covered by the general public-doc gate,
    which exempts legacy blocks per block rather than per heading.)
    """
    for relative in ("migration_guide_v2.md", "zh/migration_guide_v2.md"):
        text = Path("docs", relative).read_text(encoding="utf-8")
        scanned = 0
        for item in _iter_doc_imports(text, doc=relative):
            if not (
                isinstance(item.node, ast.ImportFrom)
                and item.node.module == "cullinan"
            ):
                continue
            assert not any(
                marker in item.heading.lower() for marker in _STALE_BLOCK_HEADING_MARKERS
            ), f"{relative}:{item.line} is under the exempt heading {item.heading!r}"
            _execute_import(item.node)
            scanned += 1
        assert scanned > 0, (
            f"{relative}: expected at least one top-level `from cullinan import` block"
        )


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
        assert "0.96a5" in content
        assert "0.94a1" not in content


def test_application_module_docs_prefer_entry_method_helpers_over_top_level_runtime_helpers():
    application_module = _read_doc_file("modules", "application.md")
    zh_application_module = _read_zh_doc_file("modules", "application.md")

    assert "top-level `run()` / `get_asgi_app()` are the shortest public startup path" not in application_module
    assert "顶层 `run()` / `get_asgi_app()` 才是最短公开启动路径" not in zh_application_module
    assert "main.run()" in application_module
    assert "main.get_asgi_app()" in application_module
    assert "main.run()" in zh_application_module
    assert "main.get_asgi_app()" in zh_application_module


# ---------------------------------------------------------------------------
# Docstring example gate (the same public-example guarantee, extended from
# ``docs/**`` to the examples shown in ``cullinan/**`` docstrings).
#
# A docstring example is treated as code when it is either a doctest example
# (``>>>`` prompts) or an indented block that parses as Python. Two things are
# checked, both fail-closed:
#   * a code-like block - one that imports ``cullinan`` - must parse, or the
#     gate fails with the file name and line instead of skipping it;
#   * every collected example that references ``cullinan`` is executed in a
#     sandboxed subprocess where names a snippet leaves undefined are stubbed
#     out. An example fails the gate when the framework itself raises - the
#     traceback carries a frame inside ``cullinan/`` - or when an import does
#     not resolve. A docstring snippet is illustrative, so a name it never
#     defines is not a failure; a call that the framework rejects is.
# ---------------------------------------------------------------------------

CULLINAN_ROOT = Path("cullinan").resolve()

# Runs a batch of example sources in one process. Each source is compiled and
# executed with a namespace that stubs undefined names, so a snippet can be
# exercised without supplying the surrounding application. Results are
# reported as JSON on the real stdout (any output the examples themselves
# print is captured and discarded so it cannot pollute the report).
_DOCSTRING_EXAMPLE_RUNNER = r'''
import io
import json
import sys

payload = json.loads(sys.stdin.read())
import cullinan

_real_stdout = sys.stdout


class _Stub:
    """Stand-in for a name a docstring example leaves undefined."""

    def __init__(self, name):
        self._name = name

    def __call__(self, *args, **kwargs):
        return _Stub(self._name)

    def __getattr__(self, item):
        if item.startswith("__"):
            raise AttributeError(item)
        return _Stub(self._name + "." + item)

    def __getitem__(self, item):
        return _Stub(self._name)

    def __iter__(self):
        return iter(())

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _Namespace(dict):
    def __missing__(self, key):
        if key.startswith("__"):
            raise KeyError(key)
        value = _Stub(key)
        self[key] = value
        return value


results = []
for index, source in enumerate(payload):
    namespace = _Namespace({"__name__": "cullinan_docstring_example"})
    for symbol in dir(cullinan):
        if not symbol.startswith("_"):
            try:
                namespace[symbol] = getattr(cullinan, symbol)
            except Exception:
                pass
    sys.stdout = io.StringIO()
    try:
        exec(compile(source, "<cullinan-docstring-example-%d>" % index, "exec"), namespace)
    except BaseException as exc:  # noqa: BLE001 - every failure is reported
        frames = []
        tb = exc.__traceback__
        while tb is not None:
            frames.append(tb.tb_frame.f_code.co_filename)
            tb = tb.tb_next
        results.append({
            "status": "error",
            "type": type(exc).__name__,
            "message": str(exc)[:200],
            "frames": frames,
            "import_error": isinstance(exc, ImportError),
        })
    else:
        results.append({"status": "ok"})
    finally:
        sys.stdout = _real_stdout

_real_stdout.write(json.dumps(results))
'''


def _iter_cullinan_docstrings():
    """Yield ``(relative_path, qualname, docstring)`` for ``cullinan/**``."""
    for path in sorted(Path("cullinan").rglob("*.py")):
        relative = path.as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                continue
            docstring = ast.get_docstring(node, clean=False)
            if docstring:
                yield relative, getattr(node, "name", relative) or relative, docstring


def _iter_indented_example_blocks(docstring: str):
    """Yield ``(line, code)`` for indented blocks under an ``Example`` heading."""
    lines = docstring.splitlines()
    index = 0
    while index < len(lines):
        heading = lines[index].strip().rstrip(":").lower()
        if heading not in ("example", "examples", "usage"):
            index += 1
            continue
        base_indent = len(lines[index]) - len(lines[index].lstrip())
        cursor = index + 1
        block = []
        while cursor < len(lines):
            line = lines[cursor]
            if line.strip() == "":
                block.append("")
                cursor += 1
                continue
            if len(line) - len(line.lstrip()) <= base_indent:
                break
            block.append(line)
            cursor += 1
        code = textwrap.dedent("\n".join(block)).strip()
        if code:
            yield index + 1, code
        index = cursor


def _looks_like_doctest(code: str) -> bool:
    return any(line.strip().startswith(">>>") for line in code.splitlines())


def _collect_cullinan_docstring_examples():
    """Return ``(examples, errors)`` for the docstrings of ``cullinan/**``.

    ``examples`` holds ``(relative_path, qualname, source)`` tuples; ``errors``
    holds a message per code-like block that does not parse. Doctest examples
    are extracted with ``doctest``; indented blocks are collected when they
    parse as Python.
    """
    examples = []
    errors = []
    parser = doctest.DocTestParser()
    for relative, qualname, docstring in _iter_cullinan_docstrings():
        try:
            doctest_examples = parser.get_examples(docstring)
        except ValueError:
            doctest_examples = []
        for example in doctest_examples:
            examples.append((relative, qualname, example.source))
        for line, code in _iter_indented_example_blocks(docstring):
            if _looks_like_doctest(code):
                continue  # covered by the doctest pass above
            try:
                ast.parse(code)
            except SyntaxError as error:
                if "from cullinan" in code or "import cullinan" in code:
                    detail = str(error).splitlines()[0] if str(error) else "syntax error"
                    errors.append(f"{relative}:{line}: code example does not parse ({detail})")
                continue
            examples.append((relative, qualname, code))
    return examples, errors


def _run_docstring_examples(sources):
    """Execute the example sources in a sandboxed subprocess; return the results."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(Path.cwd()), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _DOCSTRING_EXAMPLE_RUNNER],
            input=json.dumps(list(sources)),
            capture_output=True,
            text=True,
            cwd=str(Path.cwd()),
            env=environment,
            timeout=180,
        )
    except subprocess.TimeoutExpired as error:
        raise AssertionError(
            "a docstring example did not finish within the time limit; a docstring "
            "example must not block (start servers, wait on input, ...)"
        ) from error
    if completed.returncode != 0:
        raise AssertionError(
            "the docstring example sandbox failed to run:\n" + completed.stderr[-1000:]
        )
    return json.loads(completed.stdout)


def _frame_is_framework(frame: str) -> bool:
    """True when a traceback frame points inside the framework package."""
    if not frame or frame.startswith("<"):
        return False
    try:
        return CULLINAN_ROOT in Path(frame).resolve().parents
    except OSError:
        return False


def test_cullinan_docstring_examples_are_executable():
    """Every ``cullinan`` example in a docstring runs without a framework error.

    The gate extends the public-doc example guarantee (``docs/**``) to the
    examples embedded in ``cullinan/**`` docstrings. An example fails when an
    import it shows does not resolve, or when the framework raises while the
    example runs - the ``body_decoder`` snippet that passed an instance to a
    registry expecting a class is the registered red case. Undefined names are
    stubbed, so no illustrative snippet has to be rewritten to satisfy the
    gate; a call the framework rejects still fails it.
    """
    examples, errors = _collect_cullinan_docstring_examples()
    scanned = [example for example in examples if "cullinan" in example[2]]
    assert scanned, "the docstring example gate matched no cullinan example"

    results = _run_docstring_examples([source for _, _, source in scanned])

    failures = list(errors)
    for (relative, qualname, _source), result in zip(scanned, results):
        if result["status"] == "ok":
            continue
        if result["import_error"] or any(
            _frame_is_framework(frame) for frame in result["frames"]
        ):
            failures.append(
                f"{relative}::{qualname}: {result['type']}: {result['message']}"
            )

    assert not failures, (
        "docstring examples that do not run through the framework:\n"
        + "\n".join(failures)
    )


def test_docstring_example_runner_flags_a_framework_error():
    """Red/green control for the docstring example runner itself.

    A documented call the framework accepts passes; the same call with an
    instance where the registry requires a class fails, and the failure is
    attributed to the framework frame. This keeps the gate falsifiable: if the
    runner stopped executing examples, the red case here would stop failing.
    """
    accepted = (
        "from cullinan.web.middleware import get_middleware_registry\n"
        "from cullinan.web.middleware.body_decoder import BodyDecoderMiddleware\n"
        "registry = get_middleware_registry()\n"
        "registry.register(BodyDecoderMiddleware)\n"
    )
    rejected = (
        "from cullinan.web.middleware import get_middleware_registry\n"
        "from cullinan.web.middleware.body_decoder import BodyDecoderMiddleware\n"
        "registry = get_middleware_registry()\n"
        "registry.register(BodyDecoderMiddleware())\n"
    )

    results = _run_docstring_examples([accepted, rejected])

    assert results[0]["status"] == "ok"
    assert results[1]["status"] == "error"
    assert any(_frame_is_framework(frame) for frame in results[1]["frames"])
