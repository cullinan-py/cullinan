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

## Main exports

- `middleware`
- `Middleware`
- `MiddlewareChain`
- `BodyDecoderMiddleware`
- `get_middleware_registry()`
- `reset_middleware_registry()`

Legacy registration helpers still exist, but new code should favor decorator-based or startup-time registration through the active runtime.

## Guidance

- keep middleware thin and delegate business logic to injected services
- avoid storing request-scoped state on long-lived middleware instances
- let the gateway pipeline handle composition and ordering

## Example

```python
from cullinan.web.middleware import Middleware

class AuditMiddleware(Middleware):
    async def process_request(self, request):
        return None
```

For older middleware integrations, the application bootstrap can bridge legacy registrations into the gateway pipeline.

## See also

- [Web Runtime Guide](../web_runtime_guide.md)
- [Application Lifecycle](lifecycle.md)
