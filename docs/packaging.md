title: "Packaging Guide — Module Discovery in Frozen Environments"
slug: "packaging"
module: []
tags: []
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/packaging.md"
related_tests: []
related_examples: []
estimate_pd: null
last_updated: "2026-10-27"
pr_links: []


# Packaging Guide — Module Discovery in Frozen Environments

Cullinan v0.93a11.post2+ introduces a **unified strategy pipeline** for module
discovery across all packaging tools (Nuitka, PyInstaller) and development
environments.

## Quick Start

### Explicit Module List (Recommended for One-File Modes)

The most reliable approach for `--onefile` builds:

```python
from cullinan import configure

configure(
    explicit_modules=["myapp.services", "myapp.controllers"],
    user_packages=["myapp"],
)
```

**`explicit_modules`** replaces the deprecated `nuitka_modules` (removed in
v0.93a11.post2). It works with **all** packaging tools — Nuitka, PyInstaller, and
any future freezer.

### User Packages (Recommended for Directory Modes)

For `--standalone` / `--onedir` builds where filesystem access is available:

```python
from cullinan import configure

configure(
    user_packages=["myapp"],
    auto_scan=True,  # default
)
```

## Strategy Pipeline

Cullinan now uses a **composable pipeline** of six independent strategies.
Each pipeline is selected automatically based on `get_packaging_mode()`:

### Nuitka

| Mode | Pipeline | Notes |
|------|----------|-------|
| `--standalone` | S0 → S1 → S2 → S3 → S4 | Full filesystem scan |
| `--onefile` | S0 → S1 → S2 → S3 → S5 | Skip S4 (no source files), use recursive `dir(pkg)` + `sys.modules` fallback |

### PyInstaller

| Mode | Pipeline | Notes |
|------|----------|-------|
| `--onedir` | S0 → S1 → S4 | `_MEIPASS` + executable dir scan |
| `--onefile` | S0 → S1 → S4 | `_MEIPASS` temp extraction dir |

### Development

| Mode | Pipeline | Notes |
|------|----------|-------|
| `development` | S0 → S1 → S2 → S3 | `get_caller_package()` + fallback |

### Strategy Reference

| Strategy | Description | Runs When |
|----------|-------------|-----------|
| **S0: explicit_modules** | User-provided explicit module list | `explicit_modules` is set |
| **S1: user_packages** | Configured packages via `pkgutil.walk_packages` | `user_packages` is set |
| **S2: sys_modules_scan** | Auto-scan `sys.modules` with path heuristics | `auto_scan=True` |
| **S3: main_module_inference** | Infer package from `__main__.__file__` | Always |
| **S4: directory_scanning** | Walk filesystem for `.py`/`.pyc`/`.pyd`/`.so` | Standalone/onedir modes |
| **S5: onefile_dir_fallback** | Recursive `dir(pkg)` + `sys.modules` prefix scan | One-file modes (last resort) |

## Performance Improvements (v0.93a11.post2+)

1. **Global type hints cache** — `typing.get_type_hints()` results are cached
   at module level (shared across `ApplicationContext` instances). Previously
   each context instance had its own cache, causing duplicate resolution.

2. **Lazy source line** — `inspect.getsourcelines()` is no longer called
   during decorator registration. Source file paths are still captured; line
   numbers are deferred to on-demand diagnostics.

## Migration from v0.93a11

| Old API | New API |
|---------|---------|
| `nuitka_modules=["myapp"]` | `explicit_modules=["myapp"]` |
| `scan_modules_nuitka()` | Pipeline auto-selected |
| `scan_modules_pyinstaller()` | Pipeline auto-selected |

The old functions have been removed. No backward-compatibility aliases
are provided — update your configuration at the same time you upgrade
the framework.

## Troubleshooting

### No modules discovered in one-file mode

```python
configure(explicit_modules=["your_top_level_package"])
```

### Type hints resolution error after class reload (tests)

`PendingRegistry.reset()` now also invalidates the global type hints cache:

```python
from cullinan.core.pending import PendingRegistry
PendingRegistry.reset()  # also clears type hints cache
```

### Strategy override (advanced)

```python
from cullinan.runtime.scan_pipelines import execute_pipeline
from cullinan.support.config import get_config

modules = execute_pipeline(
    get_config(),
    packaging_mode="nuitka-onefile",
    base_dirs=["/custom/path"],
    early_termination=False,  # run ALL strategies
)
```
