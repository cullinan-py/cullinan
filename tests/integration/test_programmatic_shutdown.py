# -*- coding: utf-8 -*-
"""A programmatic stop: asked from a thread, answered on the loop.

The drain sequence has been correct since a6 -- stop accepting, finish what is in
flight, then stop the loop -- but for two releases only a signal could reach it.
``run()`` blocks, so a caller that wanted to stop a server had no object to call,
and every claim about "stopping without dropping requests" rested on a release
note rather than on a run.

Two kinds of evidence here, deliberately:

* a **real** server and a **real** in-flight request, in a subprocess, on both
  engines: nothing is mocked, and what is asserted is what a client observed
  (``tests/fixtures/programmatic_shutdown_app.py`` drives it);
* the unit-level fact underneath it: the loop is woken by a request that came
  from a thread that does not own it. That is the property that breaks silently
  -- a stop that queues work without waking an idle loop looks exactly like a
  hang.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "tests" / "fixtures" / "programmatic_shutdown_app.py"

# Generous on purpose: the slow request is 1s and the drain bound is 20s, so a
# healthy run is a few seconds. This only has to be shorter than the test
# session's own patience.
RUN_TIMEOUT = 90.0


def _free_port() -> int:
    """Ask the OS for a port nobody is using, then let go of it.

    Chosen this way rather than with a fixed number: a fixed port turns an
    unrelated process on the machine into a failure of this test, which is the
    kind of red that teaches people to re-run instead of to look.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _run_harness(engine: str) -> dict:
    port = _free_port()
    env = dict(os.environ)
    existing_path = env.get("PYTHONPATH", "")
    entries = [str(REPO_ROOT)] + ([existing_path] if existing_path else [])
    env["PYTHONPATH"] = os.pathsep.join(entries)
    env["PYTHONUNBUFFERED"] = "1"
    env["CULLINAN_ENGINE"] = engine
    env["SHUTDOWN_HARNESS_PORT"] = str(port)

    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, "-u", str(HARNESS)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
    )
    elapsed = time.monotonic() - started
    output = (completed.stdout or "") + (completed.stderr or "")

    assert completed.returncode == 0, (
        f"the {engine} run exited {completed.returncode} instead of completing the "
        f"shutdown:\n{output[-3000:]}"
    )

    results = None
    for line in (completed.stdout or "").splitlines():
        if line.startswith("RESULT "):
            results = json.loads(line[len("RESULT "):])
    assert results is not None, f"the {engine} run printed no result line:\n{output[-3000:]}"
    assert "error" not in results, f"the {engine} harness could not set the scenario up: {results}"
    results["elapsed"] = elapsed
    return results


@pytest.mark.parametrize("engine", ["tornado", "asgi"])
def test_an_in_flight_request_finishes_and_the_next_one_is_refused(engine):
    """The promise, measured: 200 for what was running, 503 for what came next.

    Both engines, because "graceful shutdown" that only works on one of them is
    half a feature -- and this repository has shipped that mistake before.

    The two engines are held to *different* proofs on purpose, because the page
    already documents that they behave differently here. `docs/deployment.md:90`
    says uvicorn "closes the listener as the *first* step of its shutdown and then
    calls ``shutdown()`` on every open connection, so there is **no window in which
    you can reach it on purpose**". A request that lands during the drain is then
    answered `503` only if it was already on its way; otherwise uvicorn aborts the
    connection and the client sees ``RemoteDisconnected``.

    Both outcomes are accepted for ASGI because both were *observed*, not inferred.
    Measured on this host with six CPU-bound processes running, ten runs of the ASGI
    harness with the client bypassing the HTTP proxy: `503` five times,
    ``error:RemoteDisconnected`` five times, nothing else (see the log in the
    implementation record). An earlier version of the assertion accepted
    ``ConnectionResetError`` as well -- that spelling was never observed here, so it
    is not accepted now; if a POSIX run reports it for the same event, the failure
    message says which value arrived and the set needs that entry *with its own
    observation*.

    That measurement is why the first repair of this case had to be redone: the
    original 1-in-10 failure was not uvicorn at all. The harness reached loopback
    through ``HTTP_PROXY`` and the proxy answered `502` when the drained server
    stopped listening -- a status no part of this framework produces. The fixture now
    bypasses the proxy, and `502` is deliberately absent from the accepted values:
    accepting it would have hidden the defect that produced it.

    Tornado keeps the strict `503` expectation: it leaves the listener open and
    answered through it in every measured run.

    What is *not* relaxed on either engine is ``inflight == 200`` -- an in-flight
    request finishing is the whole point of REQ-003, and a drain that cuts it is the
    defect this case exists to catch.
    """
    results = _run_harness(engine)

    assert results["asked"] is True, (
        f"{engine}: request_shutdown() reported there was nothing to ask, while a "
        "server was serving"
    )
    assert results["inflight"] == 200, (
        f"{engine}: the request that was already running got {results['inflight']} "
        "instead of finishing -- the drain cut it"
    )
    if engine == "tornado":
        assert results["during_drain"] == 503, (
            f"tornado: a request that arrived after the stop was asked for got "
            f"{results['during_drain']}, not 503; this engine keeps the listener open "
            "and answers through it"
        )
    else:
        assert results["during_drain"] in (503, "error:RemoteDisconnected"), (
            "asgi: a request that arrived during the drain got "
            f"{results['during_drain']!r}. Observed values on this host (n = 10, six "
            "cores busy): 503 five times, error:RemoteDisconnected five times. uvicorn "
            "closes the listener first, so either the request was already on its way "
            "(503) or the connection went away under it -- and a 502 comes from a "
            "proxy, not from this framework"
        )
    assert results["elapsed"] < 60, (
        f"{engine}: the process took {results['elapsed']:.1f}s to leave; the drain "
        "was bounded by 20s"
    )


def _wait_until_serving(port: int, deadline: float) -> bool:
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def _wait_until_ready_to_stop(adapter, deadline: float) -> bool:
    """Wait for the hook to be published, not merely for the port to accept.

    ``run()`` binds the socket before it publishes the shutdown hook, so a client
    that connects the instant the port answers can still be a moment early. The
    readiness probe cannot see that difference; this can.
    """
    while time.monotonic() < deadline:
        if adapter._shutdown_requester is not None:
            return True
        time.sleep(0.01)
    return False


def test_the_loop_is_woken_by_a_request_from_another_thread():
    """Cross-thread safety, isolated: an idle loop must still hear the request.

    The server here is idle -- no request in flight, nothing to wake the
    selector -- so the only thing that can run the drain is the scheduling itself.
    A version that hands the coroutine to the loop on the wrong thread, or calls
    it inline, leaves this loop waiting forever; that is what the timeout
    reports.
    """
    from cullinan.transport.adapter.tornado_adapter import TornadoAdapter
    from cullinan.web.gateway.dispatcher import Dispatcher

    adapter = TornadoAdapter(Dispatcher())
    port = _free_port()
    thread = threading.Thread(
        target=adapter.run,
        kwargs={"host": "127.0.0.1", "port": port},
        daemon=True,
        name="tornado-loop",
    )
    thread.start()

    if not _wait_until_serving(port, time.monotonic() + 30.0):
        pytest.fail("the Tornado server never started listening, so nothing was measured")
    if not _wait_until_ready_to_stop(adapter, time.monotonic() + 10.0):
        pytest.fail("the shutdown hook was never published")

    # Let the loop settle back into an idle selector wait: a readiness probe that
    # just connected is itself an event, and the point is a loop with nobody
    # talking to it.
    time.sleep(0.3)

    assert adapter.request_shutdown() is True, (
        "request_shutdown() reported nothing to stop while the server was listening"
    )

    thread.join(timeout=20.0)
    assert not thread.is_alive(), (
        "the loop never stopped: the shutdown was not scheduled in a way that wakes "
        "an idle loop from another thread"
    )


def test_an_application_without_a_running_server_says_no():
    """``False`` is the answer, and it is not an exception.

    A supervisor calls this on the way out whether or not it started anything;
    raising would turn an already-finished shutdown into a crash.
    """
    from cullinan.application.model import Application, module

    @module(packages=["tests"])
    class _NeverStarted:
        pass

    application = Application(_NeverStarted)
    assert application.runtime is None
    assert application.request_shutdown() is False


def test_an_assembled_application_with_no_transport_says_no():
    from cullinan.application.model import Application, module
    from cullinan.web.gateway.runtime import WebRuntime

    @module(packages=["tests"])
    class _NeverServed:
        pass

    application = Application(_NeverServed)
    application.runtime = type("_Runtime", (), {})()
    application.runtime.web_runtime = WebRuntime()

    assert application.request_shutdown() is False


def test_asking_twice_schedules_the_drain_once():
    """A repeat request must report the same fact and do nothing again.

    The drain announces, waits and closes. Running that twice is not something
    anyone has a reason to ask for, and "the process still exited cleanly" is not
    evidence that it did not happen -- it is evidence that it survived. The count
    below is the evidence: the drain ran once, and the second call still answered
    ``True``, because "this server has been asked to stop" is still true.
    """
    from cullinan.transport.adapter.tornado_adapter import TornadoAdapter
    from cullinan.web.gateway.dispatcher import Dispatcher

    adapter = TornadoAdapter(Dispatcher())
    port = _free_port()
    calls: list[int] = []
    real_drain = adapter._shutdown_gracefully

    async def counting_drain():
        calls.append(1)
        # Hold the claim open long enough for the second call to arrive while the
        # hook is still published; without this the case would measure the race
        # between two threads rather than the guard.
        await asyncio.sleep(0.2)
        await real_drain()

    adapter._shutdown_gracefully = counting_drain
    thread = threading.Thread(
        target=adapter.run,
        kwargs={"host": "127.0.0.1", "port": port},
        daemon=True,
        name="tornado-double-request",
    )
    thread.start()

    if not _wait_until_serving(port, time.monotonic() + 30.0):
        pytest.fail("the Tornado server never started listening, so nothing was measured")
    if not _wait_until_ready_to_stop(adapter, time.monotonic() + 10.0):
        thread.join(timeout=5.0)
        pytest.fail("the shutdown hook was never published, so nothing could ask for a stop")

    try:
        assert adapter.request_shutdown() is True
        assert adapter.request_shutdown() is True, (
            "a repeat call reports the same fact: the server has been asked to stop"
        )
    finally:
        thread.join(timeout=20.0)

    assert not thread.is_alive(), "the server did not stop after the request"
    assert calls == [1], f"the drain was scheduled {len(calls)} times, expected once"


@pytest.mark.parametrize("adapter_name", ["tornado", "asgi"])
def test_an_adapter_that_is_not_serving_says_no(adapter_name):
    """The same answer one layer down, on both engines."""
    from cullinan.web.gateway.dispatcher import Dispatcher

    if adapter_name == "tornado":
        from cullinan.transport.adapter.tornado_adapter import TornadoAdapter as Adapter
    else:
        from cullinan.transport.adapter.asgi_adapter import ASGIAdapter as Adapter

    assert Adapter(Dispatcher()).request_shutdown() is False
