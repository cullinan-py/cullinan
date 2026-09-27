# Middleware Pipeline Example

Declare gateway middleware through the recommended public entry, then read the
resulting layer order back with the public reflection API.

Run:

```bash
python -m examples.middleware_pipeline
```

Endpoints:

- `GET /pipeline` — returns the installed middleware in execution order, and
  prints the same list to the console
- `GET /pipeline/echo` — a normal endpoint that is only reachable when the
  outermost gate lets the request through

## Middleware declared

`root.py` declares both middleware through `@configure(middlewares=[...])`:

| Middleware | Declaration | Layer |
|---|---|---|
| `ApiKeyGateMiddleware` | `{"priority": 0}` — below the default `100` | outermost |
| `RequestMarkerMiddleware` | default priority | inner |

The order is a **declaration**, not a registration trick: the pipeline is
assembled at the framework startup point, so it cannot depend on when each class
happened to be registered. That is why the gate reliably sees every request
first.

## Expected output

`GET /pipeline` prints this to the console:

```text
middleware order (outermost first): ['ApiKeyGateMiddleware', 'RequestMarkerMiddleware', 'AccessLogMiddleware']
```

and returns the same list as JSON:

```json
{"order": ["ApiKeyGateMiddleware", "RequestMarkerMiddleware", "AccessLogMiddleware"]}
```

`AccessLogMiddleware` is the built-in layer the framework always adds; the two
declared middleware sit outside/inside it as declared.

## Observable effects

| Request | Result |
|---|---|
| `GET /pipeline` without the key | `403` `{"error": "missing demo key"}` |
| `GET /pipeline` with `X-Demo-Key: let-me-in` | `200`, plus headers `X-Demo-Gate: passed` and `X-Demo-Marker: middleware-pipeline` |
| `GET /pipeline/echo` without the key | `403` |
| `GET /pipeline/echo` with the key | `200` `{"message": "the gate let this request through"}` |

Verify the gate really is the outermost layer — the `403` comes back before the
endpoint is ever reached:

```bash
curl -i http://127.0.0.1:4085/pipeline
curl -i -H 'X-Demo-Key: let-me-in' http://127.0.0.1:4085/pipeline
```

## Port

This example binds `server_port=4085`; ports 4081–4084 are taken by the other
examples.

This example uses the recommended onion protocol — the compatibility protocol (`process_request` / `process_response`) is covered by [`examples/middleware_and_module/`](../middleware_and_module/) and described on [the middleware page](../../docs/wiki/middleware.md).
