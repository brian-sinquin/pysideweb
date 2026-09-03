#!/usr/bin/env python3
"""Reproducible microbenchmark baseline for PySideWeb's Python hot paths.

Results are JSON so runs can be compared without scraping formatted text. This
does not benchmark browser rendering or network latency; those stay in the
browser suite and a future transport benchmark respectively.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
import tracemalloc
from pathlib import Path

import pysideweb  # noqa: F401 - install the PySide6 import interceptor first
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from pysideweb import qss, state

ROOT = Path(__file__).resolve().parents[1]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def summary(values: list[float]) -> dict[str, float]:
    return {
        "min": min(values),
        "median": statistics.median(values),
        "p95": percentile(values, 0.95),
        "max": max(values),
    }


def clear_widgets() -> None:
    for root in state.get_roots():
        root.deleteLater()
    state.drain_changes()
    gc.collect()


def widget_tree(count: int) -> tuple[QWidget, float, float, int, int]:
    clear_widgets()
    tracemalloc.start()
    started = time.perf_counter()
    root = QWidget()
    layout = QVBoxLayout(root)
    for index in range(count):
        layout.addWidget(QLabel(f"Row {index}: benchmark payload"))
    root.show()
    constructed = time.perf_counter()
    payload = state.full_tree_json()
    serialized = time.perf_counter()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return root, constructed - started, serialized - constructed, len(payload), peak


def benchmark_trees(sizes: list[int], warmups: int, samples: int) -> list[dict]:
    results = []
    for count in sizes:
        for _ in range(warmups):
            root, *_ = widget_tree(count)
            root.deleteLater()
        construction, serialization, wire_bytes, peak_bytes = [], [], [], []
        for _ in range(samples):
            root, build, encode, size, peak = widget_tree(count)
            construction.append(build)
            serialization.append(encode)
            wire_bytes.append(size)
            peak_bytes.append(peak)
            root.deleteLater()
        results.append({
            "name": "widget_tree",
            "widgets": count,
            "construction_seconds": summary(construction),
            "serialization_seconds": summary(serialization),
            "wire_bytes": summary(wire_bytes),
            "peak_traced_bytes": summary(peak_bytes),
        })
    clear_widgets()
    return results


def time_queue(writes: int, distinct: bool) -> tuple[float, int, int]:
    state.drain_changes()
    started = time.perf_counter()
    for index in range(writes):
        prop = f"prop-{index}" if distinct else "value"
        state.notify_change("benchmark", prop, index)
    elapsed = time.perf_counter() - started
    pending = len(state._change_queue)  # benchmark invariant, not package API
    wire_bytes = len(json.dumps(state.drain_changes(), separators=(",", ":")))
    return elapsed, pending, wire_bytes


def benchmark_queue(samples: int, writes: int) -> list[dict]:
    results = []
    for distinct in (False, True):
        elapsed, pending, wire_bytes = [], [], []
        for _ in range(samples):
            timing, count, size = time_queue(writes, distinct)
            elapsed.append(timing)
            pending.append(count)
            wire_bytes.append(size)
        results.append({
            "name": "change_queue",
            "writes": writes,
            "distinct_properties": distinct,
            "enqueue_seconds": summary(elapsed),
            "pending_entries": summary(pending),
            "wire_bytes": summary(wire_bytes),
        })
    return results


def benchmark_qss(samples: int, iterations: int) -> dict:
    sheet = "QWidget QLabel:hover { color: #123456; padding: 4px; }"
    elapsed = []
    for _ in range(samples):
        started = time.perf_counter()
        for index in range(iterations):
            qss.translate(sheet, f'[data-wid="w{index}"]')
        elapsed.append(time.perf_counter() - started)
    return {
        "name": "qss_translation",
        "iterations": iterations,
        "seconds": summary(elapsed),
    }


def benchmark_timers(count: int) -> dict:
    before = threading.active_count()
    timers = [QTimer() for _ in range(count)]
    for timer in timers:
        timer.start(60_000)
    active = threading.active_count()
    for timer in timers:
        timer.stop()
    return {
        "name": "active_timers",
        "timers": count,
        "threads_before": before,
        "threads_active": active,
    }


def cold_import(samples: int) -> dict:
    code = (
        "import time; s=time.perf_counter(); import pysideweb; "
        "print(time.perf_counter()-s)"
    )
    values = []
    for _ in range(samples):
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, check=True,
            capture_output=True, text=True,
        )
        values.append(float(result.stdout.strip().splitlines()[-1]))
    return {"name": "cold_import", "seconds": summary(values)}


def git_metadata() -> dict[str, object]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False,
        )
        return result.stdout.strip()

    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "dirty": bool(git("status", "--porcelain")),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", type=int, nargs="+", default=[100, 1_000, 10_000])
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--queue-writes", type=int, default=10_000)
    parser.add_argument("--qss-iterations", type=int, default=10_000)
    parser.add_argument("--timers", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.samples < 1 or args.warmups < 0 or any(size < 1 for size in args.sizes):
        parser.error("sizes/samples must be positive and warmups non-negative")

    result = {
        "schema_version": 1,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            **git_metadata(),
        },
        "config": vars(args) | {"output": str(args.output) if args.output else None},
        "benchmarks": [
            cold_import(args.samples),
            *benchmark_trees(args.sizes, args.warmups, args.samples),
            *benchmark_queue(args.samples, args.queue_writes),
            benchmark_qss(args.samples, args.qss_iterations),
            benchmark_timers(args.timers),
        ],
    }
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)


if __name__ == "__main__":
    main()
