# Controller Dependency Injection Bug Fix

Author: Cullinan

## Problem Description

### Bug Symptoms

In classes decorated with `@controller`, dependencies marked with `Inject()` were not being replaced with actual service instances at runtime:

```python
@controller(url='/api')
class BotController:
    multi_channel_service: MultiChannelService = Inject()
    
    def handle_request(self):
        # Error: self.multi_channel_service is still an Inject object
        # AttributeError: 'Inject' object has no attribute 'get_binding'
        self.multi_channel_service.get_binding(...)
```

### Error Message

```
AttributeError: 'Inject' object has no attribute 'get_binding'
```

## Root Cause

`ControllerRegistry.get_instance()` was directly calling `controller_class()` to instantiate the Controller, without using `ApplicationContext._create_class_instance()` to handle dependency injection.

**Problematic Code (Before Fix)**:
```python
# cullinan/controller/registry.py
def get_instance(self, name: str):
    # ...
    # Direct instantiation, not handling Inject() markers
    instance = controller_class()
    return instance
```

## Fix Implementation

### 1. Add Global ApplicationContext Access

Added to `cullinan/core/__init__.py`:

```python
_global_application_context = None

def get_application_context():
    """Get the global ApplicationContext instance"""
    return _global_application_context

def set_application_context(ctx) -> None:
    """Set the global ApplicationContext instance"""
    global _global_application_context
    _global_application_context = ctx
```

### 2. Modify ControllerRegistry.get_instance()

Modified in `cullinan/controller/registry.py`:

```python
def get_instance(self, name: str):
    # ...
    from cullinan.core import get_application_context
    ctx = get_application_context()

    if ctx is not None and ctx.is_refreshed:
        # Create instance via ApplicationContext with dependency injection
        instance = ctx._create_class_instance(controller_class)
    else:
        # Fallback: direct instantiation (no dependency injection)
        logger.warning(f"ApplicationContext not available for controller {name}")
        instance = controller_class()
    
    return instance
```

### 3. Set Global ApplicationContext in All Entry Points

Modified the following files to call `set_application_context(ctx)` after creating `ApplicationContext`:

- `cullinan/scanner.py`
- `cullinan/bootstrap.py`
- `cullinan/application.py`
- `cullinan/app.py`

## Test Verification

### Run All Tests

```bash
python tests/run_all_di_tests.py
```

### Test Suite Overview

| Test File | Description | Tests |
|-----------|-------------|-------|
| `test_di_fix.py` | Basic fix verification | 3 |
| `test_comprehensive_di.py` | Comprehensive DI tests | 15 |
| `test_botcontroller_regression.py` | BotController regression test | 4 |

### Comprehensive Test Categories

**Specialized Tests (Controller DI Bug Fix)**:
1. Basic Controller DI
2. Multiple service injection
3. Optional dependency injection
4. hasattr check (original bug scenario)
5. Controller singleton pattern
6. Fallback when no ApplicationContext

**Robustness Tests (Service DI)**:
1. Basic Service DI
2. Chain injection
3. Service singleton pattern
4. Inject by name
5. Type inference injection

**Boundary Tests**:
1. Missing required dependency
2. Empty Controller (no dependencies)
3. Controller with `__init__`
4. Concurrent access safety

### Expected Output

```
======================================================================
All tests completed
======================================================================
  [PASS] Basic fix verification
  [PASS] Comprehensive test suite
  [PASS] BotController regression test
======================================================================
Result: All passed
```

## Modified Files

| File | Changes |
|------|---------|
| `cullinan/core/__init__.py` | Added `get_application_context()` and `set_application_context()` |
| `cullinan/controller/registry.py` | Modified `get_instance()` to use ApplicationContext for DI |
| `cullinan/scanner.py` | Added `set_application_context(ctx)` call |
| `cullinan/bootstrap.py` | Added `set_application_context(ctx)` call |
| `cullinan/application.py` | Added `set_application_context(ctx)` call |
| `cullinan/app.py` | Added `set_application_context(ctx)` call |

## New Test Files

| File | Description |
|------|-------------|
| `tests/test_di_fix.py` | Basic DI fix verification (3 tests) |
| `tests/test_comprehensive_di.py` | Comprehensive DI test suite (15 tests) |
| `tests/test_botcontroller_regression.py` | BotController regression test (4 scenarios) |
| `tests/run_all_di_tests.py` | Test runner for all DI tests |

## Notes

1. `@controller` and `@service` decorators do **not** require additional `@injectable` decorator
2. Dependency injection is automatically handled via `ApplicationContext._create_class_instance()` during Controller instantiation
3. Optional dependencies use `Inject(required=False)` marker and return `None` when not found

