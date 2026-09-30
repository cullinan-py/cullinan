# -*- coding: utf-8 -*-
"""Central semantic rule messages and warnings for Cullinan."""

from __future__ import annotations

import threading
import warnings
from typing import Dict


class CullinanSemanticWarning(UserWarning):
    """Base warning for semantic-rule deviations."""


class ComponentDiscoveryWarning(CullinanSemanticWarning):
    """Warning for component discovery semantics."""


class CompatibilitySemanticWarning(CullinanSemanticWarning):
    """Warning for compatibility-only APIs."""


class InjectionSemanticWarning(CullinanSemanticWarning):
    """Warning for injection semantics that are valid but discouraged."""


class PublicAPISemanticWarning(CullinanSemanticWarning):
    """Warning for advanced/internal entrypoints used as default app APIs."""


SEMANTIC_RULES: Dict[str, str] = {
    "component-import-execution": (
        "Component registration depends on decorators running during module import, "
        "not on static source scanning."
    ),
    "component-top-level": (
        "Automatic discovery and assembly only guarantee module-top-level components "
        "whose decorators ran during import."
    ),
    "component-declared-not-assembled": (
        "Every component declared by a decorator is either assembled or explicitly "
        "reported: declarations that the assembly pass did not pick up are surfaced "
        "instead of being dropped silently."
    ),
    "inject-unique-binding": (
        "Inject() only accepts type contracts that normalize stably and map to exactly one component."
    ),
    "inject-by-name": (
        "InjectByName() performs explicit name-based binding. Type annotations describe intent only "
        "and do not participate in name resolution."
    ),
    "refresh-freeze": (
        "After ApplicationContext.refresh(), PendingRegistry and DefinitionRegistry are frozen. "
        "Define new runtime structure boundaries before that point."
    ),
    "lifecycle-request-scope": "Singleton components cannot depend directly on request-scoped components.",
    "compatibility-api": (
        "Compatibility APIs only keep older code running. They are not the recommended programming model."
    ),
    "public-api-boundary": (
        "Regular applications should prefer Cullinan's top-level public APIs. "
        "runtime, adapter, and core paths are advanced or internal entrypoints."
    ),
    "gateway-pipeline-reset": (
        "The gateway globals are rebuilt at the startup boundary. Middleware registered on the "
        "pre-boot pipeline is reset there, and that reset is reported instead of staying silent."
    ),
    "middleware-component-declaration": (
        "A class passed to configure(middlewares=[...]) is created and injected by the container "
        "only when it is declared with @component. The framework never guesses container ownership."
    ),
    "preboot-registration-rejected": (
        "Middleware added to the gateway pipeline before the boot boundary is rejected there. "
        "The declarations and the running pipeline must agree, so a pre-boot registration is an "
        "error instead of a silently discarded entry."
    ),
}

_warned_keys = set()
_warned_lock = threading.Lock()


def describe_semantic_rule(rule_key: str) -> str:
    return SEMANTIC_RULES[rule_key]


def format_semantic_message(rule_key: str, problem: str, guidance: str | None = None) -> str:
    parts = [
        f"Semantic rule: {describe_semantic_rule(rule_key)}",
        f"Problem: {problem}",
    ]
    if guidance:
        parts.append(f"Guidance: {guidance}")
    return " ".join(parts)


def warn_semantic_once(
    *,
    key: str,
    rule_key: str,
    problem: str,
    guidance: str | None = None,
    category: type[Warning] = CullinanSemanticWarning,
    stacklevel: int = 2,
) -> None:
    with _warned_lock:
        if key in _warned_keys:
            return
        warnings.warn(
            format_semantic_message(rule_key, problem, guidance),
            category=category,
            stacklevel=stacklevel,
        )
        _warned_keys.add(key)


def reset_semantic_warnings() -> None:
    with _warned_lock:
        _warned_keys.clear()


__all__ = [
    "SEMANTIC_RULES",
    "CullinanSemanticWarning",
    "ComponentDiscoveryWarning",
    "CompatibilitySemanticWarning",
    "InjectionSemanticWarning",
    "PublicAPISemanticWarning",
    "describe_semantic_rule",
    "format_semantic_message",
    "warn_semantic_once",
    "reset_semantic_warnings",
]
