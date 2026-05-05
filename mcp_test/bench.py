from __future__ import annotations

import concurrent.futures
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .client import make_client


@dataclass(frozen=True)
class MethodLatency:
    method: str
    count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float


@dataclass(frozen=True)
class BenchResult:
    duration_s: float
    concurrency: int
    latencies: tuple[MethodLatency, ...]
    failures: tuple[str, ...] = ()
    fd_delta: int | None = None

    def to_json(self) -> dict:
        return {
            "duration_s": self.duration_s,
            "concurrency": self.concurrency,
            "fd_delta": self.fd_delta,
            "failures": list(self.failures),
            "latencies": [latency.__dict__ for latency in self.latencies],
        }


def run_bench(
    command: str,
    *,
    duration_s: float = 10.0,
    concurrency: int = 4,
    timeout: float = 10.0,
    operation: Callable | None = None,
) -> BenchResult:
    deadline = time.monotonic() + duration_s
    failures: list[str] = []
    samples: dict[str, list[float]] = {"ping": []}
    fd_before = _fd_count()

    def worker() -> None:
        try:
            with make_client(command, timeout=timeout) as client:
                while time.monotonic() < deadline:
                    start = time.perf_counter()
                    if operation:
                        operation(client)
                        method = getattr(operation, "__name__", "custom")
                    else:
                        client.ping()
                        method = "ping"
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    samples.setdefault(method, []).append(elapsed_ms)
        except Exception as exc:  # bench is best-effort; surface failures in the report
            failures.append(f"{type(exc).__name__}: {exc}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(worker) for _ in range(concurrency)]
        concurrent.futures.wait(futures)

    fd_after = _fd_count()
    return BenchResult(
        duration_s=duration_s,
        concurrency=concurrency,
        latencies=tuple(_summarize_method(method, values) for method, values in samples.items() if values),
        failures=tuple(failures),
        fd_delta=None if fd_before is None or fd_after is None else fd_after - fd_before,
    )


def compare_to_baseline(
    result: BenchResult,
    baseline_path: str | Path,
    *,
    max_p95_regression: float = 1.25,
) -> list[str]:
    """Return human-readable regression strings vs a saved baseline JSON.

    Raises FileNotFoundError if the baseline file is missing — callers usually
    want to know that explicitly rather than treat it as zero regressions.
    """

    baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    previous = {item["method"]: item for item in baseline.get("latencies", [])}
    failures: list[str] = []
    for item in result.latencies:
        old = previous.get(item.method)
        if not old:
            continue
        allowed = float(old["p95_ms"]) * max_p95_regression
        if item.p95_ms > allowed:
            failures.append(
                f"{item.method} p95 regressed from {old['p95_ms']:.2f}ms to {item.p95_ms:.2f}ms"
            )
    return failures


def _summarize_method(method: str, values: list[float]) -> MethodLatency:
    ordered = sorted(values)
    return MethodLatency(
        method=method,
        count=len(ordered),
        p50_ms=_percentile(ordered, 50),
        p95_ms=_percentile(ordered, 95),
        p99_ms=_percentile(ordered, 99),
    )


def _percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 2)
    index = int(round((pct / 100) * (len(values) - 1)))
    return round(values[index], 2)


def _fd_count() -> int | None:
    fd_dir = Path("/proc/self/fd")
    if fd_dir.exists():
        return len(list(fd_dir.iterdir()))
    try:
        return len(os.listdir("/dev/fd"))
    except OSError:
        return None
