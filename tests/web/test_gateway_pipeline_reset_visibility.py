# -*- coding: utf-8 -*-
"""Visibility and refusal of the boot-boundary gateway reset.

``Runtime.warmup()`` resets the gateway globals, and that reset is deliberate:
rebuilding the gateway is what makes a start deterministic. What it also does is
discard anything registered imperatively through ``get_pipeline().add(...)``
before startup. A registration that would be discarded is no longer accepted:
the boot boundary refuses to start, so the declarations the application made and
the pipeline it would run cannot silently disagree.

Four properties are pinned here:

* a pre-boot registration is reported once, naming the entries and their count;
* the start is then refused, with a dedicated ``error_code``;
* a start with nothing pre-registered says nothing and succeeds on both engines;
* the report survives a process whose warnings and logging are both dark, by
  falling back to stderr -- and the fallback fires before the refusal.

The last one only shows up in a process whose warning and logging state we
control, so it runs in a child process: inside pytest both channels are already
configured by the harness.
"""
from __future__ import annotations

import importlib
import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from cullinan import get_config
from cullinan.application import Application
from cullinan.core import PendingRegistry, set_application_context
from cullinan.core.semantic_rules import reset_semantic_warnings
from cullinan.support.exceptions import ConfigurationError
from cullinan.web.controller import reset_controller_registry
from cullinan.web.gateway import (
    GatewayMiddleware,
    WebRuntime,
    get_pipeline,
    reset_gateway,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The reporting logger lives with the assembly model that owns the boot boundary.
REPORT_LOGGER = "cullinan.application.model"
#: The public rule key the report is filed under.
RULE_MARKER = "gateway-pipeline-reset"
#: The dedicated code the refusal carries (never the generic ``CONFIG_ERROR``).
ERROR_CODE_MARKER = "PREBOOT_REGISTRATION_ERROR"
#: What the last-resort channel writes (``stderr``, after the ordinary ones fail).
FALLBACK_MARKER = "cullinan: [gateway-pipeline-reset]"
#: Printed by the child once assembly is over, so the parent knows it ran to the end.
CHILD_DONE = "CHILD_ASSEMBLED"


class PipelineMarkerMiddleware(GatewayMiddleware):
    """A middleware with no behaviour -- only its name matters in the report."""

    async def __call__(self, request, call_next):
        return await call_next(request)


@pytest.fixture(autouse=True)
def _reset_framework_globals():
    """Isolate each case: registries, gateway globals and configuration."""
    config = get_config()
    original = config.to_dict()
    reset_semantic_warnings()
    set_application_context(None)
    PendingRegistry.reset()
    WebRuntime.clear_active()
    reset_gateway()
    reset_controller_registry()
    yield
    reset_semantic_warnings()
    set_application_context(None)
    PendingRegistry.reset()
    WebRuntime.clear_active()
    reset_gateway()
    reset_controller_registry()
    config.from_dict(original)


def _clear_modules(prefix: str) -> None:
    for module_name in list(sys.modules):
        if module_name == prefix or module_name.startswith(f"{prefix}."):
            sys.modules.pop(module_name, None)


def _write_app_package(tmp_path: Path, package_name: str) -> None:
    root = tmp_path / package_name
    root.mkdir(parents=True, exist_ok=True)
    (root / "__init__.py").write_text("", encoding="utf-8")
    (root / "root.py").write_text(
        textwrap.dedent(
            f"""
            from cullinan import application, configure

            @configure(user_packages=["{package_name}"])
            @application
            def main(): ...
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _boot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, package_name: str):
    """Assemble a real application from a throwaway package (no port binding).

    Returns the entry method, so the caller decides what to do with it -- both
    the pre-boot step and the assembly order matter to these cases.
    """
    _write_app_package(tmp_path, package_name)
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package_name)
    return importlib.import_module(f"{package_name}.root").main


def _reports(records) -> list:
    return [record for record in records if RULE_MARKER in record.getMessage()]


# --- the report is emitted, and names what it discarded -----------------------


def test_pre_boot_registration_is_reported_then_refused(
    tmp_path, monkeypatch, caplog
):
    entry_method = _boot(tmp_path, monkeypatch, "visibility_boot_positive")
    get_pipeline().add(PipelineMarkerMiddleware())

    with caplog.at_level(logging.WARNING, logger=REPORT_LOGGER):
        with pytest.raises(ConfigurationError) as excinfo:
            entry_method.get_asgi_app()

    try:
        # Report first: the diagnostic is emitted before the refusal, so a
        # caller that catches the exception has still seen it.
        reports = [
            record
            for record in caplog.records
            if record.name == REPORT_LOGGER and record.levelno == logging.WARNING
        ]
        assert reports, caplog.text
        message = reports[-1].getMessage()
        assert "PipelineMarkerMiddleware" in message
        # The count is reported together with the name, not only the name.
        assert "1 (PipelineMarkerMiddleware)" in message

        # Then the refusal, carrying its own dedicated code.
        assert excinfo.value.error_code == ERROR_CODE_MARKER
        assert "startup boundary" in str(excinfo.value)
    finally:
        current = Application.current()
        if current is not None:
            current.uninstall()


# --- and says nothing -- and starts normally -- with nothing to report --------


def test_start_without_pre_boot_registration_is_not_reported(
    tmp_path, monkeypatch, caplog
):
    entry_method = _boot(tmp_path, monkeypatch, "visibility_boot_negative")

    with caplog.at_level(logging.WARNING, logger=REPORT_LOGGER):
        entry_method.get_asgi_app()

    try:
        assert not _reports(caplog.records), caplog.text
    finally:
        current = Application.current()
        if current is not None:
            current.uninstall()


# --- the last-resort channel, in a process that has neither channel on --------


_CHILD_SOURCE = textwrap.dedent(
    """
    import cullinan
    from cullinan import application, configure
    from cullinan.support.exceptions import ConfigurationError
    from cullinan.web.gateway import GatewayMiddleware, get_pipeline

    print("CHILD_CULLINAN_FILE", cullinan.__file__)


    class PipelineMarkerMiddleware(GatewayMiddleware):
        async def __call__(self, request, call_next):
            return await call_next(request)


    get_pipeline().add(PipelineMarkerMiddleware())

    configure(user_packages=[])


    @application
    def main(): ...


    try:
        main.get_asgi_app()
    except ConfigurationError as exc:
        print("CHILD_REFUSED", exc.error_code)
    print("CHILD_ASSEMBLED")
    """
)


def test_report_reaches_stderr_when_warnings_are_ignored_and_logging_is_unconfigured():
    """No logging handler and ``PYTHONWARNINGS=ignore``: stderr still speaks.

    Both ordinary channels are dark here, which cannot be arranged inside pytest
    -- the harness configures warnings and logging for the whole process. So the
    check runs a real child, started the way a production process could be. The
    fallback fires before the refusal, so the diagnostic outlives a caller that
    catches the exception.
    """
    env = dict(os.environ)
    env["PYTHONWARNINGS"] = "ignore"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT), *filter(None, [env.get("PYTHONPATH")])]
    )

    completed = subprocess.run(
        [sys.executable, "-c", _CHILD_SOURCE],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert CHILD_DONE in completed.stdout, completed.stdout
    assert f"CHILD_REFUSED {ERROR_CODE_MARKER}" in completed.stdout, completed.stdout
    # The child really read the package from this tree: the replay is a source
    # replay, and saying so is part of the result.
    assert str(REPO_ROOT) in completed.stdout, completed.stdout
    assert FALLBACK_MARKER in completed.stderr, completed.stderr
    assert "PipelineMarkerMiddleware" in completed.stderr, completed.stderr


# --- the report belongs to the boot boundary, not to the reset itself ---------


def test_direct_gateway_reset_is_not_reported(caplog):
    """``reset_gateway()`` is public and called directly by tests -- stay quiet."""
    get_pipeline().add(PipelineMarkerMiddleware())

    with caplog.at_level(logging.WARNING, logger=REPORT_LOGGER):
        reset_gateway()

    assert not _reports(caplog.records), caplog.text


# --- the refusal is engine-neutral: it lands before any adapter is chosen -----


class _CapturingAdapter:
    """A stand-in adapter that records its own construction."""

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs

    def run(self, **kwargs):
        self.run_kwargs = kwargs


def _stub_tornado_adapter(monkeypatch):
    from cullinan.application import public as public_api

    built: list = []

    class _Adapter(_CapturingAdapter):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            built.append(self)

    monkeypatch.setattr(public_api, "_load_tornado_adapter", lambda: _Adapter)
    return built


def test_pre_boot_registration_refuses_start_before_the_tornado_adapter(
    tmp_path, monkeypatch
):
    """The refusal comes from the boot boundary, ahead of any engine adapter.

    Because assembly runs before the engine is picked, a pre-boot registration
    fails the same way whatever engine was requested -- here, the tornado path
    with a stand-in adapter that must never be built.
    """
    from cullinan.application import public as public_api

    entry_method = _boot(tmp_path, monkeypatch, "visibility_boot_tornado")
    get_pipeline().add(PipelineMarkerMiddleware())
    built = _stub_tornado_adapter(monkeypatch)

    with pytest.raises(ConfigurationError) as excinfo:
        public_api.run(entry_method, engine="tornado")

    assert excinfo.value.error_code == ERROR_CODE_MARKER
    # Refused before the adapter was chosen, so both engines hit one boundary.
    assert built == []


def test_start_without_pre_boot_registration_succeeds_on_the_asgi_path(
    tmp_path, monkeypatch
):
    """With nothing pre-registered the boundary passes on the ASGI entry point."""
    asgi_entry = _boot(tmp_path, monkeypatch, "visibility_clear_asgi")

    asgi_app = asgi_entry.get_asgi_app()

    assert asgi_app is not None
    current = Application.current()
    if current is not None:
        current.uninstall()


def test_start_without_pre_boot_registration_reaches_the_tornado_adapter(
    tmp_path, monkeypatch
):
    """With nothing pre-registered the tornado path reaches its adapter."""
    from cullinan.application import public as public_api

    tornado_entry = _boot(tmp_path, monkeypatch, "visibility_clear_tornado")
    built = _stub_tornado_adapter(monkeypatch)

    public_api.run(tornado_entry, engine="tornado")

    # The boundary passed, so the tornado adapter was actually built.
    assert built, "the tornado adapter was never built"
    current = Application.current()
    if current is not None:
        current.uninstall()


# --- reading the registrations must not create the pipeline it reads ----------


def test_collecting_entry_names_does_not_materialize_the_pipeline():
    """The global pipeline is lazy; a reading must not bring one into being."""
    from cullinan.application.model import _registered_pipeline_entry_names
    from cullinan.web.gateway import globals as gateway_globals

    assert gateway_globals._global_pipeline is None
    assert _registered_pipeline_entry_names() == ()
    assert gateway_globals._global_pipeline is None, "reading created the pipeline"

    get_pipeline().add(PipelineMarkerMiddleware())
    assert _registered_pipeline_entry_names() == ("PipelineMarkerMiddleware",)
