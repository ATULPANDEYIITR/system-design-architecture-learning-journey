from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import RLock
from time import monotonic, sleep
from typing import Callable, Generic, TypeVar
import hashlib
import json


T = TypeVar("T")


class InvalidationStrategy(Enum):
    EXPLICIT = "explicit"
    TTL = "ttl"
    VERSION = "version"
    WRITE_THROUGH = "write-through"
    WRITE_INVALIDATE = "write-invalidate"


@dataclass
class CacheEntry(Generic[T]):
    value: T
    created_at: float
    expires_at: float | None
    version: int

    def expired(self, now: float) -> bool:
        return self.expires_at is not None and now >= self.expires_at


class Cache(Generic[T]):
    """
    Thread-safe in-memory cache.

    The cache never treats a missing value as equivalent to a cached null.
    Expired entries are removed lazily during reads and explicitly during
    cleanup. A monotonic clock is used for TTL calculations so wall-clock
    adjustments cannot extend or shorten a TTL unexpectedly.
    """

    def __init__(self, default_ttl: float | None = None):
        if default_ttl is not None and default_ttl <= 0:
            raise ValueError("default_ttl must be positive")

        self.default_ttl = default_ttl
        self._entries: dict[str, CacheEntry[T]] = {}
        self._lock = RLock()

    def get(self, key: str) -> T | None:
        self._validate_key(key)

        with self._lock:
            entry = self._entries.get(key)

            if entry is None:
                return None

            if entry.expired(monotonic()):
                del self._entries[key]
                return None

            return entry.value

    def get_entry(self, key: str) -> CacheEntry[T] | None:
        self._validate_key(key)

        with self._lock:
            entry = self._entries.get(key)

            if entry is None:
                return None

            if entry.expired(monotonic()):
                del self._entries[key]
                return None

            return entry

    def put(
        self,
        key: str,
        value: T,
        *,
        ttl: float | None = None,
        version: int = 0,
    ) -> None:
        self._validate_key(key)

        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be positive")

        effective_ttl = self.default_ttl if ttl is None else ttl
        now = monotonic()
        expires_at = None if effective_ttl is None else now + effective_ttl

        with self._lock:
            self._entries[key] = CacheEntry(
                value=value,
                created_at=now,
                expires_at=expires_at,
                version=version,
            )

    def invalidate(self, key: str) -> bool:
        self._validate_key(key)

        with self._lock:
            return self._entries.pop(key, None) is not None

    def invalidate_prefix(self, prefix: str) -> int:
        if not prefix:
            raise ValueError("prefix must not be empty")

        with self._lock:
            keys = [key for key in self._entries if key.startswith(prefix)]

            for key in keys:
                del self._entries[key]

            return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def cleanup(self) -> int:
        now = monotonic()

        with self._lock:
            expired = [
                key
                for key, entry in self._entries.items()
                if entry.expired(now)
            ]

            for key in expired:
                del self._entries[key]

            return len(expired)

    def keys(self) -> list[str]:
        with self._lock:
            self.cleanup()
            return list(self._entries)

    @staticmethod
    def _validate_key(key: str) -> None:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("cache key must be a non-empty string")


@dataclass
class Product:
    product_id: int
    name: str
    price: float
    version: int = 1


class ProductRepository:
    """Represents the authoritative data store."""

    def __init__(self):
        self._products: dict[int, Product] = {
            101: Product(101, "Keyboard", 2400.0),
            102: Product(102, "Monitor", 18500.0),
        }

    def get(self, product_id: int) -> Product:
        product = self._products.get(product_id)

        if product is None:
            raise KeyError(f"product {product_id} not found")

        # Return a copy so callers cannot silently mutate authoritative data.
        return Product(
            product.product_id,
            product.name,
            product.price,
            product.version,
        )

    def update_price(self, product_id: int, price: float) -> Product:
        if price < 0:
            raise ValueError("price cannot be negative")

        product = self._products.get(product_id)

        if product is None:
            raise KeyError(f"product {product_id} not found")

        product.price = price
        product.version += 1

        return self.get(product_id)


class ProductService:
    """
    Cache-aside service.

    Reads populate the cache after a database miss. Writes update the
    authoritative store and invalidate the corresponding cache entry.
    This avoids serving a known old representation after a successful write.
    """

    def __init__(self, repository: ProductRepository):
        self.repository = repository
        self.cache: Cache[Product] = Cache(default_ttl=5.0)

    def get_product(self, product_id: int) -> Product:
        key = f"product:{product_id}"

        cached = self.cache.get(key)

        if cached is not None:
            return cached

        product = self.repository.get(product_id)
        self.cache.put(key, product, version=product.version)

        return product

    def update_price(self, product_id: int, price: float) -> Product:
        product = self.repository.update_price(product_id, price)

        # Invalidate rather than trusting the old representation.
        self.cache.invalidate(f"product:{product_id}")

        return product

    def refresh_if_stale(self, product_id: int) -> Product:
        key = f"product:{product_id}"
        cached = self.cache.get_entry(key)
        current = self.repository.get(product_id)

        if cached is None or cached.version != current.version:
            self.cache.put(key, current, version=current.version)
            return current

        return cached.value


class VersionedCache(Generic[T]):
    """Demonstrates version-aware invalidation without waiting for TTL."""

    def __init__(self):
        self._values: dict[str, tuple[int, T]] = {}

    def put(self, key: str, version: int, value: T) -> None:
        if version < 0:
            raise ValueError("version must not be negative")

        current = self._values.get(key)

        # Older versions can never overwrite a newer cached representation.
        if current is None or version >= current[0]:
            self._values[key] = (version, value)

    def get(self, key: str, required_version: int) -> T | None:
        item = self._values.get(key)

        if item is None or item[0] < required_version:
            return None

        return item[1]

    def invalidate(self, key: str) -> None:
        self._values.pop(key, None)


def stable_cache_key(namespace: str, identifier: str) -> str:
    """
    Avoid putting raw unbounded user input into cache namespaces.
    Hashing is useful when keys contain long or sensitive identifiers.
    """
    if not namespace or not identifier:
        raise ValueError("namespace and identifier are required")

    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:24]
    return f"{namespace}:{digest}"


def demonstrate() -> None:
    repository = ProductRepository()
    service = ProductService(repository)

    first = service.get_product(101)
    second = service.get_product(101)

    print("Initial database read:", first)
    print("Second read from cache:", second)

    updated = service.update_price(101, 2600.0)
    print("Updated authoritative value:", updated)

    refreshed = service.get_product(101)
    print("Read after explicit invalidation:", refreshed)

    versioned = VersionedCache[Product]()
    versioned.put("product:101", updated.version, updated)

    older = Product(101, "Keyboard", 2000.0, version=1)
    versioned.put("product:101", older.version, older)

    current = versioned.get("product:101", required_version=updated.version)
    print("Version-protected value:", current)

    ttl_cache: Cache[str] = Cache()
    ttl_cache.put("session:demo", "temporary", ttl=0.1)

    print("TTL value before expiry:", ttl_cache.get("session:demo"))
    sleep(0.12)
    print("TTL value after expiry:", ttl_cache.get("session:demo"))

    safe_key = stable_cache_key("customer", "customer@example.com")
    print("Bounded cache key:", safe_key)


if __name__ == "__main__":
    demonstrate()
