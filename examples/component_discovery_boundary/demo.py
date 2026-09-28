"""Declared-vs-assembled reconciliation demo.

Builds the example application without starting a server, then prints the
``declared`` / ``assembled`` / ``dropped`` sets and the warning Cullinan emits
for the deliberately out-of-scope component.
"""

import logging
import warnings

from cullinan.application import Application

from .app.root import main as entry

_RULE_KEY = "component-declared-not-assembled"


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
            app = Application(entry)
            app.build()
            diff = app.get_declaration_diff()
            app.uninstall()
    finally:
        root_logger.setLevel(previous_level)
        for logger in target_loggers:
            logger.removeHandler(capture)
    return diff, [str(item.message) for item in caught], list(capture.messages)


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


if __name__ == "__main__":
    main()
