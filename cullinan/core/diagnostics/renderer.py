# -*- coding: utf-8 -*-
"""Render structured DI diagnostics in a stable, human-readable format."""

from typing import List, Dict, Any, Optional


def render_resolution_path(path: List[str]) -> str:
    """Render a resolution path in a stable format.

    Args:
        path: Ordered resolution path.

    Returns:
        A formatted path string such as ``"A -> B -> C -> A"``.
    """
    if not path:
        return "(empty)"
    return " -> ".join(path)


def render_injection_point(owner: str, location: str, is_constructor: bool = False) -> str:
    """Render an injection point.

    Args:
        owner: Owner class name.
        location: Attribute or parameter name.
        is_constructor: Whether this is constructor injection.

    Returns:
        A formatted injection point such as
        ``"UserController.user_service"`` or ``"UserService.__init__(repo)"``.
    """
    if is_constructor:
        return f"{owner}.__init__({location})"
    return f"{owner}.{location}"


def render_candidate_sources(candidates: List[Dict[str, Any]]) -> str:
    """Render candidate sources and filtering reasons.

    Args:
        candidates: Candidate list. Each item may include ``source`` and ``reason``.

    Returns:
        Formatted candidate source information.
    """
    if not candidates:
        return "  (no candidate sources)"

    lines = []
    for i, candidate in enumerate(candidates, 1):
        source = candidate.get('source', 'unknown')
        reason = candidate.get('reason', 'unknown')
        lines.append(f"  [{i}] {source} - {reason}")

    return "\n".join(lines)


def render_dependency_error(
    error_type: str,
    message: str,
    dependency_name: Optional[str] = None,
    injection_point: Optional[str] = None,
    resolution_path: Optional[List[str]] = None,
    candidate_sources: Optional[List[Dict[str, Any]]] = None,
    cause: Optional[Exception] = None
) -> str:
    """Render a complete dependency resolution error message.

    Args:
        error_type: Error type name.
        message: Error message.
        dependency_name: Dependency name.
        injection_point: Injection point.
        resolution_path: Resolution path.
        candidate_sources: Candidate sources.
        cause: Original exception.

    Returns:
        Fully formatted error text.
    """
    lines = [
        f"[{error_type}] {message}",
        ""
    ]

    if dependency_name:
        lines.append(f"Dependency: {dependency_name}")

    if injection_point:
        lines.append(f"Injection point: {injection_point}")

    if resolution_path:
        lines.append(f"Resolution path: {render_resolution_path(resolution_path)}")

    if candidate_sources:
        lines.append("Candidate sources:")
        lines.append(render_candidate_sources(candidate_sources))

    if cause:
        lines.append("")
        lines.append(f"Original error: {type(cause).__name__}: {cause}")

    return "\n".join(lines)


def format_circular_dependency_error(chain: List[str]) -> str:
    """Format a circular dependency error message.

    Args:
        chain: Ordered dependency cycle.

    Returns:
        A formatted circular dependency error message.
    """
    path_str = render_resolution_path(chain)
    return f"Circular dependency detected: {path_str}"


def format_missing_dependency_error(
    dependency_name: str,
    injection_point: Optional[str] = None,
    resolution_path: Optional[List[str]] = None,
    available_sources: Optional[List[str]] = None
) -> str:
    """Format a missing dependency error message.

    Args:
        dependency_name: Missing dependency name.
        injection_point: Injection point.
        resolution_path: Resolution path.
        available_sources: Available sources.

    Returns:
        A formatted missing dependency error message.
    """
    lines = [f"Dependency '{dependency_name}' was not found."]

    if injection_point:
        lines.append(f"Injection point: {injection_point}")

    if resolution_path:
        # Append the missing item to the rendered path.
        full_path = resolution_path + [f"{dependency_name} (missing)"]
        lines.append(f"Resolution path: {render_resolution_path(full_path)}")

    if available_sources:
        lines.append("Available sources:")
        for source in available_sources:
            lines.append(f"  - {source}")

    return "\n".join(lines)


def format_scope_violation_error(
    chain: List[str],
    origin: str,
    violating: str,
) -> str:
    """Format a human-readable scope violation error message.

    Args:
        chain: Ordered dependency chain from origin to the violating
            request-scoped component (inclusive of both endpoints).
        origin: Name of the origin component (singleton/prototype).
        violating: Name of the violating request-scoped component.

    Returns:
        A formatted scope violation error message including the full
        dependency chain, aligned with ``format_circular_dependency_error``.
    """
    chain_str = render_resolution_path(chain)
    return (
        f"Scope violation detected:\n"
        f"  Origin: {origin}\n"
        f"  Violating component: {violating} (request-scoped)\n"
        f"  Dependency chain: {chain_str}\n"
        f"Resolve the request-scoped dependency inside a request context, "
        f"or adjust the component scopes."
    )


__all__ = [
    'render_resolution_path',
    'render_injection_point',
    'render_candidate_sources',
    'render_dependency_error',
    'format_circular_dependency_error',
    'format_missing_dependency_error',
    'format_scope_violation_error',
]
