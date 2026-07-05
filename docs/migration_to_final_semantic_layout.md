title: "Final Structure Migration"
slug: "final-structure-migration"
module: []
tags: ["migration", "final-structure", "semantics"]
author: "Cullinan"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/migration_to_final_semantic_layout.md"
related_tests: ["tests/core/test_public_api_boundaries.py", "tests/core/test_semantic_package_facades.py"]
related_examples: ["examples/minimal_app", "examples/testing_flow"]
estimate_pd: 1.0
last_updated: "2026-06-02T00:00:00Z"
pr_links: []

# Final Structure Migration

This page explains how to move code written for `0.93a6` and earlier mixed layouts to the
final semantic structure introduced on the current pre branch.

## What changed

Cullinan no longer keeps historical root-level wrappers such as:

- `cullinan.app`
- `cullinan.application_model`
- `cullinan.public_api`
- `cullinan.module_scanner`
- `cullinan.scan_stats`
- `cullinan.scanner`
- `cullinan.compat`

The maintained structure is now centered on:

- `cullinan.application`
- `cullinan.web`
- `cullinan.core`
- `cullinan.runtime`
- `cullinan.transport`
- `cullinan.testing`
- `cullinan.support`

## Why this was removed

The previous layout left new semantic packages and historical wrappers side by side. That
made the package tree harder to understand, encouraged old imports to remain in use, and kept
the codebase in a long-lived intermediate state.

Cullinan now treats the semantic packages as the real structure rather than as facades placed
on top of legacy files.

## Old-to-new path mapping

| Old path | New path |
| --- | --- |
| `cullinan.app` | top-level `cullinan` entry-method API (`@application`, `configure`, then call `main()`) |
| `cullinan.application_model` | `cullinan.application` |
| `cullinan.public_api` | `cullinan.application.public` |
| `cullinan.module_scanner` | `cullinan.runtime.module_scanner` |
| `cullinan.scan_stats` | `cullinan.runtime.scan_stats` |
| `cullinan.scanner` | `cullinan.runtime.scanner` |
| `cullinan.controller` | `cullinan.web.controller` |
| `cullinan.middleware` | `cullinan.web.middleware` |
| `cullinan.params` | `cullinan.web.params` |
| `cullinan.gateway` | `cullinan.web.gateway` |
| `cullinan.handler` | `cullinan.web.handler` |
| `cullinan.adapter` | `cullinan.transport.adapter` |
| `cullinan.service` | `cullinan.core` (`@service`) / `cullinan.core.services` (`Service`, registry helpers) |
| `cullinan.config` | `cullinan.support.config` |
| `cullinan.exceptions` | `cullinan.support.exceptions` |
| `cullinan.path_utils` | `cullinan.support.path_utils` |

## Common migration rewrites

### Application startup

```python
# Before
from cullinan.public_api import run

# After
from cullinan import application, configure

@configure(user_packages=["myapp"])
@application
def main(): ...

main()
```

### Runtime model helpers

```python
# Before
from cullinan.application_model import Application

# After
from cullinan.application import Application
```

### Web-facing APIs

```python
# Before
from cullinan.controller import controller
from cullinan.params import Body

# After
from cullinan.web import controller, Body
```

### Advanced transport integration

```python
# Before
from cullinan.adapter import ASGIAdapter

# After
from cullinan.transport.adapter import ASGIAdapter
```

## Mental model change

Do not treat the migration as “find another old import that still works.”

The new rule is:

1. business application startup lives in top-level `cullinan`
2. business web development lives in `cullinan.web`
3. IoC/DI and lifecycle live in `cullinan.core`
4. discovery and scanning live in `cullinan.runtime`
5. server integration lives in `cullinan.transport`
6. support utilities live in `cullinan.support`

If existing code still depends on removed root-level wrappers, migrate the import instead of
reintroducing the wrapper.
