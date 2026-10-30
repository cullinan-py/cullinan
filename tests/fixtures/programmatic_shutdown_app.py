# -*- coding: utf-8 -*-
"""A real application whose shutdown is requested from a thread, not a signal.

Run as a script by ``tests/integration/test_programmatic_shutdown.py``. Nothing
here is mocked: a real server starts, a real request is in flight, and another
thread asks the application to stop. The script prints one machine-readable line
(``RESULT {...}``) describing what the client observed, and the test asserts on
that line rather than on internals.

Deliberately not a ``test_*.py``: it has to be a runnable ``__main__`` so that
``Application.request_shutdown()`` is reached the way an operator would reach it
-- after the server is already serving.

Configuration comes from the environment:

* ``SHUTDOWN_HARNESS_PORT`` -- the port to bind (the test picks a free one);
* ``CULLINAN_ENGINE`` -- which backend to run, read by the framework itself.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import urllib.error
import urllib.request

from cullinan import application, configure, controller
from cullinan.application import Application
from cullinan.web import get_api

PORT = int(os.environ.get("SHUTDOWN_HARNESS_PORT", "4083"))
SLOW_SECONDS = 1.0

#: A request to loopback must not go through an HTTP proxy.
#:
#: ``urllib`` reads ``HTTP_PROXY``/``http_proxy`` from the environment and, unless
#: ``NO_PROXY`` names the host, routes ``127.0.0.1`` through it like anything else.
#: That turns a measurement into a measurement of the proxy: when the server closes its
#: listener during the drain, the proxy cannot reach the upstream and answers **502** --
#: a status no part of this framework produces. Measured under load, it turned roughly
#: two runs in ten red for a reason that had nothing to do with the code under test.
_LOOPBACK_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

results: dict = {}
slow_started = threading.Event()


@controller(url="/ops")
class OpsController:
    @get_api(url="/slow")
    async def slow(self):
        # ``async`` on purpose: a handler that blocks the loop would keep the
        # server from answering anything -- including the shutdown the test is
        # about to request -- and the whole point is that the loop stays free
        # while one request is in flight.
        slow_started.set()
        await asyncio.sleep(SLOW_SECONDS)
        return {"slept": SLOW_SECONDS}

    @get_api(url="/live")
    def live(self):
        return {"alive": True}


@configure(server_port=PORT, drain_timeout=20.0)
@application
def main(): ...


def _status(path: str, timeout: float = 10.0):
    """The status code, or ``error:<kind>`` when the connection gave way."""
    try:
        with _LOOPBACK_OPENER.open(f"http://127.0.0.1:{PORT}{path}", timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError) as exc:
        return f"error:{type(exc).__name__}"


def _drive() -> None:
    deadline = time.monotonic() + 40.0
    while time.monotonic() < deadline:
        if _status("/ops/live", timeout=1.0) == 200:
            break
        time.sleep(0.05)
    else:
        results["error"] = "the server never became ready"
        return

    inflight: dict = {}

    def _slow_request() -> None:
        inflight["status"] = _status("/ops/slow", timeout=30.0)

    thread = threading.Thread(target=_slow_request, daemon=True)
    thread.start()
    if not slow_started.wait(10.0):
        results["error"] = "the slow request never started"
        return
    # The handler has been entered; give the response a moment to still be
    # pending, so "in flight" is a fact rather than a hope.
    time.sleep(0.1)

    app = Application.current()
    # This thread is not the loop thread. That is the property under test.
    results["asked"] = None if app is None else app.request_shutdown()

    results["during_drain"] = _status("/ops/live", timeout=10.0)

    thread.join(timeout=30.0)
    results["inflight"] = inflight.get("status")


def run() -> int:
    thread = threading.Thread(target=_drive, daemon=True)
    thread.start()
    try:
        main()
    finally:
        thread.join(timeout=40.0)
    print("RESULT " + json.dumps(results), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
