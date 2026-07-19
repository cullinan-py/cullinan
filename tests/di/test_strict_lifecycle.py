# -*- coding: utf-8 -*-
"""A3: strict_lifecycle configuration switch.

Verifies that the ``strict_lifecycle`` opt-out switch correctly causes
non-critical lifecycle hook failures (on_startup / on_shutdown) to
propagate as ``LifecycleError``, while the default behavior (v0.94)
logs and swallows them.

Critical hooks (on_post_construct / on_pre_destroy) always propagate,
regardless of the switch.

Context: ApplicationContext (v0.94 main path) treats on_startup /
on_shutdown as non-critical (log only), while LifecycleManager treats
them as critical (raise). strict_lifecycle=True aligns ApplicationContext
with LifecycleManager's strict semantics.
"""
import unittest

from cullinan.core.container import ApplicationContext, Definition, ScopeType
from cullinan.core.exceptions import LifecycleError
from cullinan.core.lifecycle_enhanced import SmartLifecycle


class _StartupFailsComponent(SmartLifecycle):
    """on_startup raises; on_post_construct succeeds."""
    def on_post_construct(self):
        pass

    def on_startup(self):
        raise RuntimeError("startup boom")


class _ShutdownFailsComponent(SmartLifecycle):
    """on_shutdown raises; on_pre_destroy succeeds."""
    def on_post_construct(self):
        pass

    def on_startup(self):
        pass

    def on_shutdown(self):
        raise RuntimeError("shutdown boom")

    def on_pre_destroy(self):
        pass


class _PostConstructFailsComponent(SmartLifecycle):
    """on_post_construct raises (critical hook)."""
    def on_post_construct(self):
        raise RuntimeError("post_construct boom")


class _PreDestroyFailsComponent(SmartLifecycle):
    """on_pre_destroy raises (critical hook)."""
    def on_post_construct(self):
        pass

    def on_startup(self):
        pass

    def on_shutdown(self):
        pass

    def on_pre_destroy(self):
        raise RuntimeError("pre_destroy boom")


def _register(ctx, name, cls):
    ctx.register(Definition(
        name=name,
        type_=cls,
        scope=ScopeType.SINGLETON,
        factory=lambda c, _cls=cls: _cls(),
        source=f"test:{name}",
    ))


class TestStrictLifecycleDefault(unittest.TestCase):
    """Default (strict_lifecycle=False): non-critical failures are swallowed."""

    def test_default_has_strict_lifecycle_false(self):
        ctx = ApplicationContext()
        self.assertFalse(ctx._strict_lifecycle)

    def test_startup_failure_swallowed_by_default(self):
        ctx = ApplicationContext()
        _register(ctx, "StartupFails", _StartupFailsComponent)
        # Should NOT raise: on_startup is non-critical, logged only.
        ctx.refresh()
        ctx.shutdown()

    def test_shutdown_failure_swallowed_by_default(self):
        ctx = ApplicationContext()
        _register(ctx, "ShutdownFails", _ShutdownFailsComponent)
        ctx.refresh()
        # Should NOT raise: on_shutdown is non-critical, logged only.
        ctx.shutdown()


class TestCriticalHooksAlwaysRaise(unittest.TestCase):
    """Critical hooks (on_post_construct / on_pre_destroy) always raise."""

    def test_post_construct_failure_raises_by_default(self):
        ctx = ApplicationContext()
        _register(ctx, "PostConstructFails", _PostConstructFailsComponent)
        with self.assertRaises(LifecycleError):
            ctx.refresh()

    def test_pre_destroy_failure_raises_by_default(self):
        ctx = ApplicationContext()
        _register(ctx, "PreDestroyFails", _PreDestroyFailsComponent)
        ctx.refresh()
        with self.assertRaises(LifecycleError):
            ctx.shutdown()

    def test_post_construct_failure_raises_in_strict_mode(self):
        ctx = ApplicationContext(strict_lifecycle=True)
        _register(ctx, "PostConstructFails", _PostConstructFailsComponent)
        with self.assertRaises(LifecycleError):
            ctx.refresh()

    def test_pre_destroy_failure_raises_in_strict_mode(self):
        ctx = ApplicationContext(strict_lifecycle=True)
        _register(ctx, "PreDestroyFails", _PreDestroyFailsComponent)
        ctx.refresh()
        with self.assertRaises(LifecycleError):
            ctx.shutdown()


class TestStrictLifecycleEnabled(unittest.TestCase):
    """strict_lifecycle=True: non-critical failures propagate."""

    def test_strict_lifecycle_true(self):
        ctx = ApplicationContext(strict_lifecycle=True)
        self.assertTrue(ctx._strict_lifecycle)

    def test_startup_failure_raises_in_strict_mode(self):
        ctx = ApplicationContext(strict_lifecycle=True)
        _register(ctx, "StartupFails", _StartupFailsComponent)
        with self.assertRaises(LifecycleError):
            ctx.refresh()

    def test_shutdown_failure_raises_in_strict_mode(self):
        ctx = ApplicationContext(strict_lifecycle=True)
        _register(ctx, "ShutdownFails", _ShutdownFailsComponent)
        ctx.refresh()
        with self.assertRaises(LifecycleError):
            ctx.shutdown()


class TestExceptionChain(unittest.TestCase):
    """raise LifecycleError(...) from exc must preserve __cause__ chain."""

    def test_startup_failure_preserves_cause(self):
        ctx = ApplicationContext(strict_lifecycle=True)
        _register(ctx, "StartupFails", _StartupFailsComponent)
        try:
            ctx.refresh()
        except LifecycleError as e:
            self.assertIsNotNone(e.__cause__)
            self.assertIsInstance(e.__cause__, RuntimeError)
            self.assertIn("startup boom", str(e.__cause__))
        else:
            self.fail("Expected LifecycleError")

    def test_post_construct_failure_preserves_cause(self):
        ctx = ApplicationContext()
        _register(ctx, "PostConstructFails", _PostConstructFailsComponent)
        try:
            ctx.refresh()
        except LifecycleError as e:
            self.assertIsNotNone(e.__cause__)
            self.assertIsInstance(e.__cause__, RuntimeError)
            self.assertIn("post_construct boom", str(e.__cause__))
        else:
            self.fail("Expected LifecycleError")


class TestErrorMessageContent(unittest.TestCase):
    """Error messages should include component name and method name (A3)."""

    def test_startup_error_message_includes_name_and_method(self):
        ctx = ApplicationContext(strict_lifecycle=True)
        _register(ctx, "StartupFails", _StartupFailsComponent)
        try:
            ctx.refresh()
        except LifecycleError as e:
            msg = str(e)
            self.assertIn("StartupFails", msg)
            self.assertIn("on_startup", msg)
        else:
            self.fail("Expected LifecycleError")

    def test_post_construct_error_message_includes_name_and_method(self):
        ctx = ApplicationContext()
        _register(ctx, "PostConstructFails", _PostConstructFailsComponent)
        try:
            ctx.refresh()
        except LifecycleError as e:
            msg = str(e)
            self.assertIn("PostConstructFails", msg)
            self.assertIn("on_post_construct", msg)
        else:
            self.fail("Expected LifecycleError")


if __name__ == "__main__":
    unittest.main()
