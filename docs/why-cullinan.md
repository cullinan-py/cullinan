title: "What Cullinan Is"
slug: "why-cullinan"
module: []
tags: ["docs", "positioning", "overview"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/why-cullinan.md"
related_tests: ["tests/integration/test_positioning_claims.py"]
related_examples: ["examples/minimal_app", "examples/graceful_shutdown"]
estimate_pd: 1.0
last_updated: "2026-10-25T00:00:00Z"
pr_links: []

# What Cullinan Is

Cullinan is a Python web framework in which the application is declared, not
assembled: you mark one entry method, declare services and controllers as
ordinary decorated classes, and the framework resolves the object graph, the
middleware order and the request path for you — over either a Tornado or an ASGI
backend, without changing your code.

That is the whole claim. Everything else on this page exists to make it
checkable rather than aspirational.

## Why this page is mostly a table

A framework's description is the easiest thing to inflate and the hardest thing
to audit. "Fast", "lightweight", "production-ready" cost nothing to write and
cannot be falsified, which is exactly why they are worth nothing to a reader
deciding whether to depend on the project.

So the claims here are the ones that can be checked by a machine, and each one
names its evidence. The list below is extracted and verified by
`scripts/check_claims.py`, which fails when a claim loses its evidence — a
document that shrinks is more honest than a document that keeps claiming.

## The claims, with evidence

Each entry below is ``{id, claim, evidence: [path...], symbols: ["path::Name"...]}``.
A path is a file or directory that must exist; a symbol is a declaration that
must be present in that file.

```json
{
  "claims": [
    {
      "id": "C1",
      "claim": "An application is declared with one decorated entry method plus configuration, not assembled by hand.",
      "evidence": ["examples/minimal_app/root.py", "docs/getting_started.md"],
      "symbols": ["examples/minimal_app/root.py::main"]
    },
    {
      "id": "C2",
      "claim": "Services and controllers are declared as classes and receive their dependencies through constructor injection.",
      "evidence": ["examples/controller_service_inject/services.py", "docs/dependency_injection_guide.md"],
      "symbols": ["examples/controller_service_inject/services.py::UserDirectoryService"]
    },
    {
      "id": "C3",
      "claim": "The same request path runs over a Tornado backend and an ASGI backend, chosen per deployment, and normal traffic gets the same status code and body on both.",
      "evidence": ["tests/integration/test_adapter_integration.py", "cullinan/transport/adapter"],
      "symbols": []
    },
    {
      "id": "C4",
      "claim": "The public API surface is counted and held: 44 top-level symbols, with per-namespace surfaces asserted in tests.",
      "evidence": ["tests/core/test_public_api_boundaries.py", "cullinan/_contracts.json"],
      "symbols": []
    },
    {
      "id": "C5",
      "claim": "The package ships as a typed distribution (PEP 561), so downstream type checkers can read it.",
      "evidence": ["cullinan/py.typed"],
      "symbols": []
    },
    {
      "id": "C6",
      "claim": "Shutdown is bounded and enforced: the bound is handed to the server that does the waiting, in-flight requests are cut when it expires, and the drain result is returned as a boolean.",
      "evidence": ["tests/core/test_graceful_drain_async.py", "docs/deployment.md"],
      "symbols": [
        "cullinan/core/application_context.py::ashutdown",
        "cullinan/core/application_context.py::await_drained"
      ]
    },
    {
      "id": "C7",
      "claim": "Readiness changes while there is still traffic to shed: draining is announced when the stop signal arrives, and requests that arrive during it are answered 503.",
      "evidence": ["examples/graceful_shutdown/root.py", "examples/graceful_shutdown/README.md"],
      "symbols": ["cullinan/core/application_context.py::accepts_requests"]
    },
    {
      "id": "C8",
      "claim": "Deprecation removal versions are computed from the version a deprecation landed on, never written as a literal that can drift.",
      "evidence": ["cullinan/support/deprecation.py", "tests/core/test_deprecated_api_warnings.py"],
      "symbols": ["cullinan/support/deprecation.py::resolve_removal_version"]
    },
    {
      "id": "C9",
      "claim": "Runtime dependencies are deliberately small: one package, python-dotenv, with the engines offered as extras.",
      "evidence": ["pyproject.toml"],
      "symbols": []
    },
    {
      "id": "C10",
      "claim": "Every taught feature has a runnable example and a page, checked in both directions.",
      "evidence": ["examples/features.json", "tests/integration/test_feature_example_matrix.py"],
      "symbols": []
    }
  ]
}
```

## What this page does not claim

- **Not "fastest".** Numbers without a workload are decoration. The repository
  ships a benchmark you can run on your own machine
  (`benchmarks/bench.py`) rather than a headline figure that would not transfer.
- **Not "zero configuration".** A framework that hides its configuration cannot
  be operated; this one shows you the knobs, in
  [Deploying to Production](deployment.md).
- **Not "1.0".** The line is pre-release. The API surface is frozen so that a
  dependency can be pinned without surprises, but behaviour may still change
  where a release note says so.
