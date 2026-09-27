# -*- coding: utf-8 -*-
"""Declarative static-files specification.

A :class:`StaticFiles` instance describes **one** mount point. It is a pure data
object — registration is deferred to the runtime so the same spec can be reused
across Tornado / ASGI backends.

Typical usage::

    from cullinan import configure, application
    from cullinan.web import StaticFiles

    @configure(
        user_packages=["myapp"],
        static_files=[
            StaticFiles(url="/static", directory="static"),
            StaticFiles(url="/assets", directory="dist/assets",
                        max_age=31536000, immutable=True),
            StaticFiles(url="/", directory="dist", index="index.html", spa=True),
        ],
    )
    @application
    def main(): ...

Author: plumeink
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence, Tuple


def _normalise_url_prefix(url: str) -> str:
    if not url:
        raise ValueError("StaticFiles.url must be a non-empty string like '/static' or '/'.")
    if not url.startswith("/"):
        url = "/" + url
    # Collapse trailing slashes, but keep root "/" untouched.
    if url != "/" and url.endswith("/"):
        url = url.rstrip("/")
    return url


@dataclass(frozen=True)
class StaticFiles:
    """Declarative static files / SPA mount point.

    Attributes:
        url: URL prefix to mount under. ``"/"`` mounts at the root and is
            commonly combined with ``spa=True`` for client-side routed apps.
        directory: Local filesystem path to serve from. Relative paths are
            resolved against the **project root** at registration time, falling
            back to ``os.getcwd()``.
        index: File name served when the request maps to a directory
            (defaults to ``"index.html"``).
        spa: When ``True``, requests under the prefix that do not point to an
            existing file fall back to ``index`` and respond ``200``. Requests
            for paths that *look like* asset files (containing a ``.``) still
            return ``404`` so a missing JS/CSS/image bundle is not silently
            hidden behind ``index.html``.
        max_age: ``Cache-Control: max-age`` value in seconds. ``None`` disables
            the header.
        immutable: Adds ``immutable`` directive to ``Cache-Control`` (only
            sensible for content-hashed assets).
        no_cache: Forces ``Cache-Control: no-cache, no-store, must-revalidate``
            and disables ETag emission. Overrides ``max_age`` / ``immutable``.
        etag: When ``True`` (default), emits a strong ETag derived from
            ``(mtime_ns, size)`` and honours ``If-None-Match``.
        last_modified: When ``True`` (default), emits ``Last-Modified`` and
            honours ``If-Modified-Since``.
        methods: Allowed HTTP methods. ``GET`` and ``HEAD`` only by design.
        follow_symlinks: When ``False`` (default), symlinks pointing outside
            of ``directory`` are rejected with ``404``.
        extra_headers: Additional response headers applied to every served
            file.
    """

    url: str
    directory: str
    index: str = "index.html"
    spa: bool = False
    max_age: Optional[int] = None
    immutable: bool = False
    no_cache: bool = False
    etag: bool = True
    last_modified: bool = True
    methods: Tuple[str, ...] = ("GET", "HEAD")
    follow_symlinks: bool = False
    extra_headers: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # Normalise the URL prefix in-place. Dataclass is frozen, so use
        # object.__setattr__.
        object.__setattr__(self, "url", _normalise_url_prefix(self.url))

        if not self.directory:
            raise ValueError("StaticFiles.directory must be a non-empty path.")

        if self.spa and not self.index:
            raise ValueError("StaticFiles.spa requires an 'index' file name.")

        if self.max_age is not None and self.max_age < 0:
            raise ValueError("StaticFiles.max_age must be a non-negative integer.")

        normalised_methods = tuple(m.upper() for m in self.methods)
        for method in normalised_methods:
            if method not in ("GET", "HEAD"):
                raise ValueError(
                    f"StaticFiles only supports GET / HEAD, got {method!r}. "
                    "Mutating verbs should go through a controller."
                )
        object.__setattr__(self, "methods", normalised_methods)

        if isinstance(self.extra_headers, dict):
            object.__setattr__(
                self,
                "extra_headers",
                tuple((str(k), str(v)) for k, v in self.extra_headers.items()),
            )
        else:
            object.__setattr__(
                self,
                "extra_headers",
                tuple((str(k), str(v)) for k, v in self.extra_headers),
            )

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def resolve_directory(self, project_root: Optional[str] = None) -> Path:
        """Resolve the configured ``directory`` to an absolute :class:`Path`.

        Args:
            project_root: Optional anchor directory used when ``directory``
                is relative. Defaults to ``os.getcwd()`` when not supplied.

        Returns:
            Absolute, normalised path. Does **not** require the directory
            to exist — callers must check for that explicitly.
        """
        directory_path = Path(self.directory)
        if directory_path.is_absolute():
            return directory_path.resolve(strict=False)

        anchor = Path(project_root) if project_root else Path(os.getcwd())
        return (anchor / directory_path).resolve(strict=False)

    def route_pattern(self) -> str:
        """Return the wildcard URL pattern used to register the mount.

        ``"/"`` becomes ``"/**"`` so it serves every otherwise-unmatched path.
        """
        if self.url == "/":
            return "/**"
        return f"{self.url}/**"

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @classmethod
    def spa_app(
        cls,
        directory: str,
        *,
        url: str = "/",
        index: str = "index.html",
        max_age: Optional[int] = None,
    ) -> "StaticFiles":
        """Shortcut for serving a Single-Page Application bundle.

        Equivalent to ``StaticFiles(url=url, directory=directory,
        index=index, spa=True, max_age=max_age)``.
        """
        return cls(
            url=url,
            directory=directory,
            index=index,
            spa=True,
            max_age=max_age,
        )


def coerce_static_files(values: Optional[Sequence[object]]) -> Tuple[StaticFiles, ...]:
    """Normalise a sequence of user-provided declarations into ``StaticFiles``.

    Accepted item shapes:

    * ``StaticFiles`` instance — passed through.
    * ``dict`` — expanded as keyword arguments.
    * ``(url, directory)`` tuple — minimal positional form.

    Anything else raises :class:`TypeError` so misconfiguration fails loudly at
    startup instead of producing surprising 404s.
    """
    if values is None:
        return ()

    coerced: list[StaticFiles] = []
    for item in values:
        if isinstance(item, StaticFiles):
            coerced.append(item)
        elif isinstance(item, dict):
            coerced.append(StaticFiles(**item))
        elif isinstance(item, tuple) and len(item) == 2:
            coerced.append(StaticFiles(url=item[0], directory=item[1]))
        else:
            raise TypeError(
                "static_files entries must be StaticFiles instances, dicts, "
                "or (url, directory) tuples; got %r" % (item,)
            )
    return tuple(coerced)
