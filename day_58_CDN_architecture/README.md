# CDN Architecture: Origin Servers, Edge Locations, and Cache Policies

## Scope

This project models a Content Delivery Network as a distributed caching layer between clients and origin infrastructure.

The five implementations use the same architectural concepts while deliberately emphasizing different engineering perspectives:

| Implementation | Primary perspective | Main mechanisms |
|---|---|---|
| Python | CDN workflow simulation | Classes, dataclasses, LRU cache, TTL, revalidation, routing |
| JavaScript | Event-driven CDN service model | Maps, Promises, asynchronous origin access, events |
| C++17 | High-performance governance and cache engine | STL containers, explicit cache state, policy evaluation |
| Java 17 | Enterprise domain model | Records, immutable collections, services, policies |
| PostgreSQL | Persistent operational model | Relational schema, constraints, triggers, views, functions, transactions |

The central CDN relationship is:

`Client → Edge Location → Cache Policy → Origin Server`

A cache hit terminates the request at the edge. A cache miss, expired object, or cache bypass can require an origin request.

## CDN Architecture

A CDN distributes cached content across geographically separated edge locations.

A simplified request path is:

`Client`
`  ↓`
`DNS / Anycast / Routing`
`  ↓`
`Nearest or lowest-latency Edge`
`  ↓`
`Cache Lookup`
`  ├── HIT → Response`
`  └── MISS / STALE`
`          ↓`
`       Origin`
`          ↓`
`       Edge Cache`
`          ↓`
`       Response`

The three core architectural components are:

1. **Origin server**: authoritative source of content.
2. **Edge location**: geographically distributed cache serving nearby clients.
3. **Cache policy**: rules determining what can be stored, how long it remains valid, and how requests are represented as cache keys.

## Origin Servers

An origin is authoritative for the content requested through the CDN.

The implementations model origin responses with properties such as:

- HTTP status
- response body
- content type
- entity tag
- `Cache-Control`
- generation time

The origin does not need to serve every request directly. Its purpose is to provide content when an edge cannot satisfy the request from its local cache.

### Origin failure cases

The implementations account for missing resources by returning an HTTP 404 response with `no-store`.

This is important because an error response should not automatically be treated as a long-lived cacheable object.

An origin request can occur when:

- an object is absent from the edge
- the object has expired
- conditional revalidation determines that the object changed
- a request is deliberately bypassing the cache
- authenticated content is not permitted to enter the shared cache

## Edge Locations

An edge location is a cache positioned closer to users than the origin.

The examples use representative locations:

| Edge | Region |
|---|---|
| `blr` | India |
| `fra` | Europe |
| `iad` | North America |

The routing models are intentionally deterministic. A production CDN can use:

- DNS-based routing
- Anycast
- latency measurements
- health checks
- network topology
- traffic engineering
- capacity-aware routing

The important architectural property is that a request is routed to an edge before the cache is consulted.

## Edge Cache State

Each cached object contains information equivalent to:

| Field | Purpose |
|---|---|
| Cache key | Identifies the representation |
| Response | Cached origin response |
| Stored time | Establishes cache age |
| Expiration time | Determines freshness |
| Last access | Supports LRU eviction |

The Python and Java implementations use ordered maps for LRU behavior. The C++ implementation combines a linked list with a hash index, which provides constant-time lookup and constant-time movement of cache entries.

The basic cache operations are:

`lookup → validate freshness → serve or fetch → insert/update`

## Cache Hits

A cache hit occurs when:

1. The request is cacheable.
2. A matching cache key exists.
3. The cached object has not expired.

The edge can immediately return the cached representation.

A high cache-hit ratio reduces:

- origin traffic
- origin CPU usage
- origin bandwidth consumption
- request latency
- dependency on centralized infrastructure

The PostgreSQL request log records `HIT` explicitly so operational reports can calculate the hit ratio.

## Cache Misses

A cache miss occurs when no usable cached representation exists.

The edge then retrieves the object from the origin and may store it according to the cache policy.

A typical sequence is:

`Request`
`  ↓`
`Edge lookup`
`  ↓`
`No object`
`  ↓`
`Origin request`
`  ↓`
`Response`
`  ↓`
`Cache insertion`
`  ↓`
`Client response`

The implementations distinguish a first-time miss from a stale-object revalidation path.

## Stale Objects

An object becomes stale when its expiration time has passed.

A stale object is not treated as an ordinary fresh hit.

The implementations use conditional requests based on the cached entity tag. The origin can indicate that the existing representation remains valid.

This avoids transferring the complete object when the content has not changed.

The conceptual flow is:

`Expired cache entry`
`  ↓`
`If-None-Match: cached ETag`
`  ↓`
`Origin`
`  ├── unchanged → revalidate`
`  └── changed → replace cached object`

## Entity Tags and Revalidation

An entity tag identifies a particular representation.

The Python implementation derives an ETag from a SHA-256 digest of the response body. The JavaScript, C++, and Java implementations use deterministic ETag values in their examples.

Conditional revalidation uses the previous ETag.

When the origin confirms that the representation has not changed, the edge can extend its freshness period without downloading a new representation.

This reduces bandwidth while preserving correctness.

## Cache-Control

The examples recognize directives such as:

- `public`
- `private`
- `no-store`
- `max-age`

`max-age` determines how long a response may remain fresh.

The cache policy also imposes a maximum TTL so an origin cannot unintentionally create an excessively long edge lifetime.

For example:

`public, max-age=120`

means the response is considered publicly cacheable for 120 seconds, subject to the CDN's configured policy.

## Public and Private Content

Shared CDN caches must not treat private user-specific content like public static content.

The implementations therefore bypass caching for:

- responses marked `private`
- responses marked `no-store`
- authenticated requests when the configured policy disallows shared caching

This distinction protects against serving one user's representation to another user.

The security rule is:

`User-specific response ≠ shared cache object`

A CDN configuration that ignores this distinction can create a serious data-isolation failure.

## Cache Keys

A cache key determines whether two requests refer to the same cache representation.

The implementations construct keys from values such as:

- host
- HTTP method
- path
- selected query parameters

Query parameters require explicit policy.

The examples remove common tracking parameters such as:

- `utm_source`
- `utm_medium`
- `utm_campaign`
- `utm_term`
- `utm_content`
- `fbclid`

This prevents analytics parameters from unnecessarily multiplying cache variants.

The Python and Java implementations also demonstrate allowlist-based query handling.

A simplified key is:

`host | method | path | normalized-query`

## Cache-Key Security

Cache-key construction is a security and correctness boundary.

If user-controlled parameters are incorporated inconsistently, two logically different representations can collide.

Potential risks include:

- cache poisoning
- incorrect content reuse
- cache fragmentation
- accidental disclosure
- inconsistent normalization

A production implementation should define canonicalization rules explicitly rather than accepting arbitrary request data as a cache-key component.

## LRU Eviction

An edge has finite storage.

When the cache reaches capacity, the implementations remove the least recently used object.

The LRU process is:

`Cache full`
`  ↓`
`Identify least recently accessed entry`
`  ↓`
`Remove entry`
`  ↓`
`Insert new entry`

Python uses `OrderedDict`.

JavaScript uses `Map` insertion ordering and explicitly refreshes the accessed entry.

Java uses an access-ordered `LinkedHashMap`.

C++ uses a linked list plus hash map.

The C++ design gives average constant-time cache lookup while retaining explicit control over memory structures.

## Cache Invalidation

TTL expiration is passive invalidation.

Explicit purge is active invalidation.

The implementations support invalidating cached entries for a path.

A purge is useful when content changes before its normal TTL expires.

For example:

`/assets/app.js`
`release-41 → release-42`

If the old object has a long TTL, waiting for expiration would leave users receiving release 41. Explicit invalidation removes the cached representation immediately.

Production CDN systems commonly use broader invalidation mechanisms such as:

- exact-object purge
- path purge
- tag-based purge
- versioned asset names
- complete cache purge

## Cache Busting and Versioned Assets

Long-lived static assets can use versioned filenames:

`app.41.js`

followed by:

`app.42.js`

The filename becomes part of the cache identity.

This allows a long TTL while avoiding the need to invalidate the previous asset on every deployment.

HTML or manifest resources can use shorter TTLs to expose the new asset version.

The general deployment pattern is:

`Immutable asset`
`  ↓`
`Long TTL`

and:

`HTML / manifest`
`  ↓`
`Shorter TTL`

This separates content immutability from release discovery.

## Python Implementation

The Python implementation provides the most complete standalone simulation.

### Domain objects

The main dataclasses are:

- `CachePolicy`
- `Request`
- `OriginResponse`
- `CacheEntry`
- `EdgeMetrics`

The `Enum` types separate cache outcomes from arbitrary strings.

### Origin behavior

`OriginServer` stores published resources and supports conditional ETag requests.

It also counts origin fetches so cache efficiency can be observed.

### Edge behavior

`EdgeLocation` maintains an `OrderedDict` cache.

It implements:

- cache lookup
- TTL parsing
- cacheability decisions
- insertion
- LRU eviction
- invalidation
- metrics

### CDN behavior

`CDN` performs:

- edge routing
- request classification
- authentication bypass
- cache-key construction
- hit detection
- stale handling
- origin retrieval
- revalidation
- invalidation
- reporting

The executable demonstration exercises fresh hits, tracking-parameter normalization, stale content, authenticated bypasses, POST bypass behavior, and invalidation.

## JavaScript Implementation

The JavaScript implementation uses Node.js standard-library capabilities and asynchronous processing.

### Asynchronous origin access

`OriginServer.fetch()` returns a Promise and introduces a small simulated network delay.

This makes the control flow resemble an actual CDN service where edge-to-origin communication is I/O-bound.

### Event-driven cache

`EdgeLocation` extends `EventEmitter`.

Evictions emit an `eviction` event, allowing operational instrumentation to be added without coupling the cache algorithm to logging implementation.

### Map-based LRU

JavaScript `Map` preserves insertion order.

The cache therefore:

1. removes a recently accessed key
2. re-inserts it
3. treats the final map entry order as recency

### Error handling

The executable entry point uses a rejected-Promise handler and sets a non-zero process exit status when the simulation fails.

## C++17 Implementation

The C++ implementation emphasizes explicit data structures and deterministic resource management.

### Cache structure

The cache combines:

- `std::list` for recency ordering
- `std::unordered_map` for key lookup

This is a standard design for an efficient LRU cache.

Lookup is average `O(1)` and moving an existing list node is `O(1)`.

### Strongly typed states

`enum class` is used for cache outcomes and merge decisions.

This avoids loosely typed status strings in internal logic.

### Governance engine

The program also contains a distinct repository-governance case study.

This is intentionally separate from CDN cache behavior and models another policy-driven state system using:

- Pull Requests
- status checks
- approvals
- stale approvals
- unresolved conversations
- branch protection

The governance engine demonstrates how multiple independent conditions can determine final eligibility.

## Java 17 Implementation

The Java implementation emphasizes enterprise domain modeling.

### Records

Java records represent immutable domain values such as:

- `CachePolicy`
- `Request`
- `OriginResponse`
- `CacheEntry`
- `Review`
- `StatusCheck`
- `BranchProtectionPolicy`
- `PullRequest`

This makes state boundaries explicit.

### Service layer

`CdnService` coordinates:

- routing
- cache-key construction
- origin interaction
- cache lookup
- expiration
- revalidation
- invalidation

The implementation separates domain data from workflow behavior.

### Policy service

`MergeEligibilityService` evaluates repository governance conditions using explicit policy objects.

The model distinguishes:

- open state
- draft state
- conflicts
- unresolved conversations
- status checks
- eligible approvals
- stale approvals

The service returns an explicit `MergeEligibility` state instead of relying on a collection of loosely related booleans.

## PostgreSQL Implementation

The PostgreSQL script treats CDN operation as persistent operational data.

The schema contains separate entities for:

- origins
- repositories
- edges
- cache policies
- branches
- commits
- Pull Requests
- reviewers
- reviews
- review comments
- conversations
- status checks
- branch protection
- approval requirements
- cache entries
- request logs

This separates configuration, repository governance, cache state, and traffic telemetry.

### Constraints

Database-level constraints validate:

- positive cache capacities
- valid TTL ranges
- valid status codes
- valid review counts
- unique repository and branch combinations
- unique cache entries per edge
- valid Pull Request branch relationships

### Triggers

The Pull Request trigger prevents source and target branches from belonging to different repositories.

The cache-entry trigger prevents invalid temporal relationships such as an expiration time before storage time.

### Merge eligibility

`cdn.merge_eligibility()` evaluates:

- Pull Request existence
- open state
- draft state
- merge conflicts
- required checks
- unresolved conversations
- active reviewers
- non-stale approvals
- required approval count

This function makes the final decision reproducible from persistent state.

### Operational views

`cdn.edge_cache_health` exposes:

- edge status
- capacity
- cached object count
- stale object count

`cdn.cache_performance` calculates:

- request volume
- cache hits
- misses
- revalidations
- hit percentage

## Performance Model

Let:

- `N` = number of requests
- `K` = number of cache objects
- `H` = cache hits
- `M` = cache misses

The cache-hit ratio is:

`H / N`

The miss ratio is:

`M / N`

For a hash-indexed cache, lookup is approximately `O(1)` average time.

LRU eviction requires:

- `O(1)` lookup
- `O(1)` recency update
- `O(1)` eviction

The C++ implementation explicitly provides this structure.

The PostgreSQL request-log indexes target common operational queries rather than indexing every column. Excessive indexing would increase write cost without necessarily improving CDN request reporting.

## Failure Handling

Important failure conditions include:

| Failure | Expected behavior |
|---|---|
| Missing origin object | Return 404 and avoid long-lived caching |
| `no-store` | Do not store response |
| `private` | Do not place response in shared cache |
| Authenticated request | Bypass shared cache unless explicitly allowed |
| Expired entry | Revalidate or retrieve fresh content |
| Origin content changed | Replace cached representation |
| Edge capacity exceeded | Evict least recently used object |
| Invalid cache TTL | Reject configuration |
| Invalid Pull Request branch relationship | Reject database operation |
| Failed required check | Block merge eligibility |
| Stale approval | Exclude approval from current requirement |

## Security Considerations

CDN caching changes the trust boundary because cached data may be served to many clients.

Important controls include:

### Preventing private-data caching

Authenticated and user-specific responses should not enter a shared cache unless the design explicitly isolates them.

### Cache-key normalization

The cache key must consistently represent the response variant.

### Cache poisoning resistance

Untrusted request headers and parameters should not influence cache identity unless they are explicitly part of the representation-selection policy.

### HTTPS

Production CDN deployments should use TLS between clients and edge locations and appropriate protection for edge-to-origin traffic.

### Origin access control

Origins should preferably restrict direct public access where the architecture allows it, so clients cannot bypass CDN security and caching controls.

### Purge authorization

Cache invalidation should require authenticated administrative access. A purge endpoint exposed without authorization can become a denial-of-service mechanism or cause widespread cache misses.

## Cache Policy Trade-offs

| Policy choice | Benefit | Cost |
|---|---|---|
| Long TTL | High cache efficiency | Slower propagation of changes |
| Short TTL | Faster content freshness | More origin traffic |
| Aggressive query normalization | Higher hit ratio | Risk of collapsing distinct variants |
| Private-content bypass | Stronger isolation | Lower cache efficiency |
| Large edge capacity | Fewer evictions | Higher infrastructure cost |
| Exact invalidation | Precise updates | More operational complexity |
| Versioned assets | Long safe TTLs | Requires release-aware naming |

## Freshness Versus Efficiency

CDN design is largely a balance between freshness and origin reduction.

A long TTL can improve performance but delay updates.

A short TTL reduces stale exposure but increases origin requests.

A practical architecture commonly assigns different policies to different resource classes:

| Resource | Typical policy characteristic |
|---|---|
| Immutable versioned assets | Long TTL |
| HTML | Short or moderate TTL |
| API responses | Explicitly cacheable only when safe |
| Personalized account data | Private or bypass |
| Authentication responses | Usually non-cacheable |
| Error responses | Conservative caching |

## End-to-End Workflow

The implemented architecture can be understood as:

`1. Client sends request`
`        ↓`
`2. CDN selects edge`
`        ↓`
`3. Edge applies cache policy`
`        ↓`
`4. Cache key is constructed`
`        ↓`
`5. Cache lookup`
`        ├── Fresh → HIT`
`        ├── Stale → Conditional revalidation`
`        └── Missing → Origin request`
`                         ↓`
`                    Cache policy`
`                         ↓`
`                    Cache insertion`
`                         ↓`
`6. Response returned to client`

Operationally, cache state and request telemetry can then be persisted for reporting and capacity analysis.

## Distinct Architectural Boundaries

The project deliberately separates concepts that can otherwise become conflated.

| Concept | Responsibility |
|---|---|
| Origin | Authoritative content source |
| Edge | Distributed serving and caching point |
| Cache policy | Rules governing storage and freshness |
| Cache key | Identity of a cached representation |
| TTL | Freshness duration |
| Revalidation | Verification that a stale representation remains valid |
| Invalidation | Explicit removal before normal expiration |
| Routing | Selection of an edge location |
| Request log | Operational record of CDN behavior |

A CDN is therefore not simply a collection of caches. It is a coordinated system involving routing, content identity, freshness rules, storage limits, origin communication, invalidation, security controls, and operational telemetry.
