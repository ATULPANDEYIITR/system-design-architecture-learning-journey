from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Generic, List, Optional, Protocol, TypeVar
import json
import os
import tempfile
import time


K = TypeVar("K")
V = TypeVar("V")


class CacheError(Exception):
    """Base exception for cache-specific failures."""


class CacheMiss(CacheError):
    """Raised when a required cached value does not exist."""


class CacheBackend(Protocol[K, V]):
    def get(self, key: K) -> Optional[V]:
        ...

    def put(self, key: K, value: V, ttl_seconds: Optional[float] = None) -> None:
        ...

    def delete(self, key: K) -> None:
        ...


@dataclass
class CacheEntry(Generic[V]):
    value: V
    expires_at: Optional[float] = None

    def is_expired(self, now: Optional[float] = None) -> bool:
        if self.expires_at is None:
            return False
        return (time.monotonic() if now is None else now) >= self.expires_at


class InMemoryCache(Generic[K, V]):
    """
    Small TTL-aware cache used to make the three strategies executable
    without requiring Redis or another external service.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._entries: Dict[K, CacheEntry[V]] = {}
        self.hits = 0
        self.misses = 0
        self.writes = 0

    def get(self, key: K) -> Optional[V]:
        entry = self._entries.get(key)

        if entry is None:
            self.misses += 1
            return None

        if entry.is_expired():
            del self._entries[key]
            self.misses += 1
            return None

        self.hits += 1
        return entry.value

    def put(
        self,
        key: K,
        value: V,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        expires_at = (
            None
            if ttl_seconds is None
            else time.monotonic() + ttl_seconds
        )
        self._entries[key] = CacheEntry(value, expires_at)
        self.writes += 1

    def delete(self, key: K) -> None:
        self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()

    def contains(self, key: K) -> bool:
        return self.get(key) is not None

    def stats(self) -> Dict[str, int]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "writes": self.writes,
        }


@dataclass
class Product:
    product_id: int
    name: str
    price: float
    stock: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "price": self.price,
            "stock": self.stock,
        }


class ProductRepository:
    """
    Represents the source of truth.

    A real implementation could be PostgreSQL, MySQL, DynamoDB, or another
    persistent store. The cache must never be treated as the authoritative
    database in these examples.
    """

    def __init__(self) -> None:
        self._products: Dict[int, Product] = {
            101: Product(101, "Mechanical Keyboard", 89.99, 42),
            102: Product(102, "USB-C Dock", 129.50, 17),
            103: Product(103, "Noise-Cancelling Headphones", 199.00, 9),
        }
        self.reads = 0
        self.writes = 0

    def get(self, product_id: int) -> Optional[Product]:
        self.reads += 1
        product = self._products.get(product_id)

        if product is None:
            return None

        return Product(
            product.product_id,
            product.name,
            product.price,
            product.stock,
        )

    def save(self, product: Product) -> None:
        if product.price < 0:
            raise ValueError("Product price cannot be negative")

        if product.stock < 0:
            raise ValueError("Product stock cannot be negative")

        self._products[product.product_id] = Product(
            product.product_id,
            product.name,
            product.price,
            product.stock,
        )
        self.writes += 1


class CacheStrategy(Protocol[K, V]):
    def get(self, key: K) -> Optional[V]:
        ...

    def put(self, key: K, value: V) -> None:
        ...


class CacheAside(Generic[K, V]):
    """
    Cache-aside keeps cache population in application code.

    Reads:
        application -> cache
        cache miss -> source -> cache

    Writes:
        application -> source
        application invalidates or refreshes cache
    """

    def __init__(
        self,
        cache: InMemoryCache[K, V],
        loader: Callable[[K], Optional[V]],
        saver: Callable[[K, V], None],
        ttl_seconds: float = 60.0,
    ) -> None:
        self.cache = cache
        self.loader = loader
        self.saver = saver
        self.ttl_seconds = ttl_seconds

    def get(self, key: K) -> Optional[V]:
        cached = self.cache.get(key)

        if cached is not None:
            return cached

        value = self.loader(key)

        if value is not None:
            self.cache.put(key, value, self.ttl_seconds)

        return value

    def put(self, key: K, value: V) -> None:
        self.saver(key, value)

        # Invalidation avoids leaving an old object in the cache after a
        # successful database write. A subsequent read repopulates it.
        self.cache.delete(key)


class ReadThrough(Generic[K, V]):
    """
    Read-through moves cache-miss loading into the cache abstraction.

    Application code asks the cache for a value. The cache itself invokes
    the loader when the requested value is absent.
    """

    def __init__(
        self,
        cache: InMemoryCache[K, V],
        loader: Callable[[K], Optional[V]],
        ttl_seconds: float = 60.0,
    ) -> None:
        self.cache = cache
        self.loader = loader
        self.ttl_seconds = ttl_seconds

    def get(self, key: K) -> Optional[V]:
        cached = self.cache.get(key)

        if cached is not None:
            return cached

        value = self.loader(key)

        if value is not None:
            self.cache.put(key, value, self.ttl_seconds)

        return value

    def put(self, key: K, value: V) -> None:
        self.cache.put(key, value, self.ttl_seconds)


class WriteThrough(Generic[K, V]):
    """
    Write-through writes the source of truth and cache as one application
    operation. The source write happens before the cache is updated so a
    failed source write cannot make the cache appear newer than the database.
    """

    def __init__(
        self,
        cache: InMemoryCache[K, V],
        saver: Callable[[K, V], None],
        ttl_seconds: float = 60.0,
    ) -> None:
        self.cache = cache
        self.saver = saver
        self.ttl_seconds = ttl_seconds

    def get(self, key: K) -> Optional[V]:
        return self.cache.get(key)

    def put(self, key: K, value: V) -> None:
        self.saver(key, value)
        self.cache.put(key, value, self.ttl_seconds)


class JsonFileCache(Generic[K, V]):
    """
    A simple persistent cache illustrates that cache entries may survive
    process restarts, while still requiring TTL and invalidation behavior.
    """

    def __init__(self, path: str) -> None:
        self.path = path

    def _read(self) -> Dict[str, object]:
        if not os.path.exists(self.path):
            return {}

        with open(self.path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def get(self, key: K) -> Optional[V]:
        data = self._read()
        entry = data.get(str(key))

        if not isinstance(entry, dict):
            return None

        expires_at = entry.get("expires_at")
        if expires_at is not None and time.time() >= float(expires_at):
            data.pop(str(key), None)
            self._write(data)
            return None

        return entry.get("value")  # type: ignore[return-value]

    def put(
        self,
        key: K,
        value: V,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        data = self._read()
        expires_at = (
            None
            if ttl_seconds is None
            else time.time() + ttl_seconds
        )
        data[str(key)] = {
            "value": value,
            "expires_at": expires_at,
        }
        self._write(data)

    def delete(self, key: K) -> None:
        data = self._read()
        data.pop(str(key), None)
        self._write(data)

    def _write(self, data: Dict[str, object]) -> None:
        directory = os.path.dirname(self.path)

        if directory:
            os.makedirs(directory, exist_ok=True)

        temporary = f"{self.path}.tmp"

        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

        os.replace(temporary, self.path)


class InstrumentedRepository:
    """
    Decorates a repository to make source-store access visible during
    strategy comparisons.
    """

    def __init__(self, repository: ProductRepository) -> None:
        self.repository = repository

    def get(self, product_id: int) -> Optional[Product]:
        return self.repository.get(product_id)

    def save(self, product_id: int, product: Product) -> None:
        if product_id != product.product_id:
            raise ValueError("Repository key and product ID must match")
        self.repository.save(product)


def print_product(label: str, product: Optional[Product]) -> None:
    if product is None:
        print(f"{label}: NOT FOUND")
    else:
        print(f"{label}: {product.to_dict()}")


def demonstrate_cache_aside() -> None:
    print("\n=== Cache-aside ===")

    repository = ProductRepository()
    cache: InMemoryCache[int, Product] = InMemoryCache("product-cache")

    strategy = CacheAside(
        cache=cache,
        loader=repository.get,
        saver=repository.save,
        ttl_seconds=30,
    )

    print_product("First read", strategy.get(101))
    print_product("Second read", strategy.get(101))

    updated = Product(101, "Mechanical Keyboard", 94.99, 40)
    strategy.put(101, updated)

    # The invalidated value is fetched again from the source.
    print_product("Read after update", strategy.get(101))

    print("Cache statistics:", cache.stats())
    print("Repository reads:", repository.reads)
    print("Repository writes:", repository.writes)


def demonstrate_read_through() -> None:
    print("\n=== Read-through ===")

    repository = ProductRepository()
    cache: InMemoryCache[int, Product] = InMemoryCache("read-through-cache")

    strategy = ReadThrough(
        cache=cache,
        loader=repository.get,
        ttl_seconds=30,
    )

    # The caller knows only about the cache abstraction. Cache miss loading
    # is hidden behind the read-through implementation.
    print_product("First read", strategy.get(102))
    print_product("Second read", strategy.get(102))
    print_product("Unknown product", strategy.get(999))

    print("Cache statistics:", cache.stats())
    print("Repository reads:", repository.reads)


def demonstrate_write_through() -> None:
    print("\n=== Write-through ===")

    repository = ProductRepository()
    cache: InMemoryCache[int, Product] = InMemoryCache("write-through-cache")

    strategy = WriteThrough(
        cache=cache,
        saver=repository.save,
        ttl_seconds=30,
    )

    product = Product(103, "Noise-Cancelling Headphones", 189.00, 8)
    strategy.put(103, product)

    # The cache already contains the newly persisted representation, so a
    # following read does not require a database round trip.
    print_product("Cached updated product", strategy.get(103))

    persisted = repository.get(103)
    print_product("Source-of-truth product", persisted)

    print("Cache statistics:", cache.stats())
    print("Repository reads:", repository.reads)
    print("Repository writes:", repository.writes)


def demonstrate_ttl_and_expiration() -> None:
    print("\n=== TTL and expiration ===")

    cache: InMemoryCache[str, str] = InMemoryCache("ttl-demo")
    cache.put("session:42", "active", ttl_seconds=0.05)

    print("Immediately:", cache.get("session:42"))
    time.sleep(0.08)
    print("After expiration:", cache.get("session:42"))
    print("Statistics:", cache.stats())


def demonstrate_failure_safety() -> None:
    print("\n=== Failure safety ===")

    repository = ProductRepository()
    cache: InMemoryCache[int, Product] = InMemoryCache("failure-demo")

    strategy = WriteThrough(
        cache=cache,
        saver=repository.save,
        ttl_seconds=30,
    )

    valid = Product(101, "Mechanical Keyboard", 95.00, 39)
    strategy.put(101, valid)

    invalid = Product(101, "Mechanical Keyboard", -1.00, 39)

    try:
        strategy.put(101, invalid)
    except ValueError as exc:
        print("Rejected invalid write:", exc)

    # The failed database validation occurs before cache.put(), so the cache
    # retains the last known valid representation.
    print_product("Cached value after failed write", strategy.get(101))


def demonstrate_negative_cache_consideration() -> None:
    print("\n=== Missing-key behavior ===")

    repository = ProductRepository()
    cache: InMemoryCache[int, Product] = InMemoryCache("negative-key-demo")

    strategy = CacheAside(
        cache=cache,
        loader=repository.get,
        saver=repository.save,
        ttl_seconds=30,
    )

    # This basic implementation does not cache misses. In high-volume
    # systems, repeated requests for nonexistent keys can create a cache
    # penetration problem. A production design can use a short-lived
    # negative entry, Bloom filter, request throttling, or validation.
    for _ in range(3):
        print_product("Missing product", strategy.get(404))

    print("Source reads caused by uncached misses:", repository.reads)


def demonstrate_stale_data_tradeoff() -> None:
    print("\n=== Stale-data trade-off ===")

    repository = ProductRepository()
    cache: InMemoryCache[int, Product] = InMemoryCache("staleness-demo")

    strategy = ReadThrough(
        cache=cache,
        loader=repository.get,
        ttl_seconds=0.2,
    )

    first = strategy.get(102)
    print_product("Cached representation", first)

    # Simulate another service modifying the source directly. The cache does
    # not know about that write, so it remains stale until invalidated or its
    # TTL expires.
    repository.save(Product(102, "USB-C Dock", 139.50, 16))

    print_product("Before TTL expiry", strategy.get(102))

    cache.delete(102)
    print_product("After explicit invalidation", strategy.get(102))


def demonstrate_file_cache() -> None:
    print("\n=== Persistent JSON cache ===")

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "cache.json")
        cache = JsonFileCache[str, Dict[str, object]](path)

        cache.put(
            "product:101",
            {"name": "Mechanical Keyboard", "price": 94.99},
            ttl_seconds=10,
        )

        print("Persistent entry:", cache.get("product:101"))
        cache.delete("product:101")
        print("After deletion:", cache.get("product:101"))


def compare_strategies() -> None:
    print("\n=== Strategy selection comparison ===")

    comparison = [
        (
            "Cache-aside",
            "Application explicitly checks cache and loads source data on miss",
            "Useful when application controls caching selectively",
        ),
        (
            "Read-through",
            "Cache layer loads source data automatically after a miss",
            "Useful when read access should be centralized behind one cache API",
        ),
        (
            "Write-through",
            "Successful source writes immediately update the cache",
            "Useful when fresh cached reads are important after writes",
        ),
    ]

    for name, mechanism, fit in comparison:
        print(f"\n{name}")
        print(f"Mechanism: {mechanism}")
        print(f"Typical fit: {fit}")


def run_self_checks() -> None:
    repository = ProductRepository()
    cache: InMemoryCache[int, Product] = InMemoryCache("self-check")
    strategy = CacheAside(
        cache=cache,
        loader=repository.get,
        saver=repository.save,
        ttl_seconds=30,
    )

    assert strategy.get(101) is not None
    assert strategy.get(101) is not None
    assert repository.reads == 1

    strategy.put(101, Product(101, "Mechanical Keyboard", 99.00, 38))
    assert repository.writes == 1
    assert strategy.get(101).price == 99.00
    assert repository.reads == 2

    try:
        strategy.put(
            101,
            Product(101, "Mechanical Keyboard", -10.00, 38),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Negative prices must be rejected")


def main() -> None:
    print("CACHE STRATEGIES: CACHE-ASIDE, READ-THROUGH, WRITE-THROUGH")

    demonstrate_cache_aside()
    demonstrate_read_through()
    demonstrate_write_through()
    demonstrate_ttl_and_expiration()
    demonstrate_failure_safety()
    demonstrate_negative_cache_consideration()
    demonstrate_stale_data_tradeoff()
    demonstrate_file_cache()
    compare_strategies()
    run_self_checks()

    print("\nAll self-checks passed.")


if __name__ == "__main__":
    main()
