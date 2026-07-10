---
title: "Cullinan Documentation Plan"
slug: "documentation-plan"
module: ["docs"]
tags: ["plan", "documentation"]
author: "Cullinan"
reviewers: []
status: draft
locale: en
translation_pair: "docs/zh/cullinan_documentation_plan.md"
related_tests: []
related_examples: []
estimate_pd: 0.0
last_updated: "2025-11-18T00:00:00Z"
pr_links: []
---

# Cullinan Documentation Plan

> Note: This plan is designed based on the Cullinan source code (using source implementation as the sole reference, ignoring comments). The goal is to establish a complete bilingual documentation system for the project (`docs/` and `docs/zh/` in 1:1 correspondence).

## Task Convergence and High-Level Plan

This planning document is used to collect multi-phase task plans, making it convenient to retain planning content in the repository for team review and allocation. Example follow-up actions:

- Create and commit Markdown plan files to the `docs/` directory.
- Run static checks to ensure files have no syntax/format errors (documentation files typically do not produce code compilation errors, but basic checks are still recommended).

Brief acceptance checklist (before submission):
- [x] File saved in UTF-8 encoding, Markdown format.
- [x] Includes objectives, scope, task breakdown, time estimates, quality gates, and example command descriptions.
- [x] Explicitly requires `docs/` and `docs/zh/` to be in 1:1 correspondence.

---

TL;DR: Write bilingual (English/Chinese) documentation for Cullinan (a Tornado-based IoC/DI framework) with `docs/` and `docs/zh/` in 1:1 correspondence, including getting started, examples, wiki (architecture/components/lifecycle/injection/middleware/extensions), API reference, migration guide, contributing guide, testing and local build instructions. Uses a source-code-driven research strategy (ignoring comments), preserves the existing IoC/DI design, and provides role allocation, milestones, quality gates, and run/verification command examples for PowerShell and other environments.

## 1. Objectives and Audience

- Objective: Provide clear, actionable, bilingual (English/Chinese) documentation for Cullinan to help new users get started quickly, help contributors understand internal design and injection mechanisms, and provide runnable examples and test verification steps.
- Audience: Library users (application developers), framework contributors/maintainers, code reviewers, automated test engineers.

## 2. Scope and Deliverables

Required deliverables (each must be in 1:1 correspondence under `docs/` and `docs/zh/`):

- `Getting Started` - `docs/getting_started.md` / `docs/zh/getting_started.md`
- `Examples` - `docs/examples.md` / `docs/zh/examples.md` (with runnable code kept in `examples/` in the repository)
- `Wiki` (architecture/components/lifecycle/injection/middleware/extensions) - `docs/wiki/architecture.md`, `components.md`, `lifecycle.md`, `injection.md`, `middleware.md`, `extensions.md` (and `docs/zh/wiki/*`)
- `API Reference` - `docs/api_reference.md` / `docs/zh/api_reference.md` (optionally auto-generated)
- `Migration Guide` - `docs/migration_guide.md` / `docs/zh/migration_guide.md`
- `Contributing` - `docs/contributing.md` / `docs/zh/contributing.md`
- `Testing & Verification` - `docs/testing.md` / `docs/zh/testing.md`
- `Local Build & Run` - `docs/build_run.md` / `docs/zh/build_run.md`
- Documentation templates and sample pages (front-matter, code snippet conventions, translation guidelines)

Additional deliverables (recommended):

- `examples/` runnable example collection (lightweight demos)
- Brief `README.md` update linking to `docs/` pages
- Documentation CI scripts (optional)

## 3. Research Method and Code Reading Strategy (source-code only, ignoring comments)

Research objective: Infer design and behavior from source code (not relying on comments), locate key modules and dependencies, extract external API, lifecycle, and injection behavior.

Strategy and steps:

1. High-level directory scan: First confirm top-level modules and entry points. Prioritize reading `cullinan/__init__.py`, `app.py`, `application.py`, `config.py`.
2. Core subsystem location: Locate the IoC/DI implementation (typically in `cullinan/core`). Focus on `core/__init__.py`, `core/provider.py`, `core/registry.py`, `core/scope.py`, etc. (adjust actual file names based on the `cullinan/core` directory listing).
3. Controllers/routing/middleware: Review `controller/`, `handler/`, `middleware/` files to find route registration, processing flow, and lifecycle hooks.
4. Module scanning and auto-registration: Read `module_scanner.py`, `websocket_registry.py`, etc. to understand the auto-discovery mechanism and registration timing.
5. Configuration and startup flow: Trace `main`, `start`, `initialize`, `run` style functions in `application.py` and `app.py` to form a startup sequence diagram (order, dependencies).
6. Injection point discovery: Search the source code for keywords (`inject`, `provide`, `provider`, `register`, `scope`, `singleton`, `transient`) to locate injection APIs and usage patterns.
7. Test-based verification: Review key tests under `tests/` (e.g., `test_core_injection.py`, `test_controller_injection_fix.py`, `test_registry.py`) to understand expected behavior and boundary conditions (tests are the most authoritative source of behavior specifications).
8. Dependency graph construction: Use static reading (or a simple script) to list import relationships between modules and draw a simple module dependency graph (to assist with architecture/component documentation).
9. Record findings: Record each module's responsibilities, inputs/outputs, lifecycle, and error patterns as "statements of fact." Based solely on source code behavior, not relying on comment explanations.

Tools and methods:

- Use repository search (via IDE or `rg`/`grep`) to locate symbols and string patterns.
- Read key test cases to supplement understanding.
- Build small Q&A notes (module -> responsibility -> interaction with other modules) for documentation writing.

Note: Do not change or encourage changing the existing IoC/DI design in the documentation; documentation should only describe/explain, and "improvement suggestions" may be provided as appendices or issues.

## 4. Task Breakdown and Milestones (Priority + Time Estimates)

Total estimated duration: 6 weeks (can be compressed with parallel resources). Time units are person-days (working days).

Phase A - Discovery and Outline (Priority: High, Duration: 4 person-days)
- A1. Quick source code scan and module map generation (2 person-days)
- A2. Draft documentation outline based on the map (1 person-day)
- A3. Confirm output format (Markdown structure, table of contents, translation process, whether to use Sphinx/mkdocs, etc.) (1 person-day)

Milestone A: Submit `docs/outline.md` and `docs/zh/outline.md`, including file list and owners.

Phase B - Getting Started and Examples (Priority: High, Duration: 6 person-days)
- B1. Write `Getting Started` English and Chinese versions (2 person-days)
- B2. Design and implement 2-3 minimal runnable examples in `examples/` (3 person-days)
- B3. Integrate examples into documentation and verify (1 person-day)

Milestone B: `docs/getting_started.md` and `examples/` are runnable by local users.

Phase C - Core Wiki (architecture/components/lifecycle/injection/middleware/extensions) (Priority: High, Duration: 10 person-days)
- C1. `architecture.md` (2 person-days)
- C2. `components.md` (2 person-days)
- C3. `lifecycle.md` (2 person-days)
- C4. `injection.md` (3 person-days)
- C5. `middleware.md` / `extensions.md` (1 person-day)

Milestone C: Deep understanding and documentation of core design, peer review passed.

Phase D - API Reference and Migration Guide (Priority: Medium, Duration: 8 person-days)
- D1. Decide API reference approach (auto vs manual) (0.5 days)
- D2. Generate or hand-write API summaries for all public modules (5 person-days)
- D3. Write migration guide (compatibility/breaking change descriptions) (2.5 person-days)

Milestone D: API reference complete and indexable; migration guide covers major change points.

Phase E - Contributing/Testing/Run Instructions and Local Build (Priority: Medium, Duration: 4 person-days)
- E1. `contributing.md` (1 person-day)
- E2. `testing.md` (1 person-day) - including how to run existing tests, how to write tests, CI requirements
- E3. `build_run.md` (2 person-days) - including Windows PowerShell instructions and virtual environment steps

Milestone E: Contribution process and testing guidelines ready.

Phase F - Translation, Verification, Quality Gates (Priority: High, Duration: 6 person-days)
- F1. Translation proofreading (English -> Chinese) and ensuring 1:1 file structure (3 person-days)
- F2. Documentation internal review (structure, facts, runnable examples) (2 person-days)
- F3. Final quality gate (run tests, example verification, submit PR) (1 person-day)

Milestone F: Bilingual documentation 1:1 correspondence passes QA.

Overall milestone timeline (can be shortened with parallelism):
- Week 1: Phase A complete
- Week 2: Phase B starts and completes
- Weeks 3-4: Phase C complete
- Week 5: Phases D and E complete
- Week 6: Phase F acceptance and release

## 5. Suggested Role Allocation (Example)

- 1 * Technical Writer (main documentation) - responsible for getting started, wiki body, example text
- 1 * Development Engineer (code research and example implementation) - responsible for source code mapping, runnable examples, verification tests
- 1 * Translator/Localization (Chinese proofreading) - responsible for `docs/zh/` translation and context verification
- 1 * Reviewer/Maintainer (architecture & CI review) - responsible for reviewing, CI merging, quality gate sign-off

## 6. Writing Guidelines (Must Follow)

- File encoding: UTF-8.
- Directory structure: `docs/` and `docs/zh/` must be in 1:1 correspondence, with identical filenames and relative paths.
- Language and style: Concise, fact-driven (based on source code behavior), provide examples and copyable steps where possible.
- No emoji in logs or example outputs (project convention).
- Windows PowerShell command examples should conform to Windows PowerShell v5.1 syntax; do not use `&&` to chain commands; if you need to execute multiple commands on one line, use semicolons `;`.
- When referencing files or symbols in documentation, use backticks (e.g., `cullinan/core`, `application.py`).
- For API references, clearly label "public API" vs "internal implementation," and encourage building usage examples only on public APIs.
- Translation strategy: Complete the English draft first and pass review, then do the Chinese translation; always maintain 1:1 content consistency.

## 7. Verification / Quality Gates

Each phase must pass the corresponding quality gate before proceeding to the next:

Quality gate examples:
- Code research complete: Submit `docs/outline.md` with module map and key function list; at least two engineers agree (signature or PR comment).
- Examples runnable: Examples in `examples/` can run successfully in a local virtual environment (see verification commands).
- Unit/integration tests: Run existing repository tests and ensure no regression (see commands below). Must achieve at least "same or better" pass rate as the current main branch.
- Documentation review: Each document undergoes at least 1 technical review and 1 language proofreading (Chinese).
- Pre-release: CI passes, documentation link integrity check, examples pass on Windows PowerShell.

Key verification commands (PowerShell notation, single-line examples use `;` as separator):
- Create and activate virtual environment (optional): Ensure you have a usable Python environment (virtualenv/conda/system Python, etc.). No need to hardcode activation commands in documentation.
- Install development dependencies and install this package (optional extras): `pip install -U pip; pip install -e .[dev]` or `pip install -e .`
- Run tests: `py -3 -m pytest -q` (or `pytest -q`)
- Run a single example (in `examples/` directory): `py example_script.py` or `python -m examples.demo` (depending on example implementation)
- Check documentation links/spelling (if using tools): `pylint`/`flake8` (code), `markdownlint` (documentation) (install as needed)

## 8. File Structure and Template Examples to Create

Recommended new/populated files in the repository (`docs/` and `docs/zh/` must mirror):

- `docs/README.md` (documentation home/navigation)
- `docs/getting_started.md` (quick start - environment, installation, running first application)
- `docs/examples.md` (example index and descriptions) + `examples/` directory for example code
- `docs/wiki/architecture.md` (architecture overview)
- `docs/wiki/components.md` (component responsibilities & API summary)
- `docs/wiki/lifecycle.md` (application startup/shutdown/lifecycle hooks)
- `docs/wiki/injection.md` (IoC/DI mechanism detailed explanation)
- `docs/wiki/middleware.md` (middleware chain and extension points)
- `docs/api_reference.md` (public API listed by module)
- `docs/migration_guide.md` (compatibility and migration)
- `docs/contributing.md` (contributor guide, code style, PR process)
- `docs/testing.md` (how to run existing tests, write tests, CI requirements)
- `docs/build_run.md` (local build/run instructions on Windows/Unix)
- `docs/templates/` (page templates: title, overview, example structure, API entry format, translation reference table)

Template examples (descriptions, not code blocks):
- Document top should include a brief "purpose/scope/prerequisites" three-section header; then the "examples" section follows a four-section template of "example description / code location / run steps / expected results."
- API entry template: module path -> brief description -> public class/function list (each item: signature, parameter description, return value, exceptions & usage example line references).
- Translation template: Each English file should have a reference checklist listing "suggested term translations" (e.g., IoC -> Inversion of Control, DI -> Dependency Injection).

## 9. Acceptance Criteria (Acceptance Checklist)

Each document must meet the following conditions before delivery:
- English and Chinese files in 1:1 correspondence (identical paths and filenames, equivalent content).
- Getting Started: New users can run examples and access the application within 30 minutes following the steps.
- Examples: At least 2 runnable examples (minimal: Hello World HTTP, advanced: Controller + DI + Middleware example).
- Wiki: Covers architecture diagram, component responsibilities, injection lifecycle and error model.
- API Reference: Covers all public modules with at least one usage example.
- Migration Guide: Lists all breaking changes and migration steps (if any).
- Contributing: Includes code style, PR process, test admission thresholds.
- Testing: Existing tests pass with `pytest` in a clean environment (same or better than main branch).
- Documentation review: At least 2 technical reviews and 1 text proofreading passed.
- CI/release: Documentation build or static check (if using mkdocs/sphinx) passes.

## 10. Risks and Mitigation

Risk 1: Source code understanding deviation (reading only source code, not comments, may lose design context)
- Mitigation: Use test cases as behavior specifications; confirm design intent with original authors during review and record as "author notes" appendix (without modifying source code).

Risk 2: IoC/DI design complexity makes it difficult to express intuitively
- Mitigation: Use flowcharts, sequence diagrams, and example code to demonstrate injection timing; add "common patterns/anti-patterns" in `docs/wiki/injection.md`.

Risk 3: Inconsistent English-Chinese translation or non-unified terminology
- Mitigation: Maintain a "terminology reference table"; complete English first and review, then translate item by item and verify.

Risk 4: Examples not runnable on Windows
- Mitigation: Test all examples on Windows PowerShell v5.1 and provide PowerShell-specific commands in `build_run.md` (use semicolons `;`, avoid `&&`).

Risk 5: Auto-generated API tool configuration complexity
- Mitigation: If automation cost is too high, use semi-automation (script to extract public symbols and generate templates) or manually fill in key modules.

## 11. Required Commands and Tools (PowerShell v5.1 Examples)

- Recommended development environment tools: Python 3.9+ (check `setup.py` for current project requirements), pytest, mkdocs/sphinx, markdownlint, typora/VSCode (for proofreading), optional: graphviz (for dependency diagrams).
- Virtual environment (example): If you need to create a local virtual environment, refer to your platform and preferences; documentation examples uniformly use `pip` commands assuming an available Python environment.
- Install development dependencies: `pip install -U pip; pip install -e .[dev]` (or `pip install -e .`)
- Run tests: `py -3 -m pytest -q`
- Run a single example (located at `examples/hello.py`): `py examples\hello.py`
- If using docs tools (mkdocs) to build local preview: `pip install mkdocs mkdocs-material; mkdocs serve` (run in docs root directory)

## 12. Deliverable Submission / Merge Process

- After each phase, submit a separate PR (e.g., `docs/getting-started`, `docs/wiki-injection`, etc.). The PR must include: change description, test/example verification steps, review checklist.
- Before merging, at least one code/architecture reviewer and one documentation proofreader must approve.
- Release a documentation version (tag) and update version links in `README.MD`.

---

If you need to break this plan into specific `docs/` file templates and generate initial placeholder content (English + Chinese placeholders) for each file, proceed to create these template files and specify your preference for API documentation (automation tool vs manual maintenance).
