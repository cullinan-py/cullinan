title: "Contributing"
slug: "contributing"
module: []
tags: ["contributing"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/contributing.md"
related_tests: []
related_examples: []
estimate_pd: 1.0
last_updated: "2025-12-25T00:00:00Z"
pr_links: []

# Contributing

Thanks for your interest in improving Cullinan. This page covers how to set up a
development environment, the checks that run before a change is merged, and what
a complete contribution looks like.

## Set up a development environment

Requires Python **3.9+**.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Unix: source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
```

## Before you open a pull request

Run the same checks CI runs, and make sure they pass locally:

```bash
ruff check .                 # lint
python -m pytest tests -q    # full test suite - must stay green
python -m build && twine check dist/*   # packaging health
```

## What a complete contribution includes

Any feature, behavior change, or rename should update all of the parts below
together, in the same pull request:

- **Code** - implementation under `cullinan/`, exposed through the relevant
  `__init__` public API.
- **Tests** - pytest cases under `tests/` covering **both engines**
  (Tornado + ASGI) plus the public-API path, including negative and edge cases.
- **Examples** - a runnable demo under `examples/<feature>/`, kept in sync with
  `docs/examples.md`.
- **Docs** - bilingual `docs/<feature>_guide.md` + `docs/zh/...`, and update the
  `mkdocs.yml` navigation when you add or rename a page.

## Running the examples

Each example is runnable on its own:

```bash
python -m examples.minimal_app
python -m pytest examples/testing_flow/test_app.py -q
```

## Reporting issues and proposing changes

Use the issue templates (bug report / feature request) to file an issue, and
open a pull request against `master`. Include the Cullinan version, your Python
version, the runtime you use (Tornado or ASGI), and a minimal repro when
reporting a bug.
