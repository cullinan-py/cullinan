# -*- coding: utf-8 -*-
"""Global root container management and high-availability failover tests."""

from cullinan.core import (
    ApplicationContext,
    Definition,
    ScopeType,
    get_application_context,
    get_container_manager,
    set_application_context,
)
from cullinan.core.exceptions import LifecycleError


class VersionedSingleton:
    def __init__(self, version: str):
        self.version = version


class VersionedRequest:
    def __init__(self, version: str):
        self.version = version


def _build_context(version: str) -> ApplicationContext:
    ctx = ApplicationContext(container_id=f"ctx-{version}")
    ctx.register(
        Definition(
            name="AppVersion",
            factory=lambda c, value=version: VersionedSingleton(value),
            scope=ScopeType.SINGLETON,
            source=f"test:singleton:{version}",
            eager=True,
        )
    )
    ctx.register(
        Definition(
            name="RequestVersion",
            factory=lambda c, value=version: VersionedRequest(value),
            scope=ScopeType.REQUEST,
            source=f"test:request:{version}",
        )
    )
    return ctx


def setup_function():
    set_application_context(None)


def teardown_function():
    set_application_context(None)


def test_replace_promotes_single_active_root():
    manager = get_container_manager()

    first = _build_context("v1")
    previous = manager.replace(first, refresh_if_needed=True, shutdown_replaced=False)

    assert previous is None
    assert get_application_context() is first
    assert first.get("AppVersion").version == "v1"

    second = _build_context("v2")
    previous = manager.replace(second, refresh_if_needed=True, shutdown_replaced=False)

    assert previous is first
    assert get_application_context() is second
    assert second.get("AppVersion").version == "v2"


def test_request_scope_snapshot_survives_root_switch():
    manager = get_container_manager()
    first = _build_context("v1")
    manager.replace(first, refresh_if_needed=True, shutdown_replaced=False)

    first.enter_request_context()
    try:
        old_request = first.get("RequestVersion")

        second = _build_context("v2")
        manager.replace(second, refresh_if_needed=True, shutdown_replaced=False)

        assert old_request.version == "v1"
        assert get_application_context() is second

        second.enter_request_context()
        try:
            new_request = second.get("RequestVersion")
            assert new_request.version == "v2"
        finally:
            second.exit_request_context()

        with _expect_lifecycle_error():
            first.enter_request_context()
    finally:
        first.exit_request_context()


def test_failed_candidate_refresh_does_not_replace_active_root():
    manager = get_container_manager()
    healthy = _build_context("healthy")
    manager.replace(healthy, refresh_if_needed=True, shutdown_replaced=False)

    broken = ApplicationContext(container_id="broken")
    broken.register(
        Definition(
            name="BrokenHealth",
            factory=lambda c: object(),
            scope=ScopeType.SINGLETON,
            source="test:broken",
            eager=True,
            healthcheck=lambda c, instance: False,
        )
    )

    with _expect_lifecycle_error():
        manager.replace(broken, refresh_if_needed=True, shutdown_replaced=False)

    assert get_application_context() is healthy


class _expect_lifecycle_error:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError("Expected LifecycleError to be raised")
        if not issubclass(exc_type, LifecycleError):
            return False
        return True
