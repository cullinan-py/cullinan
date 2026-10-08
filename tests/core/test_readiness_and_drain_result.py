# -*- coding: utf-8 -*-
"""Readiness predicate, draining subscription, and drain-result signalling.

These pin the Python-native readiness surface: a queryable predicate plus a
plain callback registration (mirroring ``add_shutdown_handler``), so a serving
layer can shed traffic without the framework dictating a route, a management
port or an event bus. They also pin that shutdown reports whether it actually
drained, instead of only logging it.
"""

import asyncio

import pytest

from cullinan.core.application_context import ApplicationContext, ContainerState


def _active_context(container_id: str) -> ApplicationContext:
    ctx = ApplicationContext(container_id=container_id)
    ctx.refresh()
    return ctx


def test_accepts_requests_is_true_while_active():
    ctx = _active_context("ready-active")
    assert ctx.accepts_requests is True


def test_accepts_requests_flips_false_on_draining():
    ctx = _active_context("ready-draining")
    ctx.begin_draining()
    assert ctx.accepts_requests is False
    assert ctx.state is ContainerState.DRAINING


def test_rejected_request_while_draining_matches_the_predicate():
    ctx = _active_context("ready-reject")
    assert ctx.accepts_requests is True
    ctx.begin_draining()
    with pytest.raises(Exception):
        ctx.enter_request_context()


def test_draining_handler_fires_once_on_transition():
    ctx = _active_context("ready-handler")
    calls = []
    ctx.add_draining_handler(lambda: calls.append("drained"))

    ctx.begin_draining()
    ctx.begin_draining()          # already draining: must not re-fire

    assert calls == ["drained"]


def test_draining_handler_failure_does_not_block_draining():
    ctx = _active_context("ready-handler-error")
    seen = []

    def boom():
        raise RuntimeError("handler exploded")

    ctx.add_draining_handler(boom)
    ctx.add_draining_handler(lambda: seen.append("after"))

    ctx.begin_draining()

    assert ctx.state is ContainerState.DRAINING
    assert seen == ["after"], "a failing handler must not stop the others"


def test_shutdown_reports_a_completed_drain():
    ctx = _active_context("ready-drain-ok")
    assert ctx.shutdown(timeout=0.5) is True
    assert ctx.state is ContainerState.CLOSED


def test_shutdown_reports_a_timed_out_drain():
    ctx = _active_context("ready-drain-timeout")
    ctx.enter_request_context()          # never released

    drained = ctx.shutdown(timeout=0.05)

    assert drained is False, "a timed-out drain must not report success"
    assert ctx.state is ContainerState.CLOSED


def test_ashutdown_reports_a_completed_drain():
    async def scenario():
        ctx = _active_context("ready-adrain-ok")
        return await ctx.ashutdown(timeout=0.5)

    assert asyncio.run(scenario()) is True


def test_ashutdown_reports_a_timed_out_drain():
    async def scenario():
        ctx = _active_context("ready-adrain-timeout")
        ctx.enter_request_context()
        return await ctx.ashutdown(timeout=0.05)

    assert asyncio.run(scenario()) is False


def test_application_exposes_the_readiness_predicate():
    from cullinan.application.model import Application

    assert isinstance(Application.accepts_requests, property)
    assert hasattr(Application, "add_draining_handler")
