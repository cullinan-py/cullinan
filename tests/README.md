# Cullinan Test Directory

The `tests\` directory is organized by responsibility, and `pytest` is the only official entry point. The application-first update coverage has been consolidated into directly collectible pytest tests.

## How to Run

Run from the repository root:

```powershell
.venv\Scripts\python -m pytest
```

Run by directory:

```powershell
.venv\Scripts\python -m pytest tests\core
.venv\Scripts\python -m pytest tests\di
.venv\Scripts\python -m pytest tests\web
.venv\Scripts\python -m pytest tests\integration
.venv\Scripts\python -m pytest tests\regression
.venv\Scripts\python -m pytest tests\compat
```

## Directory Structure

```text
tests/
├── compat/        # Compatibility and historical API behavior
├── core/          # Core modules, config, scanning, exceptions, and base behavior
├── di/            # IoC / DI, container, lifecycle, registry
├── integration/   # Cross-module integration tests
├── regression/    # Historical defect regression and edge cases
├── web/           # Web runtime, request handling, params/models/codec
├── helpers/       # Shared helpers (not test entry points)
└── conftest.py    # Shared pytest startup configuration
```

## Conventions

1. Official test files are uniformly named `test_*.py`.
2. When adding tests, place them in the corresponding domain directory first; only cross-module scenarios go in `integration`.
3. When adding or refreshing tests, do not use script-style main-line tests like `run_*`, `quick_*`, `verify_*`, `diagnose_*`.
4. Legacy `if __name__ == "__main__"`, `main()`, `run_all_tests()` direct-run entry points have been cleaned up; all official verification is handled by pytest collection.
5. If you need shared test utilities, put them in `tests\helpers\`; do not use them directly as test entry points.

## Writing Guidelines

1. Prefer writing test functions or `unittest.TestCase` classes that can be directly collected by `pytest`.
2. Avoid relying on manual execution patterns like `if __name__ == "__main__"`, `print("[PASS]")`, `return True/False`.
3. When you need the repository root path, rely on the unified path injection provided by `tests\conftest.py`; do not hardcode paths in new files.

## Tests Related to This Update

- `tests\core\test_application_model_refactor.py`: application-first startup, module ownership, runtime switching
- `tests\core\test_public_api_boundaries.py`: top-level recommended API, compat export warnings, public boundary consolidation
- `tests\core\test_decorators.py`: decorator registration metadata and re-scan capability
- `tests\integration\test_adapter_integration.py`: ASGI / Tornado adapter integration paths
- `tests\integration\test_gateway_integration.py`: gateway end-to-end behavior pytest integration coverage
- `tests\web\test_openapi_generator.py`: OpenAPI auto-generation and public spec path coverage
