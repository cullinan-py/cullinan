# -*- coding: utf-8 -*-
"""Machine-readable stability-contract artifact (packaged data file).

The artifact ``cullinan/_contracts.json`` is a *derived copy* of the four
frozen ``__all__`` lists. These tests are the falsifiable drift gate:

* green -- the committed artifact equals the live ``__all__`` lists, name by
  name **and shape by shape**, and is importable from the installed package tree;
* red -- an artifact-side drift, a live-``__all__``-side drift, and a drift in
  *what a name points at* must each be detected (see the ``*_detects_*`` tests).

Shape is not decoration. ``cullinan.web.controller`` was a decorator and became
a submodule in 0.96a6: the spelling stayed, the membership in ``__all__`` stayed,
every count stayed, and a consumer's ``import`` raised
``TypeError: 'module' object is not callable``. A name is the part of the promise
a count can see; the shape is the part it cannot.
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
SHAPES = ("function", "class", "module", "other")


def _load_artifact() -> dict:
    path = resources.files("cullinan").joinpath(ARTIFACT_RELATIVE)
    return json.loads(path.read_text(encoding="utf-8"))


def _live_all() -> dict:
    return {
        module_name: list(importlib.import_module(module_name).__all__)
        for module_name in COMMITMENT_MODULES
    }


def _shape_of(target) -> str:
    """The same classification the generator uses, written out here.

    Deliberately not imported from ``scripts/generate_contracts.py``: a check that
    borrows the implementation it checks cannot disagree with it, and a wrong
    classifier would then be confirmed rather than caught.
    """
    import inspect

    if inspect.ismodule(target):
        return "module"
    if inspect.isclass(target):
        return "class"
    if inspect.isroutine(target):
        return "function"
    return "other"


def _live_shapes() -> dict:
    return {
        module_name: {
            name: _shape_of(getattr(importlib.import_module(module_name), name))
            for name in importlib.import_module(module_name).__all__
        }
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


def _validate_shapes(payload: dict, live_shapes: dict) -> None:
    """Raise ``AssertionError`` if any name points at something else now."""
    recorded = payload.get("stability_shapes")
    assert recorded is not None, (
        "the artifact records no stability_shapes; a schema-1 artifact cannot "
        "detect a name that kept its spelling and changed what it points at"
    )
    assert set(recorded) == set(live_shapes), (set(recorded), set(live_shapes))
    for module_name, shapes in live_shapes.items():
        assert set(recorded[module_name]) == set(shapes), (
            f"{module_name}: recorded {sorted(set(recorded[module_name]) - set(shapes))} "
            f"are not exported; {sorted(set(shapes) - set(recorded[module_name]))} "
            f"are exported but not recorded"
        )
        for name, shape in shapes.items():
            assert recorded[module_name][name] == shape, (
                f"{module_name}.{name} now points at a {shape}, and the contract "
                f"recorded a {recorded[module_name][name]}"
            )


def _live_pinned() -> dict:
    from cullinan.support.config import configure_options

    return {
        "cullinan.support.config.configure_options": {
            "shape": _shape_of(configure_options),
            "accepted": list(configure_options()),
        }
    }


def _validate_pinned(payload: dict, live=None) -> None:
    """Raise ``AssertionError`` if a pinned symbol, or what it answers, drifted.

    Two failures are reported apart on purpose: a symbol that vanished, and a symbol
    that stayed while the set of names it accepts shrank. The second is the one a
    signature-based check cannot see -- it reads the same signature the implementation
    reads -- which is why the answer is recorded in the artifact and compared here.
    """
    recorded = payload.get("pinned_symbols")
    assert recorded is not None, (
        "the artifact records no pinned_symbols; without it a callable can keep its "
        "name and its shape while the names it accepts quietly shrink, and every check "
        "that derives that set from the same signature stays green"
    )
    live = _live_pinned() if live is None else live

    assert set(recorded) == set(live), (
        f"pinned symbols differ: recorded but not live {sorted(set(recorded) - set(live))}, "
        f"live but not recorded {sorted(set(live) - set(recorded))}"
    )
    for key, expected in live.items():
        entry = recorded[key]
        assert "accepted" in entry, f"{key}: the artifact records no accepted names"
        assert entry["shape"] == expected["shape"], (
            f"{key} now points at a {expected['shape']}, and the contract recorded a "
            f"{entry['shape']}"
        )
        gone = sorted(set(entry["accepted"]) - set(expected["accepted"]))
        new = sorted(set(expected["accepted"]) - set(entry["accepted"]))
        assert not gone and not new, (
            f"{key} accepts a different set of names: gone {gone}, new {new}"
        )


def test_contract_artifact_is_packaged_and_importable():
    # AC-2: proves package-data wiring -- a missing entry would silently drop
    # the file from the wheel.
    assert resources.files("cullinan").joinpath(ARTIFACT_RELATIVE).is_file()


def test_contract_artifact_matches_live_all():
    # AC-3 / AC-4: name-by-name equality with the live ``__all__`` lists.
    payload = _load_artifact()
    _validate_commitment(payload, _live_all())


def test_contract_artifact_matches_live_shapes():
    payload = _load_artifact()
    _validate_shapes(payload, _live_shapes())


def test_the_shape_vocabulary_is_closed():
    """Every recorded shape is one of four words.

    Without this, "record the shape" could be satisfied by writing ``other``
    everywhere, and the check would pass while promising nothing.
    """
    payload = _load_artifact()
    unknown = {
        f"{module}.{name}"
        for module, shapes in payload["stability_shapes"].items()
        for name, shape in shapes.items()
        if shape not in SHAPES
    }
    assert not unknown, f"shapes outside the vocabulary: {sorted(unknown)}"


def test_the_module_decorator_split_is_recorded_as_a_shape():
    """The 0.96a6 break, pinned.

    ``cullinan.web.controller`` and ``cullinan.web.middleware`` are submodules;
    the decorators of the same name live at the top level. If a later release
    makes one of these callable again, or moves the decorator back, this line
    fails before a consumer's ``import`` does.
    """
    payload = _load_artifact()
    web = payload["stability_shapes"]["cullinan.web"]
    assert web["controller"] == "module"
    assert web["middleware"] == "module"
    assert payload["stability_shapes"]["cullinan"]["controller"] == "function"


def test_contract_artifact_declares_schema_and_provenance():
    # AC-6: stdlib-json readable + required metadata fields.
    payload = _load_artifact()
    assert payload["schema_version"] == 3, (
        "schema 3 is the first version that records what a pinned callable answers; a "
        "lower number means a shrinking accepted set is invisible to the gate"
    )
    assert "stability_shapes" in payload
    assert "pinned_symbols" in payload
    generated_from = payload["generated_from"]
    assert "tool" in generated_from
    assert "cullinan_version" in generated_from


def test_contract_artifact_records_the_installed_version():
    # The field was only ever checked for *presence*, so a file left behind by an
    # earlier release passed every gate while naming a version that no longer
    # exists. That is the quiet direction of failure: nothing compares the copy
    # with its source, so the copy can be arbitrarily old.
    import cullinan

    payload = _load_artifact()
    assert payload["generated_from"]["cullinan_version"] == cullinan.__version__, (
        "the contract artifact names a different version than the package; "
        "regenerate it with `python scripts/generate_contracts.py`"
    )


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


def test_contract_validation_detects_a_shape_change_in_the_artifact():
    """The direction a consumer experiences: recorded as a function, is a module.

    This is the 0.96a6 failure replayed. Names and counts stay identical; only
    the referent moved.
    """
    payload = _load_artifact()
    mutated = json.loads(json.dumps(payload))
    mutated["stability_shapes"]["cullinan.web"]["controller"] = "function"
    with pytest.raises(AssertionError) as caught:
        _validate_shapes(mutated, _live_shapes())
    assert "cullinan.web.controller" in str(caught.value)


def test_contract_validation_detects_a_shape_change_in_the_package(monkeypatch):
    """The other direction: the package moves, the contract stays.

    A decorator is replaced by a module of the same name -- exactly what
    ``cullinan.web.controller`` did -- and the contract must refuse.
    """
    import types

    import cullinan.web as web_api

    payload = _load_artifact()
    live = _live_shapes()
    monkeypatch.setattr(web_api, "get_api", types.ModuleType("cullinan.web.get_api"))
    live["cullinan.web"]["get_api"] = "module"

    with pytest.raises(AssertionError) as caught:
        _validate_shapes(payload, live)
    assert "cullinan.web.get_api" in str(caught.value)


def test_contract_artifact_pins_what_configure_options_accepts():
    """The record a shrinking option set has to disagree with.

    ``configure_options()`` and the checks around it read the same signature, so a
    name that disappears from ``configure()`` disappears from the answer too and
    every one of those checks stays green. The committed artifact is the copy that
    does not move by itself.
    """
    payload = _load_artifact()
    _validate_pinned(payload)

    entry = payload["pinned_symbols"]["cullinan.support.config.configure_options"]
    assert entry["shape"] == "function", entry["shape"]
    assert len(entry["accepted"]) == 23, (
        f"the artifact pins {len(entry['accepted'])} accepted options; this release has "
        "23. Adding or removing one is a deliberate act: regenerate the artifact and "
        "update this number in the same change, so the diff records the decision."
    )


def test_a_contract_without_pinned_symbols_is_red():
    """A missing field is not "nothing to check" -- it is the hole this closes."""
    payload = _load_artifact()
    legacy = json.loads(json.dumps(payload))
    legacy.pop("pinned_symbols")

    with pytest.raises(AssertionError) as caught:
        _validate_pinned(legacy)
    assert "pinned_symbols" in str(caught.value)


def test_contract_validation_detects_a_shrunk_accepted_set_in_the_artifact():
    """A name dropped from the record must be reported by name."""
    payload = _load_artifact()
    mutated = json.loads(json.dumps(payload))
    entry = mutated["pinned_symbols"]["cullinan.support.config.configure_options"]
    entry["accepted"] = [name for name in entry["accepted"] if name != "drain_timeout"]

    with pytest.raises(AssertionError) as caught:
        _validate_pinned(mutated)
    assert "drain_timeout" in str(caught.value)


def test_contract_validation_detects_a_shrunk_accepted_set_in_the_package(monkeypatch):
    """The direction that used to be invisible: the package shrinks, the record stays."""
    import cullinan.support.config as config_api

    payload = _load_artifact()
    real = config_api.configure_options
    monkeypatch.setattr(
        config_api,
        "configure_options",
        lambda: tuple(name for name in real() if name != "drain_timeout"),
    )
    live = {
        "cullinan.support.config.configure_options": {
            "shape": "function",
            "accepted": list(config_api.configure_options()),
        }
    }

    with pytest.raises(AssertionError) as caught:
        _validate_pinned(payload, live)
    assert "drain_timeout" in str(caught.value)


def test_a_schema_one_artifact_is_red_rather_than_skipped():
    """An old artifact must fail, not pass quietly.

    If a missing ``stability_shapes`` were treated as "nothing to check", the
    gate would be satisfied by deleting the field -- the cheapest possible way to
    defeat it.
    """
    payload = _load_artifact()
    legacy = json.loads(json.dumps(payload))
    legacy.pop("stability_shapes")
    with pytest.raises(AssertionError):
        _validate_shapes(legacy, _live_shapes())


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
    assert regenerated["stability_shapes"] == payload["stability_shapes"]
    assert regenerated["pinned_symbols"] == payload["pinned_symbols"]
    assert regenerated["not_in_commitment"] == payload["not_in_commitment"]


def test_generator_writes_the_repository_line_ending(tmp_path):
    # A generated file that is committed belongs to the repository, not to the
    # machine that regenerated it. ``write_text`` translates "\n" to the platform
    # separator, so on Windows this artifact used to come out with CRLF while the
    # committed blob was LF -- it differed from the index as soon as it was
    # written, and the difference was invisible on Linux. This asserts the writer
    # agrees with ``.gitattributes``; on a Windows interpreter the previous
    # implementation fails here.
    spec = importlib.util.spec_from_file_location(
        "generate_contracts_newline", REPO_ROOT / "scripts" / "generate_contracts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    target = tmp_path / "_contracts.json"
    module.write_artifact(target, '{\n  "a": 1\n}\n')

    raw = target.read_bytes()
    assert b"\r\n" not in raw, "the artifact was written with the platform line ending"
    assert raw.endswith(b"\n")
