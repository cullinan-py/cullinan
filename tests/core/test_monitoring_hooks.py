# -*- coding: utf-8 -*-
"""The monitoring hook surface: register, dispatch, and survive a bad hook.

Nothing in the framework imports this module, which is exactly why it had no
coverage: an unreferenced module is never executed by the suite, so a defect in
it would sit there until the first user found it.
"""

from __future__ import annotations

import pytest

from cullinan.monitoring import (
    MonitoringHook,
    MonitoringManager,
    get_monitoring_manager,
    reset_monitoring_manager,
)


@pytest.fixture(autouse=True)
def _isolated_global_manager():
    """The manager is process-global; cleanup must survive a failing assertion.

    Resetting at the end of a test body only runs when the test passes. A test
    that fails midway would leave hooks registered for every later test in the
    session, which turns one failure into a cascade whose cause is invisible.
    """
    reset_monitoring_manager()
    yield
    reset_monitoring_manager()


class RecordingHook(MonitoringHook):
    def __init__(self):
        super().__init__()
        self.calls = []

    def on_service_init(self, service_name, service):
        self.calls.append(("init", service_name))

    def on_service_destroy(self, service_name, service):
        self.calls.append(("destroy", service_name))

    def on_request_start(self, context):
        self.calls.append(("start", context.get("path")))

    def on_request_end(self, context):
        self.calls.append(("end", context.get("path")))

    def on_error(self, error, context=None):
        self.calls.append(("error", type(error).__name__))

    def on_custom_event(self, event_name, data):
        self.calls.append(("custom", event_name))


class ExplodingHook(RecordingHook):
    def on_request_start(self, context):
        raise RuntimeError("hook blew up")


def test_the_default_manager_starts_empty():
    """A test that fails midway must not leave its hooks behind for the next one.

    This asserts the cleanup, not the manager: without the autouse fixture the
    previous test's hook survives a failed assertion and this count is 1.
    """
    assert get_monitoring_manager().count() == 0


def test_every_event_reaches_a_registered_hook():
    manager = MonitoringManager()
    hook = RecordingHook()
    manager.register(hook)

    manager.on_service_init("svc", object())
    manager.on_service_destroy("svc", object())
    manager.on_request_start({"path": "/a"})
    manager.on_request_end({"path": "/a"})
    manager.on_error(ValueError("boom"))
    manager.on_custom_event("tick", 1)

    assert hook.calls == [
        ("init", "svc"),
        ("destroy", "svc"),
        ("start", "/a"),
        ("end", "/a"),
        ("error", "ValueError"),
        ("custom", "tick"),
    ]


def test_registering_something_that_is_not_a_hook_is_rejected():
    manager = MonitoringManager()
    with pytest.raises(TypeError):
        manager.register(object())


def test_unregister_reports_whether_it_removed_anything():
    manager = MonitoringManager()
    hook = RecordingHook()
    manager.register(hook)

    assert manager.unregister(hook) is True
    assert manager.unregister(hook) is False


def test_one_failing_hook_does_not_stop_the_others():
    """A monitoring hook must never be able to take the request path down."""
    manager = MonitoringManager()
    good = RecordingHook()
    manager.register(ExplodingHook())
    manager.register(good)

    manager.on_request_start({"path": "/survives"})

    assert good.calls == [("start", "/survives")]


def test_reset_empties_the_manager_without_invalidating_references():
    """``reset`` empties the manager rather than replacing it.

    Replacing the object would leave every reference taken earlier pointing at a
    manager nobody dispatches through any more, which is the kind of defect that
    only shows up in a caller that cached the instance.
    """
    manager = get_monitoring_manager()
    manager.register(RecordingHook())

    reset_monitoring_manager()

    assert get_monitoring_manager() is manager
    assert manager.count() == 0


def test_a_hook_registered_before_a_reset_no_longer_hears_anything():
    """The count alone would also pass if dispatch kept the old list alive."""
    manager = get_monitoring_manager()
    stale = RecordingHook()
    manager.register(stale)

    reset_monitoring_manager()
    manager.on_request_start({"path": "/after-reset"})

    assert stale.calls == []
