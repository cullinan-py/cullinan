# -*- coding: utf-8 -*-
"""Async static-file handler used by all runtime backends.

This module is engine-neutral: the handler returns a :class:`WebResponse`
and the active driver adapter writes it out, so Tornado and ASGI behave
identically.

Author: plumeink
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
import os
from email.utils import formatdate, parsedate_to_datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional, Tuple

from cullinan.web.gateway.web_core import WebRequest, WebResponse
from cullinan.web.static.spec import StaticFiles

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Path resolution
# ----------------------------------------------------------------------


def _strip_prefix(path: str, prefix: str) -> str:
    """Return the portion of ``path`` that lies under ``prefix``.

    The leading prefix is removed and the result is returned without its
    leading slash. ``prefix == "/"`` is treated as a no-op.
    """
    if prefix == "/":
        return path.lstrip("/")
    # Router has already matched, so we can assume the path starts with prefix.
    if path == prefix:
        return ""
    if path.startswith(prefix + "/"):
        return path[len(prefix) + 1 :]
    # Defensive fallback: behave as if no prefix matched.
    return path.lstrip("/")


def _safe_join(base: Path, relative: str) -> Optional[Path]:
    """Join ``relative`` to ``base`` and ensure the result stays within ``base``.

    Returns ``None`` when the requested path escapes ``base`` (directory
    traversal attempt) or contains forbidden characters.
    """
    # Reject NUL bytes and explicit traversal segments up front.
    if "\x00" in relative:
        return None

    # Normalise separators so Windows-style backslashes do not bypass checks.
    cleaned = relative.replace("\\", "/").lstrip("/")
    if not cleaned:
        return base

    candidate = (base / cleaned).resolve(strict=False)
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


# ----------------------------------------------------------------------
# Caching helpers
# ----------------------------------------------------------------------


def _compute_etag(stat_result: os.stat_result) -> str:
    """Compute a strong ETag from ``(mtime_ns, size)``.

    A short hash keeps headers compact while remaining collision-safe for
    practical content sets.
    """
    raw = f"{stat_result.st_mtime_ns}-{stat_result.st_size}".encode("ascii")
    digest = hashlib.blake2b(raw, digest_size=12).hexdigest()
    return f'"{digest}"'


def _format_http_date(timestamp: float) -> str:
    return formatdate(timestamp, usegmt=True)


def _parse_http_date(value: str) -> Optional[float]:
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    return dt.timestamp()


def _build_cache_control(spec: StaticFiles) -> Optional[str]:
    if spec.no_cache:
        return "no-cache, no-store, must-revalidate"
    if spec.max_age is None:
        return None
    directives = [f"max-age={int(spec.max_age)}", "public"]
    if spec.immutable:
        directives.append("immutable")
    return ", ".join(directives)


# ----------------------------------------------------------------------
# Async file IO
# ----------------------------------------------------------------------


async def _read_bytes(path: Path) -> bytes:
    """Read a file fully, off the event loop when possible."""
    to_thread = getattr(asyncio, "to_thread", None)
    if to_thread is not None:  # Python 3.9+
        return await to_thread(path.read_bytes)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, path.read_bytes)


async def _stat(path: Path) -> os.stat_result:
    to_thread = getattr(asyncio, "to_thread", None)
    if to_thread is not None:
        return await to_thread(os.stat, str(path))
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, os.stat, str(path))


# ----------------------------------------------------------------------
# Response assembly
# ----------------------------------------------------------------------


def _looks_like_asset(relative: str) -> bool:
    """Return True when the relative path resembles a static asset.

    A path is treated as an asset when its **final** segment contains a dot,
    e.g. ``app.js``, ``logo.svg``, ``fonts/inter.woff2``. Pure routing paths
    such as ``settings/profile`` or ``dashboard`` are treated as virtual.
    """
    last_segment = relative.rsplit("/", 1)[-1]
    return "." in last_segment


def _content_type_for(path: Path) -> str:
    ctype, _encoding = mimetypes.guess_type(str(path))
    if not ctype:
        return "application/octet-stream"
    if ctype.startswith("text/") and "charset" not in ctype:
        return f"{ctype}; charset=utf-8"
    return ctype


async def _resolve_target(
    spec: StaticFiles,
    base_dir: Path,
    relative_path: str,
) -> Tuple[Optional[Path], bool]:
    """Resolve the on-disk target for ``relative_path``.

    Returns ``(path, is_spa_fallback)``. ``path`` is ``None`` when no file
    can be served (caller should emit 404).
    """
    target = _safe_join(base_dir, relative_path)
    if target is None:
        return None, False

    # Symlink policy
    try:
        is_symlink_root = target.is_symlink()
    except OSError:
        is_symlink_root = False
    if is_symlink_root and not spec.follow_symlinks:
        return None, False

    if target.is_dir():
        index_target = target / spec.index
        if index_target.is_file():
            return index_target, False
    elif target.is_file():
        return target, False

    if spec.spa and not _looks_like_asset(relative_path):
        spa_index = base_dir / spec.index
        if spa_index.is_file():
            return spa_index, True

    return None, False


def _apply_common_headers(
    response: WebResponse,
    spec: StaticFiles,
    stat_result: os.stat_result,
    etag_value: Optional[str],
) -> None:
    for name, value in spec.extra_headers:
        response.set_header(name, value)

    cache_control = _build_cache_control(spec)
    if cache_control is not None:
        response.set_header("Cache-Control", cache_control)

    if spec.last_modified:
        response.set_header("Last-Modified", _format_http_date(stat_result.st_mtime))

    if etag_value is not None:
        response.set_header("ETag", etag_value)

    response.set_header("Accept-Ranges", "none")


def _not_modified_response(
    spec: StaticFiles,
    stat_result: os.stat_result,
    etag_value: Optional[str],
) -> WebResponse:
    response = WebResponse(status_code=304)
    _apply_common_headers(response, spec, stat_result, etag_value)
    return response


# ----------------------------------------------------------------------
# Public factory
# ----------------------------------------------------------------------


Handler = Callable[[WebRequest], Awaitable[WebResponse]]


def build_static_handler(
    spec: StaticFiles,
    *,
    project_root: Optional[str] = None,
) -> Handler:
    """Build an async handler for the given :class:`StaticFiles` mount.

    The returned coroutine function is suitable for passing to
    :meth:`cullinan.web.gateway.router.Router.add_route`.
    """
    base_dir = spec.resolve_directory(project_root)
    if not base_dir.exists():
        logger.warning(
            "Static files directory does not exist at startup: %s "
            "(mounted at %s). Requests will return 404 until the directory "
            "becomes available.",
            base_dir,
            spec.url,
        )

    methods = frozenset(spec.methods)

    async def _handler(request: WebRequest) -> WebResponse:
        method = (request.method or "GET").upper()
        if method not in methods:
            return WebResponse.error(405, f"Method {method} not allowed")

        relative_path = _strip_prefix(request.path, spec.url)
        try:
            target, is_spa_fallback = await _resolve_target(
                spec, base_dir, relative_path
            )
        except OSError as exc:
            logger.debug(
                "Filesystem error while resolving %s under %s: %s",
                relative_path,
                base_dir,
                exc,
            )
            return WebResponse.error(404, "Not Found")

        if target is None:
            return WebResponse.error(404, "Not Found")

        try:
            stat_result = await _stat(target)
        except FileNotFoundError:
            return WebResponse.error(404, "Not Found")
        except OSError:
            return WebResponse.error(500, "Static file unreadable")

        etag_value: Optional[str] = (
            _compute_etag(stat_result) if (spec.etag and not spec.no_cache) else None
        )

        # Conditional request: If-None-Match
        if etag_value is not None:
            inm = request.headers.get("If-None-Match") if request.headers else None
            if inm and etag_value in {part.strip() for part in inm.split(",")}:
                return _not_modified_response(spec, stat_result, etag_value)

        # Conditional request: If-Modified-Since (only when no ETag match)
        if spec.last_modified and not spec.no_cache:
            ims_header = (
                request.headers.get("If-Modified-Since") if request.headers else None
            )
            if ims_header:
                ims_ts = _parse_http_date(ims_header)
                if ims_ts is not None and int(stat_result.st_mtime) <= int(ims_ts):
                    return _not_modified_response(spec, stat_result, etag_value)

        # Read body (skip for HEAD)
        if method == "HEAD":
            body: bytes = b""
        else:
            try:
                body = await _read_bytes(target)
            except OSError as exc:
                logger.error("Failed reading static file %s: %s", target, exc)
                return WebResponse.error(500, "Static file unreadable")

        content_type = _content_type_for(target)
        if is_spa_fallback:
            # SPA bundle entry is always HTML.
            content_type = "text/html; charset=utf-8"

        response = WebResponse(
            body=body,
            status_code=200,
            content_type=content_type,
        )
        # On HEAD, Content-Length should still reflect the real size.
        if method == "HEAD":
            response.set_header("Content-Length", str(stat_result.st_size))
        _apply_common_headers(response, spec, stat_result, etag_value)
        return response

    _handler.__cullinan_static_spec__ = spec  # type: ignore[attr-defined]
    _handler.__name__ = f"_static_handler_{spec.url.strip('/').replace('/', '_') or 'root'}"
    return _handler
