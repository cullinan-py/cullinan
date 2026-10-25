# Changelog

This file records the release history of Cullinan, newest first. It is a
historical record: the version currently advertised by the project is tracked
in [`README.MD`](README.MD).

The complete release notes for each version are archived in the repository's
release-note files (`RELEASE-v<version>.md`) where published.

## Unreleased

The 1.0 readiness work, landed on the 0.96 line rather than deferred to a later
milestone: the surfaces a project needs in order to be depended on, operated and
audited.

### Added

- a generated API reference (`docs/reference/api/`), built from the installed
  package by mkdocstrings, so a published signature is the signature the code
  has; the hand-written guides remain as the place that tells you which symbol
  to reach for
- a production deployment guide in both languages, naming only surfaces that
  exist and checked against them by test
- a benchmark harness (`benchmarks/bench.py`) with a recorded baseline and a
  `--check` mode that reports a regression instead of a headline number
- `examples/graceful_shutdown/`, a runnable readiness recipe built on
  `accepts_requests` and `add_draining_handler`
- `examples/features.json`, the feature-to-example map, enforced in both
  directions: a feature without an example fails, and an example nobody
  declared fails too
- `SECURITY.md`, with a private reporting channel and a supported-version table
- repository checks: `scripts/check_changelog.py` (the changelog covers the
  released versions), `scripts/check_claims.py` (every positioning claim still
  has its evidence), `scripts/check_release_tag_matches_version.py` (a tag names
  the version the code carries), and `scripts/check_channel_sync.py` (a release
  reached the documentation channel too)

### Changed

- coverage is measured and enforced: `[tool.coverage.*]` in `pyproject.toml`
  with a floor, and a CI job that runs the same number locally and in CI
- the publisher now verifies the tag against `cullinan/_version.py` and installs
  the wheel it built before uploading, so a mislabelled or unimportable artefact
  cannot reach the package index
- the docs build installs the package and generator it needs, and separates
  griffe's annotation notes from build failures without hiding them

### Documentation

- `docs/why-cullinan.md` states the positioning once, with each claim carrying
  machine-checked evidence and no claim without one
- the examples each state which feature they demonstrate, and the two that had
  no README now have one

## v0.96a6

**v0.96a6** is the sixth alpha of the 0.96 line. It is the release where the
shutdown path stops being a description and becomes a measurement: the bound is
handed to the server that waits, the drain is announced while there is still
traffic to shed, and both engines answer a request that arrives too late in a
way a reader can plan around. It also closes the framing defects that made a
HEAD request for a static file return nothing, and gives the request body a
ceiling.

### Added

- `max_request_body_bytes` on `configure(...)`: an oversized body is answered `413` while the client is still sending, on both engines, before any handler runs. Unset means "read whatever arrives", which is the previous behaviour
- `drain_timeout` on `configure(...)`, so the shutdown bound sits next to `server_port` and `server_engine` instead of requiring the advanced `Application` entry
- `405` with an `Allow` header when a path exists for another method, and `404` for `OPTIONS` on a path nobody registered — previously every method mismatch was a `404` and every unregistered `OPTIONS` a `204`
- a drain log that says how long the process is waiting and for how many requests

### Changed

- draining is announced when the stop signal arrives rather than after the wait, so `accepts_requests` turns `False` while there is still traffic to shed
- a request refused because the container is draining answers `503` with `Retry-After` instead of a bare `500`, and transport-level failures go through the gateway resolver rather than being flattened into `500`
- security headers are applied to error responses too, so the responses that echo the request path are no longer the ones without `nosniff`
- the deployment guide describes what each engine actually does during a drain: Tornado answers `503`; ASGI closes its listener first, so there is no window a probe can rely on

### Fixed

- a HEAD request for a static file returned no bytes and ended in `ASGI callable returned without completing response`: the adapter appended a second `Content-Length` (`15`) next to the one the static layer had already set (`0`). Existing headers are left alone now, and `204`/`304` never carry one
- the same request returned `200` on ASGI and `304` on Tornado, because Tornado invents an ETag and honours `If-None-Match`; the handler no longer invents one, so the status code no longer depends on the engine
- the drain bound was resolved correctly and then never passed to uvicorn, whose own default is to wait forever; a four-second request ran to completion with `drain_timeout=0.2`
- the Tornado signal handler stopped the loop directly, which cut in-flight requests instead of waiting for them
- a drain that expired with work still running left `phase` at `draining` while the container was already closed; the transport that is about to stop the world now finalises it

## v0.96a5

**v0.96a5** is the fifth alpha of the 0.96 line. It settles middleware ownership and the boot boundary, and makes the shutdown path actually graceful: draining no longer blocks the event loop it is called from, and an application can be asked whether it is still accepting requests.

### Added

- `ApplicationContext.ashutdown()` and `ApplicationContext.await_drained()`, so a caller already on an event loop has a path that yields control instead of starving the requests it is waiting for
- `ApplicationContext.accepts_requests`, a predicate that turns `False` the moment draining begins
- `ApplicationContext.add_draining_handler()`, a callback fired once on that transition, mirroring `add_shutdown_handler()`

### Changed

- `shutdown()` and `ashutdown()` now return whether the drain completed within the bound, so a clean drain and a timed-out one are distinguishable without reading logs
- the ASGI lifespan shutdown uses the asynchronous path and resolves its drain bound from `WebRuntimeConfig.drain_timeout` rather than a hard-coded default
- `uninstall()` drives the close to a terminal state instead of leaving the application in draining with its lifecycle instances unreleased
- a middleware class passed to `configure(middlewares=[Class])` — or to `configure(builtin_middleware=[Class])` — is created by the application container, with its declared dependencies injected; a class without `@component` is refused at startup, and the legacy `@middleware(priority=...)` path follows the same rule
- a refused middleware class is validated before it is constructed, so the rejection path has no side effect and nothing reaches the pipeline
- a `get_pipeline().add(...)` registration made before startup is reported and then refused at the boot boundary with a `ConfigurationError` (`PREBOOT_REGISTRATION_ERROR`), rather than being accepted and reset
- `cullinan.web.middleware` now names the middleware submodule instead of the `@middleware` decorator; the decorator moves to the top-level import (`from cullinan import middleware`)
- no public API symbol is added or removed; the four `__all__` surfaces stay at 44 / 26 / 34 / 72

### Fixed

- the drain wait no longer blocks when it is called from inside a running event loop. It used a blocking sleep there, which starved the in-flight request tasks it was waiting for, so the wait always burned the full timeout and then dropped them; the blocking wait now runs only when no loop is running, and skipping it is reported at warning level
- drain finalisation that must defer while requests are still in flight now says so instead of returning silently
- a closed-state guard compared the container state against `"CLOSED"` while the enum value is `"closed"`, so the condition was always true and guarded nothing; it now compares the enum member, in all three places that had the same mistake

### Removed

- a shutdown helper that was defined twice, byte-identical, with no callers, and waited on a request counter that did not exist on the module it read

### Documentation

- the lifecycle guide records why the synchronous wait must not run on the event loop, and shows the readiness recipe — the predicate plus the draining callback — for wiring your own probe

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
