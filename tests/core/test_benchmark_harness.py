# -*- coding: utf-8 -*-
"""Hold the benchmark harness to doing what a benchmark must do.

A benchmark that always reports the same shape of output is worse than none: it
looks like evidence. These tests check the two things that make the output
meaningful -- that it is produced by running the code, and that the regression
comparison actually distinguishes a regression from a match.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH = REPO_ROOT / "benchmarks" / "bench.py"


def _module():
    spec = importlib.util.spec_from_file_location("bench", BENCH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_harness_exists():
    assert BENCH.is_file(), "no benchmark harness, so there is no performance baseline to compare against"


def test_measure_returns_one_entry_per_benchmark():
    module = _module()
    results = module.measure(
        iterations=200,
        rounds=2,
        benchmarks={"synthetic": lambda n: sum(range(n)) / 1e9},
    )
    assert set(results) == {"synthetic"}
    assert results["synthetic"]["ops_per_second"] > 0
    assert results["synthetic"]["iterations"] == 200


def test_a_match_is_not_reported_as_a_regression():
    module = _module()
    baseline = {"metric": {"ops_per_second": 1000.0}}
    current = {"metric": {"ops_per_second": 950.0}}
    assert module.compare(current, baseline, tolerance=0.5) == []


def test_a_real_regression_is_reported():
    module = _module()
    baseline = {"metric": {"ops_per_second": 1000.0}}
    current = {"metric": {"ops_per_second": 100.0}}
    problems = module.compare(current, baseline, tolerance=0.5)
    assert problems and "metric" in problems[0]


def test_a_disappeared_metric_is_reported():
    module = _module()
    baseline = {"metric": {"ops_per_second": 1000.0}}
    problems = module.compare({}, baseline, tolerance=0.5)
    assert problems, "a renamed or removed benchmark must not pass as a healthy run"


def test_the_committed_baseline_is_well_formed():
    import json

    payload = json.loads((REPO_ROOT / "benchmarks" / "baseline.json").read_text(encoding="utf-8"))
    assert payload.get("environment"), "the baseline does not record the machine it was taken on"
    assert payload.get("metrics"), "the baseline has no metrics"
    for name, values in payload["metrics"].items():
        assert values.get("ops_per_second", 0) > 0, f"{name} has no throughput recorded"
