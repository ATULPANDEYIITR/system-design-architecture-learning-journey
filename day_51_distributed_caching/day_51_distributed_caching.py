from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from threading import RLock
from time import monotonic, sleep
from typing import Callable, Optional


class CacheBackend(Enum):
    REDIS = "redis"
    MEMCACHED = "memcached"


class CacheError(Exception):
    """Base exception for cache failures."""


class CacheUnavailable(CacheError):
    """Raised when a cache node cannot serve a request."""


@dataclass
class CacheEntry:
    value: object
    expires_at: Optional[float] = None
    version: int = 1

    def expired(self, now: float) -> bool:
        return self.expires_at is not None and now >= self.expires_at


@dataclass
class CacheNode:
    name: str
    backend: CacheBackend
    capacity: int = 100
    healthy: bool = True
    store: dict[str, CacheEntry] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    def get(self, key: str) -> Optional[object]:
        if not self.healthy:
            raise CacheUnavailable(f"{self.name} is unavailable")

        entry = self.store.get(key)
        if entry is None:
            self.misses += 1
            return None

        if entry.expired(monotonic()):
            self.store.pop(key, None)
            self.misses += 1
            return None

        self.hits += 1
        return entry.value

    def set(self, key: str, value: object, ttl: Optional[float] = None) -> None:
        if not self.healthy:
            raise CacheUnavailable(f"{self.name} is unavailable")

        if len(self.store) >= self.capacity and key not in self.store:
            # A small LRU-like approximation keeps this simulation deterministic.
            oldest_key = min(
                self.store,
                key=lambda k: self.store[k].expires_at
                if self.store[k].expires_at is not None
                else float("inf"),
            )
            self.store.pop(oldest_key)

        expires_at = monotonic() + ttl if ttl is not None else None
        previous = self.store.get(key)
        version = previous.version + 1 if previous else 1
        self.store[key] = CacheEntry(value, expires_at, version)

    def delete(self, key: str) -> None:
        if not self.healthy:
            raise CacheUnavailable(f"{self.name} is unavailable")
        self.store.pop(key, None)


class ConsistentHashRing:
    """Maps keys to nodes while minimizing remapping after node changes."""

    def __init__(self, nodes: list[CacheNode], replicas: int = 64):
        if not nodes:
            raise ValueError("At least one cache node is required")
        if replicas < 1:
            raise ValueError("replicas must be positive")

        self.replicas = replicas
        self.nodes: dict[str, CacheNode] = {}
        self.ring: list[tuple[int, str]] = []

        for node in nodes:
            self.add_node(node)

    @staticmethod
    def _hash(value: str) -> int:
        return int.from_bytes(sha256(value.encode()).digest()[:8], "big")

    def _rebuild(self) -> None:
        self.ring = []
        for node_name in self.nodes:
            for replica in range(self.replicas):
                point = self._hash(f"{node_name}:{replica}")
                self.ring.append((point, node_name))
        self.ring.sort()

    def add_node(self, node: CacheNode) -> None:
        self.nodes[node.name] = node
        self._rebuild()

    def remove_node(self, node_name: str) -> None:
        self.nodes.pop(node_name, None)
        if not self.nodes:
            raise ValueError("Cannot remove the final cache node")
        self._rebuild()

    def locate(self, key: str) -> CacheNode:
        if not self.ring:
            raise CacheUnavailable("No cache nodes available")

        point = self._hash(key)

        for ring_point, node_name in self.ring:
            if point <= ring_point:
                return self.nodes[node_name]

        return self.nodes[self.ring[0][1]]


class DistributedCache:
    """
    Cache-aside implementation with consistent hashing.

    The application remains the source of truth. A cache miss calls the
    supplied loader and then populates the selected cache node.
    """

    def __init__(self, nodes: list[CacheNode]):
        self.ring = ConsistentHashRing(nodes)
        self.lock = RLock()

    def get(self, key: str) -> Optional[object]:
        node = self.ring.locate(key)
        try:
            return node.get(key)
        except CacheUnavailable:
            # Cache failure must not automatically become application failure.
            return None

    def get_or_load(
        self,
        key: str,
        loader: Callable[[], object],
        ttl: float = 30.0,
    ) -> object:
        if not key or not key.strip():
            raise ValueError("Cache keys cannot be empty")

        value = self.get(key)
        if value is not None:
            return value

        value = loader()

        if value is None:
            raise ValueError("Loader returned None; negative caching is explicit")

        node = self.ring.locate(key)
        try:
            node.set(key, value, ttl=ttl)
        except CacheUnavailable:
            # The database/application remains authoritative.
            pass

        return value

    def set(self, key: str, value: object, ttl: float = 30.0) -> None:
        if not key:
            raise ValueError("Cache key cannot be empty")
        if ttl <= 0:
            raise ValueError("TTL must be positive")

        self.ring.locate(key).set(key, value, ttl)

    def invalidate(self, key: str) -> None:
        self.ring.locate(key).delete(key)

    def add_node(self, node: CacheNode) -> None:
        with self.lock:
            self.ring.add_node(node)

    def remove_node(self, node_name: str) -> None:
        with self.lock:
            self.ring.remove_node(node_name)

    def statistics(self) -> dict[str, dict[str, int]]:
        return {
            name: {"hits": node.hits, "misses": node.misses}
            for name, node in self.ring.nodes.items()
        }


class Repository:
    """Simulates the authoritative application database."""

    def __init__(self) -> None:
        self.products = {
            "p100": {"id": "p100", "name": "Edge Router", "price": 249.0},
            "p200": {"id": "p200", "name": "Storage Node", "price": 799.0},
        }

    def find_product(self, product_id: str) -> dict:
        sleep(0.02)  # Represents database latency.
        product = self.products.get(product_id)
        if product is None:
            raise KeyError(f"Product {product_id} does not exist")
        return dict(product)

    def update_price(self, product_id: str, price: float) -> None:
        if price < 0:
            raise ValueError("Price cannot be negative")
        if product_id not in self.products:
            raise KeyError(product_id)
        self.products[product_id]["price"] = price


def main() -> None:
    repository = Repository()

    nodes = [
        CacheNode("redis-a", CacheBackend.REDIS, capacity=10),
        CacheNode("redis-b", CacheBackend.REDIS, capacity=10),
        CacheNode("memcached-a", CacheBackend.MEMCACHED, capacity=10),
    ]

    cache = DistributedCache(nodes)

    load_product = lambda: repository.find_product("p100")

    first = cache.get_or_load("product:p100", load_product, ttl=2)
    second = cache.get_or_load("product:p100", load_product, ttl=2)

    print("First request:", first)
    print("Second request:", second)
    print("Statistics:", cache.statistics())

    # Cache invalidation is required after a write to avoid serving stale data.
    repository.update_price("p100", 299.0)
    cache.invalidate("product:p100")

    refreshed = cache.get_or_load(
        "product:p100",
        load_product,
        ttl=2,
    )
    print("After invalidation:", refreshed)

    # A failed cache node should degrade to a cache miss rather than corrupting
    # the authoritative repository.
    selected_node = cache.ring.locate("product:p200")
    selected_node.healthy = False

    fallback = cache.get_or_load(
        "product:p200",
        lambda: repository.find_product("p200"),
        ttl=10,
    )
    print("Failure-tolerant lookup:", fallback)

    selected_node.healthy = True

    # Adding a node changes ownership for only a subset of keys.
    before = {
        f"product:{index}": cache.ring.locate(f"product:{index}").name
        for index in range(20)
    }

    cache.add_node(CacheNode("redis-c", CacheBackend.REDIS, capacity=10))

    after = {
        key: cache.ring.locate(key).name
        for key in before
    }

    moved = sum(before[key] != after[key] for key in before)
    print("Keys remapped after node addition:", moved, "/", len(before))

    # TTL expiration demonstrates automatic freshness control.
    cache.set("temporary:health", {"status": "ok"}, ttl=0.05)
    print("Before TTL expiry:", cache.get("temporary:health"))
    sleep(0.06)
    print("After TTL expiry:", cache.get("temporary:health"))


if __name__ == "__main__":
    main()
