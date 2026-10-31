# Changelog

This file records the release history of Cullinan, newest first. It is a
historical record: the version currently advertised by the project is tracked
in [`README.MD`](README.MD).

**What an entry may say.** An entry describes a change someone using the package
can act on. It does not describe how the package's own checks are built: names of
internal tooling, credentials, exemptions and allowlists belong to the code that
implements them, where the reader who needs them will look. An entry written the
other way is unreadable outside the project and ships to people who cannot use
it. `scripts/check_changelog.py` reports the newest entry if it uses that
vocabulary, and an older entry is left as written — history is not rewritten.

The complete release notes for each version are archived in the repository's
release-note files (`RELEASE-v<version>.md`) where published.

## v0.96a13

**v0.96a13** turns `openapi_enabled` from a switch that was read and ignored into
one that changes the route table, and records what that means for the
registered route set.

### Changed

- **`openapi_enabled` now shrinks the registered route set when it is off.** The
  framework used to register the OpenAPI endpoints regardless of the switch, so
  turning it off changed nothing a caller could observe. With this version the
  endpoints are registered only when OpenAPI is enabled, so a deployment with
  `openapi_enabled=False` no longer serves `/openapi.json` or `/openapi.yaml`.
  That is the configuration finally taking effect, not routes going missing: the
  two endpoints exist because the feature exists. Applications that diff the
  registered route set across versions will see it change — a downstream
  application measured its snapshot going from 11 unique / 19 total routes to
  9 unique / 17 total after upgrading. Update the `current` side of such a
  baseline to match; `previous` records what the older version did and stays as
  it is.

## v0.96a12

**v0.96a12** fixes the tests and the deployment page that describe what a client sees
when Tornado refuses an oversized body. The runtime behaviour is unchanged from
`v0.96a11`: the package refuses the upload the same way it did, and nothing in
`cullinan/` behaves differently.

`v0.96a11` was tagged but never reached the package index — its test run failed after
the tag existed, so no artefact was ever published. This version carries the same
code plus that fix.

### Fixed

- **The oversized-body tests assert what the framework guarantees, not what one host
  happened to observe.** Three cases in
  `tests/integration/test_tornado_client_view_of_an_oversized_body.py` required that
  *no* status line be readable when the body is refused. Whether the `400` survives
  the close is a race below the framework: it resolved one way on Windows and the
  other way on Linux, where the same three shapes read a complete `400` every time.
  The cases now assert the part that does not move — the upload is refused and never
  answered successfully, with the documented `400` either whole or cut short by the
  close, and the connection reset or aborted when nothing is read at all. A verdict
  of its own pins the shapes that must still fail, including a `200` and a hang.

### Documentation

- **`docs/deployment.md` and `docs/zh/deployment.md` describe both outcomes.** The
  client-view table stated that these refusals carry no status line. They can carry
  one, and whether they do depends on the client's socket layer and on when its read
  lands relative to the reset — not on the shape of the upload. The counts from each
  host are shown as samples, and neither is presented as the specification.

## v0.96a11

**v0.96a11** is the eleventh alpha of the 0.96 line. Its subject is the configuration and
serving surface that used to accept a setting and do nothing with it: an application can
now terminate TLS itself on either engine, a running server can be asked to stop from
code rather than only by a signal, and a value that cannot be honoured is reported
instead of discarded. Start-up names the engine that is actually running and the layer
that chose it, because the alternative was reading the source to find out which of four
answers won.

The public surface grows in three places — four new options on `configure()`,
`Application.request_shutdown()`, and `configure_options()` — and one combination is
refused at start-up rather than served in a shape nobody asked for.

### Changed

- **A configuration file no longer enters the repository by accident.** The files
  Cullinan reads — `application.json`, `application-prod.json`, `application.local.json`
  and their `.toml` / `.yaml` / `.yml` forms — are now ignored by git, so a plain
  `git add .` leaves them out. Configuration that is *meant* to be committed is named
  as a template, `application*.example.json` (or the matching `.toml` / `.yaml` /
  `.yml` suffix), and a template holds `${VAR}` references where a value would go.

  Two consequences are worth knowing before the next commit. A file that is already
  committed stays committed: the rule stops the next `git add .`, it does not rewrite
  history. And `git add -f` still works, because an ignore rule is a default rather
  than a wall — so configuration files are also read from disk and from the index,
  and a push carrying a plaintext value under a sensitive key is refused. There is no
  switch to turn that off; `git push --no-verify` remains the visible bypass it always
  was.

### Added

- **`configure_options()` reports what the installed version's `configure()` accepts.**
  It exists for callers that have to run one codebase against two installed versions:
  `configure()` refuses an unknown keyword on purpose, so a call carrying an option the
  older version never had fails at import. Asking first — `configure(**{k: v for k, v in
  wanted.items() if k in configure_options()})` — drops what the running version does
  not have and makes the pin alone the unit of rollback. The answer is derived from the
  same signature the refusal message reads, so a name cannot be accepted by one and
  reported by neither. Imported from `cullinan.support.config`; the top-level export
  list is unchanged. The migration guide carries the snippet and the suite executes it.

- **TLS can be terminated by the application, on both engines.** Four options —
  `ssl_certfile`, `ssl_keyfile`, `ssl_client_ca` and `ssl_verify_client` — go to
  whichever backend is running, so turning TLS on is not a backend decision. Giving
  only one half of the key pair is a start-up error rather than a fallback to plain
  HTTP: a listener that was asked to be encrypted and quietly served plaintext is
  worse than one that refuses to start. A client CA turns on client certificates, and
  they are checked by default; `ssl_verify_client=False` asks for a certificate
  without checking it, documented as a migration aid rather than a mode to stay in.
  The tests perform real handshakes on both engines — trust, distrust, a missing
  client certificate, and the half-configuration refusal — against certificates
  committed in `tests/fixtures/tls/`, so no `openssl` binary is needed at test time.

- **Start-up prints which engine is running and which layer chose it.** Four layers
  can name the engine — the `run()` argument, `CULLINAN_ENGINE`, the configuration
  file's `server_engine`, and `configure(server_engine=...)` — and when two of them
  disagree there was no way to tell which won without reading the source. The line
  names both: `└---Web engine: tornado (decided by: environment (CULLINAN_ENGINE))`.
  It also reports `SERVER_ENGINE` when that variable is set, because it is not one
  this framework reads: `SERVER_HOST` and `SERVER_PORT` are, so setting the third
  member of that family is the natural mistake, and it produces the default engine
  with no error at all.

- **A running server can be asked to stop from code, not only by a signal.**
  `Application.request_shutdown()` performs the same drain a stop signal performs —
  stop accepting, answer what still arrives with `503`, wait for in-flight requests
  up to `drain_timeout`, then stop — and it does so from any thread. On Windows this
  was the missing half: `terminate()` is `TerminateProcess`, so a process asked to
  stop that way simply disappears, and there was no other way to reach the drain.
  `run()` blocks, so the call is made on `Application.current()`, which is reachable
  while the server runs. It returns `True` when a running server was asked and
  `False` when there was nothing to ask, rather than raising: a supervisor's exit
  path must not turn a finished shutdown into a crash. Measured on both engines with
  a request in flight: that request finishes with `200`, the next one is answered
  `503`. `examples/graceful_shutdown/stop_after.py` is the runnable version.

- **The stability contract records what each name points at, not just its spelling.**
  `cullinan/_contracts.json` (now schema 2) gains `stability_shapes`: every symbol in
  the four committed `__all__` lists is recorded as `function`, `class`, `module` or
  `other`, and a change to either the set of names or the shape of one fails the
  check. A count of names cannot see this kind of break — `cullinan.web.controller`
  was the `@controller` decorator and became a submodule, keeping its spelling, its
  membership and every count, and the first thing that noticed was a consumer's
  `import` raising `TypeError: 'module' object is not callable`.

- **The contract records which options `configure()` accepts.** `cullinan/_contracts.json`
  (now schema 3) gains `pinned_symbols`: the option names this version accepts, alongside
  the callable's shape. Read it to know exactly what your version supports, without
  calling the function to find out.

### Changed

- **`asgi_server="hypercorn"` with the TLS options is refused at start-up.** That branch
  does not pass `ssl_certfile`/`ssl_keyfile`/`ssl_client_ca` to hypercorn, so starting
  anyway would serve plaintext from a listener configured for TLS — the "looks
  configured, does nothing" failure this release is about. The message says the branch
  does not support it, offers the two ways forward (`asgi_server="uvicorn"`, or terminate
  at a reverse proxy), and states that it is a known limitation rather than a
  configuration mistake.

- **A misspelt option for `configure()` now says what was probably meant.** The
  call is still refused — accepting an unknown keyword with a warning would turn a
  typo into a switch that looks set and changes nothing — but the message now names
  the option, offers the closest name `configure()` does accept, and points at the
  section that lists them. The exception type is still `TypeError`, so a caller
  that already catches it keeps working. The suggestions are read from the
  function's own signature, so they cannot drift away from the options that exist.

- **The configuration page described an order the code never implemented.** It listed
  `configure(...)` above the project file. The file is applied *after* the values
  declared in code, so a key present in both takes the file's value — and still does.
  The page now states that order and why it is the useful one (one binary, several
  deployments, and the deployment answers for its own addresses), and it lists the
  keys a file may contain.

### Fixed

- **Asking for a shutdown twice no longer schedules the drain twice.** The second
  call still answers `True` — "this server has been asked to stop" remains true, and
  `False` keeps its one meaning of "nothing to ask" — but the announcement and the
  wait behind it happen once. The previous behaviour was survivable rather than
  correct: nothing asserted that the sequence ran once, so a duplicated drain
  cutting an in-flight request would have been found by a user rather than by a test.

- **An oversized upload is refused before the body is read, on ASGI too.** The
  ceiling was enforced while reading, so a client that sent slowly was answered
  only after it had finished sending, and one that never finished was never
  answered. `Content-Length` arrives with the headers, so a body that declares
  itself too large is now answered `413` at once, without reading a byte of it. A
  chunked upload declares nothing and keeps the previous behaviour: it is stopped
  when the received size crosses the ceiling. The response still carries exactly
  one `Content-Length` header.

- **A configuration switch that was declared, documented and ignored.** Nine
  `CullinanConfig` fields had no path from a configuration source into the object:
  `openapi_enabled` and its three companions, `debug`, `enable_middleware_pipeline`,
  the two `route_*` flags and `context_features`. A project file that set
  `"openapi_enabled": false` was read, accepted and dropped, so `/openapi.json` stayed
  published while the operator believed it was off. All 28 fields now round-trip
  through `from_dict`/`to_dict`, and a key outside that set is reported with the file
  it came from — including the name that was probably meant — instead of being
  discarded. A boolean written as text is read as a boolean; a value outside the
  vocabulary is refused rather than guessed at, because `bool("false")` is `True`.

- **The OpenAPI state is printed at start-up, with the layer that decided it.** Three
  layers can answer "is the document published?", and they disagree when a project
  sets one and an operator sets another. The line names the winner, so the question
  is answerable from the log rather than by reading the source.

### Documentation

- **The request-body page now states what a client observes, with counts.** There are
  two ways to lose the answer, not one: the client was still writing when the refusal
  landed, or a single write far exceeded what the connection could buffer. Measured on
  Windows against a 1 KiB ceiling — a 4 MiB body sent in one write was refused with no
  readable status line 9 times out of 13; 64 KiB written in one go was readable 13 out
  of 13, and the same 64 KiB read 20 ms later was readable 0 out of 13. The page
  carries the counts and their `n`, keeps the one rule they support (the dividing line
  is timing, not the ratio), and tells callers to treat neither "got a `400`" nor "got
  no status line" as the oversize signal. The shapes run as a test against a live
  Tornado server, so "measured" has an executor rather than being a note that decays.

- **The configuration page now says which variable chooses the engine, and which one
  only looks like it.** The engine comes from `CULLINAN_ENGINE`; `SERVER_ENGINE` is
  not read by anything, even though `SERVER_HOST` and `SERVER_PORT` are — so a
  deployment that sets the wrong one silently gets the engine `auto` picks, and two
  runs that were meant to compare engines can both be the same engine. The request
  body section of the deployment page also states, for each of the three ways a
  client can send an oversized upload, what that client observes; a check keeps that
  list, and the link from the configuration page to it, from being trimmed.

## v0.96a10

**v0.96a10** is the tenth alpha of the 0.96 line. Configuration moves out of `.env`
and into a project file that is found where the application is deployed, and the last
runtime dependency goes with it. The rest of the release is the packaging and test
surface that change exposed.

No public API symbol is added, removed or renamed, and no signature changes. What does
change is where configuration comes from: an application that relied on `.env` being
loaded for it needs one edit, described under Removed.

### Changed

- **Configuration is read from a file.** `.env` was a flat `KEY=VALUE` list with no
  nesting and no types, and in a packaged build it answered the wrong question: it
  said nothing about where the file is or whether it ended up inside the artefact.
  One configuration file per application replaces it — `application.json`, with
  `application-<profile>.json` merged over it when `CULLINAN_PROFILE` is set. TOML and
  YAML are read when the environment can parse them; JSON needs nothing, so no
  runtime dependency is introduced.

  Three properties are the point rather than the details:

  - **the file is never looked for inside the installed package** — only beside the
    launched executable and in the working directory, so a copy shipped in the bundle
    cannot shadow the file the operator edited;
  - **`${VAR}` and `${VAR:default}` are resolved from the environment after reading**,
    so a file that is committed or shipped holds a pointer rather than a value. A
    placeholder with neither is an error, because substituting `""` would turn a
    missing setting into one that looks configured;
  - **no cipher is included, deliberately.** A key shipped beside the ciphertext is not
    encryption; `load_project_config(decryptor=...)` lets a deployment supply its own
    and keep the key outside the artefact.

  Precedence, highest first: `run(...)` argument, environment variable,
  `configure(...)`, configuration file, built-in default.

### Removed

- **`python-dotenv` is no longer a dependency, and `.env` is no longer read.**
  `dependencies` in `pyproject.toml` is empty. Deployments that relied on `.env`
  being loaded by the application should move those keys into `application.json`, or
  export them as environment variables — both keep working, and the second needs no
  file at all.

### Documentation

- **A configuration guide in both languages, and a runnable example.**
  `docs/configuration.md` and `docs/zh/configuration.md` cover where the file is
  searched for, the precedence order, placeholder resolution, and what to do about
  secrets in a packaged build. `examples/config_file/` is a working application you
  can start with `python -m examples.config_file`.

### Fixed

- **The example and its description now agree.** The shipped `application.json` read
  `"${EXAMPLE_CHANNEL:#general}"` while the README said the channel falls back to
  `general`; resolving the real file produced `#general`, because a default is taken
  literally and there is no sigil that means "comment". The file now says what the
  README says.

- **The configuration example starts on Python 3.9.** `examples/config_file/root.py`
  declared `profile: str | None` without `from __future__ import annotations`. That is
  3.10 syntax evaluated when the function is defined, so on 3.9 the module raised
  `TypeError: unsupported operand type(s) for |` at import and `python -m
  examples.config_file` did not start. Both were declared supported and neither had
  been tried there.

- **A packaged build reported the directory it unpacked itself into as the place to
  keep data.** Nuitka does not set `sys.frozen` in every mode, and detection hung on
  that single flag, so the packaged branch was never reached and every path fell back
  to the development answer: logs, configuration and cache written into a temporary
  directory that is removed when the process exits. Detection now accepts several
  independent markers instead of one flag, onefile is recognised from behaviour
  rather than from a directory name, and `get_original_executable_dir()` returns the
  directory of the executable that was launched. Under a packer,
  `get_executable_dir()` and `get_user_data_dir()` now return that directory; when no
  persistent location can be established the code says so instead of returning the
  temporary one.

- **A release is built only after the tests pass on the tagged tree.** The version you
  install is the version that was tested, rather than a version whose tests ran
  somewhere else.

- **Setting up for development on 3.9 works again.** `tomli` is now a development
  dependency below 3.11, so tooling that reads `pyproject.toml` no longer fails on that
  interpreter.

## v0.96a9

**v0.96a9** is the ninth alpha of the 0.96 line. The one library change removes a
guard that was enforced in two places; the remainder of the release concerns how
the package records and checks its own version.

No public API symbol is added or removed, and no signature changes.

### Changed

- Three tests that restated the package version now derive it from
  `cullinan/_version.py`. A test that pins a literal is a second copy of the
  number, and it fails in the quiet direction: it keeps passing while the value
  it names drifts. Two of them read the file independently of importing it, so
  the assertion can still fail

### Fixed

- `MiddlewarePipeline.add()` no longer restates the mutual-exclusion rule between
  `priority` and `before`/`after`. Every path already arrives through `_append`,
  which enforces it; a second copy is a rule stated twice and drifting once.
  Behaviour is unchanged, including the message

### Documentation

- Every page that advertises a version now advertises `0.96a9`, and the pages
  whose banner changed record the date they changed

## v0.96a8

**v0.96a8** is the eighth alpha of the 0.96 line. Every maintenance item that had
a defect behind it was fixed rather than restated.

No public API symbol is added or removed, and no signature changes. What changes
for a running application is what a diagnostic says, and where one reconciliation
step runs.

### Added

- The boot boundary reports the line that registered a pre-boot pipeline entry
  (`path:line`), in the report and in the refusal. The middleware class name
  appears in a dependency's `site-packages`, not in the reader's own code, so it
  was not something anyone could search for

Two behaviours that were previously assumed are now asserted:

- Ten documented Python blocks are fragments on purpose (a method body shown
  without its class, a before/after pair whose "before" is a comment about
  output). They are an explicit set now, so an eleventh is a failure naming the
  page and first line, and an entry that starts parsing is a failure too
- The engine-native write confinement is pinned: `self.write` and `self.finish`
  may appear only in `request_handler`, and route registration is checked to hand
  the dispatcher the original function rather than the wrapper that calls it

### Changed

- `ApplicationContext.refresh()` now spells out three steps instead of one:
  drain the pending queue, reconcile declarations against the assembly, then apply
  what was drained. The reconciliation used to live inside the drain, immediately
  after the queue was emptied; moving it out is only equivalent if it keeps that
  position, because applying the drained registrations first would compare
  declarations against an assembly that already contains them. The split also
  means a registration that raises no longer takes the report down with it
- The markdown lint step publishes its findings and exit status to the job
  summary, and states that it does not fail the build

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
