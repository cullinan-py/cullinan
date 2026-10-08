# Middleware Ownership Example

Show the two declarative middleware forms side by side and the object ownership
each one implies:

- **container-managed** — `configure(middlewares=[AuditMiddleware])` passes a
  *class* declared with `@component`; the framework container creates it, injects
  its declared dependencies and installs that same instance, so the pipeline and
  the container share one object;
- **externally-owned** — `configure(middlewares=[MarkerMiddleware()])` passes an
  *instance* the application created; the framework installs it as-is.

Run:

```bash
python -m examples.middleware_ownership
```

Endpoint:

- `GET /ownership` — returns the installed middleware in execution order plus the
  ownership of each form, and prints the same to the console.

## Middleware installed

| Middleware | Declared by | Form | Ownership |
|---|---|---|---|
| `AuditMiddleware` | `@configure(middlewares=[AuditMiddleware])` | class (`@component`) | container-managed (dependencies injected) |
| `MarkerMiddleware` | `@configure(middlewares=[MarkerMiddleware()])` | instance | externally-owned |
| `AccessLogMiddleware` | framework default | — | built-in |

`AuditMiddleware` declares a `log: AuditLog` dependency. Because the class is
declared with `@component`, the container resolves and injects that dependency
during startup — an unresolvable dependency would fail there, not on the first
request.

## Expected output

`GET /ownership` prints this to the console:

```text
middleware order (outermost first): ['AuditMiddleware', 'MarkerMiddleware', 'AccessLogMiddleware']
audit entries recorded by the container instance: ['/ownership']
```

and returns the same facts as JSON:

```json
{"order": ["AuditMiddleware", "MarkerMiddleware", "AccessLogMiddleware"], "container_managed": "AuditMiddleware", "externally_owned": "MarkerMiddleware", "audit_log_entries": ["/ownership"]}
```

## Observable effects

Every accepted response carries the header of both declared layers:

```text
X-Audit-Entries: 1
X-Marker: externally-owned
```

`X-Audit-Entries` is the number of requests the container-owned middleware has
recorded into its injected `AuditLog`, so a changing value shows the middleware
type that actually ran is the container's instance.

## Port

This example binds `server_port=4087`.

For controlling the built-in layer and the legacy ordering, see
[`examples/middleware_control/`](../middleware_control/); for the declarative
entry on its own, see [`examples/middleware_pipeline/`](../middleware_pipeline/).
Background: [the middleware page](../../docs/wiki/middleware.md).
