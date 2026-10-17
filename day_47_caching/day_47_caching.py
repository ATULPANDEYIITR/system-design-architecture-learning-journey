from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import OrderedDict
from hashlib import sha256
from threading import Lock
from time import monotonic, sleep
from typing import Any, Callable, Iterable
import json


class CacheError(Exception):
    """Base exception for cache-related failures."""


class SerializationError(CacheError):
    """Raised when a value cannot be safely serialized."""


class CacheMiss(CacheError):
    """Raised when a required cache entry is unavailable."""


class CacheBackend(str, Enum):
    MEMORY = "memory"
    DISTRIBUTED = "distributed"


@dataclass(frozen=True)
class CacheEntry:
    value: Any
    created_at: float
    expires_at: float | None
    version: int = 1
    tags: frozenset[str] = frozenset()

    def is_expired(self, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        current = monotonic() if now is None else now
        return current >= self.expires_at


@dataclass
class CacheStatistics:
    hits: int = 0
    misses: int = 0
    writes: int = 0
    evictions: int = 0
    expirations: int = 0
    invalidations: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


class LRUCache:
    """
    A bounded in-process cache.

    The LRU policy removes the least recently used entry when capacity is
    exhausted. TTL and LRU solve different problems: TTL controls freshness,
    while LRU controls memory consumption.
    """

    def __init__(self, capacity: int = 128, default_ttl: float | None = 60.0):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if default_ttl is not None and default_ttl <= 0:
            raise ValueError("default_ttl must be positive or None")

        self.capacity = capacity
        self.default_ttl = default_ttl
        self._items: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = Lock()
        self.stats = CacheStatistics()

    def _expiry(self, ttl: float | None) -> float | None:
        effective_ttl = self.default_ttl if ttl is None else ttl
        if effective_ttl is None:
            return None
        if effective_ttl <= 0:
            raise ValueError("TTL must be positive or None")
        return monotonic() + effective_ttl

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._items.get(key)

            if entry is None:
                self.stats.misses += 1
                return None

            if entry.is_expired():
                del self._items[key]
                self.stats.misses += 1
                self.stats.expirations += 1
                return None

            self._items.move_to_end(key)
            self.stats.hits += 1
            return entry.value

    def put(
        self,
        key: str,
        value: Any,
        *,
        ttl: float | None = None,
        tags: Iterable[str] = (),
    ) -> None:
        if not key:
            raise ValueError("cache keys cannot be empty")

        entry = CacheEntry(
            value=value,
            created_at=monotonic(),
            expires_at=self._expiry(ttl),
            tags=frozenset(tags),
        )

        with self._lock:
            if key in self._items:
                del self._items[key]

            self._items[key] = entry
            self.stats.writes += 1

            while len(self._items) > self.capacity:
                self._items.popitem(last=False)
                self.stats.evictions += 1

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._items.pop(key, None) is not None

    def invalidate_tag(self, tag: str) -> int:
        with self._lock:
            keys = [
                key
                for key, entry in self._items.items()
                if tag in entry.tags
            ]

            for key in keys:
                del self._items[key]

            self.stats.invalidations += len(keys)
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "capacity": self.capacity,
                "entries": len(self._items),
                "statistics": {
                    "hits": self.stats.hits,
                    "misses": self.stats.misses,
                    "hit_rate": round(self.stats.hit_rate, 3),
                    "writes": self.stats.writes,
                    "evictions": self.stats.evictions,
                    "expirations": self.stats.expirations,
                    "invalidations": self.stats.invalidations,
                },
            }


@dataclass
class Product:
    product_id: str
    name: str
    price: float
    inventory: int
    version: int = 1


class ProductRepository:
    """Simulates a slower authoritative data source."""

    def __init__(self) -> None:
        self._products = {
            "P100": Product("P100", "Network Router", 129.99, 42),
            "P200": Product("P200", "Security Gateway", 349.50, 17),
            "P300": Product("P300", "Cloud Monitoring Sensor", 89.00, 75),
        }
        self.read_count = 0
        self.write_count = 0

    def find(self, product_id: str) -> Product | None:
        sleep(0.015)
        self.read_count += 1
        product = self._products.get(product_id)
        if product is None:
            return None

        return Product(
            product.product_id,
            product.name,
            product.price,
            product.inventory,
            product.version,
        )

    def update_price(self, product_id: str, new_price: float) -> Product:
        if new_price <= 0:
            raise ValueError("price must be positive")

        product = self._products.get(product_id)
        if product is None:
            raise KeyError(product_id)

        product.price = new_price
        product.version += 1
        self.write_count += 1
        return self.find(product_id)


def demonstrate_basic_caching() -> None:
    print("\n=== Basic cache-aside behavior ===")

    repository = ProductRepository()
    cache = LRUCache(capacity=8, default_ttl=30)

    def get_product(product_id: str) -> Product | None:
        cached = cache.get(product_id)

        if cached is not None:
            print(f"CACHE HIT: {product_id}")
            return cached

        print(f"CACHE MISS: {product_id}; querying authoritative source")
        product = repository.find(product_id)

        if product is not None:
            cache.put(
                product_id,
                product,
                tags={f"product:{product_id}", "catalog"},
            )

        return product

    first = get_product("P100")
    second = get_product("P100")

    print(f"First result:  {first}")
    print(f"Second result: {second}")
    print(f"Repository reads: {repository.read_count}")
    print(f"Cache state: {cache.snapshot()}")

    assert first == second
    assert repository.read_count == 1


def demonstrate_ttl_and_lru() -> None:
    print("\n=== TTL and LRU ===")

    cache = LRUCache(capacity=2, default_ttl=0.15)

    cache.put("session:A", {"user": "alice"})
    cache.put("session:B", {"user": "bob"})

    print("Initial:", cache.snapshot())

    cache.get("session:A")
    cache.put("session:C", {"user": "carol"})

    print("After accessing A and inserting C:", cache.snapshot())
    print("B should have been evicted:", cache.get("session:B"))

    sleep(0.18)
    print("A after TTL expiration:", cache.get("session:A"))
    print("Final:", cache.snapshot())


def demonstrate_cache_invalidation() -> None:
    print("\n=== Invalidation after authoritative data changes ===")

    repository = ProductRepository()
    cache = LRUCache(capacity=8, default_ttl=60)

    def read_product(product_id: str) -> Product | None:
        value = cache.get(product_id)
        if value is not None:
            return value

        value = repository.find(product_id)
        if value:
            cache.put(
                product_id,
                value,
                tags={f"product:{product_id}", "catalog"},
            )
        return value

    before = read_product("P200")
    print("Cached value:", before)

    repository.update_price("P200", 399.00)

    stale = read_product("P200")
    print("Still cached after database update:", stale)

    removed = cache.invalidate_tag("product:P200")
    fresh = read_product("P200")

    print(f"Invalidated entries: {removed}")
    print("Fresh value after invalidation:", fresh)

    assert stale.price != fresh.price


def demonstrate_cache_stampede_protection() -> None:
    """
    A cache stampede occurs when many callers observe the same miss and all
    regenerate the same expensive value simultaneously.

    A production system often uses distributed locks or request coalescing.
    This small implementation demonstrates single-process request coalescing
    with a per-key condition-like lock represented by a shared mutex.
    """

    print("\n=== Cache stampede protection ===")

    cache = LRUCache(capacity=8, default_ttl=30)
    repository = ProductRepository()
    key_lock = Lock()

    def get_expensive_product(product_id: str) -> Product | None:
        value = cache.get(product_id)
        if value is not None:
            return value

        with key_lock:
            # Another request may have filled the cache while this request
            # waited for the regeneration lock.
            value = cache.get(product_id)
            if value is not None:
                return value

            value = repository.find(product_id)
            if value is not None:
                cache.put(product_id, value, tags={f"product:{product_id}"})
            return value

    for _ in range(5):
        get_expensive_product("P300")

    print("Authoritative reads after repeated requests:", repository.read_count)
    print("Cache:", cache.snapshot())

    assert repository.read_count == 1


class VersionedCache:
    """
    Demonstrates a version-aware cache.

    The cached object carries the source version. A caller can reject a cached
    object when it knows that a newer version is required. This is useful when
    correctness is more important than maximum cache-hit rate.
    """

    def __init__(self) -> None:
        self._cache = LRUCache(capacity=64, default_ttl=300)

    def put(self, key: str, value: Product) -> None:
        self._cache.put(key, value)

    def get_if_version_at_least(self, key: str, minimum_version: int) -> Product | None:
        product = self._cache.get(key)
        if product is None:
            return None

        if product.version < minimum_version:
            self._cache.delete(key)
            return None

        return product


def stable_cache_key(
    namespace: str,
    operation: str,
    parameters: dict[str, Any],
) -> str:
    """
    Canonicalized cache keys avoid accidental misses caused by dictionary
    insertion order or inconsistent parameter formatting.
    """

    payload = json.dumps(
        parameters,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    digest = sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"{namespace}:{operation}:{digest}"


def demonstrate_key_design() -> None:
    print("\n=== Deterministic cache-key design ===")

    parameters_a = {"region": "eu-west-1", "limit": 20, "active": True}
    parameters_b = {"active": True, "limit": 20, "region": "eu-west-1"}

    key_a = stable_cache_key("catalog", "search", parameters_a)
    key_b = stable_cache_key("catalog", "search", parameters_b)

    print(key_a)
    print(key_b)
    print("Equivalent parameter sets produce the same key:", key_a == key_b)

    assert key_a == key_b


class SafeCache:
    """
    Adds a lightweight boundary around an application cache.

    Caches should not blindly contain credentials, authorization decisions,
    session secrets, or user-specific data under shared keys. This example
    rejects explicitly sensitive fields before storage.
    """

    FORBIDDEN_FIELDS = frozenset(
        {"password", "password_hash", "access_token", "refresh_token", "private_key"}
    )

    def __init__(self) -> None:
        self._cache = LRUCache(capacity=32, default_ttl=60)

    def put_document(self, key: str, document: dict[str, Any]) -> None:
        sensitive = self.FORBIDDEN_FIELDS.intersection(document)
        if sensitive:
            fields = ", ".join(sorted(sensitive))
            raise ValueError(f"refusing to cache sensitive fields: {fields}")

        self._cache.put(key, document, tags={"document"})

    def get_document(self, key: str) -> dict[str, Any] | None:
        value = self._cache.get(key)
        if value is None:
            return None
        return dict(value)


def demonstrate_security_boundary() -> None:
    print("\n=== Cache security boundary ===")

    cache = SafeCache()
    cache.put_document(
        "profile:42",
        {"user_id": 42, "display_name": "Alice", "department": "Engineering"},
    )

    print("Safe cached profile:", cache.get_document("profile:42"))

    try:
        cache.put_document(
            "profile:42",
            {"user_id": 42, "access_token": "secret-value"},
        )
    except ValueError as exc:
        print("Rejected unsafe cache payload:", exc)


def simulate_cache_benefit() -> None:
    print("\n=== Why caching changes workload ===")

    repository = ProductRepository()
    cache = LRUCache(capacity=16, default_ttl=60)

    def read(product_id: str) -> Product | None:
        cached = cache.get(product_id)
        if cached is not None:
            return cached

        product = repository.find(product_id)
        if product:
            cache.put(product_id, product)
        return product

    requested_ids = [
        "P100",
        "P100",
        "P100",
        "P200",
        "P200",
        "P300",
        "P300",
        "P100",
        "P200",
    ]

    for product_id in requested_ids:
        read(product_id)

    print("Requests:", len(requested_ids))
    print("Authoritative reads:", repository.read_count)
    print("Cache hits:", cache.stats.hits)
    print("Cache misses:", cache.stats.misses)
    print("Hit rate:", f"{cache.stats.hit_rate:.1%}")

    assert repository.read_count < len(requested_ids)


def demonstrate_negative_caching() -> None:
    print("\n=== Negative caching ===")

    cache = LRUCache(capacity=16, default_ttl=10)
    repository = ProductRepository()

    missing_key = "P404"

    # A sentinel distinguishes "cached absence" from an ordinary cache miss.
    NOT_FOUND = object()

    def find_product(product_id: str) -> Product | None:
        cached = cache.get(product_id)

        if cached is NOT_FOUND:
            return None

        if cached is not None:
            return cached

        product = repository.find(product_id)

        if product is None:
            # Negative caching prevents repeated expensive lookups for a
            # genuinely nonexistent object.
            cache.put(product_id, NOT_FOUND, ttl=5, tags={"negative"})
        else:
            cache.put(product_id, product)

        return product

    print(find_product(missing_key))
    print(find_product(missing_key))
    print("Repository reads:", repository.read_count)

    assert repository.read_count == 1


def demonstrate_stale_while_revalidate_model() -> None:
    print("\n=== Stale-while-revalidate decision model ===")

    now = monotonic()

    @dataclass(frozen=True)
    class RefreshableEntry:
        value: str
        fresh_until: float
        stale_until: float

    entry = RefreshableEntry(
        value="catalog-v42",
        fresh_until=now + 0.1,
        stale_until=now + 1.0,
    )

    def classify(entry: RefreshableEntry) -> str:
        current = monotonic()
        if current < entry.fresh_until:
            return "fresh: serve immediately"
        if current < entry.stale_until:
            return "stale-but-servable: serve and refresh asynchronously"
        return "expired: block for regeneration"

    print(classify(entry))
    sleep(0.12)
    print(classify(entry))
    sleep(0.95)
    print(classify(entry))


def run_self_checks() -> None:
    print("\n=== Self-checks ===")

    cache = LRUCache(capacity=2, default_ttl=60)
    cache.put("a", 10)
    cache.put("b", 20)

    assert cache.get("a") == 10
    assert cache.get("missing") is None

    cache.put("c", 30)
    assert cache.get("b") is None
    assert cache.get("c") == 30

    try:
        LRUCache(capacity=0)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid cache capacity was accepted")

    try:
        stable_cache_key("test", "query", {"x": object()})
    except Exception:
        # default=str makes this case serializable rather than failing.
        pass

    print("All self-checks passed.")


def main() -> None:
    print("Caching: why caching, correctness, freshness, performance, and safety")

    demonstrate_basic_caching()
    demonstrate_ttl_and_lru()
    demonstrate_cache_invalidation()
    demonstrate_cache_stampede_protection()
    demonstrate_key_design()
    demonstrate_security_boundary()
    simulate_cache_benefit()
    demonstrate_negative_caching()
    demonstrate_stale_while_revalidate_model()
    run_self_checks()

    print("\n=== Final interpretation ===")
    print(
        "Caching reduces repeated work by serving previously computed or fetched "
        "data from a faster layer. Its benefit is conditional: cached data must "
        "have an acceptable freshness model, keys must identify the correct "
        "request, invalidation must account for mutations, and sensitive data "
        "must not cross security boundaries."
    )


if __name__ == "__main__":
    main()
