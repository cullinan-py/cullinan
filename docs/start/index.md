title: "Application Build"
slug: "application-build"
module: []
tags: ["docs", "start", "knowledge-base"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/start/index.md"
related_tests: ["tests/core/test_public_api_boundaries.py", "tests/integration/test_adapter_integration.py"]
related_examples: ["examples/minimal_app"]
estimate_pd: 1.0
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# Application Build

Start here to install Cullinan, run a minimal application, and confirm the
recommended public entrypoint.

Cullinan application code should start from business decorators, business methods,
and `@application` + `@configure(...)` + `main()` API.

## Start here

1. [Getting Started](../getting_started.md) — install Cullinan and run a minimal app
2. [Examples](../examples.md) — see small end-to-end examples
3. [Build & Run](../build_run.md) — local build and execution workflow

## What this section answers

- How do I bootstrap a new Cullinan application?
- What is the recommended entrypoint?
- What should a minimal application look like?
- Where do I go next after the first successful run?

## Recommended learning path

After you finish the minimal bootstrap path, continue with:

- [Framework Semantics](../concepts/index.md) to understand Cullinan's rules
- [Engineering Practices](../how-to/index.md) for common development tasks
- [API Reference](../reference/index.md) when you already know what symbol you need

## Boundary note

This section intentionally avoids advanced runtime orchestration details. If you
need explicit runtime switching, low-level adapter work, or extension internals,
continue in [Internals & Extensions](../internals/index.md) instead of treating
those APIs as the default startup path.
