# Cache Invalidation

Cache invalidation is the process of preventing cached representations from being used after the authoritative data they represent has changed. The central problem is not storing data in a cache. It is determining when a cached value is no longer trustworthy.

This project models stale data and several invalidation strategies across Python, JavaScript, C++17, Java 17, and PostgreSQL.

## Core model

The implementations use the following relationship:

`Authoritative Store → Cache → Consumer`

A cache entry is useful only while its representation remains sufficiently fresh for the application's correctness requirements.

A write can create this state:

`Database: price = 2600, version = 2`
`Cache:    price = 2400, version = 1`

The cache is stale even if its TTL has not expired. This distinction is important because time-based expiration and correctness-based invalidation solve different problems.

## Stale data

Stale data occurs when the cached representation is older than the authoritative representation.

Common causes include:

- A database record is updated while its previous value remains cached.
- A cache entry survives longer than the business permits.
- One application instance changes data while another instance retains a local cache.
- An invalidation event is delayed or lost.
- A cache key does not represent every input that affects the result.
- Concurrent writes allow an older response to overwrite a newer cached value.
- A long TTL is selected for data that changes frequently.

The implementations therefore associate cached values with either expiration metadata, source versions, or explicit invalidation events.

## Invalidation strategies

| Strategy | Mechanism | Main benefit | Main limitation |
|---|---|---|---|
| Explicit invalidation | Remove an affected key after a write | Fast and precise | Every relevant mutation path must invalidate |
| TTL | Expire entries after a duration | Simple and resilient to missed invalidations | Stale data can remain until expiry |
| Version-based | Compare cached and authoritative versions | Detects stale data independently of TTL | Requires version information |
| Write-through | Update cache as part of the write path | Cache can remain current | Write path becomes more complex |
| Write-invalidate | Persist the write, then remove the old cache value | Avoids serving a known old value | Subsequent reads incur a cache miss |
| Stale-while-revalidate | Serve cached data while refreshing asynchronously | Low read latency | Temporarily serves data known to be old |

No strategy guarantees freshness by itself. The correct choice depends on the application's consistency requirement, update frequency, failure model, and acceptable read latency.

## Python implementation

The Python implementation models the cache directly with `CacheEntry`, `Cache`, `ProductRepository`, and `ProductService`.

`Cache` provides:

- key validation
- insertion
- lazy TTL expiration
- explicit key invalidation
- prefix invalidation
- expired-entry cleanup
- thread-safe access using `RLock`

The cache uses `time.monotonic()` for TTL calculations. A monotonic clock is preferable to wall-clock time for elapsed-duration measurements because system clock adjustments should not unexpectedly change an entry's lifetime.

`ProductRepository` acts as the authoritative store. It returns copies of products so that a caller cannot accidentally mutate the authoritative representation through an object already returned by the repository.

`ProductService` implements cache-aside behavior. A read checks the cache first and loads the repository only after a miss. A successful price update modifies the authoritative store and explicitly invalidates the affected cache key.

`VersionedCache` adds a different correctness mechanism. A cached representation carries a version, and an older version cannot overwrite a newer one.

The `stable_cache_key` function demonstrates bounded cache-key construction. Hashing can prevent excessively long identifiers from becoming unwieldy cache keys and avoids placing the raw identifier directly into the key namespace.

## JavaScript implementation

The JavaScript implementation uses Node.js standard-library facilities and emphasizes event-driven invalidation.

`MemoryCache` uses a `Map` for cache storage. Each `CacheEntry` records:

- value
- source version
- creation time
- expiration time

`ProductStore` provides asynchronous authoritative operations. This makes the cache service resemble a real service in which database access has non-zero latency.

`ProductCacheService` implements cache-aside reads and write invalidation. It extends `EventEmitter` so that a product mutation emits a `productChanged` event. The listener invalidates the affected key.

The event-driven design separates the mutation operation from the cache policy. In a distributed deployment, the same conceptual event could be transported through a durable messaging system rather than an in-process event emitter.

The stale-while-revalidate method prevents multiple concurrent callers from independently refreshing the same key. The `refreshing` map records an active refresh and reduces cache-stampede pressure.

## C++17 implementation

The C++ program treats cache invalidation as part of a strongly typed service model.

`ProductRepository` owns the authoritative product state.

`GovernanceCache` uses `std::unordered_map` for average constant-time lookup and stores an optional expiration time. `std::optional` distinguishes a cache miss from a valid cached object.

`Product` contains an explicit version number. `ProductService` implements:

- cache-aside reads
- explicit invalidation after updates
- version-aware reads
- TTL expiration
- namespace-style prefix invalidation

The implementation uses `std::chrono::steady_clock` rather than wall-clock time for expiration. This prevents changes to system time from incorrectly affecting TTL calculations.

The cache has no ownership of the authoritative product state. This separation makes invalidation explicit and prevents a cache from becoming an accidental source of truth.

## Java implementation

The Java implementation models cache state using domain-oriented records and a concurrent map.

`Product` is an immutable Java record. A price change creates a new product representation with an incremented version instead of mutating the existing record.

`CacheEntry<T>` is generic and stores the cached value, source version, and expiration timestamp.

`VersionedCache<T>` uses `ConcurrentHashMap`. Its insertion operation uses `compute` so an older version cannot replace a newer cached value. This is important when asynchronous operations complete out of order.

`ProductRepository` models the authoritative enterprise data source, while `ProductService` owns the cache-aside workflow.

The service explicitly invalidates the product key after a successful update. It also provides a version-aware read path for systems where waiting for TTL expiration is insufficient.

The Java model separates domain data, repository behavior, cache state, and service behavior. This makes policy changes easier to isolate than a design in which database access and cache manipulation are mixed throughout application code.

## PostgreSQL implementation

The PostgreSQL script represents the authoritative data and cached snapshot as separate relational structures.

The `products` table contains the authoritative representation. Its `version` column identifies the logical revision of the product.

The `cache_entries` table contains:

- cache key
- related product
- JSONB snapshot
- source version
- creation time
- expiration time

A cached row is therefore not considered fresh merely because it exists. Its `source_version` must be compatible with the current authoritative version, and its `expires_at` must not have passed.

The `invalidation_events` table records invalidation activity. This gives the database a durable audit trail that can be inspected for excessive invalidation, unexpected writes, and consumer-processing problems.

The `bump_product_version` trigger increments the product version when relevant product fields change. The version update is therefore enforced at the database boundary rather than depending entirely on application code.

`cache_product` implements cache population from the authoritative table.

`invalidate_product_cache` removes an affected cache entry and records the operation.

`remove_stale_cache_entries` detects both TTL expiration and version mismatch. This demonstrates why version-based freshness can detect stale data before a TTL expires.

The script also demonstrates PostgreSQL `LISTEN`/`NOTIFY` through a trigger. `NOTIFY` can provide low-latency notification, but it should not be treated as a durable message queue. The invalidation table provides persistent information that a transient notification alone cannot provide.

## Cache-aside workflow

The main cache-aside workflow is:

`Read request`
`    ↓`
`Check cache`
`    ↓`
`Hit ─────────────→ Return cached representation`
`    │`
`    └─ Miss`
`         ↓`
`   Read authoritative store`
`         ↓`
`   Populate cache`
`         ↓`
`   Return representation`

For a mutation:

`Write request`
`    ↓`
`Update authoritative store`
`    ↓`
`Successful commit`
`    ↓`
`Invalidate affected cache`
`    ↓`
`Next read repopulates cache`

Invalidating only after a successful authoritative write avoids deleting a cache entry for a write that ultimately failed.

## Explicit invalidation versus TTL

Explicit invalidation is generally more precise when the application knows exactly which cached representation was affected.

For example, changing product `101` can invalidate `product:101` immediately.

TTL is simpler when identifying every dependency is difficult. It provides an upper bound on cache lifetime, but it does not provide immediate consistency.

A common production design combines both:

`Write → explicit invalidation`
`Read → TTL protection`
`Read → version validation where correctness requires it`

This gives the application a fallback if an invalidation mechanism fails while still reducing the amount of stale data normally served.

## Version-based invalidation

Versioning changes the question from:

"Has enough time passed?"

to:

"Does the cached representation correspond to the current authoritative version?"

For example:

`Cache version = 7`
`Database version = 8`

The cached representation is stale regardless of its remaining TTL.

Version checks are especially useful when:

- updates can occur from multiple application instances
- asynchronous operations may finish out of order
- invalidation messages can be delayed
- a record has a natural revision number
- correctness is more important than avoiding a database read

The cost is that the application must maintain and compare versions consistently.

## Cache stampede considerations

A cache stampede occurs when a popular entry expires and many requests simultaneously miss the cache.

Without coordination:

`100 requests → 100 database reads`

With single-flight refresh behavior:

`100 requests → 1 refresh + shared cached result`

The JavaScript implementation demonstrates a per-key refresh registry for stale-while-revalidate behavior.

Other production techniques include request coalescing, jittered TTLs, background refresh, and bounded concurrency.

## Failure modes

### Missed invalidation

If a write succeeds but invalidation does not occur, the cache can continue serving old data.

TTL reduces the maximum lifetime of the stale entry, while version checking can detect the mismatch immediately when the authoritative version is inspected.

### Out-of-order refresh

Suppose version 8 and version 9 are loaded concurrently. If version 8 finishes last, blindly writing it into the cache would replace newer data.

The version-aware implementations prevent this by refusing to overwrite a newer cached version with an older one.

### Partial write failure

If the authoritative write fails, invalidating the cache before knowing the result may create an unnecessary miss. The examples therefore perform invalidation after a successful update.

### Distributed cache failure

An in-process cache is local to one application instance. Invalidating one process does not automatically invalidate another process's cache.

Distributed deployments require a shared cache, invalidation events, version checks, or another coordination mechanism.

### Cache key collision

If two logically different requests produce the same cache key, one result can be incorrectly served for another. Key construction must include every input that affects the cached result.

### Sensitive cached data

Caches can contain credentials, personal data, authorization decisions, or other sensitive values. Production systems should minimize sensitive data in caches, apply appropriate access controls, and define explicit expiration and deletion behavior.

## Performance considerations

Hash-map-based memory caches provide expected O(1) lookup and insertion.

Prefix invalidation is O(n) in the number of cached keys because the implementation must inspect keys to identify the affected namespace.

TTL cleanup can also be O(n) when performed by scanning all entries. Production caches commonly use expiration indexes, timing wheels, heaps, or specialized cache implementations to avoid full scans.

Version validation can require an authoritative read, which reduces some of the latency advantage of caching. It should therefore be applied selectively to data for which freshness has a meaningful correctness requirement.

## Consistency boundary

A cache should be treated as an optimization unless the system explicitly defines it as a separate authoritative store.

The authoritative database establishes the state of the product. The cache stores a representation of that state.

The critical invariant is:

`Cached representation must never be assumed current merely because it exists.`

Freshness must be established through an explicit mechanism such as invalidation, expiration, version comparison, or a stronger write/read protocol.

## File responsibilities

| File | Primary perspective |
|---|---|
| Python | Thread-safe cache-aside model, TTL, explicit invalidation, version checks |
| JavaScript | Event-driven invalidation, asynchronous operations, stale-while-revalidate |
| C++17 | Typed cache service using `unordered_map`, `optional`, and `chrono` |
| Java 17 | Immutable domain model, generics, concurrent cache state, version ordering |
| PostgreSQL | Authoritative relational state, cached snapshots, triggers, functions, freshness queries, invalidation events |

The five implementations deliberately use different mechanisms while preserving the same fundamental distinction between authoritative state, cached state, expiration, and invalidation.
