title: "Web Runtime Guide"
slug: "web-runtime-guide"
module: ["cullinan.web.gateway", "cullinan.transport.adapter"]
tags: ["web", "runtime", "gateway"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/web_runtime_guide.md"
related_tests: ["tests/web/test_web_runtime.py"]
related_examples: ["examples/minimal_app", "examples/middleware_and_module"]
estimate_pd: 1.5
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# Web Runtime Guide

Cullinan's current HTTP runtime is transport-agnostic. Shared request/response behavior lives in `cullinan.web.gateway`, while server-specific integration lives in `cullinan.transport.adapter`.

> **Recommended application path:** keep most business code at controller level and start applications from the top-level `cullinan` API.  
> **Advanced runtime work:** if you need explicit runtime orchestration or adapter internals, continue in [Internals & Extensions](internals/index.md).

## Public API surface

### Gateway

- `WebRequest`
- `WebResponse`
- `WebHeaders`
- `WebCookies`
- `Router`
- `Dispatcher`
- `MiddlewarePipeline`
- `ExceptionHandler`
- `WebRuntime`

### Adapters

- `WebAdapter`
- `TornadoAdapter`
- `ASGIAdapter`

Treat these adapters as transport backends, not as the recommended entrypoint
for normal controller-driven application code.

## Controller-level usage

Most applications stay at the controller layer and let the framework build `WebResponse` objects from return values.

```python
from cullinan.web.controller import controller, get_api

@controller(url="/health")
class HealthController:
    @get_api(url="/")
    async def health(self):
        return {"status": "ok"}
```

The dispatcher converts plain return values into `WebResponse` instances and applies header policy plus middleware.

## Low-level gateway usage

For runtime customization, you can work with the gateway layer directly.

```python
import asyncio

from cullinan.web.gateway import Dispatcher, Router, WebRequest

router = Router()
router.add_route("GET", "/health", handler=lambda: {"status": "ok"})
dispatcher = Dispatcher(router=router)

request = WebRequest(method="GET", path="/health")
response = asyncio.run(dispatcher.dispatch(request))
assert response.status_code == 200
```

## Response model

`WebResponse` supports:

- text / json helpers
- explicit status codes
- repeated headers
- cookie emission
- freezing before adapter write-out

Example:

```python
from cullinan.web.gateway import WebResponse

response = WebResponse.json({"ok": True})
response.set_cookie("sid", "abc", http_only=True)
response.freeze()
```

## Runtime switching

`WebRuntime` tracks the active runtime instance and supports staged replacement / draining. This is useful when a server or adapter swaps runtime state while in-flight requests still exist.

The drain bound is configurable. `WebRuntimeConfig.drain_timeout` (default `30.0`
seconds) is the timeout the finalise path hands to the application context while
it waits for request scopes to finish. It is passed through the runtime
configuration:

```python
from cullinan.web.gateway import WebRuntimeConfig

runtime_config = WebRuntimeConfig(drain_timeout=10.0)
```

Leaving the field at its default reproduces the previous behaviour exactly,
because `30.0` is the value the shutdown call used to hard-code.

## Middleware and exception flow

- `MiddlewarePipeline` composes gateway middleware
- legacy `@middleware` registrations are bridged into the gateway pipeline as individual layers
- `ExceptionHandler` turns uncaught exceptions into HTTP responses

## Migration notes

Use these names in new documentation and code:

- `WebRequest` instead of legacy request wrappers
- `WebResponse` instead of legacy response wrappers
- `WebAdapter` instead of legacy adapter naming

See also:

- [RESTful API wiki](wiki/restful_api.md)
- [Architecture](architecture.md)
