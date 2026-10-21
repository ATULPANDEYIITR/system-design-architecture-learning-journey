# Distributed Caching with Redis, Memcached, and Cache Clusters

## Scope

This project models distributed caching as an application architecture rather than as a simple key/value data structure.

The central design is a cache-aside workflow:

Application → Cache Cluster → Source of Truth

A cache hit returns data without contacting the source of truth. A cache miss loads authoritative data, returns it to the application, and normally stores a copy in the cache. Writes update the authoritative data and require a deliberate invalidation or refresh strategy.

The implementations distinguish three related but different concerns:

| Concern | Role |
|---|---|
| Redis | Feature-rich in-memory datastore suitable for caching, persistence options, atomic operations, replication, and richer data structures |
| Memcached | Lightweight distributed memory cache focused on simple key/value caching |
| Cache cluster | Multiple cache nodes coordinated through key distribution, health handling, capacity management, and operational policies |

The project does not treat Redis and Memcached as interchangeable products. Their operational models and feature sets differ even when both are used to accelerate reads.

## Core Distributed-Caching Model

A distributed cache divides cached data across multiple nodes.

For a key such as `product:p100`, the application needs a deterministic method for selecting a cache owner:

`hash("product:p100") → cache-node`

A cluster therefore needs to address:

- key distribution
- node membership
- node failure
- node addition and removal
- expiration
- invalidation
- cache misses
- stale data
- capacity limits
- observability
- fallback to the authoritative source

A cache is normally an optimization rather than the authoritative database. If a cache node fails, the application should have a defined fallback rather than treating the cache as the only copy of business data.

## Cache-Aside Workflow

The Python, JavaScript, and Java implementations use cache-aside behavior.

The logical flow is:

`request`
→ `lookup cache`
→ `hit?`
→ yes: `return cached value`

or:

`request`
→ `lookup cache`
→ `miss`
→ `load authoritative data`
→ `populate cache`
→ `return value`

This separates availability of the cache from correctness of the source of truth.

The source of truth used in the examples is an in-memory repository. The SQL implementation models PostgreSQL as the authoritative relational system while recording cache metadata and operational events.

## Expiration and TTL

A time-to-live controls how long an entry is considered usable.

For an entry with creation time `t0` and TTL `T`:

`expiration = t0 + T`

A lookup after expiration is a cache miss.

TTL is useful when data naturally becomes stale, but it is not a substitute for invalidation when correctness requires immediate freshness.

The implementations use TTL for products and temporary data. The SQL model stores expiration timestamps and provides a query that identifies expired entries that have not yet been invalidated.

TTL selection is an application-level policy. A short TTL reduces stale-data duration but increases source-of-truth traffic. A long TTL improves cache effectiveness but increases the possible stale-data window.

## Cache Invalidation

The examples use explicit invalidation after a source-of-truth update.

A representative workflow is:

`update database`
→ `invalidate cache key`
→ `next read misses`
→ `reload current value`
→ `populate cache`

This prevents a previously cached product representation from remaining active after its authoritative value changes.

Invalidation is difficult in distributed systems because a logical object may have several related cache keys. For example, changing product `p100` could affect:

- `product:p100`
- `product:list:featured`
- `product:list:category:networking`
- `product:search:router`

A production cache design therefore needs explicit key naming and invalidation ownership.

## Redis and Memcached

### Redis

Redis is represented as a backend type in the examples.

Its broader feature set makes it appropriate when an application needs more than basic cached strings, such as atomic operations, counters, sets, sorted sets, streams, or configurable persistence and replication behavior.

The project does not emulate the full Redis command set. It models the architectural role of Redis nodes in a distributed cache.

### Memcached

Memcached is represented as a separate backend type.

Its design is intentionally simple: applications generally treat it as an ephemeral distributed key/value cache. The application is responsible for handling cache misses and retaining authoritative data elsewhere.

The JavaScript and SQL artifacts preserve the distinction between Redis and Memcached instead of presenting them as identical implementations.

## Cache Clustering

A cluster contains multiple cache nodes:

`Client`
→ `Cache Cluster`
→ `Node A`
→ `Node B`
→ `Node C`

The major advantage is that memory and request load can be distributed across machines.

The major engineering consequence is that the application can no longer assume that one local memory space contains all cached data.

Node membership therefore becomes a routing concern.

## Consistent Hashing

The Python, JavaScript, C++, and Java implementations model consistent hashing.

A hash ring places virtual positions for cache nodes around a logical circular key space.

For a key:

`hash(key)`

the selected node is the first node position at or after the key's hash value, wrapping around at the end of the ring.

Virtual nodes improve distribution by placing multiple positions on the ring for each physical node.

Without consistent hashing, adding one cache node can require large-scale reassignment of existing keys. With consistent hashing, only a portion of keys normally changes ownership.

The Python implementation measures remapped keys after adding a node. The JavaScript implementation performs the same type of ownership measurement. The C++ implementation focuses on a governance-style cache engine and reports distribution across nodes. The Java implementation uses a `TreeMap` to represent ordered hash-ring positions.

## Python Implementation

The Python artifact provides the broadest simulation of cache behavior.

It contains:

- `CacheNode` for individual Redis or Memcached nodes
- `CacheEntry` for values, expiration, and versions
- `ConsistentHashRing` for distributed key ownership
- `DistributedCache` for cache-aside access
- `Repository` for authoritative data
- node-health simulation
- TTL expiration
- invalidation
- node addition
- ownership remapping
- hit/miss statistics

`get_or_load()` demonstrates the cache-aside pattern while allowing cache failures to degrade into source-of-truth reads.

The implementation uses the Python standard library only.

The node-health simulation demonstrates an important production property: cache failure should not silently become data corruption.

## JavaScript Implementation

The JavaScript artifact uses Node.js-oriented asynchronous behavior.

It adds event-driven observability through `EventEmitter`. Cache nodes emit events for:

- hits
- misses
- expiration
- sets
- deletes

The cache API uses `async` functions so that the model corresponds naturally to real networked cache clients.

`ConsistentHashRing` uses SHA-256-derived 64-bit values and binary search over sorted virtual-node positions. The implementation therefore differs from the Python and Java examples in both hashing and lookup mechanics.

The JavaScript repository uses asynchronous delays to represent database latency.

This makes the performance effect of cache hits visible conceptually: a cache hit avoids the simulated authoritative lookup.

## C++ Implementation

The C++ artifact models distributed caching as a lower-level cache engine.

The design uses:

- `unordered_map` for node-local entries
- `map` for ordered hash-ring positions
- strongly typed backend and health enums
- explicit cache exceptions
- node capacity
- versioned cache values
- ownership lookup
- source-of-truth fallback

The `ConsistentHashRing` stores virtual node positions in a `std::map`, allowing ordered successor lookup.

The implementation deliberately avoids external libraries and focuses on data-structure behavior, ownership distribution, failure handling, and cache-aside interaction.

The C++ example also demonstrates how node state affects write operations. A failed node cannot accept cache writes.

## Java Implementation

The Java artifact models distributed caching as an enterprise domain.

It uses Java 17 records for immutable domain values:

- `Product`
- `CacheRecord`

Enums represent explicit domain policies and state:

- `Backend`
- `NodeState`
- `CachePolicy`

`CacheNode` owns cache entries and enforces readable and writable node states.

`ConsistentHashRing` uses `TreeMap<Long, CacheNode>` to provide ordered ring positions.

`CacheService` separates cache mechanics from repository operations. `MergeLikeWorkflow` represents an application service that changes authoritative data and invalidates the corresponding cache entry.

The design makes policy explicit through `CachePolicy.CACHE_ASIDE` rather than hiding consistency behavior inside low-level cache operations.

## PostgreSQL Model

The SQL implementation treats PostgreSQL as an operational model for distributed caching.

The main entities are:

| Table | Purpose |
|---|---|
| `repositories` | Applications and their authoritative repositories |
| `cache_clusters` | Cluster-level configuration |
| `cache_nodes` | Redis and Memcached node inventory |
| `applications` | Systems consuming cached data |
| `cache_keys` | Key ownership, version, expiration, and invalidation metadata |
| `cache_operations` | Operational cache events |
| `cache_policies` | TTL and freshness policies |

PostgreSQL enums constrain backend types, node states, and cache policies.

Foreign keys preserve relationships between clusters, nodes, keys, applications, and operational records.

Partial indexing is used for active cache-key expiration lookups:

`invalidated_at IS NULL`

This avoids indexing invalidated entries for queries concerned with currently active cache data.

## Database Integrity Rules

The SQL triggers enforce operational invariants.

A failed or draining cache node cannot become the owner of a newly inserted or updated cache key.

Successful cache operations cannot be recorded against a failed or draining node.

These checks are intentionally enforced at the database layer because application-only validation can be bypassed by another writer or operational process.

The database also validates:

- positive cache capacities
- positive TTL policies
- valid backend values
- valid node states
- non-empty identifiers
- non-negative operation latency
- failure reasons for unsuccessful operations
- valid replication and virtual-node counts

## Operational Reporting

The SQL queries provide several operational views without introducing a separate reporting system.

Active-cache reporting identifies non-invalidated, non-expired entries and their current nodes.

Hit/miss reporting groups cache operations by node and calculates successful lookup percentages.

Expiration reporting identifies entries whose TTL has elapsed.

Failed-node reporting detects keys still associated with failed nodes.

Latency reporting compares average operation latency by backend and operation type.

Policy reporting combines cluster configuration, TTL policy, node counts, and health state.

These queries demonstrate why cache infrastructure needs observability beyond simple hit-rate measurement.

## Failure Handling

Distributed caching introduces failure modes that are not present in a single-process in-memory cache.

Important cases include:

| Failure | Expected behavior |
|---|---|
| Cache miss | Load from authoritative source |
| Node unavailable | Fall back to authoritative source |
| Entry expired | Treat as miss and refresh |
| Stale entry after write | Invalidate or refresh |
| Node capacity exhausted | Evict according to cache policy |
| Node added | Rebalance key ownership |
| Node removed | Reassign affected keys |
| Invalid TTL | Reject the cache operation |
| Invalid key | Reject before network access |

A cache should not become a single point of failure merely because it was introduced to improve performance.

## Consistency Considerations

Caching introduces a second representation of data.

The authoritative representation and cached representation can temporarily differ.

Three common approaches are represented conceptually:

| Strategy | Behavior | Main trade-off |
|---|---|---|
| Cache-aside | Application loads and invalidates cache explicitly | Simple but requires disciplined invalidation |
| Write-through | Cache write participates directly in the write path | Better cache freshness but more coupling |
| TTL-only | Entries eventually expire | Simple but permits stale data until expiration |

The project primarily implements cache-aside because it clearly exposes the relationship between authoritative data, cache misses, and invalidation.

## Thundering Herd

If a frequently accessed key expires simultaneously for many clients, multiple requests can miss at once:

`many clients`
→ `same expired key`
→ `many database requests`

This is commonly called a cache stampede or thundering herd.

The provided implementations demonstrate cache-aside but do not pretend to provide distributed request coalescing.

Production systems can address this with techniques such as request locking, single-flight loading, staggered expiration, stale-while-revalidate policies, or controlled refresh workers.

Those mechanisms require careful coordination because a distributed lock introduces its own failure and timeout behavior.

## Hot Keys

Consistent hashing distributes keys, not necessarily requests.

A single extremely popular key can remain concentrated on one cache node:

`10,000,000 requests`
→ `product:popular`
→ `one owner`

Therefore balanced key distribution does not guarantee balanced request distribution.

Hot-key mitigation may require replication, application-level request coalescing, local near-cache layers, or workload-specific partitioning.

The correct approach depends on whether the workload is read-heavy, write-heavy, latency-sensitive, or strongly consistency-sensitive.

## Security Considerations

Cache keys should not contain unnecessary sensitive information.

Applications should avoid placing credentials, session secrets, authorization tokens, or confidential personal data into general-purpose caches unless the security architecture explicitly supports it.

Important controls include:

- network isolation for cache nodes
- authentication where supported
- encrypted connections where required
- restricted administrative access
- bounded key lengths
- controlled serialization
- validation of values before caching
- explicit TTL policies
- careful treatment of multi-tenant keys

Key namespaces should separate tenants and environments when shared infrastructure is used.

A key such as `user:123` can be unsafe in a multi-tenant environment if tenant identity is not represented in the namespace and authorization is not independently enforced.

## Performance Characteristics

For a distributed cache using a hash ring:

- hash-ring lookup is approximately `O(log N)` with ordered ring positions
- local key lookup is approximately `O(1)` for hash-table storage
- cache hit avoids the latency of the authoritative database
- adding nodes requires rebuilding or updating ownership metadata
- virtual nodes improve distribution but increase ring metadata

The dominant production cost is usually not the hash computation. Network latency, serialization, cache contention, database fallback, memory pressure, and cross-node traffic often matter more.

A high cache hit rate is useful only when the cached response is correct, sufficiently fresh, and cheaper to retrieve than the authoritative representation.

## Production Design Boundaries

The examples intentionally simulate distributed behavior rather than implementing complete production Redis or Memcached clients.

They do not attempt to reproduce:

- Redis replication protocols
- Redis Cluster slot migration
- Redis Sentinel
- Memcached's complete wire protocol
- TLS negotiation
- distributed consensus
- cross-region replication
- persistence recovery
- production-grade connection pooling
- distributed locking guarantees

The architectural concepts remain applicable: a real deployment must add the corresponding infrastructure-specific behavior rather than assuming that an in-process simulation provides those guarantees.

## Relationship Between the Implementations

The five source files approach the same distributed-cache domain from different engineering perspectives.

| Implementation | Primary perspective |
|---|---|
| Python | Repository-backed cache workflow simulation |
| JavaScript | Asynchronous and event-driven cache behavior |
| C++17 | Data structures, node ownership, capacity, and failure handling |
| Java 17 | Enterprise domain modeling and explicit cache policies |
| PostgreSQL | Relational infrastructure model, integrity, operational events, and reporting |

They are deliberately not line-by-line translations of one another.

The common architectural relationship is:

`Authoritative Data`
→ `Cache Policy`
→ `Distributed Cache`
→ `Node Selection`
→ `Cache Entry`
→ `Expiration / Invalidation`
→ `Application Response`

The implementation differences show how the same distributed-caching requirements map onto different programming models, data structures, concurrency assumptions, and persistence mechanisms.
