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
last_updated: "2026-10-25T00:00:00Z"
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

## The shutdown sequence

On `SIGTERM` the process stops accepting new work, waits for the requests already
running, then exits. The wait is bounded by `drain_timeout`.

`drain_timeout` lives on the runtime configuration, which today is reached through
`Application(...)` — the **advanced entry class**. Most applications never touch
it: they declare an entry method and let the default (30s) apply. Reach for the
class only when the number has to change:

```python
from cullinan.application import Application
from cullinan.web.gateway import WebRuntimeConfig

app = Application(
    MyRoot,
    runtime_config=WebRuntimeConfig(drain_timeout=15.0),
).install()
```

Three things worth knowing about that bound:

1. **It is one number.** The lifespan shutdown and the synchronous shutdown path
   read the same configuration value, so what your process waits for and what the
   framework waits for cannot drift apart.
2. **Exceeding it is not an error, it is a decision.** When the bound passes, the
   remaining work is abandoned and the process closes. That is the correct
   behaviour for a stuck request, but it means `drain_timeout` should be longer
   than your slowest normal request and shorter than the point at which your
   orchestrator sends `SIGKILL`.
3. **The result is reported.** `ApplicationContext.shutdown()` and its async
   counterpart return `True` when the drain finished inside the bound and `False`
   when it timed out — so a shutdown that dropped work can be detected without
   reading logs.

If you are already inside an event loop, use the async form. The synchronous form
detects a running loop and refuses to block it, because blocking the loop there
starves the very requests it is waiting for; it logs a warning and returns rather
than pretending to have drained.

## Probes: readiness and liveness are different questions

The framework does not register a health or readiness route for you. That is
deliberate: a probe is part of your operations story, and a framework-chosen path
would be one more thing to disagree with your infrastructure.

What it does give you is the state and the transition:

| Surface | Answers |
|---|---|
| `Application.accepts_requests` | is this instance still willing to take new work? `False` once draining begins |
| `Application.context.add_draining_handler(callback)` | run this the moment draining begins |

A readiness probe that reads that predicate stops sending traffic at exactly the
moment the process starts finishing its work:

```python
from cullinan.application import Application
from cullinan.web import get_api


@get_api(url="/ready")
def ready(self):
    app = Application.current()
    return {"ready": bool(app is None or app.accepts_requests)}
```

Keep liveness separate and answer it with `True`. During a graceful shutdown the
process is healthy and is *supposed* to stop taking traffic; a liveness probe that
reads draining state reports a healthy shutdown as a crash and invites a restart
in the middle of a deploy. The runnable version of both probes is in
[the graceful shutdown example](examples.md).

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
- [ ] you have watched one graceful shutdown and seen the probe change before exit

The last one is not a formality: it is the only check that proves the whole chain
— signal, drain, probe, load balancer — is wired.
