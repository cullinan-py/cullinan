# -*- coding: utf-8 -*-
"""POSIX signals: the exit status differs by engine, so both are pinned here.

Every shutdown measurement in this project was originally taken on Windows,
where ``SIGTERM`` cannot be delivered to another process. This module exists so
the POSIX behaviour is asserted by a run rather than described in prose:

* ASGI (uvicorn) re-raises the signal it captured after the drain, so the
  process leaves with ``143`` (Python reports ``-SIGTERM``);
* Tornado stops the loop it owns and returns, so it leaves with ``0``.

A test that accepted "0 or -SIGTERM" would pass for either engine and therefore
prove neither -- which is exactly the mistake this file is meant to prevent.

The suite runs on ubuntu in CI, so these assertions execute there; on Windows
they are skipped with the reason stated, because the signal does not exist.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PORT = 4082  # examples/graceful_shutdown pins this in its @configure
ENGINE_TIMEOUT = 30

#: A request to loopback must not go through an HTTP proxy. ``urllib`` reads
#: ``HTTP_PROXY``/``http_proxy`` from the environment and routes ``127.0.0.1`` through it
#: unless ``NO_PROXY`` says otherwise, so a readiness probe would be answered by the
#: proxy -- 502 when it cannot reach the server being probed -- instead of by the server.
#: The same hole made ``tests/fixtures/programmatic_shutdown_app.py`` red under load.
_LOOPBACK_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="SIGTERM cannot be delivered to another process on Windows; SIGBREAK covers the same path",
)


def _wait_ready(deadline: float) -> bool:
    url = f"http://127.0.0.1:{PORT}/ops/ready"
    while time.monotonic() < deadline:
        try:
            with _LOOPBACK_OPENER.open(url, timeout=1) as response:
                if response.status == 200 and json.loads(response.read()).get("ready") is True:
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(0.1)
    return False


def _start(engine: str) -> subprocess.Popen:
    env = dict(os.environ, PYTHONUNBUFFERED="1", CULLINAN_ENGINE=engine)
    return subprocess.Popen(
        [sys.executable, "-m", "examples.graceful_shutdown"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _run(engine: str) -> tuple[int, str, float]:
    proc = _start(engine)
    try:
        if not _wait_ready(time.monotonic() + 40):
            proc.kill()
            output = proc.communicate(timeout=10)[0]
            pytest.fail(f"{engine} never became ready on port {PORT}:\n{output[-2000:]}")
        started = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        returncode = proc.wait(timeout=ENGINE_TIMEOUT)
        elapsed = time.monotonic() - started
        output = proc.stdout.read() if proc.stdout else ""
        return returncode, output, elapsed
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)


def test_asgi_exits_by_the_signal_it_received():
    """uvicorn restores its handlers and re-raises SIGTERM once the drain is done."""
    returncode, output, elapsed = _run("asgi")
    lowered = output.lower()

    assert "application shutdown complete" in lowered, (
        f"the lifespan never closed, so this was a kill rather than a drain:\n{output[-2000:]}"
    )
    assert elapsed < 15, f"the process took {elapsed:.1f}s to leave; the drain bound was not applied"
    assert returncode == -signal.SIGTERM, (
        f"expected the re-raised signal (-{signal.SIGTERM}, i.e. 143), got {returncode}:\n{output[-2000:]}"
    )


def test_tornado_exits_with_zero():
    """Tornado's adapter stops its own loop and returns, so nothing re-raises."""
    returncode, output, elapsed = _run("tornado")

    assert elapsed < 15, f"the process took {elapsed:.1f}s to leave; the drain bound was not applied"
    assert returncode == 0, (
        f"the Tornado adapter returns from its loop, so it must exit 0; got {returncode}:\n{output[-2000:]}"
    )


def test_a_request_during_the_drain_is_refused_rather_than_answered():
    """On POSIX the listener behaviour can differ from the Windows runs.

    What must hold everywhere: a request that lands while draining is either
    refused at the transport or answered 5xx -- it is never served as if the
    instance were healthy.
    """
    proc = _start("asgi")
    try:
        if not _wait_ready(time.monotonic() + 40):
            proc.kill()
            pytest.fail("server never became ready")
        proc.send_signal(signal.SIGTERM)

        status = None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/ops/ready", timeout=1) as response:
                    status = response.status
            except urllib.error.HTTPError as exc:
                status = exc.code
                break
            except (urllib.error.URLError, OSError):
                status = "refused"
                break
            time.sleep(0.02)

        assert status in (503, "refused"), f"a mid-drain request was answered with {status}"
        proc.wait(timeout=ENGINE_TIMEOUT)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
