# -*- coding: utf-8 -*-
"""Check that the production deployment guide only names things that exist.

A deployment guide is read at the worst possible moment — during an incident, or
by someone who has just been handed a service. A wrong symbol in it is worse
than no guide, because it costs the reader time before they discover the page is
fiction.

So the guide is checked against the code:

* every ``from cullinan... import ...`` in its code blocks must import;
* every configuration field it tells you to set must exist on the class it names;
* the English and Chinese versions must keep the same section structure, so a
  reader switching language does not silently lose a step.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGLISH = REPO_ROOT / "docs" / "deployment.md"
CHINESE = REPO_ROOT / "docs" / "zh" / "deployment.md"

_CODE_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)
_H2 = re.compile(r"^## (.+)$", re.MULTILINE)


def _blocks(path: Path) -> list[str]:
    return _CODE_BLOCK.findall(path.read_text(encoding="utf-8"))


def _imports(source: str) -> list[tuple[str, str]]:
    """Return ``(module, name)`` pairs imported by a code block."""
    pairs: list[tuple[str, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name != "*":
                    pairs.append((node.module, alias.name))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                pairs.append((alias.name, ""))
    return pairs


def test_both_languages_have_the_guide():
    assert ENGLISH.is_file()
    assert CHINESE.is_file()


def test_the_guide_has_code_blocks_to_check():
    blocks = _blocks(ENGLISH)
    assert len(blocks) >= 5, "the guide is mostly prose; there is nothing to hold to the code"


def test_every_imported_symbol_exists():
    failures = []
    for block in _blocks(ENGLISH):
        for module_name, symbol in _imports(block):
            if not module_name.startswith("cullinan"):
                continue
            try:
                module = importlib.import_module(module_name)
            except ImportError as error:
                failures.append(f"{module_name} cannot be imported: {error}")
                continue
            if symbol and not hasattr(module, symbol):
                failures.append(f"{module_name} has no {symbol}")
    assert not failures, "the deployment guide names symbols that do not exist: " + "; ".join(failures)


def test_the_configuration_fields_it_tells_you_to_set_exist():
    from cullinan.web.gateway import WebRuntimeConfig

    fields = set(WebRuntimeConfig.__dataclass_fields__)
    for field in ("drain_timeout", "trust_forwarded_headers"):
        assert field in fields, f"the guide sets WebRuntimeConfig.{field}, which the class does not have"

    # The guide's first example passes these to @configure(...).
    from cullinan.support.config import configure

    parameters = set(inspect.signature(configure).parameters)
    for parameter in ("user_packages", "server_host", "server_port", "server_engine", "static_files"):
        assert parameter in parameters, f"the guide passes configure({parameter}=...), which it does not accept"


def test_the_runtime_config_entry_point_it_shows_is_real():
    from cullinan.application import Application

    parameters = inspect.signature(Application.__init__).parameters
    assert "runtime_config" in parameters, (
        "the guide shows Application(..., runtime_config=...), which the constructor does not accept"
    )


def test_the_predicate_and_callback_it_tells_you_to_use_exist():
    from cullinan.application import Application
    from cullinan.core.application_context import ApplicationContext

    assert hasattr(Application, "accepts_requests")
    assert hasattr(ApplicationContext, "accepts_requests")
    assert hasattr(ApplicationContext, "add_draining_handler")


def test_both_languages_keep_the_same_section_structure():
    english = _H2.findall(ENGLISH.read_text(encoding="utf-8"))
    chinese = _H2.findall(CHINESE.read_text(encoding="utf-8"))
    assert len(english) == len(chinese), (
        "the two language versions have different section counts "
        f"({len(english)} vs {len(chinese)}), so one of them has drifted"
    )


def test_the_check_can_fail():
    """The import check must be able to report a missing symbol.

    Without this, a refactor that made ``hasattr`` always true -- or that
    accidentally compared against the module instead of the attribute -- would
    leave every test above green and the guide unverified.
    """
    from cullinan.web.gateway import WebRuntimeConfig

    assert not hasattr(WebRuntimeConfig, "definitely_not_a_field_5c1b")
