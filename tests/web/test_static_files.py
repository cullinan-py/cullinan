# -*- coding: utf-8 -*-
"""Tests for the ``cullinan.web.static`` package.

These tests exercise the static-file handler through the gateway
``Dispatcher`` so they cover the engine-neutral path. Two integration tests
additionally drive the Tornado adapter (single-handler mode) and the ASGI
adapter so we prove parity across runtimes.
"""

import asyncio
import os
from pathlib import Path

import pytest

from cullinan.web import StaticFiles
from cullinan.web.gateway import Dispatcher, Router, WebRequest
from cullinan.web.static.handler import _safe_join, _looks_like_asset
from cullinan.web.static.registry import install_static_files


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _make_dispatcher(specs, base: Path):
    router = Router()
    install_static_files(specs, router=router, project_root=str(base))
    return Dispatcher(router=router)


def _get(dispatcher, path, headers=None, method="GET"):
    request = WebRequest(method=method, path=path, headers=headers or [])
    return asyncio.run(dispatcher.dispatch(request))


@pytest.fixture()
def site(tmp_path: Path):
    """Build a small static site for tests."""
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "hello.txt").write_text("hello world", encoding="utf-8")
    (tmp_path / "static" / "app.js").write_text("console.log(1);", encoding="utf-8")
    (tmp_path / "static" / "nested").mkdir()
    (tmp_path / "static" / "nested" / "page.html").write_text("<p>hi</p>", encoding="utf-8")

    (tmp_path / "spa").mkdir()
    (tmp_path / "spa" / "index.html").write_text(
        "<!doctype html><title>SPA</title>", encoding="utf-8"
    )
    (tmp_path / "spa" / "assets").mkdir()
    (tmp_path / "spa" / "assets" / "main.js").write_text("/* bundle */", encoding="utf-8")
    return tmp_path


# ----------------------------------------------------------------------
# Spec validation
# ----------------------------------------------------------------------


def test_spec_normalises_url_prefix():
    assert StaticFiles(url="static", directory="static").url == "/static"
    assert StaticFiles(url="/assets/", directory="x").url == "/assets"
    assert StaticFiles(url="/", directory="x").url == "/"


def test_spec_rejects_invalid_methods():
    with pytest.raises(ValueError):
        StaticFiles(url="/static", directory="x", methods=("POST",))


def test_spec_rejects_negative_max_age():
    with pytest.raises(ValueError):
        StaticFiles(url="/x", directory="y", max_age=-1)


def test_spec_route_pattern_root():
    assert StaticFiles(url="/", directory="x").route_pattern() == "/**"
    assert StaticFiles(url="/static", directory="x").route_pattern() == "/static/**"


# ----------------------------------------------------------------------
# Safe join / asset detection
# ----------------------------------------------------------------------


def test_safe_join_blocks_traversal(tmp_path: Path):
    base = tmp_path.resolve()
    assert _safe_join(base, "../etc/passwd") is None
    assert _safe_join(base, "..\\..\\windows\\system32") is None
    assert _safe_join(base, "\x00bad") is None
    assert _safe_join(base, "file.txt") == base / "file.txt"


def test_looks_like_asset():
    assert _looks_like_asset("app.js") is True
    assert _looks_like_asset("static/main.css") is True
    assert _looks_like_asset("settings/profile") is False
    assert _looks_like_asset("dashboard") is False
    # A dot in a non-final segment must not trip the heuristic.
    assert _looks_like_asset("v1.2/dashboard") is False


# ----------------------------------------------------------------------
# Dispatcher integration — happy paths
# ----------------------------------------------------------------------


def test_serves_text_file(site: Path):
    dispatcher = _make_dispatcher(
        [StaticFiles(url="/static", directory="static")], site
    )
    response = _get(dispatcher, "/static/hello.txt")
    assert response.status_code == 200
    assert response.render_body() == b"hello world"
    assert "text/plain" in (response.content_type or "")


def test_serves_index_for_directory(site: Path):
    # Make /static a SPA-ish dir that resolves '/' style requests to index.
    (site / "static" / "index.html").write_text(
        "<html><body>home</body></html>", encoding="utf-8"
    )
    dispatcher = _make_dispatcher(
        [StaticFiles(url="/static", directory="static")], site
    )
    response = _get(dispatcher, "/static/")
    assert response.status_code == 200
    assert b"home" in response.render_body()


def test_404_for_missing_file(site: Path):
    dispatcher = _make_dispatcher(
        [StaticFiles(url="/static", directory="static")], site
    )
    response = _get(dispatcher, "/static/missing.txt")
    assert response.status_code == 404


def test_405_for_disallowed_method(site: Path):
    dispatcher = _make_dispatcher(
        [StaticFiles(url="/static", directory="static")], site
    )
    response = _get(dispatcher, "/static/hello.txt", method="HEAD")
    assert response.status_code == 200
    # POST is not registered as a route at all → router returns 404, not 405.
    response = _get(dispatcher, "/static/hello.txt", method="POST")
    assert response.status_code == 404


def test_head_request_returns_no_body_but_keeps_length(site: Path):
    dispatcher = _make_dispatcher(
        [StaticFiles(url="/static", directory="static")], site
    )
    response = _get(dispatcher, "/static/hello.txt", method="HEAD")
    assert response.status_code == 200
    assert response.render_body() == b""
    expected_len = (site / "static" / "hello.txt").stat().st_size
    assert response.get_header("Content-Length") == str(expected_len)


# ----------------------------------------------------------------------
# Security — directory traversal
# ----------------------------------------------------------------------


def test_directory_traversal_returns_404(site: Path, tmp_path: Path):
    # Drop a sensitive file *outside* the mount root.
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    dispatcher = _make_dispatcher(
        [StaticFiles(url="/static", directory="static")], site
    )
    response = _get(dispatcher, "/static/../secret.txt")
    assert response.status_code == 404


# ----------------------------------------------------------------------
# Caching — ETag / Last-Modified / Cache-Control
# ----------------------------------------------------------------------


def test_etag_round_trip_returns_304(site: Path):
    dispatcher = _make_dispatcher(
        [StaticFiles(url="/static", directory="static", max_age=60)], site
    )
    first = _get(dispatcher, "/static/hello.txt")
    etag = first.get_header("ETag")
    assert etag is not None
    second = _get(
        dispatcher,
        "/static/hello.txt",
        headers=[("If-None-Match", etag)],
    )
    assert second.status_code == 304
    assert second.render_body() == b""
    assert second.get_header("ETag") == etag


def test_cache_control_emitted_with_max_age(site: Path):
    dispatcher = _make_dispatcher(
        [StaticFiles(url="/static", directory="static", max_age=3600)], site
    )
    response = _get(dispatcher, "/static/hello.txt")
    cache_control = response.get_header("Cache-Control") or ""
    assert "max-age=3600" in cache_control
    assert "public" in cache_control


def test_immutable_directive_added(site: Path):
    dispatcher = _make_dispatcher(
        [StaticFiles(
            url="/assets", directory="static", max_age=31536000, immutable=True
        )],
        site,
    )
    response = _get(dispatcher, "/assets/app.js")
    assert "immutable" in (response.get_header("Cache-Control") or "")


def test_no_cache_overrides_other_directives(site: Path):
    dispatcher = _make_dispatcher(
        [StaticFiles(
            url="/static", directory="static", max_age=600, immutable=True, no_cache=True
        )],
        site,
    )
    response = _get(dispatcher, "/static/hello.txt")
    cache_control = response.get_header("Cache-Control") or ""
    assert "no-cache" in cache_control
    assert "max-age" not in cache_control
    # no-cache disables ETag emission to avoid client-side caching.
    assert response.get_header("ETag") is None


def test_extra_headers_applied(site: Path):
    dispatcher = _make_dispatcher(
        [StaticFiles(
            url="/static",
            directory="static",
            extra_headers=(("X-Hello", "world"),),
        )],
        site,
    )
    response = _get(dispatcher, "/static/hello.txt")
    assert response.get_header("X-Hello") == "world"


# ----------------------------------------------------------------------
# SPA fallback
# ----------------------------------------------------------------------


def test_spa_falls_back_to_index_for_virtual_route(site: Path):
    dispatcher = _make_dispatcher(
        [StaticFiles.spa_app(directory="spa")], site
    )
    response = _get(dispatcher, "/settings/profile")
    assert response.status_code == 200
    assert b"SPA" in response.render_body()
    assert "text/html" in (response.content_type or "")


def test_spa_returns_404_for_missing_asset(site: Path):
    dispatcher = _make_dispatcher(
        [StaticFiles.spa_app(directory="spa")], site
    )
    response = _get(dispatcher, "/assets/missing.js")
    assert response.status_code == 404


def test_spa_serves_real_asset_when_present(site: Path):
    dispatcher = _make_dispatcher(
        [StaticFiles.spa_app(directory="spa")], site
    )
    response = _get(dispatcher, "/assets/main.js")
    assert response.status_code == 200
    assert b"/* bundle */" == response.render_body()


def test_spa_serves_root_index(site: Path):
    dispatcher = _make_dispatcher(
        [StaticFiles.spa_app(directory="spa")], site
    )
    response = _get(dispatcher, "/")
    assert response.status_code == 200
    assert b"SPA" in response.render_body()


# ----------------------------------------------------------------------
# Multi-mount: order matters (more specific prefixes win in trie matching)
# ----------------------------------------------------------------------


def test_multiple_mounts_resolve_independently(site: Path):
    dispatcher = _make_dispatcher(
        [
            StaticFiles(url="/static", directory="static"),
            StaticFiles.spa_app(directory="spa"),
        ],
        site,
    )

    static_resp = _get(dispatcher, "/static/hello.txt")
    assert static_resp.status_code == 200
    assert static_resp.render_body() == b"hello world"

    spa_resp = _get(dispatcher, "/some/spa/route")
    assert spa_resp.status_code == 200
    assert b"SPA" in spa_resp.render_body()


# ----------------------------------------------------------------------
# Engine parity — Tornado adapter
# ----------------------------------------------------------------------


def test_tornado_adapter_serves_static_file(site: Path):
    tornado = pytest.importorskip("tornado")
    tornado_testing = pytest.importorskip("tornado.testing")
    from cullinan.transport.adapter import TornadoAdapter

    dispatcher = _make_dispatcher(
        [StaticFiles(url="/static", directory="static")], site
    )
    adapter = TornadoAdapter(dispatcher=dispatcher)
    app = adapter.create_app()

    class _Case(tornado_testing.AsyncHTTPTestCase):
        def get_app(self_inner):
            return app

    case = _Case()
    case.setUp()
    try:
        response = case.fetch("/static/hello.txt")
        assert response.code == 200
        assert response.body == b"hello world"
    finally:
        case.tearDown()


def test_tornado_adapter_static_not_shadowed_by_production_settings(site: Path):
    """Regression: a ``/static`` mount must survive the production Tornado
    settings produced by ``_build_tornado_settings()``.

    Historically ``_build_tornado_settings()`` injected ``static_path``, which
    made Tornado auto-register its native ``StaticFileHandler`` on the
    ``/static/`` prefix. That handler shadowed Cullinan's catch-all gateway
    handler, so every ``/static/*`` request returned a Tornado 404 instead of
    reaching the dispatcher. This test wires the adapter with the *real*
    production settings to prove the shadow is gone (engine-neutral router
    registration).
    """
    tornado = pytest.importorskip("tornado")
    tornado_testing = pytest.importorskip("tornado.testing")
    from cullinan.application.legacy import _build_tornado_settings
    from cullinan.transport.adapter import TornadoAdapter

    settings = _build_tornado_settings()
    assert "static_path" not in settings

    dispatcher = _make_dispatcher(
        [StaticFiles(url="/static", directory="static")], site
    )
    adapter = TornadoAdapter(dispatcher=dispatcher, settings=settings)
    app = adapter.create_app()

    class _Case(tornado_testing.AsyncHTTPTestCase):
        def get_app(self_inner):
            return app

    case = _Case()
    case.setUp()
    try:
        response = case.fetch("/static/hello.txt")
        assert response.code == 200
        assert response.body == b"hello world"
    finally:
        case.tearDown()


# ----------------------------------------------------------------------
# Engine parity — ASGI adapter
# ----------------------------------------------------------------------


def test_asgi_adapter_serves_static_file(site: Path):
    from cullinan.transport.adapter import ASGIAdapter

    dispatcher = _make_dispatcher(
        [StaticFiles(url="/static", directory="static")], site
    )
    adapter = ASGIAdapter(dispatcher=dispatcher)
    app = adapter.create_app()

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/static/hello.txt",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 9000),
        "server": ("localhost", 8080),
        "scheme": "http",
    }

    messages_in = [{"type": "http.request", "body": b"", "more_body": False}]
    messages_out: list = []

    async def receive():
        return messages_in.pop(0)

    async def send(message):
        messages_out.append(message)

    asyncio.run(app(scope, receive, send))

    start = next(m for m in messages_out if m["type"] == "http.response.start")
    body_messages = [m for m in messages_out if m["type"] == "http.response.body"]
    assert start["status"] == 200
    full_body = b"".join(m.get("body", b"") for m in body_messages)
    assert full_body == b"hello world"


# ----------------------------------------------------------------------
# configure() wiring
# ----------------------------------------------------------------------


def test_configure_accepts_static_files_list(tmp_path: Path, monkeypatch):
    from cullinan.support.config import configure, get_config

    monkeypatch.chdir(tmp_path)
    static_dir = tmp_path / "public"
    static_dir.mkdir()
    (static_dir / "robots.txt").write_text("User-agent: *", encoding="utf-8")

    configure(
        user_packages=[],
        auto_scan=False,
        static_files=[
            StaticFiles(url="/public", directory=str(static_dir)),
            {"url": "/cdn", "directory": str(static_dir)},
            ("/assets", str(static_dir)),
        ],
    )
    cfg = get_config()
    assert len(cfg.static_files) == 3
    assert all(isinstance(spec, StaticFiles) for spec in cfg.static_files)
    # Reset for other tests
    cfg.static_files = []
