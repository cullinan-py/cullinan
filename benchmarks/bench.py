#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Measure the framework's own overhead, on this machine, reproducibly.

What this answers: *did a change make the framework slower?* It deliberately
does not answer "how many requests per second will my service handle" -- that
depends on the handler, the network and the deployment, none of which are here.
So the benchmark drives the framework's own path (router, dispatcher, response
rendering) with a trivial handler and reports throughput for that path alone.

Reproducibility rules, because a benchmark nobody can repeat is a rumour:

* no network, no server, no threads -- one process, one event loop;
* a warm-up pass before each measurement, so import and first-call costs do not
  land in the number;
* the reported value is the **best** of several rounds, not the mean: the best
  round is the one least disturbed by whatever else the machine was doing, and
  it is the only statistic that is stable across machines;
* the environment is recorded with the numbers, so a comparison between two
  different machines is visibly a comparison between two different machines.

Usage::

    python benchmarks/bench.py                          # print a report
    python benchmarks/bench.py --out benchmarks/baseline.json
    python benchmarks/bench.py --check benchmarks/baseline.json
    python benchmarks/bench.py --check benchmarks/baseline.json --tolerance 0.5

``--check`` exits non-zero when a metric is more than ``--tolerance`` (a
fraction, default 0.5) slower than the baseline. It is a **regression** alarm,
not a performance target: crossing it means "look at what changed", not "the
build is broken because the number moved".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence

# Importing from the repository root keeps this runnable without installing,
# which matters because the point is to measure the working tree you are on.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cullinan.web.gateway import Dispatcher, Router, WebRequest  # noqa: E402


def _build_dispatcher() -> Dispatcher:
    router = Router()
    router.add_route("GET", "/health", handler=lambda: {"status": "ok"})
    router.add_route("GET", "/users/{user_id}", handler=lambda user_id: {"id": user_id})
    return Dispatcher(router=router)


def bench_router_static(iterations: int) -> float:
    router = Router()
    router.add_route("GET", "/health", handler=lambda: None)
    match = router.match
    start = time.perf_counter()
    for _ in range(iterations):
        match("GET", "/health")
    return time.perf_counter() - start


def bench_router_param(iterations: int) -> float:
    router = Router()
    router.add_route("GET", "/users/{user_id}", handler=lambda user_id: None)
    match = router.match
    start = time.perf_counter()
    for _ in range(iterations):
        match("GET", "/users/42")
    return time.perf_counter() - start


def bench_dispatch_json(iterations: int) -> float:
    dispatcher = _build_dispatcher()
    request = WebRequest(method="GET", path="/health")
    dispatch = dispatcher.dispatch

    async def run() -> None:
        for _ in range(iterations):
            await dispatch(request)

    start = time.perf_counter()
    asyncio.run(run())
    return time.perf_counter() - start


def bench_dispatch_param(iterations: int) -> float:
    dispatcher = _build_dispatcher()
    request = WebRequest(method="GET", path="/users/42")
    dispatch = dispatcher.dispatch

    async def run() -> None:
        for _ in range(iterations):
            await dispatch(request)

    start = time.perf_counter()
    asyncio.run(run())
    return time.perf_counter() - start


def bench_dispatch_miss(iterations: int) -> float:
    dispatcher = _build_dispatcher()
    request = WebRequest(method="GET", path="/no-such-route")
    dispatch = dispatcher.dispatch

    async def run() -> None:
        for _ in range(iterations):
            await dispatch(request)

    start = time.perf_counter()
    asyncio.run(run())
    return time.perf_counter() - start


BENCHMARKS: Dict[str, Callable[[int], float]] = {
    "router_match_static": bench_router_static,
    "router_match_param": bench_router_param,
    "dispatch_json": bench_dispatch_json,
    "dispatch_param": bench_dispatch_param,
    "dispatch_miss": bench_dispatch_miss,
}


def environment() -> Dict[str, str]:
    from cullinan._version import __version__

    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cullinan": __version__,
    }


def measure(
    *,
    iterations: int = 5000,
    rounds: int = 5,
    benchmarks: Optional[Mapping[str, Callable[[int], float]]] = None,
) -> Dict[str, Dict[str, float]]:
    """Return ``{metric: {"ops_per_second": ..., "rounds": ..., "iterations": ...}}``."""
    selected = dict(benchmarks or BENCHMARKS)
    results: Dict[str, Dict[str, float]] = {}
    for name, function in selected.items():
        # Warm-up: a cold first round measures the import graph and the
        # allocator, not the code path.
        function(max(1, iterations // 10))
        best = min(function(iterations) for _ in range(rounds))
        results[name] = {
            "ops_per_second": round(iterations / best, 1) if best > 0 else 0.0,
            "seconds": round(best, 6),
            "rounds": rounds,
            "iterations": iterations,
        }
    return results


def compare(
    current: Mapping[str, Mapping[str, float]],
    baseline: Mapping[str, Mapping[str, float]],
    tolerance: float = 0.5,
) -> List[str]:
    """Return the regressions: metrics that fell more than ``tolerance`` below baseline.

    Only metrics present in **both** runs are compared: a newly added benchmark
    has no baseline to regress against, and a renamed one must not be reported
    as a 100% regression of the old name.
    """
    regressions: List[str] = []
    for name, base in baseline.items():
        if name not in current:
            regressions.append(f"{name}: measured in the baseline but absent now (renamed or removed?)")
            continue
        base_rate = float(base.get("ops_per_second", 0.0))
        now_rate = float(current[name].get("ops_per_second", 0.0))
        if base_rate <= 0:
            continue
        allowed = base_rate * (1.0 - tolerance)
        if now_rate < allowed:
            drop = (base_rate - now_rate) / base_rate * 100.0
            regressions.append(
                f"{name}: {now_rate:,.0f} op/s vs baseline {base_rate:,.0f} op/s ({drop:.0f}% slower, "
                f"tolerance {tolerance:.0%})"
            )
    return regressions


def _report(results: Mapping[str, Mapping[str, float]], env: Mapping[str, str]) -> None:
    print(f"python {env['python']} ({env['implementation']}) on {env['platform']}, cullinan {env['cullinan']}")
    print()
    print(f"{'metric':<22}{'ops/second':>14}{'seconds/round':>16}")
    for name, values in results.items():
        print(f"{name:<22}{values['ops_per_second']:>14,.0f}{values['seconds']:>16.4f}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--out", default=None, help="write the result as JSON to this path")
    parser.add_argument("--check", default=None, help="compare against this baseline JSON")
    parser.add_argument("--tolerance", type=float, default=0.5, help="allowed slowdown fraction (default 0.5)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    env = environment()
    results = measure(iterations=args.iterations, rounds=args.rounds)

    if not args.quiet:
        _report(results, env)

    if args.out:
        payload = {"environment": env, "metrics": results}
        Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        if not args.quiet:
            print(f"\nwrote {args.out}")

    if args.check:
        baseline_path = Path(args.check)
        if not baseline_path.is_file():
            print(f"BENCHMARK CHECK FAIL: no baseline at {baseline_path}")
            return 1
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        regressions = compare(results, baseline.get("metrics", {}), tolerance=args.tolerance)
        if regressions:
            print("BENCHMARK CHECK FAIL")
            for line in regressions:
                print(f"  - {line}")
            base_env = baseline.get("environment", {})
            if base_env.get("platform") != env["platform"]:
                print(f"  note: baseline was recorded on {base_env.get('platform')!r}, "
                      f"this run on {env['platform']!r} -- compare like with like")
            return 1
        print(f"BENCHMARK CHECK PASS -- no metric more than {args.tolerance:.0%} below baseline")

    return 0


if __name__ == "__main__":
    sys.exit(main())
