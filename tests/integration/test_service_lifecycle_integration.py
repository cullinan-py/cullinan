# -*- coding: utf-8 -*-
"""Test Service lifecycle integration into application startup flow (using ApplicationContext)"""

import asyncio

from cullinan.core import ApplicationContext, Inject, set_application_context
from cullinan.core.lifecycle_enhanced import reset_lifecycle_manager
from cullinan.core.pending import PendingRegistry
from cullinan.core.services import Service, service


STARTUP_LOG = []
SHUTDOWN_LOG = []
ASYNC_LOG = []


class DatabaseService(Service):
    def get_phase(self) -> int:
        return -100

    def on_startup(self):
        STARTUP_LOG.append("DatabaseService")

    def on_shutdown(self):
        SHUTDOWN_LOG.append("DatabaseService")


class BotService(Service):
    database: DatabaseService = Inject()

    def get_phase(self) -> int:
        return -50

    def on_startup(self):
        STARTUP_LOG.append("BotService")
        assert type(self.database).__name__ == "DatabaseService"

    def on_shutdown(self):
        SHUTDOWN_LOG.append("BotService")


class UserService(Service):
    def get_phase(self) -> int:
        return 0

    def on_startup(self):
        STARTUP_LOG.append("UserService")

    def on_shutdown(self):
        SHUTDOWN_LOG.append("UserService")


class AsyncBotService(Service):
    def get_phase(self) -> int:
        return -50

    async def on_startup_async(self):
        ASYNC_LOG.append("startup_begin")
        await asyncio.sleep(0.001)
        ASYNC_LOG.append("startup_complete")

    async def on_shutdown_async(self):
        ASYNC_LOG.append("shutdown_begin")
        await asyncio.sleep(0.001)
        ASYNC_LOG.append("shutdown_complete")


def _reset_state():
    STARTUP_LOG.clear()
    SHUTDOWN_LOG.clear()
    ASYNC_LOG.clear()
    PendingRegistry.reset()
    reset_lifecycle_manager()
    set_application_context(None)


def test_service_lifecycle_with_phase():
    _reset_state()
    service(DatabaseService)
    service(BotService)
    service(UserService)

    ctx = ApplicationContext()
    set_application_context(ctx)
    try:
        ctx.refresh()

        expected_order = ["DatabaseService", "BotService", "UserService"]
        assert STARTUP_LOG == expected_order
        assert set(ctx.list_definitions()) >= {"DatabaseService", "BotService", "UserService"}
    finally:
        ctx.shutdown()
        set_application_context(None)
        PendingRegistry.reset()
        reset_lifecycle_manager()

    expected_shutdown = ["UserService", "BotService", "DatabaseService"]
    assert SHUTDOWN_LOG == expected_shutdown
    _reset_state()


def test_async_lifecycle_hooks():
    _reset_state()
    service(AsyncBotService)

    ctx = ApplicationContext()
    set_application_context(ctx)
    try:
        ctx.refresh()

        assert "startup_begin" in ASYNC_LOG
        assert "startup_complete" in ASYNC_LOG
    finally:
        ctx.shutdown()
        set_application_context(None)
        PendingRegistry.reset()
        reset_lifecycle_manager()

    assert "shutdown_begin" in ASYNC_LOG
    assert "shutdown_complete" in ASYNC_LOG
    _reset_state()
