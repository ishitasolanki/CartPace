"""Memory and latency evidence for the O(1) claim (NFR1, NFR2, AC7).

This is patent evidence, so it measures rather than asserts, and it reports the
commands and numbers needed to reproduce it.

Two claims are under test:

* **Constant memory.** Controller state must not grow with the number of
  patients seen. Measured two ways -- the controller's own declared state, and
  the process's actual traced heap -- because a declared byte count proves
  nothing if the implementation is quietly retaining decisions somewhere else.
* **Bounded per-decision latency.** Microseconds, and flat as the stream grows.

The two are measured in **separate passes**, and the first version of this file
got both wrong in instructive ways:

* Retaining every latency sample to compute percentiles added ~40 bytes per
  decision, which showed up as 4 MB of "controller" growth over 100k decisions.
  The measuring instrument was the leak. Latency is now summarised with
  streaming accumulators and a bounded reservoir.
* Timing while `tracemalloc` is active inflated per-decision latency roughly
  twentyfold -- 528 us against a true 24 us -- because it instruments every
  allocation. Memory and latency therefore never run in the same pass.

Run: python bench/footprint.py
"""

import gc
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.policy import CartPaceController      # noqa: E402
from sim import arrivals, scenarios                   # noqa: E402

CHECKPOINTS = (1_000, 5_000, 10_000, 50_000, 100_000)


def _advance(ctrl, days, on_decision):
    """Feed days through the controller, calling `on_decision` per patient."""
    for day in days:
        ctrl.start_day(day.budget)
        for i in range(day.n):
            on_decision(ctrl, day, i)
        ctrl.end_day(day.n)


def measure_memory():
    """Pass 1: traced heap at checkpoints. No timing here."""
    cfg = scenarios.get("volatile")
    ctrl = CartPaceController(scenarios.N_STRATA, np.random.default_rng(1))
    days = arrivals.make_days(cfg, 700, seed=3)

    gc.collect()
    tracemalloc.start()
    base_declared = ctrl.state_bytes
    _, base_heap = tracemalloc.get_traced_memory()

    rows, seen = [], 0
    targets = list(CHECKPOINTS)
    for day in days:
        ctrl.start_day(day.budget)
        for i in range(day.n):
            ctrl.decide(float(day.scores[i]), int(day.strata[i]),
                        float(day.times[i]))
            seen += 1
            if targets and seen >= targets[0]:
                gc.collect()
                _, heap = tracemalloc.get_traced_memory()
                rows.append({"decisions": seen,
                             "declared": ctrl.state_bytes,
                             "heap_kb": (heap - base_heap) / 1024.0})
                targets.pop(0)
        ctrl.end_day(day.n)
        if not targets:
            break
    tracemalloc.stop()
    return base_declared, rows


def measure_latency():
    """Pass 2: timing, with tracemalloc off.

    Latency is summarised with streaming accumulators plus a bounded reservoir
    for the tail, so the measurement itself allocates nothing per decision.
    """
    cfg = scenarios.get("volatile")
    ctrl = CartPaceController(scenarios.N_STRATA, np.random.default_rng(1))
    days = arrivals.make_days(cfg, 700, seed=3)

    rows, seen = [], 0
    targets = list(CHECKPOINTS)
    RES = 4096
    reservoir = np.zeros(RES)
    n_res = 0
    rng = np.random.default_rng(7)
    total = 0.0

    for day in days:
        ctrl.start_day(day.budget)
        for i in range(day.n):
            t0 = time.perf_counter()
            ctrl.decide(float(day.scores[i]), int(day.strata[i]),
                        float(day.times[i]))
            dt = time.perf_counter() - t0
            total += dt
            seen += 1
            if n_res < RES:                       # reservoir sampling for p99
                reservoir[n_res] = dt
                n_res += 1
            else:
                j = int(rng.integers(0, seen))
                if j < RES:
                    reservoir[j] = dt
            if targets and seen >= targets[0]:
                w = reservoir[:n_res] * 1e6
                rows.append({"decisions": seen,
                             "mean_us": total / seen * 1e6,
                             "p99_us": float(np.percentile(w, 99))})
                targets.pop(0)
        ctrl.end_day(day.n)
        if not targets:
            break
    return rows


def main():
    base, mem = measure_memory()
    lat = measure_latency()
    rows = [{**m, **l} for m, l in zip(mem, lat)]

    print("\nCartPace -- controller footprint and latency")
    print(f"state at start: {base} bytes")
    print("memory and latency measured in separate passes; timing under "
          "tracemalloc is ~20x inflated\n")
    print(f"{'decisions':>10}{'declared B':>13}{'heap KB':>10}"
          f"{'mean us':>10}{'p99 us':>10}")
    print("-" * 53)
    for r in rows:
        print(f"{r['decisions']:>10,}{r['declared']:>13}{r['heap_kb']:>10.1f}"
              f"{r['mean_us']:>10.1f}{r['p99_us']:>10.1f}")

    declared = {r["declared"] for r in rows}
    flat_declared = len(declared) == 1 and declared == {base}
    growth = rows[-1]["heap_kb"] - rows[0]["heap_kb"]
    ratio = rows[-1]["decisions"] / rows[0]["decisions"]
    flat_heap = growth < 64.0

    mean_first, mean_last = rows[0]["mean_us"], rows[-1]["mean_us"]
    flat_latency = mean_last < mean_first * 1.5 and mean_last < 200.0

    print("\n--- claims ---")
    print(f"NFR1 declared state constant              : "
          f"{'PASS' if flat_declared else 'FAIL'}  ({base} bytes throughout)")
    print(f"NFR1 heap flat over a {ratio:.0f}x longer stream : "
          f"{'PASS' if flat_heap else 'FAIL'}  ({growth:+.1f} KB)")
    print(f"NFR2 per-decision latency bounded, in us  : "
          f"{'PASS' if flat_latency else 'FAIL'}  "
          f"({mean_first:.1f} -> {mean_last:.1f} us mean, "
          f"{rows[-1]['p99_us']:.1f} us p99)")

    ok = flat_declared and flat_heap and flat_latency
    print(f"\nAC7: {'PASS' if ok else 'FAIL'}")
    print("\nReproduce: python bench/footprint.py")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
