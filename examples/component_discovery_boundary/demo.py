"""Declared-vs-assembled reconciliation demo.

Builds the example application without starting a server, then prints the
``declared`` / ``assembled`` / ``dropped`` sets and the diagnosis Cullinan emits
for the deliberately out-of-scope component.

A second section shows the opt-in upgrade: ``configure(strict_assembly=True)``
makes that same difference stop startup, and the intentional-exclusion list
acknowledges a component instead of failing on it.

This is an **advanced / boundary** example. It uses the advanced entry class
``cullinan.application.Application`` directly because it needs the application
*object* to read the declaration difference without starting a server; the
recommended entry form (``@application`` + ``@configure(...)`` + ``main()``)
starts a server. Regular business code stays on the recommended form.
"""

import importlib
import logging
import sys
import warnings

from cullinan import configure
from cullinan.application import Application
from cullinan.core import PendingRegistry
from cullinan.core.semantic_rules import reset_semantic_warnings
from cullinan.support.exceptions import ConfigurationError

from .app.root import main as entry

_RULE_KEY = "component-declared-not-assembled"
_OUTSIDE_MODULE = "examples.component_discovery_boundary.outside.services"
_OUTSIDE_COMPONENT = f"{_OUTSIDE_MODULE}.DroppedService"


class _WarningLogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        # The handler may be attached to more than one logger; keep each
        # message once.
        if message not in self.messages:
            self.messages.append(message)


def inspect_boundary():
    """Build the app, then return ``(diff, warning_messages, log_messages)``."""
    capture = _WarningLogCapture()
    root_logger = logging.getLogger()
    # Pollution defence (not a visibility requirement): when this demo runs
    # inside a larger test session, an earlier test may have left
    # ``propagate = False`` on the ``cullinan`` logger — the framework sets that
    # when it auto-enables console logging — and may have cleared the root
    # handlers. Attaching the capture handler to both loggers keeps the
    # illustrative log line stable regardless of that leftover state. Visibility
    # of the diagnostic itself does not depend on this handler: it is guaranteed
    # by the standard ``warnings`` channel captured below.
    target_loggers = [root_logger, logging.getLogger("cullinan")]
    for logger in target_loggers:
        logger.addHandler(capture)
    previous_level = root_logger.level
    root_logger.setLevel(logging.WARNING)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            # Advanced / boundary entry: `Application` takes the `@application`
            # entry method as its root.
            app = Application(entry)
            app.build()
            diff = app.get_declaration_diff()
            app.uninstall()
    finally:
        root_logger.setLevel(previous_level)
        for logger in target_loggers:
            logger.removeHandler(capture)
    return diff, [str(item.message) for item in caught], list(capture.messages)


def _redeclare_out_of_scope_component() -> None:
    """Re-run the out-of-scope module's declaration for the strict section.

    This is demo plumbing, not application code. Building an application consumes
    the import-time declaration snapshot, so a second build in the same process
    would reconcile against an empty set and have nothing to enforce; the
    reconciliation is per startup, and a real application starts once. Cleared
    and re-imported, the module's own ``@service`` decorator runs again — nothing
    is registered by hand.

    The once-only diagnostic de-duplication is cleared for the same reason: it
    exists so one long-running process does not repeat itself, and this demo
    deliberately starts more than once.
    """
    PendingRegistry.reset()
    reset_semantic_warnings()
    stale = [
        name
        for name in list(sys.modules)
        if name == _OUTSIDE_MODULE or name.startswith(f"{_OUTSIDE_MODULE}.")
    ]
    for name in stale:
        sys.modules.pop(name, None)
    importlib.import_module(_OUTSIDE_MODULE)


def inspect_strict(excludes=None):
    """Run one startup with ``strict_assembly`` on.

    Returns ``(failure_message, diff, warning_messages)``. ``failure_message`` is
    the ``ConfigurationError`` text when startup was rejected and ``None`` when it
    completed; ``diff`` is the reconciliation of the completed build and ``None``
    when nothing was built. Exclusions remove the rejection without removing the
    fact, so an excluded component still shows up in ``diff.dropped``.
    """
    _redeclare_out_of_scope_component()
    try:
        configure(
            strict_assembly=True,
            strict_assembly_excludes=[] if excludes is None else list(excludes),
        )
        failure = None
        diff = None
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            # Advanced / boundary entry: `Application` takes the `@application`
            # entry method as its root.
            app = Application(entry)
            try:
                app.build()
            except ConfigurationError as error:
                failure = str(error)
            else:
                try:
                    diff = app.get_declaration_diff()
                finally:
                    app.uninstall()
        return failure, diff, [str(item.message) for item in caught]
    finally:
        # The switch is process-wide; put the demo default back so running this
        # demo does not change how anything else starts.
        configure(strict_assembly=False, strict_assembly_excludes=[])


def run_example_assertions() -> None:
    """Assertions used by the example's integration test."""
    diff, caught, _logs = inspect_boundary()

    assert diff.dropped_count == len(diff.dropped)
    assert any(
        name.endswith("outside.services.DroppedService") for name in diff.dropped
    ), diff.dropped
    assert any(
        name.endswith("app.services.AssembledService") for name in diff.assembled
    ), diff.assembled

    # The diagnostic is guaranteed to be visible through the standard
    # ``warnings`` channel: ``ComponentDiscoveryWarning`` subclasses
    # ``UserWarning``, whose default filter action is ``default`` (printed once,
    # no switch required). Assert on that channel — not on a log record, which
    # the framework's own logger does not surface by default.
    rule_messages = [message for message in caught if _RULE_KEY in message]
    assert rule_messages, caught
    assert any(
        f"{diff.dropped_count} component(s)" in message for message in rule_messages
    ), rule_messages
    assert any(
        dropped in message
        for dropped in diff.dropped
        for message in rule_messages
    ), (diff.dropped, rule_messages)

    # Default (off): reported, non-blocking -- asserted above.

    # On: the very same declarations now stop startup ...
    failure, strict_diff, strict_warnings = inspect_strict()
    assert failure is not None, "strict_assembly=True must reject unassembled declarations"
    assert _RULE_KEY in failure, failure
    assert "1 component(s)" in failure, failure
    assert _OUTSIDE_COMPONENT in failure, failure
    assert "user_packages" in failure, failure
    assert strict_diff is None
    # ... and the report still went out first, so the trace survives an upper
    # layer that swallows the exception.
    assert any(_RULE_KEY in message for message in strict_warnings), strict_warnings

    # Acknowledged: the exclusion changes the action, not the fact.
    failure, acknowledged_diff, _warnings = inspect_strict(excludes=[_OUTSIDE_COMPONENT])
    assert failure is None, failure
    assert acknowledged_diff is not None
    assert _OUTSIDE_COMPONENT in acknowledged_diff.dropped, acknowledged_diff.dropped
    assert _OUTSIDE_COMPONENT not in acknowledged_diff.assembled, acknowledged_diff.assembled


def main() -> None:
    diff, caught, logs = inspect_boundary()

    print("Component declaration boundary demo")
    print("=" * 36)
    print("user_packages = ['examples.component_discovery_boundary.app']")
    print()

    print(f"declared  (import-time)          : {len(diff.declared)}")
    for name in diff.declared:
        print(f"    {name}")
    print()

    print(f"assembled (runtime)              : {len(diff.assembled)}")
    for name in diff.assembled:
        print(f"    {name}")
    print()

    print(f"dropped   (declared - assembled) : {diff.dropped_count}")
    for name in diff.dropped:
        print(f"    {name}")
    print()

    if diff.dropped:
        print("warning:", caught[-1] if caught else "(none)")
        print("log    :", logs[-1] if logs else "(none)")
        print()
        print("Fix: add 'examples.component_discovery_boundary.outside' to")
        print("     @configure(user_packages=[...]), or move the component into")
        print("     a package that is already listed.")
    else:
        print("No dropped declarations: every declared component was assembled.")

    print()
    print("Strict mode (opt-in)")
    print("=" * 36)
    print("configure(strict_assembly=True)")
    print("  The same difference, required to be empty. The report still goes out;")
    print("  startup then fails.")
    print()

    failure, _strict_diff, strict_warnings = inspect_strict()
    print(f"  failure : {failure}")
    print(f"  warning : {strict_warnings[-1] if strict_warnings else '(none)'}")
    print()

    print(
        "configure(strict_assembly=True, "
        f"strict_assembly_excludes=['{_OUTSIDE_COMPONENT}'])"
    )
    failure, acknowledged_diff, _warnings = inspect_strict(excludes=[_OUTSIDE_COMPONENT])
    print(f"  failure : {failure if failure else '(none - startup completed)'}")
    print(f"  dropped : {acknowledged_diff.dropped if acknowledged_diff else '(not built)'}")
    print("  The exclusion changes the action, not the fact: the component is still")
    print("  reported as declared-but-not-assembled.")
    print()
    print("Use strict_assembly when a declaration that never reaches the container")
    print("must not pass unnoticed. It is off by default; leave it off to keep the")
    print("report non-blocking.")


if __name__ == "__main__":
    main()
