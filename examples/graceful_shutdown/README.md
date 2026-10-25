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
| `/ops/ready` | readiness — what a request sees mid-drain depends on the engine: Tornado answers `503`; ASGI closes the listener and then every open connection, so the probe mostly sees a refusal or a hang |
| `/ops/slow` | a 5s request, so there is still work in flight when the signal arrives |
| `/ops/live` | liveness — `{"alive": true}` for as long as the process runs |

Wire `/ops/ready` to your readiness probe and `/ops/live` to your liveness
probe. Neither path is registered by the framework for you: the route is yours,
because the probe is part of your operations story.

## The drain bound

The framework waits up to `drain_timeout` (default 30s, settable on
`@configure(...)`; **this example sets 2s** so that `/ops/slow` — which takes 5s —
is still running when the bound expires) for in-flight requests before closing. The same value is
handed to the server that actually does the waiting — uvicorn's graceful
shutdown timeout — so the number your process waits for and the number the
framework waits for cannot drift apart. A drain that finishes inside the bound
returns `True`; one that times out returns `False` — read the return value
rather than parsing logs.

## Try the transition by hand

The example runs on ASGI unless you set `CULLINAN_ENGINE=tornado`.

```bash
python -m examples.graceful_shutdown &        # in one terminal
curl -i http://127.0.0.1:4082/ops/ready       # 200 {"ready": true}
curl -i http://127.0.0.1:4082/ops/slow &      # takes 5s; still running when the bound expires
kill -TERM %1                                 # (Windows: Ctrl+Break on the console)
curl -i http://127.0.0.1:4082/ops/ready       # mid-drain: see the table below
```

What the next `curl /ops/ready` shows depends on the engine, and that difference
is real rather than a formatting detail:

| Engine | What you should see |
|---|---|
| Tornado | `503` with `Retry-After: 1` while `/ops/slow` is still running |
| ASGI (uvicorn) | a refused connection or a hang: uvicorn stops listening and then drops open connections, so there is no deliberate window in which to read a status |

Because the bound (2s) is shorter than the request (5s), the drain expires while
`/ops/slow` is still running: the process exits about two seconds after the
signal and `/ops/slow` is cut — on ASGI it gets a `500` (the server cancels the
task), on Tornado the connection is dropped. Raise `drain_timeout` above 5s and
the same request finishes with `200` and the process exits after it; that
difference is the knob doing its job, and it is the one thing worth trying
yourself.

The point of the exercise is that the framework's own state turned to "not
ready" at the signal rather than after the wait — the status code you happen to
observe depends on who still has a connection open.
