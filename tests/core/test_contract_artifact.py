# -*- coding: utf-8 -*-
"""Machine-readable stability-contract artifact (packaged data file).

The artifact ``cullinan/_contracts.json`` is a *derived copy* of the four
frozen ``__all__`` lists. These tests are the falsifiable drift gate:

* green -- the committed artifact equals the live ``__all__`` lists, name by
  name, and is importable from the installed package tree;
* red -- both an artifact-side drift and a live-``__all__``-side drift must be
  detected (see the ``*_detects_*`` tests).
"""

import importlib
import importlib.util
import json
from importlib import resources
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_RELATIVE = "_contracts.json"
COMMITMENT_MODULES = (
    "cullinan",
    "cullinan.application",
    "cullinan.web",
    "cullinan.core",
)
EXCLUDED_GATEWAY = "cullinan.web.gateway"
GATEWAY_OUTSIDE_COUNT = 31


def _load_artifact() -> dict:
    path = resources.files("cullinan").joinpath(ARTIFACT_RELATIVE)
    return json.loads(path.read_text(encoding="utf-8"))


def _live_all() -> dict:
    return {
        module_name: list(importlib.import_module(module_name).__all__)
        for module_name in COMMITMENT_MODULES
    }


def _validate_commitment(payload: dict, live: dict) -> None:
    """Raise ``AssertionError`` if the artifact drifts from the live lists."""
    commitment = payload["stability_commitment"]
    assert set(commitment) == set(live), (set(commitment), set(live))
    for module_name, live_names in live.items():
        assert set(commitment[module_name]) == set(live_names), module_name

    frozen_union = set()
    for names in live.values():
        frozen_union.update(names)
    gateway = importlib.import_module(EXCLUDED_GATEWAY)
    outside = sorted(set(gateway.__all__) - frozen_union)
    assert len(outside) == GATEWAY_OUTSIDE_COUNT, len(outside)

    excluded = payload["not_in_commitment"]
    assert EXCLUDED_GATEWAY in excluded
    assert excluded[EXCLUDED_GATEWAY]["outside_commitment"] == len(outside)


def test_contract_artifact_is_packaged_and_importable():
    # AC-2: proves package-data wiring -- a missing entry would silently drop
    # the file from the wheel.
    assert resources.files("cullinan").joinpath(ARTIFACT_RELATIVE).is_file()


def test_contract_artifact_matches_live_all():
    # AC-3 / AC-4: name-by-name equality with the live ``__all__`` lists.
    payload = _load_artifact()
    _validate_commitment(payload, _live_all())


def test_contract_artifact_declares_schema_and_provenance():
    # AC-6: stdlib-json readable + required metadata fields.
    payload = _load_artifact()
    assert isinstance(payload["schema_version"], int)
    generated_from = payload["generated_from"]
    assert "tool" in generated_from
    assert "cullinan_version" in generated_from


def test_contract_artifact_does_not_touch_public_api():
    # AC-7: the artifact is data only -- the top-level contract is unchanged.
    import cullinan

    assert len(cullinan.__all__) == 44
    for module_name, expected in (
        ("cullinan", 44),
        ("cullinan.application", 26),
        ("cullinan.web", 34),
        ("cullinan.core", 72),
    ):
        assert len(importlib.import_module(module_name).__all__) == expected, module_name


def test_contract_validation_detects_artifact_drift():
    # AC-5 (red side A): a mutated artifact must fail validation.
    payload = _load_artifact()
    mutated = json.loads(json.dumps(payload))
    mutated["stability_commitment"]["cullinan.web"] = [
        name for name in mutated["stability_commitment"]["cullinan.web"] if name != "Param"
    ]
    with pytest.raises(AssertionError):
        _validate_commitment(mutated, _live_all())


def test_contract_validation_detects_live_all_drift(monkeypatch):
    # AC-5 (red side B): a real change to a live ``__all__`` must fail
    # validation of the committed artifact.
    import cullinan.web as web_api

    payload = _load_artifact()
    monkeypatch.setattr(web_api, "__all__", list(web_api.__all__) + ["__ghost_symbol__"])
    with pytest.raises(AssertionError):
        _validate_commitment(payload, _live_all())


def test_generator_reproduces_committed_commitment():
    # Guards the generator: re-deriving from the live package must reproduce
    # the committed ``stability_commitment`` and ``not_in_commitment`` exactly.
    spec = importlib.util.spec_from_file_location(
        "generate_contracts", REPO_ROOT / "scripts" / "generate_contracts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    regenerated = module.build_contract()
    payload = _load_artifact()

    assert regenerated["stability_commitment"] == payload["stability_commitment"]
    assert regenerated["not_in_commitment"] == payload["not_in_commitment"]
