# Content Delivery Networks: Edge Servers, Caching, and Geographic Distribution

## Scope

This project models a Content Delivery Network (CDN) as a distributed content-delivery system positioned between clients and an origin service.

The five implementations use a common technical domain while emphasizing different engineering perspectives:

| Implementation | Primary perspective | Main mechanisms |
|---|---|---|
| Python | CDN workflow simulation | Dataclasses, cache state, routing, validation, metrics |
| JavaScript | Event-driven CDN service | Promises, events, Maps, asynchronous origin access |
| C++17 | Performance-oriented edge engine | STL containers, explicit state, routing and failure handling |
| Java 17 | Enterprise domain model | Records, interfaces, policy objects, services, explicit states |
| PostgreSQL | Persistent CDN control plane | Relational integrity, triggers, functions, indexes, transactions |

The central distinction is between the origin, edge infrastructure, cache state, routing decisions, and the request lifecycle.

A simplified architecture is:

    Client
       |
       v
    Geographic Routing
       |
       v
    Nearest Suitable Edge
       |
       +---- Cache HIT --------> Client
       |
       +---- Cache MISS
                 |
                 v
              Origin
                 |
                 v
           Edge Cache Fill
                 |
                 v
              Client

The purpose is not to reproduce a commercial CDN. The implementations provide executable models of the mechanisms that make geographically distributed caching work.

## Core CDN Model

A CDN reduces the distance between clients and frequently requested content by maintaining copies at edge locations.

The important entities are:

| Entity | Responsibility |
|---|---|
| Origin | Authoritative source of content |
| Edge server | Serves requests close to clients |
| Cache entry | Stores a temporary representation of origin content |
| Client region | Input to geographic routing |
| Cache policy | Determines whether content may be cached |
| TTL | Determines how long a cached representation remains fresh |
| Invalidation | Removes cached content before natural expiration |
| Health state | Determines whether an edge should receive traffic |
| Request | Records delivery behavior and latency |

The implementations distinguish origin truth from edge state. An edge can contain an older version even though the origin already contains a newer version.

## Edge Servers

An edge server is a geographically distributed delivery point. It is not the authoritative source of content in this model.

Each edge maintains:

- an identifier
- a geographic region
- a health state
- a cache capacity
- a base processing latency
- cache entries
- cache performance counters

The supported states are:

| State | Routing behavior |
|---|---|
| `HEALTHY` | Normal candidate for routing |
| `DEGRADED` | Available with a substantial routing penalty |
| `OFFLINE` | Excluded from routing |

The health state is intentionally separated from cache state. An edge can have valid cached content while still being unsuitable for new traffic because of infrastructure health.

## Geographic Distribution

Geographic routing attempts to select an edge that minimizes delivery latency while respecting edge health.

The executable models use a simplified score:

    score =
        geographic_latency
        + edge_processing_latency
        + health_penalty

A healthy edge receives no health penalty. A degraded edge receives a large penalty, while an offline edge is excluded.

This is a teaching model rather than a complete global traffic-management system. Real systems may consider network telemetry, routing protocols, DNS behavior, anycast, congestion, capacity, load, packet loss, availability zones, and provider-specific traffic policies.

The important design principle is that geographic proximity alone is insufficient. The nearest edge is not always the best operational edge.

## Caching

Caching is the central data-plane mechanism.

A request follows this basic path:

    Request
       |
       v
    Edge lookup
       |
       +---- Fresh entry ----> HIT
       |
       +---- Missing/stale --> Origin fetch
                                  |
                                  v
                              Cache fill
                                  |
                                  v
                                Response

The implementations distinguish:

| Result | Meaning |
|---|---|
| `HIT` | A fresh cached representation served the request |
| `MISS` | The edge did not have a usable representation |
| `STALE` | A cached representation existed but had expired |
| `BYPASS` | Shared caching was intentionally skipped |
| `ORIGIN_ERROR` | The request could not be completed from the origin |

A cache hit normally has lower modeled latency than an origin request because the content does not need to travel from the origin to the edge for that request.

## TTL and Freshness

Time-to-live controls cache freshness.

The Python, C++, JavaScript, and Java implementations store a cache insertion time and compare it with the configured TTL.

The PostgreSQL implementation represents this explicitly through `stored_at` and `expires_at`.

The conceptual rule is:

    fresh when:
        current_time < expires_at

When an entry becomes stale, the model removes it before fetching a current representation.

TTL is a consistency-versus-performance control:

| Short TTL | Long TTL |
|---|---|
| Faster propagation of origin changes | Higher cache-hit potential |
| More origin traffic | Lower origin traffic |
| Lower stale-content window | Longer stale-content window |

TTL does not guarantee immediate propagation. Explicit invalidation is required when a change must reach edges before natural expiration.

## Cache Eviction

The Python and JavaScript implementations use bounded caches.

The Python implementation uses an `OrderedDict` to maintain LRU-style ordering.

The JavaScript implementation uses `Map` insertion order to implement a compact LRU-style policy.

The Java implementation uses `LinkedHashMap` with access ordering.

The C++ implementation uses an unordered cache with deterministic entry removal when capacity is exceeded. Its purpose is to emphasize low-level data structures and explicit resource boundaries rather than reproduce a full production LRU implementation.

Cache capacity creates an important trade-off:

    larger cache
        -> more retained objects
        -> potentially higher hit ratio
        -> higher memory requirement

    smaller cache
        -> lower memory use
        -> more evictions
        -> potentially more origin requests

## Cache Invalidation

TTL expiration is passive invalidation. The content remains cached until the expiration condition is reached.

Explicit invalidation is active invalidation.

The implementations support invalidating a path across edge servers. The PostgreSQL implementation records the invalidation in an `invalidations` table and performs cache deletion transactionally.

A typical deployment sequence is:

    Publish new origin version
             |
             v
    Record invalidation
             |
             v
    Remove cached copies
             |
             v
    Next request obtains new version
             |
             v
    Edge caches new representation

This mechanism matters when an old representation cannot remain available until its TTL expires.

## Origin Servers

The origin is authoritative in the model.

It stores versioned content such as:

- JavaScript assets
- SVG images
- private JSON
- other static resources

Each published version has an explicit version number.

For example:

    /static/app.js
        version 1
        version 2

An edge may still hold version 1 after version 2 has been published at the origin. This demonstrates why cache invalidation and freshness policies are necessary.

Origin availability is also modeled as an explicit state. When the origin becomes unavailable, the implementations return an origin failure rather than allowing an exception to terminate the entire CDN simulation.

A production CDN may apply stale serving, retry policies, origin shielding, failover origins, circuit breakers, or other resilience mechanisms.

## Private Content and Cache Bypass

Shared caching can create a security problem when personalized or sensitive content is accidentally stored in a shared cache.

The implementations therefore treat paths beginning with `/private/` as non-shared content.

The rule is:

    private content
        -> authentication required
        -> shared cache bypass
        -> origin retrieval

The PostgreSQL database enforces this at database level through the `prevent_private_cache` trigger.

The request-validation trigger also rejects unauthenticated requests for private paths.

This illustrates an important architectural principle: security-sensitive invariants should not depend exclusively on application-level discipline.

## Python Implementation

The Python program is a complete simulation of CDN request processing.

Its main domain types are:

- `Content`
- `CacheEntry`
- `EdgeServer`
- `OriginServer`
- `CDN`
- `RequestResult`

`Content` is immutable through a frozen dataclass. It stores path, body, type, version, caching eligibility, and TTL.

`EdgeServer` owns cache state and implements:

- lookup
- freshness validation
- cache insertion
- bounded eviction
- invalidation
- hit and miss accounting

The `CDN` class coordinates geographic routing, security validation, edge lookup, origin retrieval, cache population, and metrics.

The routing model selects a non-offline edge using geographic distance, base latency, and health state.

The demonstration also covers:

- cache hits
- origin misses
- private-content bypass
- content version changes
- explicit invalidation
- origin failure
- malformed path rejection
- metrics
- assertions

The path validation rejects traversal-like paths containing `..`, null bytes, oversized paths, and paths that do not begin with `/`.

## JavaScript Implementation

The JavaScript file models the CDN as an event-driven service.

JavaScript-specific mechanisms include:

- `Map`
- `EventEmitter`
- Promises
- asynchronous origin retrieval
- immutable status constants
- object-oriented domain classes

`OriginServer.fetch()` introduces an asynchronous boundary using a Promise. This represents the network behavior of a real origin request without requiring an external HTTP service.

The CDN emits events such as:

- `cacheHit`
- `originFetch`
- `originError`
- `invalidation`

This makes operational events observable without coupling the CDN request method directly to a particular logging implementation.

The JavaScript cache uses `Map` insertion order to maintain a compact LRU-style policy.

The demonstration changes an edge from healthy to degraded and then performs a request. The routing policy penalizes that edge, allowing another healthy edge to become preferable.

The implementation also demonstrates asynchronous origin failure handling without an uncaught process exception.

## C++17 Implementation

The C++ program focuses on an explicit performance-oriented engine.

Its principal types are:

- `Content`
- `CacheEntry`
- `RequestResult`
- `OriginServer`
- `EdgeServer`
- `CdnGovernanceEngine`

The implementation uses STL containers including:

- `unordered_map`
- `vector`
- `map`
- `optional`

`std::optional` represents the absence of a usable cached object without using sentinel values.

The engine explicitly validates:

- cache capacity
- latency
- TTL
- content paths
- edge availability

The request path distinguishes private content, cache lookup, origin retrieval, cache insertion, and origin failure.

The C++ implementation intentionally does not attempt to reproduce every higher-level abstraction used in the Java implementation. It exposes the state-management and data-structure decisions more directly.

The main performance characteristics are:

| Operation | Typical modeled complexity |
|---|---|
| Edge lookup by cache key | Average O(1) |
| Cache insertion | Average O(1) |
| Cache invalidation | Average O(1) |
| Edge selection | O(E) |
| Aggregated metrics | O(E) |

`E` represents the number of edge servers.

## Java 17 Implementation

The Java implementation represents CDN behavior using explicit enterprise-style domain boundaries.

It uses:

- records
- interfaces
- enums
- immutable value-oriented content records
- collections
- custom exceptions
- service classes
- policy objects
- streams

`CachePolicy` separates caching decisions from request orchestration.

`StandardCachePolicy` determines whether an object can be shared and whether private content requires authentication.

`RoutingPolicy` is responsible for geographic edge selection.

`OriginService` owns authoritative content and origin availability.

`EdgeNode` owns edge cache state.

`CdnService` coordinates the complete request lifecycle.

This separation prevents the routing algorithm, cache policy, origin behavior, and request workflow from becoming one monolithic class.

The enterprise-oriented design also makes policy behavior replaceable. A different implementation of `CachePolicy` can introduce alternative caching rules without rewriting the request service.

## PostgreSQL Implementation

The PostgreSQL script models the CDN control plane as relational data.

The schema contains:

- `regions`
- `origins`
- `edge_servers`
- `geographic_latency`
- `objects`
- `cache_entries`
- `cdn_requests`
- `invalidations`

The relationship can be represented as:

    Region
      |
      +---- Origin
      |
      +---- Edge Server
                 |
                 +---- Cache Entry
                            |
                            v
                          Object

    Client Request
          |
          +---- Region
          +---- Edge
          +---- Object

The database uses primary keys, foreign keys, uniqueness constraints, check constraints, indexes, functions, triggers, CTEs, and transactions.

### Database Constraints

Important rules are enforced close to the data.

Examples include:

- edge capacity must be positive
- latency cannot be negative
- TTL cannot be negative
- paths must begin with `/`
- paths containing `..` are rejected
- cache expiry must follow storage time
- private objects cannot be inserted into shared cache state
- unauthenticated private requests are rejected

The `prevent_private_cache` trigger prevents an application from bypassing the shared-cache security invariant accidentally.

### Routing Function

`select_edge()` calculates an effective latency for candidate edges.

The calculation includes:

    geographic latency
    + edge base latency
    + degraded-state penalty

Offline edges are excluded.

The function returns the lowest-latency eligible edge.

This is a relational representation of a routing decision rather than an attempt to implement a global DNS or anycast system inside PostgreSQL.

### Current Object Resolution

`current_object()` selects the highest version currently available at the origin for a path.

The query uses descending version order and returns one row.

This provides a clear distinction between:

- historical content versions
- the currently selected origin representation
- edge cache entries

### Cache State Reporting

The cache report identifies entries as either `FRESH` or `STALE` by comparing `expires_at` with the current timestamp.

This allows operational queries to identify cache entries requiring refresh.

### Request Analytics

The request table supports reporting by:

- edge
- region
- request status
- latency
- time
- authentication state

The reporting query calculates hit counts, miss counts, hit percentage, and average latency.

The index on `(requested_at, status)` supports time-oriented operational analysis, while `(edge_id, requested_at)` supports edge-specific request analysis.

### Transactions

The invalidation workflow is transactional.

The transaction:

1. records the invalidation request
2. removes matching cache entries
3. marks the invalidation complete
4. commits the complete operation

If the transaction fails before commit, PostgreSQL can roll back the changes together.

This is important because recording an invalidation without removing the cache or deleting the cache without recording the invalidation could create inconsistent operational state.

## Failure Handling

The implementations explicitly model several failure conditions.

| Failure | Model behavior |
|---|---|
| Malformed path | Request rejected |
| Path traversal pattern | Request rejected |
| Missing origin object | Origin error |
| Origin unavailable | Origin error |
| No available edge | Routing failure |
| Offline edge | Excluded from routing |
| Degraded edge | Penalized during routing |
| Expired cache entry | Treated as stale |
| Full cache | Existing entry evicted |
| Unauthenticated private request | Cache bypass and rejection |
| Private object cache insertion | Database trigger rejection |

A real CDN can have additional failure domains such as regional network partitioning, DNS failures, TLS failures, certificate expiration, origin overload, routing convergence problems, cache poisoning, and stale-if-error behavior.

## Security Considerations

The model includes several basic security controls.

### Path Validation

Paths are validated before cache or origin access.

The implementations reject:

- paths without a leading slash
- paths containing `..`
- null-byte input where applicable
- excessively long paths

This reduces the risk of treating attacker-controlled paths as trusted resource identifiers.

### Private Content

Private content bypasses shared caching.

This prevents a response associated with one authenticated user from being treated as universally reusable content.

Real systems must also distinguish public and private cache keys, authentication headers, cookies, authorization context, and cache-control directives.

### Cache Poisoning

A CDN must ensure that attacker-controlled request attributes cannot cause an unsafe response to be stored under a reusable cache key.

The model uses a simple path-based key and therefore intentionally does not attempt to implement the complete HTTP cache-key model.

### Origin Protection

An origin outage is handled as an explicit failure state.

Production systems commonly add rate limiting, retries with limits, circuit breakers, origin shielding, connection pooling, and overload controls.

## Performance Considerations

The major performance benefit of edge caching is reducing repeated origin requests.

For a cacheable object:

    first request
        -> origin
        -> edge cache

    subsequent fresh requests
        -> edge cache

The modeled latency therefore distinguishes edge delivery from origin retrieval.

Cache hit ratio is calculated as:

    hit ratio = cache hits / total requests

A higher hit ratio is generally beneficial, but it is not sufficient as a standalone performance metric.

Other important measurements include:

- edge latency
- origin latency
- origin request rate
- cache eviction rate
- stale response rate
- error rate
- regional traffic distribution
- edge availability

The Python, JavaScript, and Java implementations calculate cache-related metrics. The PostgreSQL model supports persistent aggregation over request history.

## Cache Consistency

CDNs trade strict origin freshness for delivery efficiency.

The basic consistency sequence is:

    Origin version 1
          |
          v
    Edge caches version 1
          |
          v
    Origin publishes version 2
          |
          +--------------------+
          |                    |
          v                    v
    Wait for TTL          Explicit invalidation
          |                    |
          v                    v
    Edge refreshes       Edge removes old copy

The choice between TTL-based freshness and invalidation depends on application requirements.

Static assets with versioned filenames can often tolerate long cache lifetimes.

Frequently changing or operationally sensitive resources may require shorter TTLs or explicit invalidation.

## Relationship Between the Five Implementations

The implementations represent the same CDN domain at different architectural boundaries.

The Python model emphasizes simulation and validation.

The JavaScript model emphasizes asynchronous behavior and event emission.

The C++ model emphasizes explicit state, STL data structures, and performance-oriented control.

The Java model emphasizes domain separation and replaceable policy objects.

The PostgreSQL model emphasizes persistent state, relational integrity, reporting, and transactional workflows.

They are complementary rather than line-by-line translations.

## Edge Cases

The demonstrations cover several cases that are easy to miss in a basic cache example:

- repeated requests for the same object
- content version replacement
- stale cache entries
- bounded cache capacity
- explicit invalidation
- private content
- missing content
- origin outage
- degraded edges
- offline edges
- malformed paths
- geographic latency
- authentication requirements

One important edge case is the difference between an origin update and cache invalidation. Updating the origin does not automatically delete an existing edge representation.

Another is the difference between an unavailable edge and an unavailable origin. An offline edge can be avoided through routing. An origin outage affects cache misses and refresh operations unless another origin or resilience mechanism exists.

## Design Limitations

The implementations intentionally simplify several production CDN mechanisms.

They do not implement:

- real DNS resolution
- BGP or anycast routing
- HTTP/2 or HTTP/3
- TLS termination
- compression negotiation
- range requests
- complete HTTP cache-control semantics
- Vary-based cache keys
- signed URLs
- distributed cache coherence protocols
- multi-origin failover
- real network telemetry
- distributed consensus
- persistent object storage
- actual edge-to-origin network connections

The simplifications preserve the central concepts while keeping each implementation executable and inspectable.

## Practical Request Lifecycle

A complete modeled request can be represented as:

    1. Validate request path
           |
    2. Determine whether content may be shared
           |
    3. Select a suitable geographic edge
           |
    4. Check edge cache
           |
       +---+---+
       |       |
      HIT    MISS/STALE
       |       |
       |       v
       |     Query origin
       |       |
       |       v
       |   Cache if allowed
       |       |
       +---+---+
           |
           v
        Response

The architecture deliberately separates the stages so that routing, caching, origin retrieval, security policy, and persistence can evolve independently.

## Educational Focus

The technical distinctions represented by the project are:

| Concept | Core question |
|---|---|
| Edge server | Where should content be delivered from? |
| Geographic distribution | Which location is operationally suitable? |
| Cache | Can the request be served without contacting the origin? |
| TTL | How long is the cached representation considered fresh? |
| Invalidation | How can cached content be removed before expiry? |
| Origin | What is the authoritative representation? |
| Health state | Can an edge safely receive traffic? |
| Cache policy | Is this content safe and useful to cache? |
| Request metrics | How effectively is the CDN serving traffic? |
| Database constraints | Which CDN invariants must remain true regardless of application behavior? |

The resulting model treats a CDN as a coordinated system of geographic routing, distributed caches, origin services, policies, health state, security controls, and persistent operational data rather than as a simple key-value cache.
