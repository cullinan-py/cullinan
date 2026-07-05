title: "Local Build & Run"
slug: "build-run"
module: []
tags: ["build", "run"]
author: "Cullinan"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/build_run.md"
related_tests: []
related_examples: []
estimate_pd: 1.0
last_updated: "2025-12-25T00:00:00Z"
pr_links: []

# Local Build & Run

This page describes how to set up a local environment, install Cullinan in editable mode, run tests, and start example applications on Windows (PowerShell), Linux, and macOS.

## Prerequisites

- Python 3.9 or newer
- Git

## Clone the repository

On all platforms:

```bash
git clone https://github.com/cullinan-py/cullinan.git
cd Cullinan
```

## Create and activate a virtual environment (optional but recommended)

On Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

On Linux / macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

## Install dependencies in editable mode

On all platforms:

```bash
python -m pip install -U pip
pip install -e .
```

Cullinan now declares editable/build metadata in `pyproject.toml`; `setup.py`
remains a compatibility shim for legacy setuptools workflows.

If you need an engine/runtime extra, install it explicitly:

```bash
pip install -e .[tornado]
pip install -e .[asgi]
pip install -e .[full]
```

If you have additional development extras configured in `setup.py` or `pyproject.toml`, you can install them as needed, for example:

```bash
pip install -e .[dev]
```

## Run the test suite

On all platforms:

```bash
pytest -q
```

If your environment uses a different test runner, adapt the command accordingly (e.g. `python -m pytest`).

## Run an example application

The maintained runnable examples now live under the root `examples/` directory as
small packages. Start from the minimal example, then move to the more focused guides.

### Minimal app

```powershell
python -m examples.minimal_app
```

Then open `http://localhost:4080/hello` to verify the server is running.

### Business layering with injection

```powershell
python -m examples.controller_service_inject
```

Use this example to see the recommended `@service` + `@controller` + `Inject()` path.

### Middleware and module boundary

```powershell
python -m examples.middleware_and_module
```

This example shows runtime boundary ownership through `@module` and request-pipeline
extension through `@middleware`.

### Parameter binding

```powershell
python -m examples.parameter_handling
```

Use it alongside the parameter guide to see `Path`, `Query`, and `Body` on controller methods.

### Example-level testing flow

```powershell
python -m pytest examples/testing_flow/test_app.py -q
```

This path exercises the example through the decorated entry method and `main.get_asgi_app()` without launching
an external server process.
