# Middleware Pipeline Control Example

Show two pipeline-assembly controls through one `@configure(...)` call:

- **replace the built-in layer** — `builtin_middleware=[QuietAccessLogMiddleware()]`
  installs your own access-log layer instead of the framework default; pass
  `builtin_middleware=[]` to switch the built-in layer off entirely;
- **unify the ordering** — a legacy `@middleware(priority=...)` class joins the
  pipeline as its own layer, ordered by the same declarative `priority` key as
  the declared and built-in layers.

Run:

```bash
python -m examples.middleware_control
```

Endpoint:

- `GET /control` — returns the installed middleware in execution order, and
  prints the same list to the console.

## Middleware installed

| Middleware | Declared by | Priority | Layer |
|---|---|---|---|
| `LegacyAuditMiddleware` | `@middleware(priority=10)` (legacy hook protocol) | 10 — below the default `100` | outermost |
| `TraceHeaderMiddleware` | `@configure(middlewares=[...])` (onion protocol) | default `100` | middle |
| `QuietAccessLogMiddleware` | `@configure(builtin_middleware=[...])` | default `100` | inner |

The legacy hook sits **outside** the declared middleware because it declares the
lower priority — the hook protocol and the onion protocol share one ordering
instead of the legacy chain being wrapped as a single opaque layer.

## Expected output

`GET /control` prints this to the console:

```text
middleware order (outermost first): ['LegacyAuditMiddleware', 'TraceHeaderMiddleware', 'QuietAccessLogMiddleware']
```

and returns the same list as JSON:

```json
{"order": ["LegacyAuditMiddleware", "TraceHeaderMiddleware", "QuietAccessLogMiddleware"]}
```

## Observable effects

Every accepted response carries `X-Control-Trace`, written outermost-first:

```text
X-Control-Trace: legacy-outer>declared
```

Read it outermost (`legacy-outer`) to innermost (`declared`): the legacy hook ran
on a more outer layer, the declared middleware on the next one in.

## Port

This example binds `server_port=4086`; ports 4081–4085 are taken by the other
examples.

For the declarative entry on its own, see
[`examples/middleware_pipeline/`](../middleware_pipeline/); for the compatibility
protocol on its own, see
[`examples/middleware_and_module/`](../middleware_and_module/). Background:
[the middleware page](../../docs/wiki/middleware.md).
