# -*- coding: utf-8 -*-
"""Graceful-drain semantics.

These pin the behaviour that makes shutdown actually graceful:

* the synchronous ``shutdown()`` must never block a running event loop (a
  blocking wait inside the loop starves the very requests the drain waits for);
* the asynchronous ``ashutdown()``/``await_drained()`` must let in-flight
  request scopes finish;
* the ASGI lifespan shutdown must take the loop-friendly path.
"""

import asyncio
import time

import pytest

from cullinan.core.application_context import ApplicationContext, ContainerState


def _new_context(container_id: str) -> ApplicationContext:
    """A context that has reached ACTIVE, so request scopes may be entered."""
    ctx = ApplicationContext(container_id=container_id)
    ctx.refresh()
    return ctx


def test_sync_shutdown_inside_running_loop_does_not_block(caplog):
    """Calling shutdown() from a live loop must return at once, not stall."""
    captured: dict = {}

    async def scenario():
        ctx = _new_context("drain-sync")
        ctx.enter_request_context()          # one in-flight request scope
        started = time.monotonic()
        with caplog.at_level("WARNING"):
            ctx.shutdown(timeout=2.0)
        captured["elapsed"] = time.monotonic() - started
        # The scope is deliberately left open: the point is that shutdown()
        # returned anyway instead of blocking the loop for the whole timeout.
        ctx.exit_request_context()

    asyncio.run(scenario())

    assert captured["elapsed"] < 0.5, (
        f"shutdown() blocked the loop for {captured['elapsed']:.2f}s"
    )
    assert any("running event loop" in record.message for record in caplog.records), (
        "the non-blocking skip must be reported, never silent"
    )


def test_ashutdown_drains_in_flight_scope():
    """The async path must give in-flight scopes room to finish."""

    async def scenario():
        ctx = _new_context("drain-async")
        ctx.enter_request_context()

        async def finish_request():
            await asyncio.sleep(0.05)
            ctx.exit_request_context()

        asyncio.create_task(finish_request())
        await ctx.ashutdown(timeout=2.0)
        return ctx

    ctx = asyncio.run(scenario())

    assert ctx.active_request_count == 0
    assert ctx.state is ContainerState.CLOSED


def test_await_drained_reports_timeout_without_blocking():
    """A scope that never closes must time out with a False, not a hang."""

    async def scenario():
        ctx = _new_context("drain-timeout")
        ctx.enter_request_context()
        started = time.monotonic()
        drained = await ctx.await_drained(timeout=0.05)
        return drained, time.monotonic() - started

    drained, elapsed = asyncio.run(scenario())

    assert drained is False
    assert elapsed < 1.0


def test_asgi_lifespan_shutdown_takes_the_loop_friendly_path(monkeypatch):
    """The ASGI lifespan handler must drain without blocking its own loop."""
    from cullinan.transport.adapter import asgi_adapter

    ctx = _new_context("drain-asgi")
    ctx.enter_request_context()

    monkeypatch.setattr("cullinan.core.get_application_context", lambda: ctx)

    messages = [{"type": "lifespan.shutdown"}]
    sent: list = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    async def scenario():
        async def finish_request():
            await asyncio.sleep(0.05)
            ctx.exit_request_context()

        asyncio.create_task(finish_request())
        await asgi_adapter._handle_lifespan({"type": "lifespan"}, receive, send)

    asyncio.run(scenario())

    assert {"type": "lifespan.shutdown.complete"} in sent
    assert ctx.active_request_count == 0, "in-flight scope was starved by the loop"


@pytest.mark.parametrize("timeout", [0.0, 0.05])
def test_await_drained_returns_true_when_already_idle(timeout):
    async def scenario():
        ctx = _new_context(f"drain-idle-{timeout}")
        return await ctx.await_drained(timeout=timeout)

    assert asyncio.run(scenario()) is True
