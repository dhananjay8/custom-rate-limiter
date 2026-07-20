"""Concurrency tests for rate limiter."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from app.algorithms.fixed_window import FixedWindowAlgorithm
from app.algorithms.sliding_window_log import SlidingWindowLogAlgorithm
from app.algorithms.token_bucket import TokenBucketAlgorithm
from app.repositories.memory_repository import MemoryRepository


class TestConcurrentFixedWindow:
    """Concurrency tests for Fixed Window algorithm."""

    def test_concurrent_requests_respect_limit(self) -> None:
        """Concurrent requests must not exceed the limit."""
        repo = MemoryRepository()
        algo = FixedWindowAlgorithm()
        limit = 10
        num_threads = 20
        results: list[bool] = []
        lock = threading.Lock()

        def make_request() -> None:
            result = algo.allow_request(repo, "client-1", "foo", limit=limit, window=60)
            with lock:
                results.append(result.allowed)

        threads = [threading.Thread(target=make_request) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        allowed_count = sum(1 for r in results if r)
        assert allowed_count == limit

    def test_concurrent_different_clients(self) -> None:
        """Concurrent requests from different clients are independent."""
        repo = MemoryRepository()
        algo = FixedWindowAlgorithm()
        limit = 5
        results: dict[str, list[bool]] = {"client-1": [], "client-2": []}
        lock = threading.Lock()

        def make_request(client_id: str) -> None:
            result = algo.allow_request(repo, client_id, "foo", limit=limit, window=60)
            with lock:
                results[client_id].append(result.allowed)

        threads = []
        for _ in range(10):
            threads.append(threading.Thread(target=make_request, args=("client-1",)))
            threads.append(threading.Thread(target=make_request, args=("client-2",)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sum(1 for r in results["client-1"] if r) == limit
        assert sum(1 for r in results["client-2"] if r) == limit


class TestConcurrentSlidingWindowLog:
    """Concurrency tests for Sliding Window Log algorithm."""

    def test_concurrent_requests_respect_limit(self) -> None:
        """Concurrent requests must not exceed the limit."""
        repo = MemoryRepository()
        algo = SlidingWindowLogAlgorithm()
        limit = 10
        num_threads = 20
        results: list[bool] = []
        lock = threading.Lock()

        def make_request() -> None:
            result = algo.allow_request(repo, "client-1", "bar", limit=limit, window=60)
            with lock:
                results.append(result.allowed)

        threads = [threading.Thread(target=make_request) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        allowed_count = sum(1 for r in results if r)
        assert allowed_count == limit


class TestConcurrentTokenBucket:
    """Concurrency tests for Token Bucket algorithm."""

    def test_concurrent_burst(self) -> None:
        """Concurrent burst must not exceed bucket capacity."""
        repo = MemoryRepository()
        algo = TokenBucketAlgorithm()
        limit = 10
        num_threads = 20
        results: list[bool] = []
        lock = threading.Lock()

        def make_request() -> None:
            result = algo.allow_request(repo, "client-1", "foo", limit=limit, window=60)
            with lock:
                results.append(result.allowed)

        threads = [threading.Thread(target=make_request) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        allowed_count = sum(1 for r in results if r)
        assert allowed_count == limit


class TestConcurrentRepository:
    """Concurrency tests for repository operations."""

    def test_memory_repo_thread_safety(self) -> None:
        """Memory repository handles concurrent increments safely."""
        repo = MemoryRepository()
        num_threads = 100

        def increment() -> None:
            repo.increment_counter("shared:key", ttl=60)

        threads = [threading.Thread(target=increment) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert repo.get_counter("shared:key") == num_threads

    def test_memory_repo_concurrent_timestamps(self) -> None:
        """Memory repository handles concurrent timestamp additions."""
        repo = MemoryRepository()
        num_threads = 50
        base_time = time.time()

        def add_ts(i: int) -> None:
            repo.add_request_timestamp("shared:log", base_time + i)

        threads = [threading.Thread(target=add_ts, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        count = repo.get_request_count("shared:log", base_time - 1)
        assert count == num_threads
