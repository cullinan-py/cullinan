# -*- coding: utf-8 -*-
"""A configuration key either takes effect or is reported. There is no third state.

The framework used to have a third state, and a security switch lived in it.
``CullinanConfig`` declares 28 fields; ``from_dict`` assigned 19 of them. The
other nine could be read from ``get_config()``, were commented in the source and
autocompleted in an editor, but no entry point could set them. A project file
carrying ``"openapi_enabled": false`` was read, accepted by the loader, and then
dropped -- so ``/openapi.json`` stayed published while the operator believed it
was off. Nothing failed; a switch that looks obeyed is worse than no switch.

These tests hold the three sets together -- declared, accepted, exported -- and
make an unapplied key say so out loud. The end-to-end half (a real server
answering 404) is measured by hand and recorded on the configuration page,
because a live-server test would make this file the slowest thing in the suite
for a property that can be read off the router.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from cullinan.support.config import CullinanConfig, as_flag, get_config


def _declared_fields() -> set[str]:
    return {name for name in vars(CullinanConfig()) if not name.startswith("_")}


def test_every_declared_field_is_accepted_and_exported():
    """Three sets, one truth.

    ``__init__`` declares a field, ``from_dict`` accepts it, ``to_dict`` reports
    it. A field missing from either of the other two is the shape of the defect
    this file exists for: it is visible, documented and inert. Equality rather
    than ``<=`` in both directions, because an exported key that cannot be
    accepted makes ``push_config_overrides`` restore a snapshot it cannot apply.
    """
    declared = _declared_fields()
    accepted = CullinanConfig.field_names()
    exported = set(CullinanConfig().to_dict())

    assert accepted == declared, (
        "these fields are declared but not accepted from a mapping, so no "
        f"configuration source can set them: {sorted(declared - accepted)}"
    )
    assert exported == declared, (
        "these fields are declared but not exported by to_dict, so a restore "
        f"cannot put them back: {sorted(declared - exported)}"
    )


def test_a_config_mapping_round_trips_without_losing_a_field():
    """Every exported key is also accepted, with the same value.

    ``to_dict`` -> ``from_dict`` -> ``to_dict`` must be the identity. This is how
    ``push_config_overrides`` restores the global object after a ``run()``, so a
    field that survives only one direction leaks its value into the next start-up
    in the same process.
    """
    source = CullinanConfig()
    source.context_features = dict(source.context_features)
    source.context_features["request_id_format"] = "sequential"
    source.openapi_enabled = False
    source.openapi_title = "Billing API"
    snapshot = source.to_dict()

    restored = CullinanConfig().from_dict(json.loads(json.dumps(snapshot)))

    assert restored.to_dict() == snapshot


def test_a_textual_false_is_read_as_false():
    """``bool("false")`` is ``True``, which is the whole defect in one line.

    JSON, TOML and YAML hand back real booleans, but a hand-edited file can hold
    the string. Guessing "any non-empty string is true" turns the switch back
    into the silent one.
    """
    assert as_flag("openapi_enabled", "false") is False
    assert as_flag("openapi_enabled", "FALSE") is False
    assert as_flag("openapi_enabled", "0") is False
    assert as_flag("openapi_enabled", "off") is False
    assert as_flag("openapi_enabled", "true") is True
    assert as_flag("openapi_enabled", True) is True
    assert as_flag("openapi_enabled", 0) is False


def test_a_textual_value_that_is_neither_is_refused_not_guessed():
    with pytest.raises(ValueError) as caught:
        as_flag("openapi_enabled", "sometimes")
    assert "openapi_enabled" in str(caught.value)


def test_the_openapi_switch_reaches_the_field_from_a_file(tmp_path, monkeypatch):
    from cullinan.support import config_file

    path = tmp_path / "application.json"
    path.write_text(
        json.dumps({"server_port": 4321, "openapi_enabled": False}), encoding="utf-8"
    )

    monkeypatch.setattr(get_config(), "openapi_enabled", True)
    config_file.apply_project_config(path=path)

    assert get_config().openapi_enabled is False
    assert get_config().server_port == 4321


def test_an_unknown_key_is_reported_with_the_file_it_came_from(tmp_path, caplog):
    """A typo must not look like a setting.

    The message has to name the key *and* where it came from: a project reads
    several sources, and "unknown key" without a source sends the reader looking
    in the wrong file.
    """
    from cullinan.support import config_file

    path = tmp_path / "application.json"
    path.write_text(json.dumps({"openapi_enabeld": False}), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="cullinan.support.config"):
        config_file.apply_project_config(path=path)

    messages = [record.getMessage() for record in caplog.records]
    assert any("openapi_enabeld" in message for message in messages), messages
    assert any(path.name in message for message in messages), messages
    assert any("openapi_enabled" in message and "Did you mean" in message for message in messages), (
        f"the report must name the key the caller probably meant: {messages}"
    )


def test_an_unknown_key_is_reported_once_per_source(tmp_path, caplog):
    """Applied from three entry points, reported once.

    ``apply_project_config`` runs from ``run()``, from ``Application.run`` and
    from the scanner. A warning repeated three times in one start-up is a warning
    that gets filtered out by the reader, not by the logger.
    """
    from cullinan.support import config_file

    path = tmp_path / "application.json"
    path.write_text(json.dumps({"server_prot": 1234}), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="cullinan.support.config"):
        config_file.apply_project_config(path=path)
        config_file.apply_project_config(path=path)
        config_file.apply_project_config(path=path)

    reports = [r for r in caplog.records if "server_prot" in r.getMessage()]
    assert len(reports) == 1, [r.getMessage() for r in reports]


def _routes(monkeypatch):
    from cullinan.web.gateway.router import Router

    router = Router()
    import cullinan.web.gateway as gateway

    monkeypatch.setattr(gateway, "get_router", lambda: router, raising=False)
    return router


def test_the_document_endpoint_is_not_registered_when_the_switch_is_off(monkeypatch, caplog):
    """The switch decides whether a route exists -- asserted on the router.

    Reading ``cfg.openapi_enabled`` back proves the field was stored, not that
    anything consulted it. The router is the object that answers ``/openapi.json``,
    so that is what this asserts.
    """
    from cullinan.application import legacy

    router = _routes(monkeypatch)
    monkeypatch.setattr(get_config(), "openapi_enabled", False)

    with caplog.at_level(logging.INFO, logger="cullinan.application.legacy"):
        legacy._setup_openapi()

    assert router.get_all_routes() == [], "a disabled document still registered a route"
    assert any(
        "disabled" in record.getMessage() and "configuration" in record.getMessage()
        for record in caplog.records
    ), [record.getMessage() for record in caplog.records]


def test_the_document_endpoint_reports_which_layer_decided(monkeypatch, caplog):
    """"Is the document published?" has to be answerable from the log.

    Three layers can answer it, and they disagree when a project sets one and an
    operator sets another. Naming the layer is what makes the line usable for an
    audit rather than merely informative.
    """
    from cullinan.application import legacy

    router = _routes(monkeypatch)
    monkeypatch.setattr(get_config(), "openapi_enabled", True)
    monkeypatch.setenv("CULLINAN_OPENAPI_ENABLED", "false")

    with caplog.at_level(logging.INFO, logger="cullinan.application.legacy"):
        legacy._setup_openapi()

    assert router.get_all_routes() == []
    message = " | ".join(record.getMessage() for record in caplog.records)
    assert "environment" in message and "CULLINAN_OPENAPI_ENABLED" in message, message
