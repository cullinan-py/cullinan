"""Visibility of the declared-vs-assembled report must not depend on the process
warning policy.

The reconciliation is announced through a semantic warning and a log record.
Either channel can be dark: a process started with ``-W ignore`` /
``PYTHONWARNINGS=ignore`` silences the first (a common way to quiet noisy
dependencies in production), and a package logger carrying only a ``NullHandler``
silences the second until the application configures logging.

These tests pin two properties:
  1. at least one channel always speaks;
  2. the last-resort channel stays out of the way when an ordinary one is live.

They run real child processes, because the difference only shows up in a process
whose own logging and warning state we control -- inside pytest both are already
configured. The child starts a server and is killed once the report has been
emitted; the report happens during assembly, well before that.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import textwrap
import threading
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MARKER = "cullinan: [component-declared-not-assembled]"  # last-resort channel
# Upper bound on how long a child is drained when nothing settles it earlier.
# The report is written about a second after start, so this is a wide margin;
# it replaces a flat 12s that every child used to burn in full.
SETTLE_TIMEOUT_S = 5.0
# Slack allowed for the child to actually die after it is asked to stop.
STOP_TIMEOUT_S = 5.0
# The example app serves through uvicorn, and its "server is up" line is written
# only after assembly finished -- so once it appears the framework cannot have
# anything left to report, and reading can stop. This is purely a latency
# optimisation: should the line never show up (port taken, different launcher,
# renamed message) the wait simply degrades to SETTLE_TIMEOUT_S and the
# assertions are unaffected.
SERVER_UP_HINT = "Uvicorn running on "

# NOTE: built with .replace() rather than %-formatting, because the logging
# format string itself contains %(levelname)s and would be eaten as a placeholder.
_RUNNER = textwrap.dedent(
    """
    import logging, sys
    if CONFIGURE_LOGGING:
        logging.basicConfig(level=logging.WARNING, stream=sys.stdout,
                            format="LOGCAP|%(levelname)s|%(name)s|%(message)s")
    import examples.component_discovery_boundary.app.root as root
    try:
        root.main.run()
    except SystemExit:
        pass
    except Exception:
        pass
    """
)


def _run(configure_logging: bool, warnings_ignored: bool) -> str:
    """Everything the child printed, up to the point its report had gone out.

    The child starts a server, so it never exits on its own. Draining both pipes
    while it runs and stopping it as soon as the interesting output has landed
    keeps each case down to about a second instead of a fixed timeout. Nothing
    written is lost by doing so: the pipe keeps buffering, and the readers are
    joined after the child is gone, which drains every remaining byte to EOF
    before the result is assembled.
    """
    env = dict(os.environ)
    env.pop("PYTHONWARNINGS", None)
    if warnings_ignored:
        env["PYTHONWARNINGS"] = "ignore"
    code = _RUNNER.replace("CONFIGURE_LOGGING", str(configure_logging))
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )

    chunks: list[str] = []
    lock = threading.Lock()
    settled = threading.Event()

    def drain(stream) -> None:
        for line in stream:
            with lock:
                chunks.append(line)
            if MARKER in line or SERVER_UP_HINT in line:
                settled.set()

    readers = [
        threading.Thread(target=drain, args=(stream,), daemon=True)
        for stream in (proc.stdout, proc.stderr)
    ]
    for reader in readers:
        reader.start()

    deadline = time.monotonic() + SETTLE_TIMEOUT_S
    while not settled.is_set() and proc.poll() is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        settled.wait(min(remaining, 0.05))

    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=STOP_TIMEOUT_S)
    for reader in readers:
        reader.join(timeout=STOP_TIMEOUT_S)
    proc.stdout.close()
    proc.stderr.close()
    with lock:
        return "".join(chunks)


# --- property 1: at least one channel always speaks ----------------------------


def test_report_survives_ignored_warnings_without_logging():
    """PYTHONWARNINGS=ignore + no logging config: the last-resort channel speaks."""
    output = _run(configure_logging=False, warnings_ignored=True)
    assert MARKER in output, output[-2000:]


def test_report_present_when_logging_configured():
    """With logging configured the record reaches it, and no fallback is needed."""
    output = _run(configure_logging=True, warnings_ignored=True)
    assert "Components declared but not assembled" in output, output[-2000:]


# --- property 2: no duplicate when an ordinary channel is live -----------------


def test_no_duplicate_with_default_settings():
    """Warnings are live here, so the last-resort line must not also fire."""
    output = _run(configure_logging=False, warnings_ignored=False)
    assert "component-declared-not-assembled" in output, output[-2000:]
    assert MARKER not in output, output[-2000:]


# --- the two helpers, directly (cheap) ----------------------------------------


def test_real_logging_handler_exists_ignores_a_lone_null_handler():
    """A NullHandler is not a working sink, so it must not count as one."""
    from cullinan.core.application_context import _real_logging_handler_exists

    root = logging.getLogger()
    saved = list(root.handlers)
    for handler in saved:
        root.removeHandler(handler)
    try:
        assert _real_logging_handler_exists() is False
        root.addHandler(logging.StreamHandler())
        assert _real_logging_handler_exists() is True
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in saved:
            root.addHandler(handler)


def test_warnings_may_be_suppressed_reflects_the_filter_state():
    import warnings

    from cullinan.core.application_context import _warnings_may_be_suppressed

    assert _warnings_may_be_suppressed() is False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert _warnings_may_be_suppressed() is True
