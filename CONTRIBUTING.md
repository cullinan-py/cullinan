# Contributing to Cullinan

Thanks for your interest in improving Cullinan!

This project iterates through pull requests against `master` (stable) and the
active `release/**` pre-release branch.

## Development setup

Requires Python **3.9+**.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Unix: source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
```

## Before you open a PR

Run the same gates CI runs:

```bash
ruff check .                 # lint (E9 + F)
python -m pytest tests -q    # full test suite - must stay green
python -m build && twine check dist/*   # packaging health
```

## A complete change (mandatory)

Any feature, behavior change, or rename MUST update **all of the parts below
together**, in the same PR:

1. **Code** - implementation under `cullinan/`, exposed through the
   relevant `__init__` public API.
2. **Tests** - pytest cases under `tests/` covering **both engines**
   (Tornado + ASGI) plus the public-API path, including negative & edge cases.
3. **Examples** - a runnable demo under `examples/<feature>/` with
   `__main__.py` + `README.md`.
4. **Docs** - bilingual `docs/<feature>_guide.md` + `docs/zh/...`, and
   update `mkdocs.yml` nav + `README.MD`.

A change is not "done" until the code, tests, examples, and docs all agree.

If an item does not apply to this change, mark it N/A and explain why.

## Engine neutrality

Cullinan runs on both Tornado and ASGI. Features route through the gateway
`Router` / `Dispatcher`, **not** engine-native handlers. Do not add
backend-specific behavior that diverges between engines.

## Code style

- Lint with `ruff check .` (config in `ruff.toml`).
- Match surrounding code; comment only where clarification is needed.

## Commits

- Use a clear type prefix: `feat:`, `fix:`, `docs:`, `ci:`, `build:`,
  `refactor:`, `test:`.
- Describe the root cause and which parts of the change you touched (code, tests, examples, docs).
- Attribute the project to `plumeink` and only to `plumeink`. Do not add AI
  co-author trailers or any other attribution: every public-facing name in this
  repository is `plumeink`, and the product name `Cullinan` is the project name
  rather than an author.

## Versioning

Follows PEP 440. An `aN` suffix marks a feature iteration, which may add to the
public API; a `.postM` suffix marks a patch/defect fix that adds no new public
API. Because the release line advances over time, this section deliberately
describes the suffixes by meaning instead of pinning them to a specific major
or minor version. The canonical package version lives in `cullinan/_version.py`;
`pyproject.toml`, `cullinan/__init__.py`, and `cullinan/core/__init__.py` must
stay aligned to that single source.

## Reporting issues

Use the issue templates (bug report / feature request). Include Cullinan
version, Python version, engine (Tornado/ASGI), and a minimal repro.
