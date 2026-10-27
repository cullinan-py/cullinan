# Changelog

This file records the release history of Cullinan, newest first. It is a
historical record: the version currently advertised by the project is tracked
in [`README.MD`](README.MD).

The complete release notes for each version are archived in the repository's
release-note files (`RELEASE-v<version>.md`) where published.

## v0.96a8

**v0.96a8** is the eighth alpha of the 0.96 line, and it is a debt round: every
maintenance item that had a defect behind it was fixed rather than restated, and
two gates that could pass without checking anything now check the thing they are
named after.

No public API symbol is added or removed, and no signature changes. What changes
for a running application is what a diagnostic says, and where one reconciliation
step runs.

### Added

- `check_tag_gate.py` reconciles the docs version banners before a tag: every
  page that advertises a version must advertise the one in `cullinan/_version.py`,
  and at least eight such banners must exist -- a check that finds nothing would
  otherwise pass without comparing anything. The Chinese pages use a full-width
  colon and different wording, so an English-only pattern would have covered half
  the tree and reported green on the half it never read
- The review and sync credentials carry `#tree=<40 hex>` and the gate compares it
  with `HEAD^{tree}`. Bound to the tree, not the commit: `d69e66d` and the merge
  commit that released it are different commits with the same tree, and a
  commit-bound token would have rejected a valid approval. The sign-off
  credential is exempt, because it binds to its evidence bundle. The gate says
  what it does not prove -- format and scope, not authenticity
- The boot boundary reports the line that registered a pre-boot pipeline entry
  (`path:line`), in the report and in the refusal. The middleware class name
  appears in a dependency's `site-packages`, not in the reader's own code, so it
  was not something anyone could search for

Two checks that did not exist before, both for things that were believed rather than shown:

- Ten documented Python blocks are fragments on purpose (a method body shown
  without its class, a before/after pair whose "before" is a comment about
  output). They are an explicit set now, so an eleventh is a failure naming the
  page and first line, and an entry that starts parsing is a failure too
- The engine-native write confinement is pinned: `self.write` and `self.finish`
  may appear only in `request_handler`, and route registration is checked to hand
  the dispatcher the original function rather than the wrapper that calls it

### Changed

- `ApplicationContext.refresh()` emits the declared-versus-assembled report as a
  step of its own. It used to run inside `_process_pending_registrations()`;
  nothing was broken, because that drain returns early only after the report, but
  a later "nothing pending, return sooner" would have silenced a
  `strict_assembly=True` failure with no test to notice it
- The markdown lint step publishes its findings and exit status to the job
  summary, and states that it does not fail the build. It still does not: making
  it a gate needs the size of the existing debt, and suppressing the result is
  what kept that number unknown

### Fixed

- The wheel no longer declares a top-level `overrides` module. `overrides/` is
  the MkDocs theme override directory, but `packages.find` read it as a package,
  so `top_level.txt` listed a module the wheel does not ship -- under a name that
  belongs to a real distribution
- A banner stating a minimum (`**Version**: 0.90a5+`) is no longer read as a
  claim about the current version. A lookahead is not enough to filter it: the
  greedy group backtracks and captures `0.90a` out of `0.90a5+`, which then looks
  like a legitimate version

### Documentation

- Nineteen pages carry the metadata the rest already had. Six had none at all and
  thirteen carried only `last_updated`, so a reader of the source could not tell
  which locale a page belonged to or which page it pairs with. `estimate_pd` is
  null where nothing was estimated -- inventing a number to make a field look
  uniform would be worse than leaving it visibly unmeasured
- `docs/examples.md` lists all sixteen runnable examples. It listed ten, so a
  reader following only that page could not find the shutdown, packaging,
  body-limit, runtime-knob or legacy demos at all
- The body-limit example says what a client observes when a body is far over the
  ceiling -- a reset with no status line -- and points at the page that measured
  the boundaries, instead of leaving a reader to branch on `400`
- The release-note template no longer counts. The rule says a symbol count cannot
  stand in for a shape check, and then gave a count of its own, one that was
  wrong
## v0.96a7.post1

**v0.96a7.post1** is a patch on `v0.96a7`. It carries one behaviour fix and three
documentation corrections, all of them raised by a project that upgraded to
0.96a7 and wrote down what it hit.

The fix is about who pays for a warning. The corrections are about saying what a
client observes rather than what the server sends, and about what "compatible"
means when a name keeps its spelling and changes what it points at.

### Fixed

- Importing `cullinan` no longer emits a `DeprecationWarning`. The legacy
  compatibility symbols warned while `cullinan.core` was being imported, so
  every consumer paid for it, including the ones that never touch those symbols;
  under `-W error::DeprecationWarning` — and the equivalent `pytest.ini` setting
  — that warning made `import cullinan` fail outright, during collection, inside
  a third-party import. Each of the five symbols is still wrapped by
  `@deprecated`, so using one warns exactly as before. Two subprocess tests pin
  both halves: the import survives the strict filter, and it emits nothing

### Documentation

- `deployment.md` describes an oversized body by what the client observes, not
  only by the status the server sends. A client still writing when the server
  refuses sees its connection reset with no status line, so receiving `400` is
  not a reliable oversize signal. The measured boundaries — which sizes still
  answer `400`, which end in a reset, and that a chunked upload ends in a reset
  at a much smaller overage — are on the page, in both languages
- `migration_guide_v2.md` gained a step on rolling back across this line: two
  `configure()` keywords arrived in 0.96a6 and are rejected by 0.96a5 at import
  time, so the rollback unit is the pin *and* the configuration, not the pin
- The release-note template now requires compatibility claims to describe
  referents rather than names, and says why a symbol count cannot stand in for
  that: a name that keeps its spelling and changes what it points at is a break,
  and a count of names cannot see it

## v0.96a7

**v0.96a7** is the seventh alpha of the 0.96 line. It is mostly about the parts of
a project that are easy to let rot because nothing fails when they do: the
documentation tree, the address of every page in it, and the discipline that
keeps a page from describing a version of the framework that no longer exists.

Two of the changes are gates rather than features. One requires every published
page to say when it last changed, and compares that date against the commit that
last changed the page, so a page edited without its date moving is a failure
instead of a habit. The other resolves each call shown in the guides to the
callable it names and compares the keywords against the live signature, which
catches a guide that imports a function correctly and then calls it with a
parameter that was renamed.

### Changed

- The internals pages moved from `docs/wiki/` to `docs/internals/`, matching the
  name the navigation had always used for that section. The old addresses are
  answered by redirects in both languages, so a saved bookmark still lands on the
  page it named
- `docs/template/` and `docs/templates/` are one directory. They differed by a
  single letter and held different things
- Every example in `examples/features.json` now declares a kind (`runnable`,
  `test-driven`, `historical`), and the check requires that kind's shape instead
  of one shape for all of them. A testing example has no entry point by design,
  and treating that as a defect was the reason five directories never matched the
  rule

- The multi-OS workflow lives in the repository rather than on a throwaway
  branch, so the cross-platform run a release depends on can be reproduced from a
  clean clone. It still runs only on `dev/**` and on demand

### Fixed

- Both artifacts built from this tree carried `benchmarks/bench.py`, as did the
  ones published as 0.96a6. The benchmark is a development tool with no place in
  an installed package; it is excluded now, and a wheel built from this tree
  carries 131 files rather than 132
- The package metadata records the licence as `License-Expression: MIT` instead
  of the table form that the packaging specification has deprecated

### Documentation

- Every page states when it last changed, in one form, with a date that matches
  its own history. Fourteen pages had no such statement at all and thirty-three
  advertised a date older than their last edit
- The four module reference pages say in their first sentence that they list the
  entrypoints worth starting from rather than the full export surface, and point
  at the generated reference that carries every symbol
- The navigation no longer carries an exclusion list. It had eleven entries and
  six of them named paths that did not exist; an orphan page is a defect, and the
  strict build now fails on one instead of hiding it

## v0.96a6

**v0.96a6** is the sixth alpha of the 0.96 line. It is the release where the
shutdown path stops being a description and becomes a measurement: the bound is
handed to the server that waits, the drain is announced while there is still
traffic to shed, and both engines answer a request that arrives too late in a
way a reader can plan around. It also closes the framing defects that made a
HEAD request for a static file return nothing, and gives the request body a
ceiling.

It also lands the surfaces a project needs in order to be depended on, operated and audited: a generated API reference, a deployment guide in both languages, a benchmark harness with a recorded baseline, and repository checks that fail when the changelog, the example map or the version copies fall behind.

### Added

- `max_request_body_bytes` on `configure(...)`: an oversized body is refused without reading the rest of it, before any handler runs. ASGI answers `413`; Tornado's protocol layer (`max_body_size`) answers `400` first — both stop early, the status differs by engine. Unset means "read whatever arrives", which is the previous behaviour
- `drain_timeout` on `configure(...)`, so the shutdown bound sits next to `server_port` and `server_engine` instead of requiring the advanced `Application` entry
- `ContainerDrainingError` in `cullinan.core.exceptions`: the error a route raises when the container has begun draining, so a caller can tell "shut down" apart from "this handler failed"
- `405` with an `Allow` header when a path exists for another method, and `404` for `OPTIONS` on a path nobody registered — previously every method mismatch was a `404` and every unregistered `OPTIONS` a `204`
- a drain log that says how long the process is waiting and for how many requests
- `examples/runtime_controls/`: every knob a deployment usually sets (`project_root`, `exclude_packages`, `startup_error_policy`, `server_engine`, `asgi_server`, `server_host`, `verbose`) in one runnable file, so each option can be seen taking effect
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

- draining is announced when the stop signal arrives rather than after the wait, so `accepts_requests` turns `False` while there is still traffic to shed
- a request refused because the container is draining answers `503` with `Retry-After` instead of a bare `500`, and transport-level failures go through the gateway resolver rather than being flattened into `500`
- security headers are applied to error responses too, so the responses that echo the request path are no longer the ones without `nosniff`
- the deployment guide describes what each engine actually does during a drain: Tornado answers `503`; ASGI closes its listener first, so there is no window a probe can rely on
- the exit status after a stop signal is documented as what it is: ASGI exits `143` on Linux and macOS because uvicorn re-raises the signal it captured, Tornado exits `0` on all three platforms because its adapter stops the loop it owns and returns, and Windows uses `SIGBREAK`
- coverage is measured and enforced: `[tool.coverage.*]` in `pyproject.toml`
  with a floor, and a CI job that runs the same number locally and in CI
- the publisher now verifies the tag against `cullinan/_version.py` and installs
  the wheel it built before uploading, so a mislabelled or unimportable artefact
  cannot reach the package index
- the docs build installs the package and generator it needs, and separates
  griffe's annotation notes from build failures without hiding them
- **breaking:** `cullinan.web.controller` now names the controller submodule instead of the `@controller` decorator, matching `cullinan.web.middleware` in `v0.96a5`; the decorator stays at `from cullinan import controller` and at `from cullinan.web.controller import controller`. Code importing the decorator from `cullinan.web` fails loudly with `'module' object is not callable` rather than binding a module by accident
- the dotted import path `import cullinan.web.controller.<module> as x` works again; while the decorator owned the name it raised `ImportError: cannot import name ... (unknown location)`

### Fixed

- `configure(verbose=True)` now lowers the framework logger to `DEBUG`. It was stored and never read, so turning it on changed nothing; the registration lines it is supposed to reveal are now actually emitted
- `configure(verbose=False)` restores the logger level that was in place before `verbose=True` raised it; the switch used to work in one direction only, so every later configuration in the same process inherited the noise
- `check_controller_init_source(..., strict=True)` now raises `StatefulControllerError`. It raised inside a `try` whose generic handler caught the exception, so the refusal arrived as a debug log line and the function returned normally
- **Tornado ignored a stop signal on Linux.** The handler scheduled the drain with `add_callback`, which does not wake a loop blocked in `epoll`, so after `SIGTERM` the callback waited for an unrelated event and the process kept sitting there until something else killed it. The loop is now resolved when the handlers are installed and the drain is scheduled with `add_callback_from_signal`; a failure to schedule is logged instead of swallowed. Measured on Linux and macOS: the process now exits with `0` within the drain bound.
- a HEAD request for a static file returned no bytes and ended in `ASGI callable returned without completing response`: the adapter appended a second `Content-Length` (`0`) next to the one the static layer had already set (`15`). Existing headers are left alone now, and `204`/`304` never carry one
- the same request returned `200` on ASGI and `304` on Tornado, because Tornado invents an ETag and honours `If-None-Match`; the handler no longer invents one, so the status code no longer depends on the engine
- the drain bound was resolved correctly and then never passed to uvicorn, whose own default is to wait forever; a four-second request ran to completion with `drain_timeout=0.2`
- the Tornado signal handler stopped the loop directly, which cut in-flight requests instead of waiting for them
- a drain that expired with work still running left `phase` at `draining` while the container was already closed; the transport that is about to stop the world now finalises it

### Documentation

- `docs/why-cullinan.md` states the positioning once, with each claim carrying
  machine-checked evidence and no claim without one
- the examples each state which feature they demonstrate, and the two that had
  no README now have one

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
