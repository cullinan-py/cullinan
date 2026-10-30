#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regenerate ``cullinan/_contracts.json`` from the live package ``__all__``.

The committed artifact is a *derived copy*: it drifts whenever one of the four
frozen ``__all__`` lists changes. Regenerate and commit it whenever the
stability commitment surface changes::

    python scripts/generate_contracts.py

The companion falsifiable check lives in
``tests/core/test_contract_artifact.py`` and asserts ``artifact == live`` for the
four contract modules -- **by name and by shape** -- and that
``cullinan.web.gateway`` is explicitly recorded as outside the commitment.

Schema 2 added ``stability_shapes``. Schema 1 recorded names only, and a name is
not a promise about what it is: ``cullinan.web.controller`` was a decorator and
became a submodule while keeping its spelling and its place in ``__all__``. Every
gate stayed green and the break arrived at a consumer's ``import``. The shape is
the part of the promise a name cannot express, so it is recorded next to it.
"""

from __future__ import annotations

import datetime
import importlib
import inspect
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCHEMA_VERSION = 2

#: The closed vocabulary a shape may take. Closed on purpose: if every symbol
#: could report ``other``, the check would be satisfied by degrading itself.
SHAPES = ("function", "class", "module", "other")

# Module order is part of the artifact; keep it stable across regenerations.
COMMITMENT_MODULES = (
    "cullinan",
    "cullinan.application",
    "cullinan.web",
    "cullinan.core",
)

# Facades deliberately kept outside the 1.0 stability commitment.
EXCLUDED_MODULES = ("cullinan.web.gateway",)

EXCLUDED_REASON = (
    "Layered, explicitly-imported integration facade; deliberately outside the "
    "1.0 stability commitment."
)

ARTIFACT_PATH = REPO_ROOT / "cullinan" / "_contracts.json"


def shape_of(target: object) -> str:
    """Classify an exported symbol by what a caller can do with it.

    Four kinds, because those are the four that change how code at a call site
    behaves: a function is called, a class is instantiated (and called), a module
    is imported from, and everything else is passed around. A decorator that
    starts resolving to a module is a "function" that becomes a "module", which
    is the transition this vocabulary exists to make visible.
    """
    if inspect.ismodule(target):
        return "module"
    if inspect.isclass(target):
        return "class"
    if inspect.isroutine(target):
        return "function"
    return "other"


def build_contract() -> dict:
    """Build the contract payload from the *live* ``__all__`` lists."""
    modules = {
        module_name: importlib.import_module(module_name)
        for module_name in COMMITMENT_MODULES
    }
    commitment = {
        module_name: list(module.__all__) for module_name, module in modules.items()
    }
    shapes = {
        module_name: {
            name: shape_of(getattr(module, name)) for name in module.__all__
        }
        for module_name, module in modules.items()
    }

    frozen_union: set[str] = set()
    for names in commitment.values():
        frozen_union.update(names)

    not_in_commitment = {}
    for module_name in EXCLUDED_MODULES:
        declared = list(importlib.import_module(module_name).__all__)
        outside = sorted(set(declared) - frozen_union)
        not_in_commitment[module_name] = {
            "reason": EXCLUDED_REASON,
            "declared": len(declared),
            "inside_commitment": len(declared) - len(outside),
            "outside_commitment": len(outside),
        }

    from cullinan import _version as version_api

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_from": {
            "tool": "scripts/generate_contracts.py",
            "cullinan_version": version_api.__version__,
            "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
        },
        "stability_commitment": commitment,
        "stability_shapes": shapes,
        "not_in_commitment": not_in_commitment,
    }


def write_artifact(path: Path, serialized: str) -> None:
    """Write the artifact with the repository's line ending, not the platform's.

    ``Path.write_text`` translates ``"\\n"`` to the platform separator, so on
    Windows the artifact came out with CRLF throughout while the committed blob
    was LF: the file differed from the index the moment it was written, and the
    difference was invisible on Linux. The repository decides this file's bytes
    (``.gitattributes``), so the writer has to agree with it.

    ``newline`` is passed to ``open`` rather than to ``write_text`` because the
    latter only accepts it from Python 3.10, and this script has to run on the
    declared floor of 3.9.
    """
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(serialized)


def main() -> int:
    contract = build_contract()
    serialized = json.dumps(contract, indent=2, ensure_ascii=False) + "\n"
    write_artifact(ARTIFACT_PATH, serialized)
    print(f"Wrote {ARTIFACT_PATH}")
    for module_name, names in contract["stability_commitment"].items():
        print(f"  {module_name}: {len(names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
