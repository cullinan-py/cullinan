"""See the drain transition without starting a server.

Run it:

    python -m examples.graceful_shutdown.demo

It prints the readiness predicate before and after draining, and the callback
that a deployment would use to start failing its own probe. Everything here is
the real API -- there is no example-only shortcut.
"""

from cullinan.core.application_context import ApplicationContext


def main() -> int:
    ctx = ApplicationContext(container_id="graceful-shutdown-demo")
    ctx.refresh()

    ctx.add_draining_handler(lambda: print("  draining started -> tell the load balancer to stop sending traffic"))

    print(f"accepting requests: {ctx.accepts_requests}")
    print("shutting down (no requests in flight, so this returns immediately)")
    drained = ctx.shutdown(timeout=5.0)
    print(f"  drained within the bound: {drained}")
    print(f"accepting requests: {ctx.accepts_requests}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
