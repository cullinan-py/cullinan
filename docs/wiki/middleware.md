title: "Middleware"
slug: "middleware"
module: ["cullinan.web.middleware"]
tags: ["middleware"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/wiki/middleware.md"
related_tests: ["tests/web/test_web_runtime.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-05-30T00:00:00Z"
pr_links: []

# Middleware

Cullinan middleware participates in the unified Web Runtime pipeline.

## Two middleware protocols

Cullinan supports two middleware protocols. New code should use the onion
protocol; the hook-based protocol is kept for backward compatibility.

### Recommended: onion protocol

Subclass `cullinan.web.gateway.GatewayMiddleware` and implement
`async def __call__(self, request, call_next)`. The middleware runs inside the
gateway pipeline, so it can inspect and rewrite both the request and the
response:

```python
from cullinan.web.gateway import GatewayMiddleware


class AuditMiddleware(GatewayMiddleware):
    async def __call__(self, request, call_next):
        response = await call_next(request)
        response.set_header("X-Audited", "1")
        return response
```

Declare middleware at startup through the top-level `configure()` entry point.
The pipeline is assembled at the framework startup point, so ordering follows
the declaration and never the moment a middleware happened to be registered:

```python
from cullinan import application, configure


@configure(user_packages=["your_app"], middlewares=[AuditMiddleware()])
@application
def main(): ...
```

Ordering is declared, never timed. `before=` / `after=` anchor a middleware to
another one, matched by instance, class or class name. `priority=` is an
optional global key: a **lower** priority runs on a **more outer** layer, and the
default is `100` — the same direction and default as the legacy
`@middleware(priority=...)` decorator. Use it to declare "this one is the
outermost layer":

```python
# priority 10 < the default 100, so the audit wrapper ends up outermost
configure(middlewares=[(AuditMiddleware(), {"priority": 10})])
```

With no declaration at all, the first declared middleware stays the outermost
layer.

### Controlling the built-in layer

The framework installs a built-in layer of its own — the access-log middleware.
It is declarative too: `configure(builtin_middleware=[...])` replaces it with
your own layer, and `builtin_middleware=[]` switches it off entirely.

```python
from cullinan import application, configure
from cullinan.web.gateway import GatewayMiddleware


class MyAccessLog(GatewayMiddleware):
    async def __call__(self, request, call_next):
        response = await call_next(request)
        print(request.method, request.path, response.status_code)
        return response


# Replace the built-in access log with an equivalent implementation.
@configure(user_packages=["your_app"], builtin_middleware=[MyAccessLog()])
@application
def main(): ...
```

Pass an empty list to keep the built-in layer out of the pipeline altogether:

```python
configure(user_packages=["your_app"], builtin_middleware=[])
```

Omitting the parameter keeps the framework default, so existing applications are
unaffected. Whatever the built-in layer ends up being, it takes part in the same
declarative ordering as `middlewares`.

### Legacy: `process_request` / `process_response`

The hook pair on `cullinan.web.middleware.Middleware` still works and is
auto-bridged into the gateway pipeline — one layer per legacy middleware. Each
bridged layer is ordered by the same declarative `priority` key as the built-in
and declared layers, so a legacy `@middleware(priority=10)` lands on a more
outer layer than the built-in access log (default `100`). Keep it only for
existing integrations:

```python
from cullinan.web.middleware import Middleware, middleware


@middleware(priority=100)
class LegacyAuditMiddleware(Middleware):
    def process_request(self, request):
        print(f"Request: {request.method} {request.path}")
```

Note that this protocol is capability-limited. If any legacy `process_request`
hook returns `None`, the request is treated as rejected: the legacy chain stops
right there, no remaining middleware runs, and the handler is never reached. The
bridge then substitutes a **fixed** error response — status `403` with the body
`Request rejected by middleware`
(`cullinan/web/gateway/pipeline.py:447`). That short-circuit response cannot be
customized from the hook protocol: no hook can set a different status code, body
or headers. The legacy protocol can only accept or reject a request; it cannot
shape the rejection itself.

For a custom short-circuit response (a different status, a JSON body, extra
headers), use the onion protocol and return your own response from `__call__`
without calling `call_next`:

```python
from cullinan.web.gateway import GatewayMiddleware, WebResponse


class ApiKeyGate(GatewayMiddleware):
    async def __call__(self, request, call_next):
        if request.get_header("X-Api-Key") != "secret":
            # returned as-is; the framework does not overwrite it
            return WebResponse.json({"error": "missing api key"}, status_code=401)
        return await call_next(request)
```

## Introspection

`cullinan.web.gateway.get_pipeline().list_middleware()` lists the installed
middleware in execution order, where index `0` is the outermost layer. It is the
pipeline counterpart of `Router.get_all_routes()`.

## Guidance

- keep middleware thin and delegate business logic to injected services
- avoid storing request-scoped state on long-lived middleware instances
- let the gateway pipeline handle composition and ordering
- prefer the onion protocol for new code

## See also

- [Web Runtime Guide](../web_runtime_guide.md)
- [Application Lifecycle](lifecycle.md)
