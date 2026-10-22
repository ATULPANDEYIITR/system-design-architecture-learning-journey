# Cache Failure Patterns: Stampede, Penetration, and Avalanche

## Scope

This project models three distinct cache failure patterns that can turn a cache from a performance layer into a source of origin overload:

| Pattern | Primary cause | Characteristic symptom | Main controls |
|---|---|---|---|
| Cache stampede | One hot entry expires while many callers request it simultaneously | A large concurrent backend load for one key | Single-flight refresh, request coalescing, stale-while-revalidate |
| Cache penetration | Requests repeatedly target data that does not exist or should never be cached | Persistent origin traffic for invalid or nonexistent keys | Negative caching, key validation, admission filters |
| Cache avalanche | Many independent entries expire or become unavailable in a correlated interval | Broad origin-load spike across many keys | TTL jitter, staggered expiration, stale serving, capacity controls |

The three mechanisms must not be treated as synonyms. A stampede is primarily a concurrency problem around a hot key. Penetration is primarily an admission and nonexistent-data problem. An avalanche is primarily a correlated-expiration or broad-cache-availability problem.

The relationship can be represented as:

`Request -> Cache decision -> Fresh hit / stale hit / miss -> Origin -> Refresh`

with different failure points:

`many callers + one expired key -> STAMPEDE`

`invalid or nonexistent key -> PENETRATION`

`many keys expire together -> AVALANCHE`

## Cache Stampede

A cache stampede occurs when a popular cache entry expires and a large number of requests discover the miss at approximately the same time.

Without coordination, a simplified sequence is:

`Client A -> miss -> origin`
`Client B -> miss -> origin`
`Client C -> miss -> origin`
`Client N -> miss -> origin`

Every request independently performs the same expensive refresh.

The important characteristic is that the key may be valid and the origin may be healthy. The failure is caused by concurrent refresh behavior.

### Single-flight refresh

The implementations coordinate refreshes per cache key.

Python uses a per-key `Lock`. The first caller acquires the lock and performs the backend operation. Other callers wait and then re-check the cache.

JavaScript uses a `Map` of in-flight `Promise` objects. Concurrent callers requesting the same key receive the same asynchronous operation rather than creating independent backend operations.

Java uses `ConcurrentHashMap<K, CompletableFuture<Optional<V>>>`. `putIfAbsent` selects one refresh future for a key, allowing other callers to join that future.

C++ uses a per-key refresh state containing a condition variable. The first caller performs the load while other threads wait for completion.

The important invariant is:

`one cache key + one active refresh`

rather than:

`one cache key + one refresh per caller`.

### Double-checking after coordination

The Python implementation checks the cache again after acquiring the per-key lock. This prevents an unnecessary second origin request when another operation populated the key just before the waiting caller obtained the lock.

The same principle appears in asynchronous and concurrent implementations through shared refresh state.

Single-flight does not make the origin infinitely scalable. It reduces duplicate work for a particular key. If thousands of different keys miss simultaneously, other protections are still necessary.

## Cache Penetration

Cache penetration occurs when traffic targets data that does not exist or should not be allowed into the cache.

For example:

`GET product:404`

may repeatedly miss the cache and then query the database. If an attacker or malfunctioning client generates many nonexistent identifiers, the cache provides little protection because every request can reach the origin.

### Negative caching

Negative caching stores the fact that an object does not exist.

Conceptually:

`product:404 -> NULL -> short negative TTL`

The next request can terminate at the cache rather than querying the source again.

Negative TTLs should normally be shorter than normal positive TTLs. Source data can appear later, and an excessively long negative entry can hide a newly created object.

The Python, JavaScript, Java, and PostgreSQL implementations explicitly distinguish negative entries from ordinary cached objects.

### Key admission

Negative caching alone does not solve every penetration problem. Requests can use malformed, untrusted, or effectively unbounded key spaces.

The implementations therefore validate keys before backend access.

Examples of rejected input include:

`../../secret`

or other values outside the accepted cache-key grammar.

The PostgreSQL function `evaluate_cache_key` applies a regular-expression key policy. The application implementations apply equivalent admission rules.

An admission filter should be used carefully. Rejecting a valid key because it has not previously been observed can cause legitimate traffic to fail. An allowlist is most appropriate when the valid key universe is known or can be maintained reliably.

## Cache Avalanche

A cache avalanche occurs when a large population of cache entries becomes unavailable during the same period.

A common cause is synchronized expiration:

`T = 10:00:00 -> thousands of keys expire`

If those keys are popular, the origin suddenly receives requests that were previously absorbed by the cache.

The same effect can occur when an entire cache cluster becomes unavailable. In that case, TTL jitter alone cannot solve the problem because the cache service itself has failed.

### TTL jitter

The implementations randomize TTLs around a configured base value.

For a base TTL `T` and jitter ratio `j`, an expiration can be selected from approximately:

`T - Tj <= TTL <= T + Tj`

For example, a 60-second TTL with 20% jitter produces values around the 48-to-72-second range.

This spreads expiration events instead of making a large set of entries expire at one timestamp.

Jitter changes timing rather than reducing the total amount of eventual refresh work. It is therefore a distribution mechanism, not a replacement for capacity planning.

### Stale-while-revalidate

The implementations also support a short stale grace period.

Instead of immediately turning an expired object into a miss:

`expired -> origin`

the system can temporarily use:

`expired but within grace -> serve stale + refresh`

This is useful for read-heavy workloads where a slightly old value is preferable to an origin outage or latency spike.

The trade-off is explicit consistency. A stale value may violate freshness requirements. Financial balances, authorization state, inventory constraints, and other strongly consistent data may require different policies.

## Python Implementation

The Python file models a complete cache service around a backend loader.

`CacheEntry` stores the value and expiration time. `CacheMetrics` records operational behavior such as hits, misses, backend reads, negative hits, rejected penetration attempts, and single-flight waiters.

`SafeCache` combines several controls:

- Per-key locking prevents duplicate concurrent refreshes.
- Negative TTLs absorb repeated missing-object requests.
- TTL jitter distributes expiration.
- A stale grace period permits limited stale reads.
- Key admission validation rejects malformed or untrusted identifiers.
- Explicit invalidation allows source-of-truth updates to remove cached state.

The threaded stampede scenario creates many workers after expiration. The metric `singleflight_waiters` makes contention observable.

The penetration scenario separates two cases: a legitimate nonexistent product that can be negative-cached and an invalid identifier rejected before reaching the backend.

The avalanche demonstration compares expiration spread with and without TTL jitter.

## JavaScript Implementation

The JavaScript implementation uses Node.js asynchronous execution rather than translating the Python locking model.

Its central mechanism is the `inFlight` map:

`cache key -> Promise`

A request that encounters an existing promise joins the refresh. This is naturally suited to an event-driven Node.js service because multiple requests can await one asynchronous backend operation without creating one backend operation per caller.

The implementation also demonstrates:

- Promise-based backend access
- Negative caching
- Regular-expression key validation
- TTL jitter
- Stale-while-revalidate
- Explicit invalidation
- Operational metrics
- Error conversion into a domain-specific `CacheError`

The stale path deliberately returns the old value immediately and schedules a refresh. This prevents a large number of callers from waiting for the same backend operation.

## C++ Implementation

The C++ program treats cache protection as a concurrent systems problem.

`OriginStore` represents a source of truth protected by `shared_mutex`. Reads can share the read lock while writes acquire exclusive access.

`CacheFailureEngine` maintains separate synchronization domains:

- Cache state uses `cacheMutex`.
- Refresh ownership uses `inFlightMutex`.
- Per-refresh waiting uses a condition variable.
- Metrics use `metricsMutex`.

This separation avoids turning the entire cache into one globally serialized critical section.

The C++ design also makes the performance trade-off explicit. Per-key coordination allows unrelated keys to refresh concurrently while preventing duplicate work for the same key.

The key validator limits accepted cache-key syntax. This is an operational and security boundary rather than merely a formatting rule.

## Java Implementation

The Java program represents cache behavior as an enterprise domain service.

`CachePolicy` captures operational rules:

- normal TTL
- negative TTL
- stale grace period
- jitter ratio
- unknown-key rejection

`CacheEntry` is immutable and records whether the entry represents a negative result.

`CacheService` uses `ConcurrentHashMap` for cache entries and another concurrent map for refresh futures.

The `CompletableFuture` map provides asynchronous single-flight behavior:

`key -> active refresh`

The first refresh becomes the shared operation. Later requests join it.

Java records provide compact immutable domain values for products, policies, entries, and metrics. `Optional` distinguishes the absence of a source object from an actual object value.

The enterprise model also includes explicit invalidation after a source update. This is important because TTL expiration is not the only reason cached state becomes incorrect.

## PostgreSQL Model

The SQL implementation represents cache behavior relationally rather than treating the database as a simple key-value store.

The main entities are:

| Table | Purpose |
|---|---|
| `repository` | Associates cache configuration with an application environment |
| `cache_namespace` | Defines TTL, negative TTL, jitter, stale grace, and admission policy |
| `source_object` | Represents the authoritative source data |
| `cache_entry` | Represents cached positive, negative, stale, or expired state |
| `refresh_request` | Provides a durable model for refresh coordination |
| `failure_event` | Records stampede, penetration, and avalanche observations |
| `cache_request` | Stores request-level cache outcomes and backend calls |

Constraints enforce positive TTLs, valid jitter ranges, valid stale windows, and relational integrity.

The `calculate_expiration` function implements randomized TTLs.

The `refresh_cache_entry` function demonstrates both positive and negative caching. A missing source object creates a `NEGATIVE` cache entry with a shorter expiration.

The `evaluate_cache_key` function provides an explicit policy decision for whether a key should call the backend, whether stale data may be served, and why.

The `cache_health_report` view combines recent request traffic and failure events for operational analysis.

The final CTE calculates backend-call ratios. A high backend-to-request ratio can indicate poor cache effectiveness, synchronized expiration, insufficient TTLs, or a failure pattern.

## Distinguishing the Controls

The controls operate at different layers.

| Control | Stampede | Penetration | Avalanche |
|---|---:|---:|---:|
| Per-key single-flight | Primary | Not sufficient | Partial |
| Negative caching | No | Primary | No |
| Key validation | No | Primary | No |
| TTL jitter | Secondary | No | Primary |
| Stale-while-revalidate | Primary mitigation | No | Primary mitigation |
| Explicit invalidation | Useful | No | Useful |
| Capacity planning | Required | Required | Required |
| Monitoring | Required | Required | Required |

The distinction matters because applying the wrong control can leave the actual failure mechanism unchanged.

For example, adding negative caching does not prevent a hot valid key from causing a stampede. Adding TTL jitter does not stop an attacker from generating thousands of nonexistent identifiers. Single-flight for one key does not prevent thousands of different keys from expiring together.

## Operational Metrics

Useful metrics include:

- cache hit rate
- negative-cache hit rate
- backend reads per second
- refreshes per second
- concurrent refreshes by key
- number of deduplicated requests
- stale responses served
- rejected invalid keys
- negative-cache creation rate
- expiration distribution
- origin latency
- cache latency
- backend error rate

A particularly useful stampede indicator is:

`backend refreshes / requests for the same hot key`

A penetration indicator is:

`requests for nonexistent keys / total requests`

An avalanche indicator is:

`expired keys in time window / total active keys`

These metrics should be correlated with backend CPU, database connection usage, queue depth, latency, and error rates.

## Edge Cases and Failure Conditions

### Backend failure during refresh

Single-flight prevents duplicate work, but it does not make a failed backend request succeed.

A production service needs a defined failure policy, such as:

`fresh -> stale -> backend -> controlled failure`

rather than allowing an unbounded retry loop.

Retry policies should use bounded attempts and backoff. Otherwise, retries can amplify the same origin overload that caused the failure.

### Negative-cache poisoning

Negative entries must have appropriate expiration policies. If a previously missing object is created, an excessively long negative TTL can continue returning the old negative result.

Applications that create important objects should explicitly invalidate the negative cache entry.

### Hot-key concentration

A cache can have a high overall hit rate while still suffering from one extremely hot key. Monitoring should therefore include per-key distributions, not just aggregate hit rate.

### Stale data

Stale-while-revalidate improves availability but deliberately relaxes freshness.

The acceptable stale period depends on the data. Product descriptions may tolerate seconds or minutes. Authorization decisions may not.

### Cache cluster failure

TTL jitter does not protect against complete cache infrastructure loss.

When an entire cache cluster disappears, the system needs broader protection such as origin rate limiting, admission control, load shedding, fallback responses, replicas, or controlled warm-up.

## Performance Considerations

Single-flight changes concurrent origin work from approximately:

`O(number of simultaneous callers)`

toward:

`O(1 refresh per key)`

for a single hot key during a refresh interval.

The cost is coordination state and waiting time.

Negative caching converts repeated missing-object requests into inexpensive cache operations after the first lookup.

TTL jitter has negligible computational cost compared with backend access but changes expiration distribution.

Stale-while-revalidate trades freshness for lower latency and reduced origin pressure.

Per-key synchronization is preferable to one global cache lock for high-cardinality workloads because unrelated keys should not block one another.

## Security Considerations

Cache-key validation prevents malformed identifiers from becoming backend requests.

Negative caching can reduce the impact of random identifier probing, but it is not an authentication or authorization mechanism.

Authorization-sensitive responses should not be cached solely by a resource identifier when the result depends on user identity, tenant identity, permissions, or session state.

Cache keys must include all security-relevant dimensions required to distinguish responses. A cache-key collision across tenants can become a data-isolation vulnerability.

Sensitive payloads should also follow appropriate encryption, access-control, logging, and retention policies.

## Design Relationships

The three failure patterns form different relationships between traffic, cached state, and the origin:

`Stampede`
`one hot key + simultaneous misses -> duplicate refresh work`

`Penetration`
`invalid/nonexistent key + repeated misses -> unnecessary origin work`

`Avalanche`
`many keys + correlated expiration/unavailability -> broad origin load`

Their controls therefore address different mechanisms:

`single-flight -> concurrency`

`negative caching/admission -> invalid or nonexistent demand`

`jitter/stale serving -> expiration correlation`

A resilient cache normally combines these controls instead of relying on a single technique.
