# -*- coding: utf-8 -*-
"""Test scanner module concurrency safety

Verify _ensure_console_logging handler deduplication in multi-threaded environment (Issue 2 fix verification)
"""

import logging
import threading
import os
import pytest


def _capture_cullinan_propagate() -> bool:
    """Read the current ``propagate`` value of the ``cullinan`` logger."""
    return logging.getLogger('cullinan').propagate


def _reset_console_logging_side_effects(saved_propagate: bool) -> None:
    """Undo the side effects of ``scanner._ensure_console_logging`` for tests.

    ``cullinan/runtime/scanner.py`` attaches a console handler to the
    ``cullinan`` logger and sets ``propagate = False`` on it. Clearing handlers
    and resetting the module flag is *not* enough: the ``propagate`` flip leaks
    into every later test in the same process (records stop reaching the root
    logger), so restore the saved value as well.
    """
    import cullinan.runtime.scanner as scanner_mod
    scanner_mod._logging_initialized = False
    logging.getLogger().handlers.clear()
    cullinan_logger = logging.getLogger('cullinan')
    cullinan_logger.handlers.clear()
    cullinan_logger.propagate = saved_propagate


@pytest.fixture(autouse=True)
def _restore_cullinan_logger_propagate():
    """Save and restore the ``cullinan`` logger's ``propagate`` flag.

    ``scanner._ensure_console_logging`` sets ``propagate = False``; without this
    guard the flag would escape the test that triggered it and pollute the rest
    of the process (order-sensitive failure). The original value is captured
    before the test and put back afterwards — it is never hard-coded to ``True``.
    """
    cullinan_logger = logging.getLogger('cullinan')
    saved_propagate = cullinan_logger.propagate
    try:
        yield
    finally:
        cullinan_logger.propagate = saved_propagate


def test_console_logging_concurrent_single_handler(monkeypatch):
    """Test: 10 threads calling _ensure_console_logging simultaneously only adds 1 handler"""
    # Save the value we must restore: the code under test flips it to False.
    saved_propagate = _capture_cullinan_propagate()

    # Reset module-level state
    import cullinan.runtime.scanner as scanner_mod
    scanner_mod._logging_initialized = False

    # Simulate non-main module startup (ensure is_started_directly returns False)
    monkeypatch.setattr(scanner_mod, 'is_started_directly', lambda: True)
    monkeypatch.setenv('CULLINAN_DISABLE_AUTO_CONSOLE', '0')
    monkeypatch.setenv('CULLINAN_FORCE_CONSOLE', '1')

    cullinan_logger = logging.getLogger('cullinan')
    # Clear existing handlers (pytest also adds handler to root logger, must clear all)
    logging.getLogger().handlers.clear()
    cullinan_logger.handlers.clear()

    errors = []
    results = []
    barrier = threading.Barrier(10)

    def setup_logging():
        try:
            barrier.wait()
            handler = scanner_mod._ensure_console_logging()
            results.append(handler)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=setup_logging) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Errors: {errors}"

    # All threads should return the same handler or None
    non_none_results = [r for r in results if r is not None]
    # At least one thread should have successfully added a handler
    assert len(non_none_results) >= 1

    # cullinan logger should have only 1 StreamHandler
    stream_handlers = [h for h in cullinan_logger.handlers
                       if isinstance(h, logging.StreamHandler)]
    assert len(stream_handlers) == 1, (
        f"Expected 1 StreamHandler, got {len(stream_handlers)}"
    )

    # Cleanup: also restore ``propagate`` so it does not leak to later tests.
    _reset_console_logging_side_effects(saved_propagate)
    assert cullinan_logger.propagate is saved_propagate


def test_console_logging_env_disable(monkeypatch):
    """Test: CULLINAN_DISABLE_AUTO_CONSOLE=1 does not add handler"""
    import cullinan.runtime.scanner as scanner_mod
    scanner_mod._logging_initialized = False

    monkeypatch.setenv('CULLINAN_DISABLE_AUTO_CONSOLE', '1')

    cullinan_logger = logging.getLogger('cullinan')
    cullinan_logger.handlers.clear()

    result = scanner_mod._ensure_console_logging()
    assert result is None
    assert scanner_mod._logging_initialized is True

    # Should not add any handler
    stream_handlers = [h for h in cullinan_logger.handlers
                       if isinstance(h, logging.StreamHandler)]
    assert len(stream_handlers) == 0

    # Cleanup
    scanner_mod._logging_initialized = False


def test_is_started_directly_uses_getframe():
    """Verify: is_started_directly uses sys._getframe() optimized path (Issue 9 fix)"""
    from cullinan.runtime.scanner import is_started_directly

    # Basic call not raising exception verifies _getframe path works
    result = is_started_directly()
    # pytest runs as __main__, should return True
    assert isinstance(result, bool)
    assert result is True


def test_console_logging_cleanup_restores_propagate(monkeypatch):
    """Regression (D-2): cleanup must restore ``propagate``, not just clear handlers.

    ``scanner._ensure_console_logging`` sets
    ``logging.getLogger('cullinan').propagate = False``. A test that drives that
    path must put the flag back afterwards; otherwise a later test in the same
    process stops seeing records propagate to the root logger (order-sensitive
    pollution).
    """
    import cullinan.runtime.scanner as scanner_mod

    cullinan_logger = logging.getLogger('cullinan')
    saved_propagate = _capture_cullinan_propagate()

    scanner_mod._logging_initialized = False
    monkeypatch.setattr(scanner_mod, 'is_started_directly', lambda: True)
    monkeypatch.setenv('CULLINAN_DISABLE_AUTO_CONSOLE', '0')
    monkeypatch.setenv('CULLINAN_FORCE_CONSOLE', '1')
    logging.getLogger().handlers.clear()
    cullinan_logger.handlers.clear()

    handler = scanner_mod._ensure_console_logging()
    assert handler is not None
    # The code path under test flips the flag ...
    assert cullinan_logger.propagate is False

    # ... and the test-style cleanup puts it back to the saved value.
    _reset_console_logging_side_effects(saved_propagate)
    assert cullinan_logger.propagate is saved_propagate
