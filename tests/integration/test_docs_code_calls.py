"""The calls the docs show must take the keywords the shipped callables accept.

The existing public-guide gate proves that every ``cullinan`` import resolves.
That is necessary but not sufficient: a page can import ``configure`` correctly
and still teach ``configure(port=8080)`` after the parameter was renamed, and
nothing goes red. This gate reads each documented call, resolves the callable it
is actually referring to, and compares the keywords against the live signature.

Resolution is deliberately conservative -- a name is only checked when the same
code block imports it from ``cullinan``. A block that builds its own objects is
left alone, because guessing what those objects are would produce findings that
are about the parser rather than about the docs.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"
EXCLUDED_DIRS = {"templates"}
PY_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)
HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.M)

# Same markers as the import-resolution gate in test_examples_public_guides.py:
# a block under a heading that says it is deprecated, about to be removed, or a
# pre-migration "v0.9x" sample is teaching history on purpose, and holding it to
# today's signature would delete the lesson.
STALE_HEADING_MARKERS = ("deprecated", "will be removed", "弃用", "移除", "v0.9x")


def public_pages():
    for page in sorted(DOCS.rglob("*.md")):
        if not EXCLUDED_DIRS & set(page.relative_to(DOCS).parts):
            yield page.relative_to(REPO_ROOT).as_posix(), page.read_text(encoding="utf-8")


def _resolve_dotted(dotted: str):
    """Import the longest importable prefix, then getattr the rest."""
    parts = dotted.split(".")
    for cut in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:cut]))
        except ImportError:
            continue
        try:
            for attr in parts[cut:]:
                obj = getattr(obj, attr)
        except AttributeError:
            return None
        return obj
    return None


def _bindings(tree: ast.Module) -> dict[str, object]:
    """Names this block imports from the package, mapped to the real objects."""
    bound: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "cullinan":
            for alias in node.names:
                obj = _resolve_dotted(f"{node.module}.{alias.name}")
                if obj is not None:
                    bound[alias.asname or alias.name] = obj
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "cullinan":
                    obj = _resolve_dotted(alias.name)
                    if obj is not None:
                        bound[alias.asname or alias.name.split(".")[0]] = obj
    return bound


def _qualname(expr: ast.expr, bound: dict[str, object]) -> str | None:
    if isinstance(expr, ast.Name):
        return expr.id if expr.id in bound else None
    if isinstance(expr, ast.Attribute):
        base = _qualname(expr.value, bound)
        return f"{base}.{expr.attr}" if base else None
    return None


def _dotted_target(expr: ast.expr, bound: dict[str, object]):
    name = _qualname(expr, bound)
    if not name:
        return None
    head, _, rest = name.partition(".")
    if head not in bound:
        return None
    obj = bound[head]
    for attr in filter(None, rest.split(".")):
        if not hasattr(obj, attr):
            return None
        obj = getattr(obj, attr)
    return obj


def _heading_before(text: str, position: int) -> str:
    heading = ""
    for match in HEADING.finditer(text, 0, position):
        heading = match.group(2).strip()
    return heading


def documented_call_problems(text: str) -> list[str]:
    problems: list[str] = []
    for match in PY_BLOCK.finditer(text):
        if any(marker in _heading_before(text, match.start()).lower() for marker in STALE_HEADING_MARKERS):
            continue
        block = match.group(1)
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        bound = _bindings(tree)
        if not bound:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = _dotted_target(node.func, bound)
            if target is None or not callable(target):
                continue
            try:
                signature = inspect.signature(target)
            except (TypeError, ValueError):
                continue
            parameters = signature.parameters
            if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
                continue
            for keyword in node.keywords:
                if keyword.arg is None:
                    continue
                if keyword.arg not in parameters:
                    problems.append(
                        f"{_qualname(node.func, bound)}(...): no parameter {keyword.arg!r}; "
                        f"takes {sorted(parameters)}"
                    )
    return problems


def test_documented_calls_use_parameters_that_exist():
    failures = []
    checked = 0
    for rel, text in public_pages():
        for problem in documented_call_problems(text):
            failures.append(f"{rel}: {problem}")
        checked += _resolved_call_count(text)

    assert not failures, "documented calls do not match the shipped signatures:\n" + "\n".join(failures)
    # A gate that resolves nothing passes for the wrong reason. The docs carry
    # several hundred resolvable calls today; if this floor trips, the resolver
    # broke and the green above stopped meaning anything.
    assert checked >= 200, (
        f"only {checked} documented calls could be resolved, which is too few to "
        "call this gate a check rather than a formality"
    )


def _resolved_call_count(text: str) -> int:
    count = 0
    for match in PY_BLOCK.finditer(text):
        if any(marker in _heading_before(text, match.start()).lower() for marker in STALE_HEADING_MARKERS):
            continue
        try:
            tree = ast.parse(match.group(1))
        except SyntaxError:
            continue
        bound = _bindings(tree)
        if not bound:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = _dotted_target(node.func, bound)
                if target is not None and callable(target):
                    count += 1
    return count


def test_the_signature_gate_can_actually_fail():
    """Feed it a call that cannot be right, and require it to be reported."""
    block = (
        "```python\n"
        "from cullinan import configure\n"
        "configure(this_parameter_does_not_exist=1)\n"
        "```\n"
    )
    problems = documented_call_problems(block)
    assert problems, "the gate silently accepted a call with an impossible parameter"
    assert "this_parameter_does_not_exist" in problems[0]
