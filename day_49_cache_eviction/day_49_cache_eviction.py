from __future__ import annotations

from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from enum import Enum
import heapq
import time
from typing import Any, Optional


class EvictionPolicy(Enum):
    LRU = "LRU"
    LFU = "LFU"
    FIFO = "FIFO"
    TTL = "TTL"


@dataclass
class CacheEntry:
    key: str
    value: Any
    inserted_at: float
    last_access: float
    expires_at: Optional[float] = None
    frequency: int = 1
    sequence: int = 0

    def expired(self, now: float) -> bool:
        return self.expires_at is not None and now >= self.expires_at


class Cache:
    """Educational in-memory cache implementing four eviction strategies."""

    def __init__(
        self,
        capacity: int,
        policy: EvictionPolicy,
        default_ttl: Optional[float] = None,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if policy is EvictionPolicy.TTL and default_ttl is None:
            raise ValueError("TTL policy requires default_ttl")
        if default_ttl is not None and default_ttl <= 0:
            raise ValueError("default_ttl must be positive")

        self.capacity = capacity
        self.policy = policy
        self.default_ttl = default_ttl
        self._entries: dict[str, CacheEntry] = {}
        self._sequence = 0
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def _now(self) -> float:
        return time.monotonic()

    def _remove_expired(self, now: float) -> None:
        expired_keys = [
            key for key, entry in self._entries.items()
            if entry.expired(now)
        ]
        for key in expired_keys:
            del self._entries[key]
            self.evictions += 1

    def get(self, key: str) -> Optional[Any]:
        now = self._now()
        entry = self._entries.get(key)

        if entry is None or entry.expired(now):
            if entry is not None:
                del self._entries[key]
                self.evictions += 1
            self.misses += 1
            return None

        entry.last_access = now
        entry.frequency += 1
        self.hits += 1
        return entry.value

    def put(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        if not key:
            raise ValueError("cache key cannot be empty")

        now = self._now()
        self._remove_expired(now)

        if ttl is None:
            ttl = self.default_ttl

        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be positive")

        if key in self._entries:
            entry = self._entries[key]
            entry.value = value
            entry.last_access = now
            entry.frequency += 1
            entry.expires_at = now + ttl if ttl is not None else None
            return

        self._sequence += 1
        entry = CacheEntry(
            key=key,
            value=value,
            inserted_at=now,
            last_access=now,
            expires_at=now + ttl if ttl is not None else None,
            sequence=self._sequence,
        )
        self._entries[key] = entry

        if len(self._entries) > self.capacity:
            self._evict_one()

    def _evict_one(self) -> None:
        if not self._entries:
            return

        if self.policy is EvictionPolicy.LRU:
            victim = min(
                self._entries.values(),
                key=lambda e: (e.last_access, e.sequence),
            )
        elif self.policy is EvictionPolicy.LFU:
            # Frequency is primary. Recency breaks ties so an old,
            # equally-frequent item is not arbitrarily selected.
            victim = min(
                self._entries.values(),
                key=lambda e: (e.frequency, e.last_access, e.sequence),
            )
        elif self.policy is EvictionPolicy.FIFO:
            victim = min(
                self._entries.values(),
                key=lambda e: e.sequence,
            )
        elif self.policy is EvictionPolicy.TTL:
            # TTL normally removes entries because they expire. If capacity
            # is reached before expiration, the earliest expiration wins.
            victim = min(
                self._entries.values(),
                key=lambda e: (
                    e.expires_at if e.expires_at is not None else float("inf"),
                    e.sequence,
                ),
            )
        else:
            raise RuntimeError(f"Unsupported policy: {self.policy}")

        del self._entries[victim.key]
        self.evictions += 1

    def delete(self, key: str) -> bool:
        return self._entries.pop(key, None) is not None

    def contains(self, key: str) -> bool:
        return self.get(key) is not None

    def snapshot(self) -> list[dict[str, Any]]:
        now = self._now()
        self._remove_expired(now)
        return [
            {
                "key": entry.key,
                "value": entry.value,
                "frequency": entry.frequency,
                "age_seconds": round(now - entry.inserted_at, 3),
                "ttl_remaining": (
                    round(entry.expires_at - now, 3)
                    if entry.expires_at is not None
                    else None
                ),
            }
            for entry in self._entries.values()
        ]

    def statistics(self) -> dict[str, Any]:
        total = self.hits + self.misses
        return {
            "policy": self.policy.value,
            "capacity": self.capacity,
            "size": len(self._entries),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
            "evictions": self.evictions,
        }


class DeterministicCacheSimulator:
    """Simulation using logical time so eviction behavior can be reproduced."""

    def __init__(self, capacity: int, policy: EvictionPolicy) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self.policy = policy
        self.clock = 0.0
        self.sequence = 0
        self.entries: dict[str, CacheEntry] = {}

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("time cannot move backward")
        self.clock += seconds
        self._expire()

    def _expire(self) -> None:
        expired = [
            key for key, entry in self.entries.items()
            if entry.expired(self.clock)
        ]
        for key in expired:
            del self.entries[key]

    def put(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        self._expire()
        self.sequence += 1
        self.entries[key] = CacheEntry(
            key=key,
            value=value,
            inserted_at=self.clock,
            last_access=self.clock,
            expires_at=self.clock + ttl if ttl else None,
            sequence=self.sequence,
        )

        if len(self.entries) > self.capacity:
            self.evict()

    def get(self, key: str) -> Optional[Any]:
        self._expire()
        entry = self.entries.get(key)
        if entry is None:
            return None
        entry.last_access = self.clock
        entry.frequency += 1
        return entry.value

    def evict(self) -> str:
        self._expire()

        if not self.entries:
            raise RuntimeError("cannot evict from an empty cache")

        if self.policy is EvictionPolicy.LRU:
            victim = min(
                self.entries.values(),
                key=lambda e: (e.last_access, e.sequence),
            )
        elif self.policy is EvictionPolicy.LFU:
            victim = min(
                self.entries.values(),
                key=lambda e: (e.frequency, e.last_access, e.sequence),
            )
        elif self.policy is EvictionPolicy.FIFO:
            victim = min(self.entries.values(), key=lambda e: e.sequence)
        else:
            victim = min(
                self.entries.values(),
                key=lambda e: (
                    e.expires_at if e.expires_at is not None else float("inf"),
                    e.sequence,
                ),
            )

        del self.entries[victim.key]
        return victim.key

    def keys(self) -> list[str]:
        self._expire()
        return list(self.entries)


def demonstrate_policy(policy: EvictionPolicy) -> None:
    cache = DeterministicCacheSimulator(capacity=3, policy=policy)

    cache.put("user:101", "A")
    cache.put("user:102", "B")
    cache.put("user:103", "C")

    # Access patterns distinguish LRU and LFU from insertion order.
    cache.get("user:101")
    cache.get("user:101")
    cache.get("user:102")

    cache.put("user:104", "D")

    print(f"{policy.value}: remaining keys = {cache.keys()}")


def demonstrate_ttl() -> None:
    cache = DeterministicCacheSimulator(capacity=3, policy=EvictionPolicy.TTL)

    cache.put("session:A", "active", ttl=5)
    cache.put("session:B", "active", ttl=10)
    cache.put("session:C", "active", ttl=20)

    cache.advance(6)

    print("TTL after 6 seconds:", cache.keys())
    print("session:A:", cache.get("session:A"))


def compare_policies() -> None:
    print("Eviction policy comparison")
    print("-" * 40)

    for policy in (
        EvictionPolicy.LRU,
        EvictionPolicy.LFU,
        EvictionPolicy.FIFO,
    ):
        demonstrate_policy(policy)

    demonstrate_ttl()


def workload(cache: Cache, requests: list[str]) -> None:
    """Simulate a read-heavy application cache."""
    for key in requests:
        value = cache.get(key)
        if value is None:
            # In production this branch would call the authoritative data
            # source. The example uses a deterministic computed value.
            value = f"database-value-for-{key}"
            cache.put(key, value)


def benchmark_policies() -> None:
    requests = (
        ["product:1"] * 20
        + ["product:2"] * 15
        + ["product:3"] * 10
        + ["product:4"] * 5
        + ["product:5"] * 3
        + ["product:6"] * 2
    )

    for policy in (
        EvictionPolicy.LRU,
        EvictionPolicy.LFU,
        EvictionPolicy.FIFO,
    ):
        cache = Cache(capacity=3, policy=policy)
        workload(cache, requests)
        print(cache.statistics())


def demonstrate_edge_cases() -> None:
    print("\nEdge-case validation")

    try:
        Cache(capacity=0, policy=EvictionPolicy.LRU)
    except ValueError as exc:
        print("Invalid capacity:", exc)

    try:
        Cache(capacity=2, policy=EvictionPolicy.TTL)
    except ValueError as exc:
        print("Missing TTL:", exc)

    try:
        cache = Cache(2, EvictionPolicy.LRU)
        cache.put("", "invalid")
    except ValueError as exc:
        print("Invalid key:", exc)

    cache = Cache(2, EvictionPolicy.LRU)
    cache.put("x", 10)
    cache.put("y", 20)
    cache.delete("x")
    print("After explicit deletion:", cache.snapshot())


def production_considerations() -> None:
    """Keep design concerns executable as a compact configuration check."""
    configuration = {
        "bounded_capacity": True,
        "expiration_policy": "TTL",
        "clock": "monotonic",
        "cache_values_sensitive": False,
        "authoritative_store_exists": True,
        "stampede_protection": "required for high-concurrency workloads",
    }

    if not configuration["bounded_capacity"]:
        raise RuntimeError("Unbounded caches can exhaust process memory")

    print("\nProduction configuration:")
    for key, value in configuration.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    compare_policies()
    print("\nRead-heavy workload:")
    benchmark_policies()
    demonstrate_edge_cases()
    production_considerations()
