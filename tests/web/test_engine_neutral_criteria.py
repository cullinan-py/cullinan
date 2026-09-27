"""Executable criteria for the framework's engine-neutral guarantee.

These tests pin the *criteria* for engine neutrality; they do not implement any
additional engine-neutral behaviour. Each test states one property that makes
the guarantee checkable rather than a promise:

1. Both engines share a single gateway dispatcher, so a shared pipeline change
   cannot fork per engine.
2. An engine-native dependency stays inside the transport adapter layer.
3. The isolation check is itself falsifiable - an engine-native import outside
   the adapter layer is reported instead of being ignored.
4. The descriptions the framework reports through its own extension-point
   introspection surface name no single engine, and that check is itself
   falsifiable.

The dual-engine, field-by-field response parity check belongs to a later
milestone; this module only pins the criteria that make such a check meaningful.
"""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_SHARED_DISPATCHER_IMPORT = "from cullinan.web.gateway.dispatcher import Dispatcher"
_ADAPTER_RELATIVE_PATH = "cullinan/transport/adapter/"

# Engines the framework abstracts over; a single one of these named in an
# introspection description would bind an otherwise neutral statement to it.
_ENGINE_NAME_PATTERN = re.compile(
    r"\b(tornado|asgi|twisted|uvicorn|hypercorn|daphne|gevent|gunicorn)\b",
    re.IGNORECASE,
)


def _top_level_imports(source: str):
    """Return the set of top-level module names imported by ``source``."""
    tree = ast.parse(source)
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    return modules


def _paths_importing(sources, module: str):
    """Return the sorted relative paths whose source imports ``module``."""
    return sorted(
        relative
        for relative, source in sources.items()
        if module in _top_level_imports(source)
    )


def _cullinan_sources():
    """Map repository-relative paths to source for every file under ``cullinan/``."""
    return {
        path.relative_to(REPO_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((REPO_ROOT / "cullinan").rglob("*.py"))
    }


def test_both_engines_share_a_single_dispatcher():
    """Both adapters route through the same gateway ``Dispatcher``.

    Dispatching every request through one shared pipeline means a change applies
    to both engines at once, so behaviour cannot silently diverge.
    """
    adapter_dir = REPO_ROOT / "cullinan" / "transport" / "adapter"
    for name in ("tornado_adapter.py", "asgi_adapter.py"):
        source = (adapter_dir / name).read_text(encoding="utf-8")
        assert _SHARED_DISPATCHER_IMPORT in source, (
            f"{name} must dispatch through the shared gateway Dispatcher"
        )


def test_engine_native_dependency_is_confined_to_the_transport_adapter_layer():
    """An engine-native import such as ``tornado`` stays inside the adapter layer."""
    offenders = [
        relative
        for relative in _paths_importing(_cullinan_sources(), "tornado")
        if not relative.startswith(_ADAPTER_RELATIVE_PATH)
    ]
    assert not offenders, (
        "engine-native `tornado` imports leaked outside the transport adapter "
        f"layer: {offenders}"
    )


def test_engine_native_isolation_check_is_falsifiable():
    """The isolation check reports an engine-native import outside the layer."""
    sources = {
        "cullinan/transport/adapter/tornado_adapter.py": "import tornado.web\n",
        "cullinan/web/controller/leak.py": "from tornado import web\n",
    }
    flagged = _paths_importing(sources, "tornado")
    assert flagged == [
        "cullinan/transport/adapter/tornado_adapter.py",
        "cullinan/web/controller/leak.py",
    ]
    offenders = [
        relative
        for relative in flagged
        if not relative.startswith(_ADAPTER_RELATIVE_PATH)
    ]
    assert offenders == ["cullinan/web/controller/leak.py"], (
        "the isolation criterion must flag an engine-native import outside the "
        "adapter layer"
    )


def _descriptions_naming_an_engine(descriptions):
    """Return the descriptions that name a specific engine.

    A pure predicate over plain strings, so it can be exercised on synthetic
    input and shown to be falsifiable rather than being a tautology.
    """
    return [text for text in descriptions if _ENGINE_NAME_PATTERN.search(text)]


def test_introspection_descriptions_name_no_single_engine():
    """The extension-point descriptions the framework reports name no engine.

    The framework advertises engine neutrality, so the descriptions it exposes
    through its own introspection surface must not bind to a single engine.
    """
    from cullinan.support.extensions import (
        list_extension_points,
        reset_extension_registry,
    )

    reset_extension_registry()
    try:
        descriptions = [
            point["description"] for point in list_extension_points()
        ]
    finally:
        reset_extension_registry()

    offenders = _descriptions_naming_an_engine(descriptions)
    assert not offenders, (
        "extension-point descriptions must stay engine-neutral, but bind to a "
        f"single engine: {offenders}"
    )


def test_engine_name_check_in_descriptions_is_falsifiable():
    """The engine-name check flags a description that names a single engine."""
    neutral = "Register custom route handlers"
    bound = "Register custom Tornado request handlers"
    assert _descriptions_naming_an_engine([neutral]) == []
    assert _descriptions_naming_an_engine([bound]) == [bound], (
        "the criterion must flag a description that names a single engine"
    )
