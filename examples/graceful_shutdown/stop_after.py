"""Stop the server from your own code, without a signal.

Windows has no way to deliver a graceful stop to another process: ``terminate()``
is ``TerminateProcess``, the process simply disappears, and ``SIGBREAK`` only
exists for a console it owns. So a supervisor that could not send a signal had no
way to ask for the drain at all -- even though the framework has had the sequence
for two releases. This example is that way in.

Run it:

    python -m examples.graceful_shutdown.stop_after

It starts the same application as ``python -m examples.graceful_shutdown``, waits
until it is actually serving, then asks it to stop from a thread that is not the
one serving requests. ``request_shutdown()`` returns ``True`` when there was a
running server to ask and ``False`` when there was not, so the caller never has
to guess and never has to catch.
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request

from cullinan.application import Application

from .root import PORT, main

#: How long the server is left serving before the stop is asked for.
DELAY_SECONDS = 3.0


def _server_is_up(timeout: float) -> bool:
    """Wait until the application answers, so the request has somewhere to land.

    Asking before the server is listening would return ``False`` -- correctly, but
    it would look like the feature did not work.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/ops/live", timeout=1.0) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.05)
    return False


def ask_after(delay: float = DELAY_SECONDS, timeout: float = 30.0) -> bool:
    """Wait ``delay`` for the server, then ask the application to stop."""
    if not _server_is_up(timeout):
        print("the server never started, so there was nothing to stop")
        return False
    time.sleep(delay)
    application = Application.current()
    if application is None:
        print("no application is installed, so there was nothing to stop")
        return False
    # Not the loop thread: the call is safe from here, which is the whole point.
    asked = application.request_shutdown()
    print(f"request_shutdown() -> {asked}")
    return asked


def run() -> int:
    thread = threading.Thread(target=ask_after, daemon=True)
    thread.start()
    main()
    thread.join(timeout=30.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
