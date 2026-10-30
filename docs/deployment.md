title: "Deploying to Production"
slug: "deployment"
module: []
tags: ["docs", "guide", "operations", "production"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/deployment.md"
related_tests: ["tests/integration/test_deployment_guide_symbols.py", "tests/integration/test_feature_example_matrix.py"]
related_examples: ["examples/graceful_shutdown"]
estimate_pd: 2.0
last_updated: "2026-10-30"
pr_links: []

# Deploying to Production

This page is about the process boundary: what starts, what stops, what a load
balancer should ask it, and which knob changes which behaviour. It assumes you
have an application that runs locally — if you do not, start with
[Getting Started](getting_started.md).

Everything below names a surface that exists in this release. If a knob is not
on this page, it is not a supported way to change production behaviour.

## What you deploy

You deploy **one process** that runs one entry method. That method is a normal
Python function marked with `@application` and configured with `@configure(...)`:

```python
from cullinan import application, configure


@configure(user_packages=["myapp"], server_host="0.0.0.0", server_port=8080)
@application
def main(): ...
```

`main()` starts the server and blocks until the process is asked to stop. Put it
behind a supervisor — systemd, a container runtime, or your platform's process
manager — rather than forking it yourself: restart policy, log collection and
signal delivery all belong to the supervisor, and duplicating them inside the
framework would give you two places to look when a process will not die.

### Scaling is horizontal

Run N processes behind a load balancer. There is no cluster membership, no shared
state and no leader election: each process is an independent replica, which is
what makes a rolling deploy a matter of starting new ones and stopping old ones.

## Choosing the engine

The framework runs over either backend and the request path is the same. Pick one
per deployment, not per route:

```python
@configure(user_packages=["myapp"], server_engine="asgi")
@application
def main(): ...
```

`server_engine` accepts `"auto"`, `"tornado"` or `"asgi"`. The environment
variable `CULLINAN_ENGINE` does the same thing, which is usually the better
choice in a container: the same image can run either backend without a rebuild.
`SERVER_ENGINE` is **not** a variable this framework reads, even though
`SERVER_HOST` and `SERVER_PORT` are — see
[configuration](configuration.md#precedence). Set the wrong one and you get the
engine `auto` picks, silently.

## The shutdown sequence

On a stop signal (`SIGTERM`; `SIGINT` and, on Windows, `SIGBREAK`) the process
does four things in this order:

1. **announces the drain** — the readiness predicate turns `False` immediately,
   so a probe or a load balancer has a window in which to stop sending work;
2. **answers what still arrives with `503`** — not `500`. A request that lands
   during the drain is a timing problem, not a broken request, and the two need
   to be distinguishable by whoever reads the status code;
3. **waits for the requests already running**, up to `drain_timeout`;
4. **closes** — the listener goes away, the container closes, the process exits.

Step 2 needs a caveat that cost a release to learn: **who can still reach you
during the drain depends on the engine.**

| Engine | A request that arrives during the drain |
|---|---|
| Tornado | the listener stays open, so it is accepted and answered `503` with `Retry-After: 1` |
| ASGI (uvicorn) | uvicorn closes the listener as the *first* step of its shutdown and then calls `shutdown()` on every open connection, so there is **no window in which you can reach it on purpose**: for roughly the first 0.1s after the signal a request may still be answered `503`, after that existing connections are aborted and new ones are not accepted (a client hangs or is refused). Treat it as "the instance is gone" |

The framework cannot change that ordering: the bound is handed to the server,
and the server decides when to stop listening and when to drop connections. Plan
for it — a probe that opens a new connection on every poll will see the instance
disappear rather than see `503`, which is still a correct "do not send me
traffic" signal, but it is not a status code you can read. On ASGI the only
reliable readiness signal is the one you read *before* the shutdown begins.

Step 3 is bounded by one number, and that number is handed to the server that
actually does the waiting:

```python
from cullinan import application, configure


@configure(user_packages=["your_app"], drain_timeout=15.0)
@application
def main(): ...


main()
```

`drain_timeout` sits on `@configure(...)`, next to `server_port` and
`server_engine`, because a knob that only the advanced entry can reach is a knob
most applications will never find. `Application(...)` — the **advanced entry class** — still works with
`WebRuntimeConfig(drain_timeout=...)`, and an explicitly passed runtime config
takes precedence.

Three things worth knowing about the bound:

1. **It is enforced, not advisory.** With `drain_timeout=1.0` and a request that
   needs 6s, the process is gone in about 1.1–1.4s on either engine — the bound plus
   teardown, not a fixed per-engine figure — and the slow request is cut. What the cut looks like to the client differs:
   ASGI returns a `500` (the server cancels the task), Tornado drops the
   connection. If you need slow requests to finish, say so with a larger bound.
2. **It must fit your platform.** It should be longer than your slowest normal
   request and shorter than the orchestrator's kill grace period; the framework
   cannot know either number for you.
3. **The result is reported.** `ApplicationContext.shutdown()` and `ashutdown()`
   return `True` when the drain finished inside the bound and `False` when it
   timed out. One caveat: called from a thread inside a running event loop, the
   synchronous form refuses to block that loop, logs a warning, returns `False`,
   **and still closes the container** — so `False` means "did not wait", not
   "nothing happened".

### Stopping from your own code

A signal is not always something you can send. On Windows `terminate()` is
`TerminateProcess`: the process disappears without draining, and `SIGBREAK` only
reaches a process that owns a console. A supervisor, an admin route, or a test
still needs a way to ask a **running** server to stop — and `run()` blocks, so the
object to ask is not the one you are holding.

```python
from cullinan.application import Application

app = Application.current()          # reachable while run() is blocking
if app is not None:
    asked = app.request_shutdown()   # True: a server was asked to drain
```

| Value | Meaning |
|---|---|
| `True` | a running server was asked to stop; the sequence above begins |
| `False` | there was nothing to ask — the server had not started or had already stopped |

`request_shutdown()` runs the **same** drain a signal runs, so there is no second
shutdown path to keep correct. It is safe from any thread: the request is
scheduled onto the loop that owns the server (a threaded callback on Tornado,
`should_exit` on uvicorn), which is also why it works while the loop is idle. It
never raises to say "nothing to do" — `False` is the answer, because a
supervisor's exit path must not turn a finished shutdown into a crash.

Asking twice is not an error, and it does not drain twice: the second call still
answers `True` (the server has been asked to stop, and still will), while the
announcement and the wait behind it happen once. `False` keeps its single
meaning — there was nothing to ask.

The runnable version is `python -m examples.graceful_shutdown.stop_after`, which
waits until the application is serving and then asks it to stop from a thread
that is not serving requests.

## Probes: readiness and liveness are different questions

The framework does not register a health or readiness route for you. It gives
you the state and the transition:

| Surface | Answers |
|---|---|
| `Application.accepts_requests` | is this instance still willing to take new work? `False` from the moment draining begins |
| `Application.context.add_draining_handler(callback)` | run this the moment draining begins |

Because the drain is announced at the signal rather than after the wait, a
readiness route that reads the predicate — or simply returns `503` while
`accepts_requests` is `False` — changes while there is still traffic to shed:

```python
from cullinan.application import Application
from cullinan import controller
from cullinan.web import get_api


@controller(url="/ops")
class OpsController:
    @get_api(url="/ready")
    def ready(self):
        app = Application.current()
        ready = app is None or app.accepts_requests
        return {"ready": ready}
```

Keep liveness separate and answer it with `True`. During a graceful shutdown the
process is healthy and is *supposed* to stop taking traffic; a liveness probe
that reads draining state reports a healthy shutdown as a crash.

The runnable version of both probes is the
`examples/graceful_shutdown/` package: `python -m examples.graceful_shutdown`
starts it, and `root.py` holds the two routes.

## What the two engines do not share (yet)

The request path, the response bodies and the status codes for normal traffic
are the same on both engines. These are not, and are listed so you can plan
around them rather than discover them:

- the `server` response header (`uvicorn` versus `TornadoServer`), which is set
  by the server, not by the framework;
- during a drain, whether a *new* connection is answered `503` (Tornado) or not
  accepted at all (ASGI, because uvicorn closes the listener first) — see the
  shutdown section above;
- what a client sees when the drain bound cuts an in-flight request: `500` on
  ASGI, a dropped connection on Tornado;
- the status for a body over `max_request_body_bytes`: `413` on ASGI, `400` on
  Tornado — see the request-body section below; both stop reading at the limit,
  which is the part that matters.

For normal traffic the two engines agree on status codes, bodies, `Allow` on a
`405`, and `404` for an `OPTIONS` on an unknown path. The differences above are
listed so you can plan around them rather than discover them.

## Reverse proxies and forwarded headers

Behind a proxy the client address and scheme arrive in headers, not in the
connection. Trust them only when a proxy you control sets them:

```python
from cullinan.web.gateway import WebRuntimeConfig

config = WebRuntimeConfig(trust_forwarded_headers=True)
```

With it off — the default — the framework reads the connection. Turning it on
when there is no proxy lets a client claim any address it likes, which is how
per-IP rate limits and audit logs quietly stop meaning anything.

## The exit status after `SIGTERM`

The drain completing and the process exiting are two different events, and the
status depends on **which engine** shut down:

| Engine | Exit status after a clean drain | Where it was measured |
|---|---|---|
| ASGI (uvicorn) | `143` — Python reports the child as `-15` | Linux and macOS |
| Tornado | `0` | Linux, macOS (`SIGTERM`) and Windows (`SIGBREAK`); the adapter stops its own loop and returns |

With uvicorn the non-zero status is by design: after the loop has drained and
the lifespan has closed it restores the original handlers and **re-raises the
signal it captured**, so the shell and any supervisor see the real cause — not
an aborted shutdown:

```
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [2550]
# ASGI:  $? is 143 (128 + 15)
```

The Tornado adapter has no such step: it stops the loop it owns and returns, so
the process leaves with `0`.

Read the log for whether the drain completed, not the exit status. A supervisor
that requires `0` will report a healthy uvicorn shutdown as a crash, and one
that requires `143` will report a healthy Tornado shutdown as one too.

## Request body size

The framework reads the body before it knows which route will handle it, so a
ceiling has to be enforced at the edge:

```python
from cullinan import application, configure


@configure(user_packages=["your_app"], max_request_body_bytes=1_000_000)
@application
def main(): ...
```

With no value set, whatever the client sends is read — the historical
behaviour, kept as the default because turning it into a limit would break
existing uploads. With a value, a body that crosses it is refused **without
reading the rest of it**, before any handler runs. The status depends on which
layer refuses, and that differs by engine:

| Engine | Oversized body |
|---|---|
| ASGI | `413 Payload Too Large` with a JSON body, raised by the adapter |
| Tornado | `400 Bad Request` with an empty body, raised by Tornado's protocol layer (`max_body_size`) before the framework sees the request |

That table is the server's answer. What the **client** sees is a different
question, and it turns on one thing: was the client still writing when the
refusal landed?

| Client behaviour | What it observes |
|---|---|
| Finished writing before the refusal landed | `400` with an empty body — the reset arrives afterwards, by which time the response has been read |
| Still writing when the refusal landed | the connection is reset or aborted (`ConnectionResetError` / `ConnectionAbortedError`; WSAECONNRESET on Windows) — **no status line** |
| Streams it in chunks (`Transfer-Encoding: chunked`) | the connection is aborted — **no status line** |

The dividing line is not the ratio but the race. Measured against a 1 KiB ceiling
on Windows: a 2 KiB body and a 64 KiB body, each sent in a single write, both
returned a readable `400` — the second one's reset arrived on the next read, too
late to hide it. The same 64 KiB sent in 1 KiB pieces, and a chunked upload only
1.5× over, ended with no status line at all. A large body is not by itself what
denies you the status code; writing it slowly is.

Those three cases run as a test against a live server
(`tests/integration/test_tornado_client_view_of_an_oversized_body.py`), because
"measured" written in a page is a claim, and a claim with no executor is what
drifts.

Two consequences for callers:

- **Do not use "received a `400`" as the oversize signal.** The reliable signal
  is that the request did not complete normally; on an upload path, treat a
  reset or an abort as a possible oversized body.
- **Measure the payload before sending it** when the size is yours to know. A
  server that has already refused cannot give you a status code it never sends.

Both engines stop early, which is the property that matters; the two are not the
same status, and pretending otherwise would be a difference you discover in
production.

Set it if the deployment accepts uploads from anywhere: without a ceiling, a
1 MiB body posted to a path that does not exist is read in full before the
`404`.

## Static files

Two valid deployments:

- **Serve statics from the proxy.** Fastest, and it keeps the application process
  doing only application work. Point the proxy at the same directory.
- **Serve them from the application** with `configure(static_files=[...])`. Useful
  when you have no proxy, or when the files are generated by the app itself.

Either way, set a cache policy at the layer that serves them; the framework does
not guess one for you.

## Upgrades and deprecation windows

Removals are announced with a version, and the announced version does not move.
That is the difference between a deprecation you can plan around and one that
slides forward every release until nobody believes it.

When a symbol is deprecated, the removal version is computed from the version line
the deprecation landed on plus the policy window — never written as a literal in
the source, so there is one value and not two. If you pin a version range in
production, pin against the announced removal, not against "a few releases from
now".

## A deployment checklist

Before you call a deployment production-ready:

- [ ] the process runs under a supervisor that forwards `SIGTERM` and waits
- [ ] `drain_timeout` is longer than your slowest normal request
- [ ] the orchestrator's kill timeout is longer than `drain_timeout`
- [ ] the load balancer's idle timeout is longer than the readiness probe interval
- [ ] readiness reads `accepts_requests`; liveness does not
- [ ] the proxy strips inbound `X-Forwarded-*` unless it sets them itself
- [ ] you know whether statics are served by the proxy or the application, and the
      cache policy is set at that layer
- [ ] you have watched one graceful shutdown on **your** engine and seen what it actually does: on Tornado a `503` from a request that arrives mid-drain, on ASGI the instance stop answering — and you have confirmed your probe treats both as "do not send traffic"

The last one is not a formality: it is the only check that proves the whole chain
— signal, drain, probe, load balancer — is wired.
