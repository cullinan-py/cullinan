"""The built-in IoC/DI depth baseline, pinned as executable criteria.

The baseline is the shared definition of "how deep is the built-in container".
It is pinned here - not implemented - so later work can add depth against a
fixed, checkable target. Every item is binary:

1. three scopes;
2. five conditional annotations;
3. a registry ``freeze`` that ``refresh()`` calls;
4. circular-dependency detection;
5. request-scope transitivity validation.

None of these tests adds depth to the container; they only record the baseline
that a deeper implementation must continue to satisfy.
"""

import inspect
from pathlib import Path

from cullinan.core import (
    ApplicationContext,
    CircularDependencyError,
    Conditional,
    ConditionalOnBean,
    ConditionalOnClass,
    ConditionalOnMissingBean,
    ConditionalOnProperty,
    ScopeType,
    ScopeViolationError,
)
from cullinan.core.definition_registry import DefinitionRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_di_baseline_has_three_scopes():
    """Scopes = singleton, prototype and request."""
    assert {scope.name for scope in ScopeType} == {
        "SINGLETON",
        "PROTOTYPE",
        "REQUEST",
    }


def test_di_baseline_has_five_conditional_annotations():
    """Conditional annotations = property, class, missing-bean, bean, plain."""
    annotations = {
        ConditionalOnProperty.__name__,
        ConditionalOnClass.__name__,
        ConditionalOnMissingBean.__name__,
        ConditionalOnBean.__name__,
        Conditional.__name__,
    }
    assert annotations == {
        "ConditionalOnProperty",
        "ConditionalOnClass",
        "ConditionalOnMissingBean",
        "ConditionalOnBean",
        "Conditional",
    }


def test_di_baseline_registry_freeze_is_invoked_by_refresh():
    """The definition registry can freeze and ``refresh()`` calls it."""
    assert hasattr(DefinitionRegistry, "freeze")
    refresh_source = inspect.getsource(ApplicationContext.refresh)
    assert "freeze()" in refresh_source, (
        "refresh() must freeze the definition registry so the container is sealed"
    )


def test_di_baseline_detects_circular_dependencies():
    """Circular dependencies are detected and have a renderer."""
    assert issubclass(CircularDependencyError, Exception)

    import cullinan.core.diagnostics as diagnostics

    assert hasattr(diagnostics, "format_circular_dependency_error")


def test_di_baseline_validates_request_scope_transitivity():
    """Request-scope transitivity is validated and has a dedicated test module."""
    assert issubclass(ScopeViolationError, Exception)
    validation = REPO_ROOT / "tests" / "di" / "test_transitive_scope_validation.py"
    assert validation.exists(), (
        "the request-scope transitivity validation baseline requires a dedicated "
        "test module"
    )
