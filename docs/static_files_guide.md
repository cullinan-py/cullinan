title: "Static Files and SPA Guide"
slug: "static-files-guide"
module: ["cullinan.web.static"]
tags: ["web", "static", "spa", "caching"]
author: "Cullinan"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/static_files_guide.md"
related_tests: ["tests/web/test_static_files.py"]
related_examples: ["examples/static_files_and_spa"]
estimate_pd: 1.0
last_updated: "2026-06-29T00:00:00Z"
pr_links: []

# Static Files and SPA Guide

Cullinan ships a declarative static-files API that works identically under
the Tornado and ASGI runtimes. Mounts are described as data on
`@configure(...)`; the framework registers them on the gateway router at
startup so they coexist with regular controllers and middleware without
engine-specific glue code.

> **Recommended for:** product teams shipping bundled SPAs, design teams
> shipping branded asset directories, and services that need predictable
> caching headers without standing up a separate CDN tier in development.

## Why a first-class API

Most Python web frameworks treat static files as either ad-hoc
`send_file` calls or as a settings dictionary deep inside a server
adapter. Cullinan promotes them to a first-class declaration because the
public path of the framework is decorator-first: routing, controllers,
middleware, and now static mounts are all expressed at the application
boundary and assembled by the runtime.

The result is a configuration that survives switching between Tornado
and ASGI, packaging with Nuitka / PyInstaller, and integration testing
through `main.get_asgi_app()` — without rewriting any handlers.

## Public API

### `cullinan.web.StaticFiles`

A frozen dataclass describing one mount point. Pass instances (or
matching `dict`s / `(url, directory)` tuples) to the `static_files`
parameter of `@configure(...)`:

```python
from cullinan import application, configure
from cullinan.web import StaticFiles

@configure(
    user_packages=["myapp"],
    static_files=[
        StaticFiles(url="/static", directory="static"),
        StaticFiles(url="/assets", directory="dist/assets",
                    max_age=31536000, immutable=True),
        StaticFiles.spa_app(directory="dist"),
    ],
)
@application
def main(): ...
```

Fields:

| Field | Default | Purpose |
| --- | --- | --- |
| `url` | required | URL prefix. `"/"` mounts at the root (typical SPA case). |
| `directory` | required | On-disk path; relative paths resolve against the project root, falling back to `os.getcwd()`. |
| `index` | `"index.html"` | File served when the request maps to a directory or, in SPA mode, when no file matches. |
| `spa` | `False` | Enables the SPA fallback strategy described below. |
| `max_age` | `None` | Adds `Cache-Control: max-age=<seconds>, public`. |
| `immutable` | `False` | Adds the `immutable` directive (only for content-hashed assets). |
| `no_cache` | `False` | Forces `no-cache, no-store, must-revalidate` and disables ETag emission. |
| `etag` | `True` | Emits a strong ETag derived from `(mtime_ns, size)` and honours `If-None-Match`. |
| `last_modified` | `True` | Emits `Last-Modified` and honours `If-Modified-Since`. |
| `methods` | `("GET", "HEAD")` | Allowed methods. Only `GET` and `HEAD` are accepted by design. |
| `follow_symlinks` | `False` | Reject symlinks pointing outside `directory`. |
| `extra_headers` | `()` | Additional response headers applied to every served file. |

### `StaticFiles.spa_app`

Shortcut for the SPA-at-root use case:

```python
StaticFiles.spa_app(directory="dist")  # url="/", spa=True, index="index.html"
```

## Behaviour

### Engine neutrality

A `StaticFiles` declaration becomes one or more `RouteEntry` rows on the
gateway `Router`. The Tornado and ASGI adapters route everything through
`Dispatcher.dispatch()`, so the same files, headers, and status codes
appear under either backend.

> **The `/static` prefix is not special.** Cullinan does not pass Tornado a
> `static_path` setting, so Tornado never auto-registers its built-in
> `StaticFileHandler` on `/static/`. A `StaticFiles(url="/static", ...)` mount
> is served entirely through the router on both engines — exactly like any
> other prefix.

### Routing precedence

Cullinan's router prefers static and parameterised segments over
wildcards. That means `@controller(url="/api/users")` always wins over a
broad `StaticFiles(url="/")` mount. Order in the list only matters when
two mounts share a prefix.

### SPA fallback

`spa=True` opts into the convention used by Vue, React Router, and
Angular bundles:

- Existing files are served verbatim (`/assets/main.js` → real file).
- A path that does **not** look like a file (no `.` in the final segment,
  e.g. `/settings/profile`) and does not match a real file falls back to
  `index.html` with status `200`.
- A path that **does** look like a file (`/assets/missing.js`) returns
  `404` so a broken asset URL is never silently hidden behind the
  index page.

### Caching contract

- ETags use BLAKE2 over `(mtime_ns, size)` and are deterministic across
  processes mounting the same file.
- `If-None-Match` and `If-Modified-Since` both produce a fully-formed
  `304 Not Modified` response with caching headers intact.
- `no_cache=True` disables ETag emission so intermediaries cannot reuse
  the previous body.

### Security defaults

- Path traversal is blocked at resolution time using
  `Path.resolve()`/`relative_to(...)` so requests such as
  `/static/../etc/passwd` return `404`.
- Symlinks pointing outside the mount directory are rejected unless
  `follow_symlinks=True` is set explicitly.
- Mutating verbs (`POST`, `PUT`, `DELETE`, `PATCH`) are never registered.

### Limitations (v1)

- Responses are fully buffered. Streaming and HTTP `Range` requests are
  on the roadmap; declare them in your CDN tier for very large assets.
- Compression (`gzip` / `br`) is not yet auto-negotiated. Pre-compressed
  assets can be served by adding the appropriate `Content-Encoding` via
  `extra_headers` on a dedicated mount.

## Recipes

### A classic `/static/*` mount

```python
StaticFiles(url="/static", directory="static", max_age=3600)
```

Equivalent to the pattern shipped by Flask `send_from_directory` or
FastAPI's `StaticFiles` mount.

### Hashed asset bundles

```python
StaticFiles(
    url="/assets",
    directory="dist/assets",
    max_age=31536000,
    immutable=True,
)
```

Use with Vite / webpack hashed filenames so cached clients never
revalidate.

### SPA with API on the same origin

```python
@configure(
    user_packages=["myapp"],
    static_files=[
        StaticFiles(url="/assets", directory="dist/assets",
                    max_age=31536000, immutable=True),
        StaticFiles.spa_app(directory="dist"),
    ],
)
@application
def main(): ...
```

Cullinan keeps `/api/...` controllers in front of the SPA fallback —
your API responds first, the SPA fills in everything else.

## Verification

The behaviour above is covered by `tests/web/test_static_files.py`,
which exercises the dispatcher path, the Tornado adapter, and the ASGI
adapter against a temporary site fixture. Run them with:

```bash
python -m pytest tests/web/test_static_files.py -v
```

## See also

- `examples/static_files_and_spa/` — runnable demo
- [Web Runtime Guide](web_runtime_guide.md)
- [Framework Semantics](framework_semantics.md)
- [Examples](examples.md)
