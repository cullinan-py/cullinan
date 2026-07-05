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
from cullinan import (
    WebRequest, WebResponse,          # Unified request/response
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
from cullinan import GatewayMiddleware, get_pipeline

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

**Backward compatibility**: Old `@middleware` classes are auto-bridged via `LegacyMiddlewareBridge`.

### 7. OpenAPI Integration

```python
from cullinan import OpenAPIGenerator, get_router

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
| `Handler` class | Deprecated (warning) | v3.0 |
| `HttpResponse` | Deprecated (auto-bridged) | v3.0 |
| `EncapsulationHandler.add_url()` | Internal only | v3.0 |
| `self.write()` in controllers | Deprecated | v3.0 |
| Old middleware (`Middleware` base) | Auto-bridged | v3.0 |
