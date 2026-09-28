# Migration Guide: v0.9x → v0.93

> **Cullinan Framework** — Comprehensive migration guide for upgrading from v0.9x to v0.93.

> **Upgrade-only page:** keep this page for version transition work, not for first-time onboarding.

## Overview of Changes

Cullinan v0.93 is a major architectural rewrite introducing:

| Feature | v0.9x | v0.93 |
|---------|-------|------|
| **HTTP Engine** | Tornado only | Tornado or ASGI (configurable) |
| **Request Handling** | One Handler per URL (Servlet-per-URL) | Single Dispatcher (Spring-style) |
| **Request Object** | `tornado.httputil.HTTPServerRequest` | `WebRequest` (transport-agnostic) |
| **Response Object** | `HttpResponse` + `self.write()` | `WebResponse` (factory methods) |
| **Routing** | Dynamic `type('Servlet'...)` classes | Prefix-tree Router |
| **Middleware** | Init-only, not in request pipeline | Onion-model pipeline for every request |
| **Tornado Dependency** | Required | Optional (`pip install cullinan[tornado]`) |
| **ASGI Support** | None | Full ASGI 3.0 (uvicorn/hypercorn) |
| **WebSocket** | Tornado only | Tornado + ASGI |
| **OpenAPI** | None | Auto-generated from routes |

## Installation

```bash
# Tornado mode
pip install cullinan[tornado]

# ASGI mode (uvicorn)
pip install cullinan[asgi]

# Full install
pip install cullinan[full]
```

## Step-by-Step Migration

### 1. Import Path Changes

Keep existing controller/service imports as-is, but use the new Web entry names:

```python
# v0.9x — still works in v0.93
from cullinan.web.controller import controller, get_api, post_api
from cullinan.core.services import service, Service
from cullinan.core import Inject

# v0.93 — new semantic imports available
from cullinan import WebRequest, WebResponse   # Unified request/response

# Gateway layer: routing, dispatch, middleware pipeline and OpenAPI spec
from cullinan.web.gateway import (
    Router, Dispatcher,               # Gateway layer
    GatewayMiddleware, CORSMiddleware,# Middleware pipeline
    OpenAPIGenerator,                 # OpenAPI spec
)

# Advanced transport integration stays explicit
from cullinan.transport.adapter import ASGIAdapter, TornadoAdapter, WebAdapter
```

### 2. Controller Changes

#### v0.9x: Controller methods used Tornado `self.write()`

```python
# v0.9x — handler operates on tornado internals
@controller(url='/api/users')
class UserController:
    @get_api(url='/{id}')
    async def get_user(self, url_params=None):
        user_id = url_params.get('id')
        # ... business logic ...
        return HttpResponse(body=user_data, status=200)
```

#### v0.93: Controller methods return `WebResponse`

```python
# v0.93 — transport-agnostic, returns WebResponse
from cullinan import WebResponse

@controller(url='/api/users')
class UserController:
    user_service: UserService = Inject()

    @get_api(url='/{id}')
    async def get_user(self, id):
        user = self.user_service.get_by_id(id)
        if not user:
            return WebResponse.error(404, "User not found")
        return WebResponse.json(user)
```

**Backward compatibility**: The old `HttpResponse` return type still works — the `Dispatcher` auto-converts it.

### 3. Response Object Migration

| v0.9x | v0.93 Equivalent |
|-------|-----------------|
| `HttpResponse(body=data, status=200)` | `WebResponse.json(data)` |
| `HttpResponse(body="text", status=200)` | `WebResponse.text("text")` |
| `HttpResponse(body=data, status=404)` | `WebResponse.error(404, "msg")` |
| `return {"key": "value"}` (dict) | `return {"key": "value"}` (auto-JSON, still works) |
| `return None` | `return None` (auto 204 No Content) |

### 4. Running the Application

#### v0.9x: Tornado only

```python
from cullinan.public_api import run
run()  # legacy direct startup entrypoint
```

#### v0.94a1: Prefer an entry method, then choose explicit runtime helpers only when needed

```python
from cullinan import application, configure

@configure(user_packages=["myapp"])
@application
def main(): ...

main()

# For an external ASGI server, prefer the entry-method helper
app = main.get_asgi_app()
# Then: uvicorn myapp:app
```

Environment variable: `CULLINAN_ENGINE=asgi`, or config: `server_engine='auto'` / `'asgi'` / `'tornado'`.

### 5. Configuration Changes

```python
from cullinan import configure

configure(
    user_packages=['myapp'],
    # New v0.93 options:
    # server_engine='auto',           # 'auto', 'tornado', or 'asgi'
    # asgi_server='uvicorn',          # 'uvicorn' or 'hypercorn'
    # route_trailing_slash=False,
    # route_case_sensitive=True,
    # debug=False,
)
```

### 6. Middleware Migration

#### v0.9x: Middleware registered but not in request pipeline

```python
from cullinan.web.middleware import Middleware, middleware

@middleware(order=1)
class AuthMiddleware(Middleware):
    def process_request(self, request):
        # was initialized at startup, but not called per-request
        pass
```

#### v0.93: Middleware in the onion pipeline

```python
from cullinan.web.gateway import GatewayMiddleware, get_pipeline

class AuthMiddleware(GatewayMiddleware):
    async def __call__(self, request, call_next):
        token = request.get_header('Authorization')
        if not token:
            return WebResponse.error(401, "Unauthorized")
        response = await call_next(request)
        return response

# Register
get_pipeline().add(AuthMiddleware())
```

**Startup resets this entry point.** `get_pipeline().add(...)` writes into the
pipeline that exists *before* boot; the gateway globals are rebuilt when the
application is assembled, so anything registered this way is reset at startup and
never handles a request. The reset is no longer silent — it leaves one diagnostic
naming the dropped entries and how many there were. Declare middleware through
`configure(middlewares=[...])` or the `@middleware` decorator instead: those are
read by the assembly and survive it.

The support level is the same as its behaviour: `get_pipeline().add(...)` is a
runtime-introspection, advanced-use and testing entry point, *not* the recommended
way for an application or a library to integrate middleware. `Runtime.warmup()`
rebuilds the gateway globals — pipeline, router, dispatcher and exception handler —
so the entries it discards are announced in one diagnostic rather than dropped
silently. Integrate middleware through the declarative entries:
`configure(middlewares=[...])` or the `@middleware` decorator.

**Backward compatibility**: Old `@middleware` classes are still auto-bridged into the gateway pipeline — one layer per legacy middleware.

#### v0.96a1: Legacy middleware join the declarative order

Legacy `@middleware` classes used to be collapsed into a single bridge layer
that always sat *inside* the built-in access-log layer, so a legacy `priority`
could not move it — the priority only ranked middleware within the legacy chain
and never crossed the bridge boundary. Each legacy middleware is now bridged as
its own pipeline layer and ordered by the same declarative `priority` key as the
declared and built-in layers, so a low legacy `priority` can now place a legacy
middleware outside the built-in layer.

**Who is affected.** Only applications that use the legacy middleware protocol
(`@middleware(priority=...)` / `cullinan.web.middleware`) are affected, and the
change is visible only when a legacy middleware declares a priority other than
the default `100`, or when a legacy layer interacts with a declared
`configure(middlewares=[...])` entry that declares its own priority.

| Scenario | Before (outer → inner) | After (outer → inner) | Visible change? |
|---|---|---|---|
| no priority declared (default `100`) | built-in access log, legacy | built-in access log, legacy | no |
| legacy `priority` below `100` (e.g. `50`) | built-in access log, legacy | legacy, built-in access log | **yes** — the legacy layer now wraps the built-in layer |
| legacy `priority` above `100` (e.g. `150`) | built-in access log, legacy | built-in access log, legacy (still inside) | no |
| two legacy peers with the *same* priority (e.g. both default `100`) | built-in access log, then the peers in declaration order | built-in access log, then the peers in declaration order | no — the tie keeps the declaration order |

The relative order *between* legacy middleware is unchanged, and so is the
request/response unwinding order. Only the placement of a legacy layer that
declares a priority below the built-in layer's `100` changes: it now wraps the
built-in layer instead of sitting inside it.

**Where the `priority` order is decided.** The `priority` key fixes the relative
order of two legacy middleware only when their priorities **differ**; in that
case the order is determined by the declared priority values, and it does not
depend on which of them was registered first. When two legacy middleware declare
the **same** priority they are peers, and the order among those peers is broken
by their **declaration order** — the order in which they are registered through
`@middleware` / imported. Within a module that is the source order, so the
resolved order is deterministic: the same declarations always produce the same
order. To make the order independent of the declaration order, give
same-priority peers distinct explicit priorities.

**What to check.** Most applications need no change — with the default priority
the resolved order is identical. Only if you relied on the whole legacy chain
always sitting inside the built-in layer, and assumed a legacy `priority` could
never cross the bridge boundary, review the `priority` values you declared and
confirm the new placement matches your intent.

**Introspection.** `cullinan.web.gateway.get_pipeline().list_middleware()`
reports one entry per legacy middleware — the entry count goes from a single
bridge entry to one entry per registered middleware — and each entry is named
after the real middleware instead of after the bridge, so the resolved order is
directly readable.

The built-in layer is declarative too: `configure(builtin_middleware=[...])`
replaces it, and `configure(builtin_middleware=[])` switches it off.

### 7. OpenAPI Integration

```python
from cullinan.web.gateway import OpenAPIGenerator, get_router

# Auto-generate spec from all registered routes
gen = OpenAPIGenerator(
    title='My API',
    version='1.0.0',
    description='My awesome API',
)

# Register /openapi.json and /openapi.yaml endpoints
gen.register_spec_routes()

# Or get the spec programmatically
spec_dict = gen.to_dict()
json_str = gen.to_json()
```

### 8. WebSocket Changes

#### v0.9x: Tornado WebSocket only

```python
@websocket_handler(url='/ws/chat')
class ChatHandler:
    def on_open(self):
        pass
    def on_message(self, message):
        self.write_message(f"echo: {message}")
    def on_close(self):
        pass
```

#### v0.93: Same API, works with both Tornado and ASGI

The `@websocket_handler` API is unchanged. When running in ASGI mode, WebSocket connections are handled natively via the ASGI WebSocket protocol.

### 9. Parameter System

The `cullinan.web.params` system (`Path`, `Query`, `Body`, `Header`) is unchanged and works identically in v0.93. Parameters are now resolved by the `Dispatcher` instead of Tornado handlers.

## Architecture Comparison

### v0.9x Architecture

```
Request → Tornado → Dynamic Handler(per-URL) → Controller method → self.write()
```

### v0.93 Architecture

```
Request → Adapter(Tornado/ASGI) → WebRequest → Middleware Pipeline
  → Dispatcher → Router → Controller method → WebResponse
  → Adapter → Native Response
```

## Breaking Changes

1. **`tornado` is no longer a required dependency** — install with `pip install cullinan[tornado]` if you need it.
2. **`Handler` base class** is deprecated — controllers no longer inherit from `tornado.web.RequestHandler`.
3. **Direct Tornado API usage** (`self.set_status()`, `self.write()`, `self.finish()`) in controllers is deprecated — use `WebResponse` instead.

## Deprecation Timeline

| Item | v0.93 Status | Planned Removal |
|------|-------------|-----------------|
| `Handler` class | Deprecated (warning) | End of the deprecation window |
| `HttpResponse` | Deprecated (auto-bridged) | End of the deprecation window |
| `EncapsulationHandler.add_url()` | Internal only | End of the deprecation window |
| `self.write()` in controllers | Deprecated | End of the deprecation window |
| Old middleware (`Middleware` base) | Auto-bridged | End of the deprecation window |

Removal versions are not hand-written. Each is derived from the release line
the surface was deprecated on plus a fixed deprecation window, so the value
this table shows stays fixed instead of drifting one minor further out on each
release.
