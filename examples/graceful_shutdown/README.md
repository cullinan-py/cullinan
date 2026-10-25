# Graceful Shutdown and Readiness

Shows how a deployment learns that an instance is going away, and how an
application answers "should I still receive traffic?" from state the framework
already tracks.

Two surfaces, both on the application:

| Surface | Answers | Use it for |
|---|---|---|
| `Application.accepts_requests` | is this instance still willing to take new work? | a readiness probe — it flips to `False` the moment draining begins |
| `Application.context.add_draining_handler(callback)` | *the moment* draining begins | taking the instance out of a load balancer, flushing a queue, closing a pool |

Readiness and liveness are different questions. This example answers liveness
from a constant on purpose: during a graceful shutdown the process is healthy
and is supposed to stop taking traffic, so a liveness probe that reads draining
state would report a healthy shutdown as a crash and invite a restart.

## Run it

The whole transition, without a server:

```bash
python -m examples.graceful_shutdown.demo
```

The application itself:

```bash
python -m examples.graceful_shutdown
```

## Endpoints

| Path | Meaning |
|---|---|
| `/ops/ready` | readiness — a request on an established connection gets `503` while draining; under ASGI the listener is closed first, so a *new* connection is not accepted |
| `/ops/live` | liveness — `{"alive": true}` for as long as the process runs |

Wire `/ops/ready` to your readiness probe and `/ops/live` to your liveness
probe. Neither path is registered by the framework for you: the route is yours,
because the probe is part of your operations story.

## The drain bound

The framework waits up to `WebRuntimeConfig.drain_timeout` (default 30s) for
in-flight requests before closing. That is the same value the ASGI lifespan
shutdown uses, so the number your process waits for and the number the
framework waits for cannot disagree. A drain that finishes inside the bound
returns `True`; one that times out returns `False` — read the return value
rather than parsing logs.

## Try the transition by hand

```bash
python -m examples.graceful_shutdown          # in one terminal
curl -i http://127.0.0.1:4082/ops/ready       # 200 {"ready": true}
# send a stop signal to the process, then:
curl -i http://127.0.0.1:4082/ops/ready       # 503 while the drain is running
```

While a long request is still running you will see `503` before the process
exits — that window is the whole point, and it is why the drain is announced at
the signal rather than after the wait.
