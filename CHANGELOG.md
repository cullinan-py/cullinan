# Changelog

This file records the release history of Cullinan, newest first. It is a
historical record: the version currently advertised by the project is tracked
in [`README.MD`](README.MD).

The complete release notes for each version are archived in the repository's
release-note files (`RELEASE-v<version>.md`) where published.

## v0.96a4

**v0.96a4** is the fourth alpha of the 0.96 line. It makes the boot boundary name the gateway pipeline entries the framework resets, and discloses in the documentation the support level of the imperative entry point that registers them:

- the entries a gateway reset discards at startup are now named, with their count, in a diagnostic that is visible at default warning settings and falls back to stderr when warnings are suppressed globally and no logging handler is configured
- the imperative `get_pipeline().add(...)` entry point is documented as a runtime-introspection / advanced-use / testing entry point rather than the recommended way to integrate middleware, with the declarative entries (`configure(middlewares=[...])`, `@middleware`) named as the recommended path
- no public API is added or removed; the four `__all__` surfaces stay at 44 / 26 / 34 / 72
- the entries registered through that imperative entry point are still reset at startup: this release adds visibility and documentation, not a change to the reset semantics

## v0.96a3

**v0.96a3** is the third alpha of the 0.96 line. It makes the declared-versus-assembled reconciliation survive the production settings that used to silence it, and lets an application opt in to failing at startup instead of only reporting:

- the diagnostic that names components declared but never assembled can no longer be silenced by a deployment that suppresses warnings and configures no logging handler of its own
- `configure(strict_assembly=True)` turns the same difference into a startup failure, raised after the diagnostic has been emitted rather than instead of it
- `configure(strict_assembly_excludes=[...])` acknowledges a component that is deliberately left unassembled, changing the action without changing the facts

## v0.96a2

**v0.96a2** is the second alpha of the 0.96 line. It closes the gap between
what the framework declares and what it actually does:

- component declarations outside the discovery scope are reported at default
  settings instead of being dropped silently, and the guard meant to catch them
  can finally fire
- the package ships a machine-readable description of its stability commitment,
  so whether an import surface is covered can be answered offline, in advance
  and as a plain yes or no
- deprecation removal windows are anchored to the version a deprecation was
  announced in, so announced removals arrive instead of sliding forward with
  every release
- `cullinan.core.extensions` no longer carries a divergent copy of the support
  implementation and a second registry with it
- commits touching governed paths must carry a change declaration
- the guides state how lifecycle error records are actually surfaced, and how
  component-discovery diagnostics are actually delivered
- runnable API examples in docstrings are gated, and the local scratch
  directory can no longer be committed unnoticed

## v0.96a1

**v0.96a1** was the first alpha of the 0.96 line. It closed the capability gaps
found in the 0.95 middleware surface and declares the public API stability
freeze ahead of the 1.0 milestone:

- a single ordering key for the gateway middleware pipeline, so a middleware
  declared on the application and one added to the pipeline can be ordered
  against each other
- `configure(builtin_middleware=...)` to switch the built-in access-log layer
  off or replace it
- `drain_timeout` wired to the real shutdown-timeout source, with the default
  behaviour unchanged
- `RouteGroup.middleware_tags` deprecated
- the 1.0 public API stability freeze declared in the API reference
- engine-neutral wording across the guides, examples and public docstrings

## v0.95

**v0.95** remains the current stable line. It is the Phase A convergence cut for
the 1.0 roadmap, continuing the v0.94 opt iteration, and locks down the public
surface and packaging baseline around:

- `@application` + `@configure(...)` + `main()` as the startup flow
- decorator-first discovery through Python imports
- `@module` as the structured boundary for runtime ownership
- built-in IoC/DI, lifecycle, and semantic diagnostics
- a semantic package surface centered on the top-level `cullinan` API, with
  advanced semantic namespaces under `cullinan.application`, `cullinan.web`,
  and `cullinan.core`
- engine-neutral runtime selection over Tornado / ASGI backends
- `pyproject.toml` + `setuptools.build_meta` packaging with `setup.py` kept as a compatibility shim
- PEP 561 typed-package distribution via `cullinan/py.typed`

The v0.94 opt iteration (A1-A4 kernel behavior optimization + B1-B3 mkdocs
mechanism) deprecates legacy compatibility symbols, adds strict
`_xxx` private-injection and strict lifecycle propagation switches, optimizes
scope validation, and restructures the docs build channel mapping so
`origin/preview` is the single pre-release authority.
