# Assembly Snapshot Example

Teaches the **assembly-snapshot** query: after an application has started, ask
it — in a single call — what the assembly actually *holds*, surface by surface.

Cullinan rebuilds every gateway global at the boot boundary. Where the
[component-discovery example](../component_discovery_boundary/) reconciles
*declared vs assembled* **components** (`Application.get_declaration_diff()`),
this example reconciles the **registration surfaces**: the four gateway globals
`pipeline` / `router` / `dispatcher` / `exception_handler`, plus the container.

Run:

```bash
python -m examples.assembly_snapshot
```

## One call, every surface

`Application.get_assembly_snapshot()` returns a `gateway` mapping with the four
sub-surfaces and a `container` surface. Each surface carries the same three
fields — the vocabulary the component face already uses:

| Field | Meaning |
|---|---|
| `declared` | what the surface held **before** the boot boundary |
| `assembled` | what it holds **after** the boundary — what this assembly actually carries |
| `dropped` | `declared - assembled`: pre-boot entries the boundary discarded |

This is an **advanced / boundary** example: the recommended entry form is
`@application` + `@configure(...)` + `main()`, which starts a server. Reading an
assembly snapshot needs the application *object* without starting a server, so
this example reaches for the advanced entry class
`cullinan.application.Application` directly. `Application(...)` accepts either a
`@module` class or an `@application` entry method (here the entry method
`main`). Regular business code should stay on the recommended entry form.

```python
from cullinan.application import Application

app = Application(main)
app.build()
snapshot = app.get_assembly_snapshot()
print(snapshot.gateway["router"].assembled)
print(snapshot.gateway["router"].dropped)
print(snapshot.container.declared)
app.uninstall()
```

The return value is a module-private, read-only view (its type is not part of the
public export surface), and the query never materialises a lazy global: reading a
snapshot does not create the objects it reports on.

## The pre-boot route, side by side

The demo registers a route *before* the application starts:

```python
from cullinan.web.gateway import get_router

get_router().add_route("GET", "/pre-boot-check", handler=lambda request: None)
```

The boot boundary rebuilds the router, so that entry never reaches request
handling. It does not vanish from the report, though: the snapshot names it in
`gateway.router.dropped`, next to the assembled set. This is the whole point —
the entry is **dropped and still queryable**, not merely logged.

## Per-surface note: the pipeline is different

On a **successful** start the pipeline sub-surface's `dropped` is always empty.
A pre-boot `get_pipeline().add(...)` does not get dropped — it *refuses the
start* (see the [middleware page](../../docs/wiki/middleware.md)). So for the
pipeline, `dropped` is **present and empty**, and a snapshot that omitted the
field entirely would be a failure, not a silent omission. The other three
gateway surfaces only *record* a pre-boot registration; they do not refuse the
start, which is why `dropped` is where their side-by-side value shows.

## Expected output

`python -m examples.assembly_snapshot` prints:

```text
Assembly snapshot demo
========================================

One call: Application.get_assembly_snapshot()
  -> gateway{4 sub-surfaces} + container
  each surface: declared / assembled / dropped

gateway.pipeline
    declared : []
    assembled: []
    dropped  : []

gateway.router
    declared : ['GET /pre-boot-check']
    assembled: []
    dropped  : ['GET /pre-boot-check']

gateway.dispatcher
    declared : []
    assembled: ['router', 'pipeline', 'exception_handler', 'header_policy', 'return_value_handler', 'exception_resolver']
    dropped  : []

gateway.exception_handler
    declared : []
    assembled: []
    dropped  : []

container
    declared : ['examples.assembly_snapshot.app.services.ReportService']
    assembled: ['examples.assembly_snapshot.app.services.ReportService']
    dropped  : []

Notes
-----
* gateway.router.dropped names the route registered before the app
  started: the boot boundary rebuilds the router, so it is dropped.
  It stays queryable here instead of vanishing silently.
* gateway.pipeline.dropped is present and empty: on a successful start
  the boundary refuses a pre-boot pipeline registration rather than
  dropping it, so nothing is dropped (a missing field would be a
  failure, not a silent omission).
* The four gateway sub-surfaces are rebuilt at the boundary; the
  container surface reports the component reconciliation.
```

The `dispatcher` surface reports its wiring (what a dispatcher *holds* is the
collaborators it dispatches through), and the `container` surface reports the
same component reconciliation `get_declaration_diff()` exposes.

## When to reach for it

Reach for `get_assembly_snapshot()` when you need to answer "what did this
assembly actually end up with?" in one place — for diagnostics, for a startup
check, or to reconcile a registration made before the boot boundary. Regular
business code stays on `@application` + `@configure(...)`.
