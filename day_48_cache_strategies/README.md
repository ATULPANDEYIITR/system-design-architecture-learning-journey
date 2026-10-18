# Cache Strategies: Cache-Aside, Read-Through, and Write-Through

## Scope

This repository models three cache strategies that solve related but different problems:

- **Cache-aside** makes the application responsible for checking the cache, loading missing data from the source, populating the cache, and deciding when a cached value should be invalidated.
- **Read-through** moves cache-miss loading behind the cache abstraction. The caller asks the cache for a value, and the cache obtains the value from the source when it is absent.
- **Write-through** makes a successful source write immediately update the cache, keeping subsequent cached reads aligned with the newly persisted representation.

The distinction is primarily about **where responsibility for cache population and synchronization lives**. TTL, invalidation, stale data, negative caching, concurrent misses, and source-of-truth rules operate around these strategies rather than replacing them.

The examples use a product catalog because product reads and updates expose the consistency and latency trade-offs clearly.

## Core Model

The source database is authoritative.

    Application
        |
        +---------------- Cache-aside ----------------+
        |                                             |
        |       cache hit -> cached value             |
        |       cache miss -> source -> cache         |
        |                                             |
        +---------------- Read-through ---------------+
        |                                             |
        |       application -> cache                  |
        |                    cache miss                |
        |                         |                   |
        |                         +--> source         |
        |                              |              |
        |                              +--> cache     |
        |                                             |
        +---------------- Write-through --------------+
                                                      |
                               successful write       |
                                    |                 |
                                    +--> source       |
                                    |                 |
                                    +--> cache        |

A cache is a performance layer, not normally the system of record. If a cached product says that a keyboard costs `89.99` while the authoritative store says `94.99`, the application must have an explicit policy for whether that cached representation is still acceptable.

## Cache-Aside

Cache-aside is the most application-controlled of the three strategies.

A read follows this pattern:

    application
        |
        +--> cache.get(key)
               |
               +--> hit: return cached value
               |
               +--> miss
                     |
                     +--> source.get(key)
                            |
                            +--> cache.put(key, value)
                            |
                            +--> return value

The Python `CacheAside` class makes these responsibilities explicit. Its `get()` method first checks `InMemoryCache`, then invokes the repository loader only after a miss. A successful source lookup populates the cache.

The write path deliberately invalidates the cache after the repository accepts the update. This means the next read reconstructs the cached representation from the source of truth.

That design is useful when the application knows which objects are expensive to load and which objects should never be cached.

### Why invalidation matters

Suppose the cache contains:

    product 101 -> price 89.99

The database is updated to:

    product 101 -> price 94.99

If the application writes the database but leaves the cache untouched, subsequent reads can continue returning `89.99`.

Cache-aside therefore commonly uses:

    successful source write
            |
            +--> invalidate cache key
            |
            +--> next read reloads source

The Python implementation demonstrates exactly this behavior.

## Read-Through

Read-through changes who owns the cache-miss loading operation.

The caller does not need to know that a database lookup is required:

    application
         |
         v
    cache.get(key)
         |
         +-- hit --> return value
         |
         +-- miss --> loader(key)
                        |
                        +--> source
                        |
                        +--> cache
                        |
                        +--> return value

The Python `ReadThrough` class receives a loader function. The cache-facing service performs the source lookup after a miss and inserts the resulting value into the cache.

The JavaScript version extends this idea with an asynchronous loader. This is significant in Node.js applications because source access is commonly asynchronous. The cache layer can therefore hide the asynchronous database operation while preserving a simple `get()` interface.

Read-through is particularly useful when many application components should share one consistent cache-loading policy.

## Write-Through

Write-through concerns the write path rather than only cache-miss reads.

A successful write follows:

    application
         |
         v
    write-through service
         |
         +--> source store
         |
         +--> cache

The implementations persist the source value first and update the cache only after the source operation succeeds.

This ordering prevents a failed source validation from inserting an invalid value into the cache.

For example, the Python implementation rejects a negative product price in the repository. Because the cache update follows the repository operation, the rejected price never becomes the new cached state.

The Java implementation uses the same ordering while also modeling product versions. A successful persistence operation receives a new version and the persisted object, rather than blindly copying the caller's object into the cache.

## Strategy Distinctions

| Concern | Cache-aside | Read-through | Write-through |
|---|---|---|---|
| Cache miss | Application loads source | Cache layer loads source | Usually combined with a separate read strategy |
| Cache population after read | Application | Cache abstraction | Depends on read implementation |
| Cache update after write | Usually invalidation or explicit refresh | Not inherently defined | Immediate cache update after successful source write |
| Application control | High | Lower | Moderate |
| Main benefit | Flexible selective caching | Centralized read behavior | Fresh cache immediately after successful writes |
| Main risk | Application can forget invalidation | Cache abstraction becomes more complex | Write latency and consistency coordination |

These are not mutually exclusive architectural categories in every system. A production application can combine read-through behavior with write-through behavior. The important distinction is which component owns each responsibility.

## Python Implementation

The Python implementation is an executable model of the three strategies.

`ProductRepository` represents the authoritative store. It validates product prices and stock quantities and tracks source reads and writes so the effect of caching can be observed.

`InMemoryCache` provides:

- Cache hits and misses.
- TTL expiration.
- Cache writes.
- Deletion and invalidation.
- Simple operational metrics.

`CacheAside` explicitly performs the miss lookup and invalidation.

`ReadThrough` hides source loading behind the cache-facing operation.

`WriteThrough` performs the source write before updating the cache.

The script also includes a JSON-file cache to show that cache storage does not have to be purely in memory. The file implementation uses temporary-file replacement for safer updates rather than writing directly over the active cache file.

The examples cover missing keys, TTL expiration, failed writes, stale data caused by an external source mutation, and a discussion of negative caching.

## JavaScript Implementation

The JavaScript implementation focuses on asynchronous and event-driven behavior.

`ProductRepository.get()` and `save()` are asynchronous. This models the latency of a networked database without requiring an external database.

The JavaScript cache uses `Map` for expected constant-time key lookup and stores an explicit expiration timestamp with each value.

The event-driven example introduces an `EventBus`. Cache hits, misses, and population events are emitted so operational instrumentation can observe cache behavior without embedding monitoring logic into every repository method.

The concurrent-miss example demonstrates a cache stampede control technique. Multiple requests for the same missing key share a single in-flight promise:

    request A ----+
    request B ----+--> one source request --> cache
    request C ----+
    request D ----+

Without this coordination, many simultaneous requests could observe the same cache miss and independently query the database.

The implementation also demonstrates JavaScript's asynchronous error propagation during write-through persistence.

## C++ Case Study

The C++ program treats a product catalog as a latency-sensitive service.

`Repository` models the authoritative data store. `TtlCache` stores products in an `unordered_map`, giving expected constant-time lookup and update behavior.

The cache stores:

- The product value.
- An optional expiration timestamp.

`CacheAsideService` owns explicit miss handling and invalidation.

`ReadThroughCache` centralizes source loading after a miss.

`WriteThroughService` persists first and updates the cache after successful persistence.

The C++ case study also demonstrates stale data created by a source update that bypasses the cache. Explicit cache invalidation then forces the following read to reload the source.

The TTL demonstration uses `steady_clock`, which is appropriate for elapsed-duration measurement because it is not intended to move backward when the system wall clock changes.

The implementation uses standard C++17 facilities only.

## Java Implementation

The Java implementation uses explicit domain abstractions suitable for an enterprise service.

`Product` is a Java record with constructor validation. This makes the domain object's invariants part of object creation rather than an assumption made by cache code.

`StrategyType` identifies the selected cache strategy.

`CachePolicy` separates strategy configuration from execution. TTL and the negative-cache policy are represented as explicit policy values rather than hidden constants.

The service interfaces separate reading and writing behavior:

- `ProductReader` defines the read contract.
- `ProductWriter` defines the write contract.
- `CacheAsideService`, `ReadThroughService`, and `WriteThroughService` provide different implementations.

The Java cache tracks expiration with `Instant`. Expired entries are removed during lookup, which prevents an expired value from being returned as a normal hit.

The write-through service receives the persisted product from the repository and places that persisted representation in the cache. This is preferable to assuming that the object supplied by the caller is identical to the final database representation.

## SQL Data Model

The PostgreSQL implementation represents cache strategy behavior relationally.

The main entities are:

- `repositories` identifies independent catalog repositories.
- `products` stores the authoritative product representation.
- `cache_policies` records which strategy applies to each repository.
- `cache_entries` stores materialized cached product values.
- `cache_events` records hits, misses, population, invalidation, expiration, and write-through operations.

The database uses foreign keys so cache entries cannot refer to nonexistent products or policies.

The `products` table enforces:

- Non-negative prices.
- Non-negative stock.
- Positive versions.

The `cache_entries` table enforces valid cached prices and stock quantities and prevents duplicate entries for the same policy and product.

## Version-Based Freshness

The SQL model gives each product a monotonically increasing version.

When a meaningful product field changes, the PostgreSQL trigger increments the source version.

A cache entry records `cached_version`.

Freshness can therefore be evaluated without comparing every attribute:

    source version == cached version
        -> same known version

    source version > cached version
        -> cached representation is stale

    cached version > source version
        -> invalid state that the trigger prevents

The `validate_cache_entry_version()` trigger rejects an attempt to insert a cache version newer than the authoritative source version.

This is an important database-level invariant because application code should not be the only layer responsible for preventing impossible cache states.

## TTL and Expiration

TTL places an upper bound on how long an entry can remain valid without being refreshed.

For an entry created at time `T` with TTL `D`:

    expires_at = T + D

A cache read checks whether the current time has reached `expires_at`.

TTL does not guarantee perfect freshness. It guarantees only that the implementation will not intentionally serve the entry beyond its configured expiration boundary.

A long TTL can reduce database load while increasing the potential staleness window.

A short TTL improves freshness at the cost of more source-store traffic.

The appropriate value depends on how frequently the underlying data changes and how costly stale data is.

## Invalidation Versus Refresh

Invalidation removes a cache entry so the next read must retrieve the source value.

Refresh replaces the cached value immediately.

Cache-aside often prefers invalidation because the application can avoid duplicating source serialization logic:

    write source
        |
        +--> invalidate key
        |
        +--> future read reloads source

Write-through generally prefers immediate refresh because the successful write already produced the representation that should be available to subsequent reads.

Neither mechanism is universally superior. The correct choice depends on the relationship between write latency, read traffic, consistency requirements, and the ability to reliably coordinate invalidation.

## Stale Data

Staleness occurs when the source changes without the cache receiving a corresponding update or invalidation.

A common example is:

    Service A -> updates database
    Service B -> reads old cache entry

The cache can remain stale until:

- Explicit invalidation occurs.
- The entry expires.
- A refresh operation replaces it.
- An external invalidation mechanism propagates the change.

This becomes especially important when several application instances share a distributed cache.

A local in-process cache cannot automatically know that another process has modified the source database.

## Cache Stampede

A cache stampede occurs when a popular key expires or is evicted and many requests simultaneously miss.

Without coordination:

    100 requests
        |
        +--> 100 database queries

A protected implementation can coordinate the miss:

    100 requests
        |
        +--> one database query
                 |
                 +--> shared result

The JavaScript implementation demonstrates this using an `inFlight` map containing promises for active loads.

Other production designs can use distributed locks, request coalescing, leases, or carefully controlled refresh windows.

The important property is that the protection mechanism must itself avoid becoming a scalability bottleneck.

## Negative Caching

A missing object can be cached as a short-lived negative result.

This can protect the source database against repeated requests for nonexistent keys:

    product:999999 -> NOT_FOUND

Negative caching must use a shorter TTL in many systems because an object that does not exist now may be created later.

It also requires care with authorization and multi-tenant data. A cached "not found" result must never leak the existence or absence of an object across security boundaries.

The Python implementation intentionally does not cache misses by default and documents the resulting repeated source reads.

## Failure Handling

The source store remains authoritative in all three implementations.

For write-through:

    validate
       |
    persist
       |
    success?
      / \
     no  yes
     |    |
    stop  update cache

The cache is not updated when the source write fails.

This prevents a failed mutation from being represented as successful cached state.

A production distributed system has a harder problem because the source and cache may not share one transaction. A source write can succeed while a cache update fails, or a cache update can succeed while the source operation is later rolled back.

The appropriate recovery model depends on the cache's role. If the cache is only an optimization, it should be possible to reconstruct it from the authoritative source.

## Performance Considerations

For a typical in-memory cache backed by a hash table, expected lookup is approximately `O(1)`.

A cache hit removes the source-store operation from the request path:

    request latency ≈ cache lookup

A miss adds the source lookup:

    request latency ≈ cache lookup + source lookup + cache population

The performance benefit therefore depends strongly on the hit ratio.

A high hit ratio is useful only if cached values are sufficiently fresh and the cache lookup itself does not introduce excessive network or serialization overhead.

A distributed cache such as a network service has different latency characteristics from an in-process map. It can provide shared state across application instances but introduces network latency, serialization cost, connection management, and additional failure modes.

## Security Considerations

Caching must preserve the security properties of the source system.

Sensitive or user-specific data should not be placed in a shared cache without a key design that includes the necessary authorization or tenant boundaries.

A dangerous pattern is:

    cache key = "account:42"

when the returned object depends on the requesting user's permissions.

The cache key may need to represent the security context, or the cached representation may need to contain only data safe for every caller that can access the key.

Cache poisoning is another concern. Applications should validate data before it enters the cache and should avoid allowing untrusted clients to directly control cache keys or cached representations without validation.

## Common Failure Modes

### Treating the cache as the source of truth

A cache entry can disappear because of eviction, restart, expiration, or infrastructure failure. A design that cannot reconstruct its cache from authoritative data is fragile.

### Updating the database without invalidating cache-aside data

This creates a stale-value window whose length is controlled by the invalidation mechanism or TTL.

### Updating the cache before a write is confirmed

A failed database write can then leave the cache representing a state that never became authoritative.

### Using one TTL for unrelated data

Highly volatile inventory and relatively stable product descriptions can require very different freshness policies.

### Ignoring concurrent misses

A high-traffic key can produce a large burst of identical database requests immediately after expiration.

### Assuming TTL equals consistency

TTL limits the lifetime of a cached value. It does not coordinate concurrent writers or instantly propagate changes between independent services.

## Production Design Considerations

A production cache usually requires more than a key-value operation.

Useful operational measurements include:

- **Hit ratio:** Indicates whether the cache is actually avoiding source work.
- **Miss rate:** High misses can expose poor key selection or unsuitable TTLs.
- **Eviction rate:** Excessive eviction can indicate insufficient capacity.
- **Source latency during misses:** Cache misses expose the underlying store.
- **Stale-entry frequency:** Freshness problems may remain hidden behind a high hit ratio.
- **Error rate:** Cache infrastructure can fail independently from the source database.

Cache keys should be deterministic and versioned when serialization formats can change.

Serialization should be bounded and validated.

Timeouts should prevent an unavailable cache from blocking the entire application indefinitely.

If the cache is an optimization, a fallback path should normally remain available when cache infrastructure fails.

The most important architectural decision is to preserve a clear source of truth and define exactly how cached state is created, refreshed, invalidated, expired, and recovered.
