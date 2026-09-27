# Middleware and Module Boundary Example

This example explains two ideas that are easy to confuse:

- `@module` defines a runtime boundary for a package
- `@middleware` extends the request pipeline, not the application bootstrap model

> This example uses the **compatibility** middleware protocol
> (`process_request` / `process_response`). For new code, prefer the recommended
> onion protocol shown in [`examples/middleware_pipeline/`](../middleware_pipeline/);
> see [the middleware page](../../docs/wiki/middleware.md).

Run:

```bash
python -m examples.middleware_and_module
```

Endpoint:

- `GET /inventory/summary`

Response headers:

- `X-Cullinan-Example: middleware-and-module`
- `X-Module-Boundary: examples.middleware_and_module`

