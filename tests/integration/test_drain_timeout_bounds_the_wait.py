# -*- coding: utf-8 -*-
"""Does ``drain_timeout`` actually bound the wait, or only reach the call?

The wiring test proves the number arrives at ``context.shutdown(timeout=...)``. That is
necessary and it is not the claim: a value that is passed correctly and then not
enforced would pass it too. The claim is behavioural -- a request longer than the bound
is cut when the bound expires, and the same request inside a longer bound finishes.

So this file starts a real server, sends a request that takes five seconds, asks for a
shutdown, and measures wall clock and outcome:

* ``drain_timeout=1.0`` ⇒ the process leaves in about a second and the request does not
  complete;
* ``drain_timeout=10.0`` ⇒ the request completes with 200 and the process leaves after
  it.

Both engines, because "the bound is enforced" is a property of the shutdown sequence,
not of one adapter. The tolerance is wide on purpose (0.8–4.0s for a 1s bound): this
measures that the bound exists, not how precisely a Python process can be scheduled.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "tests" / "fixtures" / "programmatic_shutdown_app.py"
SLOW_SECONDS = 5.0
RUN_TIMEOUT = 120.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _run(engine: str, *, drain_timeout: float) -> dict:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT)] + ([existing] if existing else []))
    env["PYTHONUNBUFFERED"] = "1"
    env["CULLINAN_ENGINE"] = engine
    env["SHUTDOWN_HARNESS_PORT"] = str(_free_port())
    env["SHUTDOWN_HARNESS_SLOW_SECONDS"] = str(SLOW_SECONDS)
    env["SHUTDOWN_HARNESS_DRAIN_TIMEOUT"] = str(drain_timeout)

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
        f"the {engine} run exited {completed.returncode} instead of completing:\n{output[-3000:]}"
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
def test_a_short_bound_cuts_the_request_and_leaves_on_time(engine):
    """The request must not succeed, and the drain must end when the bound says.

    "Did not succeed" is the property, not "the client saw an abort": uvicorn answers
    ``500`` when it cancels the task at the bound, while Tornado stops the loop and the
    connection closes with the process, so the client may report no status at all.
    """
    results = _run(engine, drain_timeout=1.0)

    assert results.get("inflight") != 200, (
        f"{engine}: the 5s request came back {results.get('inflight')!r} even though the "
        "drain bound was 1s, so the bound did not cut anything"
    )
    assert 0.8 <= results["drain_seconds"] <= 4.0, (
        f"{engine}: the drain took {results['drain_seconds']}s with a 1s bound; the bound is "
        "not what ended the wait"
    )


@pytest.mark.parametrize("engine", ["tornado", "asgi"])
def test_a_long_bound_lets_the_request_finish(engine):
    results = _run(engine, drain_timeout=10.0)

    assert results.get("inflight") == 200, (
        f"{engine}: the 5s request got {results.get('inflight')!r} under a 10s drain bound; "
        "the bound cut a request that fitted inside it"
    )
    assert results["drain_seconds"] >= SLOW_SECONDS * 0.9, (
        f"{engine}: the drain took {results['drain_seconds']}s, before the 5s request could "
        "have finished -- so it did not wait for it"
    )
