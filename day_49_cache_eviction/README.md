# Cache Eviction: LRU, LFU, FIFO, TTL

## Scope

Cache eviction determines which cached data should be removed when cached data becomes invalid, reaches its lifetime limit, or the cache reaches its capacity. LRU, LFU, FIFO, and TTL are related mechanisms, but they make different decisions.

**LRU** removes the item that has been unused for the longest time.  
**LFU** removes the item with the lowest access frequency, with recency useful as a tie-breaker.  
**FIFO** removes the item that entered the cache first, regardless of how frequently it has subsequently been read.  
**TTL** associates data with an expiration deadline and removes or invalidates it when that deadline is reached.

The important distinction is that LRU, LFU, and FIFO are primarily capacity-eviction policies, while TTL is primarily an expiration mechanism. A production cache can combine them. For example, entries may have a TTL while the cache uses LRU when capacity is exhausted.

## Core Cache Model

A cache entry in the implementations contains more than a key and value. The eviction decision can require:

- `insertedAt` or an insertion sequence for FIFO ordering.
- `lastAccess` for LRU ordering.
- `frequency` for LFU ordering.
- `expiresAt` for TTL enforcement.
- The cached value and its key for normal retrieval.

A bounded cache must distinguish three different outcomes:

| Situation | Meaning |
|---|---|
| Cache hit | The requested entry exists and is still valid. |
| Cache miss | The entry is absent or has expired. |
| Eviction | An existing cache entry is deliberately removed to satisfy capacity or expiration rules. |

A miss does not necessarily mean that an eviction occurred. An entry can be missing because it was never cached, explicitly deleted, expired, or previously evicted.

## LRU

Least Recently Used eviction assumes that recently accessed data is more likely to be requested again.

The Python implementation stores `last_access` and compares it when capacity is exceeded. Its deterministic simulator makes the ordering reproducible without depending on wall-clock behavior.

The JavaScript implementation takes advantage of `Map` insertion ordering. When an LRU entry is accessed, it is removed and inserted again, making the first entry in the map the least recently used candidate.

The C++ implementation keeps explicit timestamps and sequence values. It uses an `unordered_map` for average constant-time key lookup, then scans the bounded cache when choosing a victim.

LRU is useful for workloads with temporal locality. A weakness appears when a large one-time scan touches many unrelated objects. Those accesses can displace objects that are normally hot.

## LFU

Least Frequently Used eviction measures how often entries have been accessed.

The implementations maintain an access frequency for each entry. A low-frequency entry becomes a candidate for removal even when it was recently accessed.

Frequency alone can produce undesirable behavior. An object that was extremely popular several hours ago can retain a high frequency while a newer object receives repeated current accesses. The examples therefore use recency as a tie-breaker rather than pretending that frequency completely describes usefulness.

LFU is valuable when popularity is relatively stable and frequency carries stronger predictive value than immediate recency. Its bookkeeping is more involved than FIFO because access counts must be maintained and victim selection must account for them.

## FIFO

First In, First Out uses insertion order rather than access behavior.

The entry with the oldest insertion sequence is selected first. Reading an entry does not improve its position.

This makes FIFO simple and predictable, but it can remove a frequently accessed object simply because that object happens to be old. That behavior is intentional and distinguishes FIFO from LRU.

The C++ case study uses an explicit `sequence` field so FIFO remains independent of hash-table iteration order.

## TTL

Time To Live assigns a maximum lifetime to cached data.

An entry with an expiration timestamp is valid before its deadline and invalid after the deadline. TTL is particularly important for data that must not remain cached indefinitely, such as rapidly changing configuration, temporary session metadata, or values whose freshness requirements are explicit.

The Python simulator uses a logical clock so expiration can be tested deterministically. The SQL model stores `expires_at` and has a PostgreSQL function that marks expired entries.

TTL does not answer the same question as LRU. Suppose a cache contains several valid entries and reaches capacity. TTL can identify which entry will expire soonest, but an application may still choose LRU, LFU, or FIFO as its capacity policy. Expiration and capacity are separate dimensions.

## Relationship Between the Policies

A useful mental model is:

`request -> lookup -> validity check -> hit/miss -> origin retrieval -> cache insertion -> capacity enforcement`

For an entry that has expired, the request should not receive stale data merely because the entry is physically present in memory.

For a cache that is full, the system needs a capacity policy. LRU considers recency, LFU considers frequency, and FIFO considers insertion order.

A combined policy can therefore look like:

`TTL determines whether data remains valid; LRU determines which valid entry leaves when capacity is exhausted.`

The implementations also demonstrate a TTL-oriented capacity decision in which the entry with the nearest expiration is preferred when a TTL cache must remove an item before its natural expiration.

## Python Implementation

The Python program provides both a real-time `Cache` and a deterministic `DeterministicCacheSimulator`.

The real-time cache uses `time.monotonic()` instead of wall-clock time for expiration measurement. A monotonic clock is appropriate for elapsed-duration calculations because system clock adjustments should not unexpectedly extend or shorten a TTL.

`CacheEntry` stores insertion time, access time, frequency, sequence number, and optional expiration. The `_evict_one()` method selects a victim according to the configured policy.

The deterministic simulator is useful for understanding policy differences because its logical clock can be advanced directly. This makes expiration behavior reproducible and avoids tests that depend on sleeping for real time.

The workload simulation uses repeated product requests. A miss produces a deterministic representation of a backing-store lookup and then populates the cache. The resulting statistics expose hits, misses, hit rate, capacity, and eviction count.

Validation rejects zero capacity, empty keys, invalid TTL values, and TTL configuration without a TTL duration.

## JavaScript Implementation

The JavaScript implementation uses Node.js `EventEmitter` to model cache lifecycle events.

Events such as `hit`, `miss`, `set`, `update`, `evict`, `expire`, and `delete` make the cache observable. This is useful in operational systems where eviction behavior should be measurable rather than hidden inside a data structure.

`Map` provides insertion-order behavior that is particularly convenient for an LRU representation. On a successful LRU access, the implementation removes and re-inserts the entry, moving it to the most-recent position.

The `CachedProductService` adds an asynchronous application boundary. A cache miss invokes `originLookup()`, representing a database or network request, and the retrieved object is then cached. This demonstrates why eviction is part of a larger read-through caching workflow rather than an isolated data-structure operation.

The implementation avoids third-party dependencies and can execute directly in a Node.js environment.

## C++ Repository Metadata Case Study

The C++ program models a bounded cache for repository build metadata.

The scenario uses keys such as `repo:api`, `repo:web`, and `repo:worker`. The cache represents data that can be reconstructed from an authoritative source but is expensive enough to justify caching.

`RepositoryMetadataCache` uses an `unordered_map` so lookup by cache key has average O(1) complexity. Victim selection scans the current entries, giving O(C) eviction selection for capacity `C`.

This trade-off is intentional for a compact case study. A high-scale production implementation could use policy-specific structures. An LRU implementation commonly combines a hash map with a linked list so lookup and recency updates are O(1). LFU can use frequency buckets and linked sets to avoid scanning the entire cache.

The program also demonstrates validation of capacity, cache keys, and TTL values. Its logical clock makes TTL behavior deterministic.

## Java Enterprise Model

The Java implementation models cache resources with the `CacheKey` record, which separates service identity from resource identity.

`CachePolicy` contains the configuration boundary. It validates capacity and enforces the rule that a TTL policy must have a positive lifetime.

`CacheEntry` models state and maintains insertion time, access time, expiration, frequency, and sequence information. `CacheService` owns the lifecycle operations and eviction decision.

The Java program uses an enum for the four policies and a comparator selected according to the active policy. This makes policy behavior explicit rather than embedding all decisions in one generic conditional workflow.

The enterprise workload treats catalog resources as cacheable objects. Repeated pricing accesses create a hot entry, allowing LFU behavior to differ from FIFO and LRU.

Java's standard collections and `Optional` are sufficient for the model. No third-party dependency is required.

## PostgreSQL Data Model

The SQL implementation represents cache behavior relationally.

`cache_profiles` stores the selected policy, capacity, and default TTL. A database `CHECK` constraint prevents a TTL profile from being created without a positive TTL.

`cache_entries` stores the cached value, insertion sequence, access count, last access timestamp, expiration timestamp, and lifecycle state. The unique constraint on `(profile_id, cache_key)` prevents duplicate active identities within one cache profile.

`cache_access_log` records hits and misses separately from the current cache state. This distinction allows historical performance analysis without treating the current entry table as an access-history table.

Partial indexes support the principal victim-selection queries:

- LRU uses `last_accessed_at` and insertion sequence.
- LFU uses `access_count` and recency.
- FIFO uses `insertion_sequence`.
- TTL uses `expires_at`.

The SQL script also uses PostgreSQL `ENUM` types, `JSONB`, PL/pgSQL functions, window functions, filtered aggregates, and transactions.

## Database-Level Enforcement

The database should enforce invariants that must remain true regardless of which application writes the data.

The schema rejects non-positive capacities and invalid TTL configurations. It also prevents an expiration timestamp from being earlier than the insertion timestamp.

The `register_cache_access()` function performs an expiration check before recording a hit. It uses a row lock when updating a live entry so concurrent access updates do not blindly overwrite one another.

The transaction near the end of the script demonstrates atomic eviction state changes. The victim is selected and marked `EVICTED` within one transaction.

Application code is still responsible for deciding when to populate a cache and how cache invalidation interacts with the authoritative data source. Database constraints do not replace those application-level policies.

## Policy Comparison

| Policy | Primary signal | Access changes priority? | Typical strength | Main weakness |
|---|---|---:|---|---|
| LRU | Last access time | Yes | Strong temporal locality | Scan workloads can cause churn |
| LFU | Access frequency | Yes, through count | Stable popularity | Historical popularity can become stale |
| FIFO | Insertion order | No | Simple and predictable | Hot old entries can be removed |
| TTL | Expiration deadline | Not inherently | Freshness control | Does not by itself solve capacity selection |

The choice should follow workload behavior rather than implementation convenience.

## Edge Cases

An entry can expire between two operations. The cache must validate expiration when reading it instead of assuming that physical presence means logical validity.

Updating an existing key should not accidentally create a second entry for the same logical resource. The Python, JavaScript, Java, and SQL implementations enforce or model unique cache identity.

A cache with capacity one exposes policy differences particularly clearly. Every insertion that is not an update forces a capacity decision.

LFU requires a tie-breaking rule. Without one, equal-frequency entries can produce unpredictable behavior. The implementations use recency and insertion sequence where appropriate.

TTL values must be positive. A zero or negative TTL is rejected rather than silently producing an immediately invalid or ambiguous cache entry.

## Performance Considerations

A simple dictionary or hash map provides average O(1) key lookup.

Victim selection by scanning all entries is O(C), where `C` is cache capacity. This is acceptable for small bounded caches but becomes expensive for very large caches.

An efficient LRU design typically combines a hash map with a doubly linked list. The map locates an entry in O(1), while the list maintains recency order.

An optimized LFU implementation can maintain frequency buckets and a minimum-frequency pointer. This avoids scanning every entry when the least frequently used entry must be selected.

TTL expiration can be implemented lazily, where expired entries are removed when accessed, or proactively, where a background mechanism removes them periodically. Lazy expiration reduces background work but can retain expired objects in memory until another operation encounters them.

## Failure Modes

A cache can become harmful when it is treated as an authoritative database. Cache entries are copies and can become stale unless invalidation and freshness rules are explicit.

A miss storm can occur when many requests discover the same missing or expired key simultaneously. Each request may then independently query the backing service. High-throughput systems can mitigate this with request coalescing, locking, or single-flight mechanisms.

An eviction storm can occur when the cache is too small for the working set. The system repeatedly removes objects and immediately reloads them, producing poor hit rates and unnecessary origin traffic.

A TTL that is too long can serve stale data. A TTL that is too short can produce excessive misses. TTL therefore expresses a freshness requirement as well as a memory-lifetime decision.

## Security Considerations

Sensitive values should not automatically be cached simply because they are technically cacheable.

Authentication and authorization data require particular care. A stale authorization decision can create a security failure if permissions change while an old decision remains cached.

TTL can reduce the exposure window for sensitive temporary data, but TTL is not a substitute for explicit invalidation when a security-sensitive event requires immediate revocation.

Cache keys should not unintentionally combine identities. A key that omits tenant, user, locale, permission scope, or another security boundary can cause one principal to receive another principal's cached data.

Cache contents should also be treated as potentially sensitive operational data. Logging complete cached values can leak credentials, personal data, tokens, or proprietary configuration.

## Common Design Mistakes

Using FIFO when the workload depends heavily on recent access can remove frequently used entries simply because they are old.

Using LFU without considering time can preserve historically popular entries after their popularity has disappeared.

Using LRU as though it were a freshness mechanism is incorrect. LRU says when an item was used, not whether its value is still valid.

Using TTL as the only capacity policy can leave a cache with many long-lived entries and no principled answer to which valid entry should be removed when capacity is reached.

Treating a cache hit as proof that the underlying data is current is unsafe unless the cache's freshness contract guarantees that property.

## Production Architecture

A practical read-through architecture separates the authoritative data source from the cache:

`Client -> Service -> Cache -> Origin Store`

A hit returns cached data without contacting the origin. A miss reads from the origin and populates the cache.

Eviction belongs inside the cache layer, while invalidation can originate from application events. For mutable business data, an update event can explicitly invalidate a key instead of waiting for its TTL.

Operational metrics should include hit rate, miss rate, eviction count, expiration count, cache size, origin request volume, and latency. These measurements reveal whether an eviction policy is actually improving the workload.

The central design relationship is therefore:

`LRU/LFU/FIFO -> capacity decision`

`TTL -> freshness/expiration decision`

`Application invalidation -> correctness after authoritative changes`

A robust cache design uses these mechanisms for their distinct purposes rather than treating them as interchangeable names for the same eviction behavior.
