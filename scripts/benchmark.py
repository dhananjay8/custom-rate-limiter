"""Benchmark script for rate limiter performance testing."""

from __future__ import annotations

import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

# Add project root to path
sys.path.insert(0, ".")

from app.config.settings import AlgorithmType, Settings, StorageBackend
from app.factory import create_app


@dataclass
class BenchmarkResult:
    """Results from a benchmark run."""

    total_requests: int = 0
    allowed: int = 0
    rejected: int = 0
    latencies: list[float] = field(default_factory=list)
    errors: int = 0
    duration_seconds: float = 0.0

    @property
    def average_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.mean(self.latencies) * 1000

    @property
    def median_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.median(self.latencies) * 1000

    @property
    def p95_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[idx] * 1000

    @property
    def p99_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[idx] * 1000

    @property
    def requests_per_second(self) -> float:
        if self.duration_seconds == 0:
            return 0.0
        return self.total_requests / self.duration_seconds


def run_benchmark(
    num_requests: int,
    storage: StorageBackend = StorageBackend.MEMORY,
    algorithm: AlgorithmType = AlgorithmType.FIXED_WINDOW,
    concurrency: int = 10,
) -> BenchmarkResult:
    """Run a benchmark with the specified parameters.

    Args:
        num_requests: Total number of requests to make.
        storage: Storage backend to use.
        algorithm: Algorithm to use for /foo.
        concurrency: Number of concurrent workers.

    Returns:
        BenchmarkResult with performance metrics.
    """
    settings = Settings(
        app_env="benchmark",
        rate_limit_storage=storage,
        sqlite_db_path=":memory:",
        foo_algorithm=algorithm,
        bar_algorithm=AlgorithmType.SLIDING_WINDOW_LOG,
        client_basic_foo_limit=1000000,  # High limit to measure throughput
        client_basic_foo_window=60,
        client_basic_bar_limit=1000000,
        client_basic_bar_window=60,
        client_premium_foo_limit=1000000,
        client_premium_foo_window=60,
        client_premium_bar_limit=1000000,
        client_premium_bar_window=60,
    )
    app = create_app(settings=settings)
    app.config["TESTING"] = True
    client = app.test_client()

    result = BenchmarkResult()

    start_time = time.time()

    def make_request() -> tuple[bool, float]:
        req_start = time.time()
        response = client.get("/foo", headers={"Authorization": "Bearer client-basic"})
        latency = time.time() - req_start
        return response.status_code == 200, latency

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(make_request) for _ in range(num_requests)]
        for future in as_completed(futures):
            try:
                allowed, latency = future.result()
                result.total_requests += 1
                result.latencies.append(latency)
                if allowed:
                    result.allowed += 1
                else:
                    result.rejected += 1
            except Exception:
                result.errors += 1

    result.duration_seconds = time.time() - start_time
    return result


def print_results(label: str, result: BenchmarkResult) -> None:
    """Print formatted benchmark results."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Total Requests:      {result.total_requests:,}")
    print(f"  Allowed:             {result.allowed:,}")
    print(f"  Rejected:            {result.rejected:,}")
    print(f"  Errors:              {result.errors:,}")
    print(f"  Duration:            {result.duration_seconds:.2f}s")
    print(f"  Requests/sec:        {result.requests_per_second:,.0f}")
    print(f"  Average Latency:     {result.average_latency_ms:.3f}ms")
    print(f"  Median Latency:      {result.median_latency_ms:.3f}ms")
    print(f"  P95 Latency:         {result.p95_latency_ms:.3f}ms")
    print(f"  P99 Latency:         {result.p99_latency_ms:.3f}ms")
    print(f"{'='*60}")


def main() -> None:
    """Run all benchmarks."""
    print("\n" + "=" * 60)
    print("  RATE LIMITER BENCHMARK SUITE")
    print("=" * 60)

    configs = [
        (100, "Warm-up: 100 requests"),
        (1000, "Standard: 1,000 requests"),
        (5000, "High: 5,000 requests"),
        (10000, "Stress: 10,000 requests"),
    ]

    # Memory + Fixed Window benchmarks
    print("\n\n--- Storage: Memory | Algorithm: Fixed Window ---")
    for num_requests, label in configs:
        result = run_benchmark(
            num_requests=num_requests,
            storage=StorageBackend.MEMORY,
            algorithm=AlgorithmType.FIXED_WINDOW,
        )
        print_results(f"[Memory/FixedWindow] {label}", result)

    # Memory + Token Bucket benchmarks
    print("\n\n--- Storage: Memory | Algorithm: Token Bucket ---")
    for num_requests, label in configs[:3]:
        result = run_benchmark(
            num_requests=num_requests,
            storage=StorageBackend.MEMORY,
            algorithm=AlgorithmType.TOKEN_BUCKET,
        )
        print_results(f"[Memory/TokenBucket] {label}", result)

    # SQLite + Fixed Window benchmarks
    print("\n\n--- Storage: SQLite | Algorithm: Fixed Window ---")
    for num_requests, label in configs[:3]:
        result = run_benchmark(
            num_requests=num_requests,
            storage=StorageBackend.SQLITE,
            algorithm=AlgorithmType.FIXED_WINDOW,
        )
        print_results(f"[SQLite/FixedWindow] {label}", result)

    print("\n\nBenchmark complete!")


if __name__ == "__main__":
    main()
