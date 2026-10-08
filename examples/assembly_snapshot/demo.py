"""Assembly-snapshot demo.

Cullinan rebuilds every gateway global at the boot boundary. This demo reads
back, in a single call, what the assembly actually holds afterwards -- surface by
surface -- and shows a registration made *before* the boundary alongside the
assembled set.

The entry point is ``Application.get_assembly_snapshot()``::

    snapshot = app.get_assembly_snapshot()
    snapshot.gateway["router"].assembled
    snapshot.gateway["router"].dropped
    snapshot.container.declared

It returns ``gateway`` (the four sub-surfaces ``pipeline`` / ``router`` /
``dispatcher`` / ``exception_handler``) plus ``container``; each surface is a
``declared`` / ``assembled`` / ``dropped`` triple. Building the app without
running a server keeps the demo engine-neutral.

This is an **advanced / boundary** example. It reaches for the advanced entry
class ``cullinan.application.Application`` on purpose: reading an assembly
snapshot needs an application *object*, and the recommended entry form
(``@application`` + ``@configure(...)`` + ``main()``) deliberately starts a
server. Regular business code stays on that recommended form; reach for
``Application`` only when you need the object itself (see ``examples/README.md``).
"""

from cullinan.application import Application
from cullinan.web.gateway import get_router

from .app.root import main as entry

GATEWAY_SURFACES = ("pipeline", "router", "dispatcher", "exception_handler")
PRE_BOOT_METHOD = "GET"
PRE_BOOT_PATH = "/pre-boot-check"


def _register_pre_boot_route() -> None:
    """Register a route before the application starts.

    The boot boundary rebuilds the router, so this entry never reaches request
    handling. Because the router is one of the surfaces the boundary only
    *records* (it does not refuse the start, unlike the pipeline), the
    application still starts -- and the snapshot names the entry as dropped.
    """
    get_router().add_route(
        PRE_BOOT_METHOD,
        PRE_BOOT_PATH,
        handler=lambda request: None,
    )


def inspect_snapshot():
    """Build the app without a server, then return its assembly snapshot."""
    _register_pre_boot_route()
    # Advanced / boundary entry: `Application` takes the `@application` entry
    # method as its root (the decorator attaches module metadata to the method).
    app = Application(entry)
    app.build()
    try:
        return app.get_assembly_snapshot()
    finally:
        app.uninstall()


def _render_surface(label: str, holdings) -> None:
    print(label)
    print(f"    declared : {list(holdings.declared)}")
    print(f"    assembled: {list(holdings.assembled)}")
    print(f"    dropped  : {list(holdings.dropped)}")


def run_example_assertions() -> None:
    """Assertions used by the example's integration test."""
    snapshot = inspect_snapshot()

    # One call covers every surface the boot boundary rebuilds, plus the
    # container.
    assert set(snapshot.gateway.keys()) == set(GATEWAY_SURFACES)

    # The pre-boot route is dropped, reported side by side with the assembled
    # set -- and still queryable.
    pre_boot = f"{PRE_BOOT_METHOD} {PRE_BOOT_PATH}"
    router = snapshot.gateway["router"]
    assert pre_boot in router.dropped, router.dropped
    assert pre_boot not in router.assembled, router.assembled

    # Every surface reconciles in one place: dropped is declared minus assembled.
    for surface in GATEWAY_SURFACES:
        holdings = snapshot.gateway[surface]
        assert set(holdings.dropped) <= set(holdings.declared)
        assert set(holdings.assembled).isdisjoint(holdings.dropped)

    # The pipeline sub-surface is present with an empty dropped field on a
    # successful start: a missing field would be a failure, not a silent
    # omission.
    assert snapshot.gateway["pipeline"].dropped == ()

    # The container surface reports what the container assembled.
    assert snapshot.container.assembled, snapshot.container


def main() -> None:
    snapshot = inspect_snapshot()

    print("Assembly snapshot demo")
    print("=" * 40)
    print()
    print("One call: Application.get_assembly_snapshot()")
    print("  -> gateway{4 sub-surfaces} + container")
    print("  each surface: declared / assembled / dropped")
    print()

    for surface in GATEWAY_SURFACES:
        _render_surface(f"gateway.{surface}", snapshot.gateway[surface])
        print()

    _render_surface("container", snapshot.container)
    print()

    print("Notes")
    print("-----")
    print("* gateway.router.dropped names the route registered before the app")
    print("  started: the boot boundary rebuilds the router, so it is dropped.")
    print("  It stays queryable here instead of vanishing silently.")
    print("* gateway.pipeline.dropped is present and empty: on a successful start")
    print("  the boundary refuses a pre-boot pipeline registration rather than")
    print("  dropping it, so nothing is dropped (a missing field would be a")
    print("  failure, not a silent omission).")
    print("* The four gateway sub-surfaces are rebuilt at the boundary; the")
    print("  container surface reports the component reconciliation.")


if __name__ == "__main__":
    main()
