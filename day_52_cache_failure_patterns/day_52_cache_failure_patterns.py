#!/usr/bin/env python3
"""
Cache Failure Patterns
Models and simulates three failure modes:

- Cache stampede: many requests miss the same hot key simultaneously.
- Cache penetration: requests repeatedly target data that does not exist.
- Cache avalanche: many cached entries expire or become unavailable together.

The implementation uses only the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from time import monotonic
from typing import Callable, Optional
import random
import statistics


class FailurePattern(Enum):
    STAMPEDE = "stampede"
    PENETRATION = "penetration"
    AVALANCHE = "avalanche"


@dataclass
class CacheEntry:
    value: object
    expires_at: float


@dataclass
class CacheMetrics:
    hits: int = 0
    misses: int = 0
    backend_reads: int = 0
    negative_hits: int = 0
    rejected_penetration: int = 0
    singleflight_waiters: int = 0
    refreshes: int = 0
    failures: int = 0

    @property
    def total_requests(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests


class SafeCache:
    """
    Thread-safe cache with:

    1. Positive TTLs for normal objects.
    2. Negative caching for known-missing objects.
    3. Per-key single-flight locking to prevent stampedes.
    4. TTL jitter to spread expiration times.
    5. Optional stale-while-revalidate behavior.
    """

    def __init__(
        self,
        loader: Callable[[str], Optional[object]],
        *,
        default_ttl: float = 10.0,
        negative_ttl: float = 3.0,
        jitter_ratio: float = 0.10,
        stale_grace: float = 2.0,
        penetration_filter: Optional[set[str]] = None,
    ) -> None:
        if default_ttl <= 0:
            raise ValueError("default_ttl must be positive")
        if negative_ttl <= 0:
            raise ValueError("negative_ttl must be positive")
        if not 0 <= jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")
        if stale_grace < 0:
            raise ValueError("stale_grace cannot be negative")

        self.loader = loader
        self.default_ttl = default_ttl
        self.negative_ttl = negative_ttl
        self.jitter_ratio = jitter_ratio
        self.stale_grace = stale_grace
        self.penetration_filter = penetration_filter or set()

        self._entries: dict[str, CacheEntry] = {}
        self._locks: dict[str, Lock] = {}
        self._global_lock = Lock()
        self.metrics = CacheMetrics()

    def _key_lock(self, key: str) -> Lock:
        with self._global_lock:
            return self._locks.setdefault(key, Lock())

    def _ttl(self, base: float) -> float:
        # Randomized TTL reduces synchronized expiration.
        delta = base * self.jitter_ratio
        return max(0.001, base + random.uniform(-delta, delta))

    def _lookup(self, key: str) -> tuple[Optional[CacheEntry], bool]:
        entry = self._entries.get(key)
        if entry is None:
            return None, False

        now = monotonic()
        fresh = entry.expires_at > now
        stale = entry.expires_at + self.stale_grace > now
        return entry, fresh or stale

    def get(self, key: str) -> Optional[object]:
        if not key:
            raise ValueError("cache key cannot be empty")

        # A small allowlist/filter can reject obviously invalid IDs before
        # they reach the backend, protecting against cache penetration.
        if self.penetration_filter and key not in self.penetration_filter:
            self.metrics.rejected_penetration += 1
            return None

        entry = self._entries.get(key)
        now = monotonic()

        if entry and entry.expires_at > now:
            self.metrics.hits += 1
            if entry.value is None:
                self.metrics.negative_hits += 1
            return entry.value

        self.metrics.misses += 1

        lock = self._key_lock(key)
        acquired = lock.acquire(blocking=False)

        if not acquired:
            self.metrics.singleflight_waiters += 1
            with lock:
                entry = self._entries.get(key)
                if entry and entry.expires_at > monotonic():
                    self.metrics.hits += 1
                    if entry.value is None:
                        self.metrics.negative_hits += 1
                    return entry.value
                # Another loader failed. Do not recursively retry forever.
                return None

        try:
            # Double-check after acquiring the per-key lock.
            entry = self._entries.get(key)
            if entry and entry.expires_at > monotonic():
                self.metrics.hits += 1
                if entry.value is None:
                    self.metrics.negative_hits += 1
                return entry.value

            self.metrics.backend_reads += 1
            value = self.loader(key)

            ttl = self.negative_ttl if value is None else self.default_ttl
            self._entries[key] = CacheEntry(
                value=value,
                expires_at=monotonic() + self._ttl(ttl),
            )
            self.metrics.refreshes += 1
            return value
        except Exception:
            self.metrics.failures += 1
            raise
        finally:
            lock.release()

    def get_stale_while_revalidate(self, key: str) -> Optional[object]:
        """
        Return a stale value during a short grace period.

        A production implementation would enqueue the refresh rather than
        performing it in the caller. This demonstration keeps refresh
        behavior synchronous so it remains self-contained.
        """
        entry = self._entries.get(key)
        if entry is not None:
            now = monotonic()
            if entry.expires_at + self.stale_grace > now:
                if entry.expires_at <= now:
                    self.metrics.hits += 1
                    return entry.value
        return self.get(key)

    def invalidate(self, key: str) -> None:
        self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()

    def snapshot(self) -> dict[str, int | float]:
        return {
            "hits": self.metrics.hits,
            "misses": self.metrics.misses,
            "backend_reads": self.metrics.backend_reads,
            "negative_hits": self.metrics.negative_hits,
            "rejected_penetration": self.metrics.rejected_penetration,
            "singleflight_waiters": self.metrics.singleflight_waiters,
            "refreshes": self.metrics.refreshes,
            "failures": self.metrics.failures,
            "hit_rate": round(self.metrics.hit_rate, 4),
        }


@dataclass
class Backend:
    records: dict[str, dict[str, object]] = field(default_factory=dict)
    reads: int = 0

    def read(self, key: str) -> Optional[dict[str, object]]:
        self.reads += 1
        return self.records.get(key)


def demonstrate_penetration() -> None:
    backend = Backend(
        records={
            "product:100": {"name": "Keyboard", "price": 49.0},
        }
    )

    cache = SafeCache(
        backend.read,
        default_ttl=10,
        negative_ttl=5,
        penetration_filter={
            "product:100",
            "product:404",
            "product:405",
        },
    )

    # The first missing request reaches the backend and stores a negative
    # cache entry. Repeated requests are then absorbed by the cache.
    for _ in range(20):
        cache.get("product:404")

    # An obviously invalid key is rejected before backend access.
    for _ in range(20):
        cache.get("product:does-not-exist")

    print("PENETRATION")
    print("backend reads:", backend.reads)
    print("metrics:", cache.snapshot())
    print()


def demonstrate_stampede() -> None:
    import threading

    backend_reads = 0
    backend_lock = Lock()

    def slow_backend(key: str) -> dict[str, object]:
        nonlocal backend_reads
        import time

        with backend_lock:
            backend_reads += 1
        time.sleep(0.03)
        return {"key": key, "payload": "hot object"}

    cache = SafeCache(
        slow_backend,
        default_ttl=0.05,
        jitter_ratio=0,
    )

    # Prime then force expiry.
    cache.get("hot:1")

    import time
    time.sleep(0.06)

    results: list[object] = []
    result_lock = Lock()

    def worker() -> None:
        value = cache.get("hot:1")
        with result_lock:
            results.append(value)

    threads = [threading.Thread(target=worker) for _ in range(30)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    print("STAMPEDE")
    print("concurrent callers:", len(results))
    print("backend reads:", backend_reads)
    print("single-flight waiters:", cache.metrics.singleflight_waiters)
    print("metrics:", cache.snapshot())
    print()


def demonstrate_avalanche() -> None:
    backend = Backend(
        records={
            f"item:{index}": {"id": index}
            for index in range(100)
        }
    )

    # Without jitter, synchronized TTLs make expiration highly correlated.
    synchronized = SafeCache(
        backend.read,
        default_ttl=1,
        jitter_ratio=0,
    )

    # Jitter changes individual expiration points.
    distributed = SafeCache(
        backend.read,
        default_ttl=1,
        jitter_ratio=0.25,
    )

    for index in range(100):
        synchronized.get(f"item:{index}")
        distributed.get(f"item:{index}")

    # We cannot wait for the TTL in a deterministic example. Instead, compare
    # generated expiration offsets by sampling the cache's internal entries.
    sync_offsets = [
        entry.expires_at
        for entry in synchronized._entries.values()
    ]
    distributed_offsets = [
        entry.expires_at
        for entry in distributed._entries.values()
    ]

    print("AVALANCHE")
    print(
        "synchronized expiration spread:",
        round(max(sync_offsets) - min(sync_offsets), 6),
    )
    print(
        "jittered expiration spread:",
        round(max(distributed_offsets) - min(distributed_offsets), 6),
    )
    print()


def demonstrate_hot_key_load() -> None:
    backend = Backend(
        records={
            "config:homepage": {
                "version": 42,
                "feature_flags": ["search", "checkout"],
            }
        }
    )

    cache = SafeCache(
        backend.read,
        default_ttl=30,
        jitter_ratio=0.15,
        stale_grace=5,
    )

    latencies: list[float] = []

    for _ in range(1000):
        start = monotonic()
        cache.get("config:homepage")
        latencies.append(monotonic() - start)

    print("HOT KEY")
    print("backend reads:", backend.reads)
    print("requests:", len(latencies))
    print("median cache lookup:", f"{statistics.median(latencies) * 1_000:.3f} ms")
    print("p95 cache lookup:", f"{sorted(latencies)[949] * 1_000:.3f} ms")
    print()


if __name__ == "__main__":
    demonstrate_penetration()
    demonstrate_stampede()
    demonstrate_avalanche()
    demonstrate_hot_key_load()
