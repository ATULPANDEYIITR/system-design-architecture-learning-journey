# Caching: Why Caching?

Caching is a controlled reuse mechanism. Instead of recomputing or refetching a value every time it is requested, an application keeps a copy in a faster or cheaper location and serves subsequent requests from that copy when its consistency and freshness rules permit it.

The central engineering question is not simply whether a cache makes a program faster. The important question is whether the reduction in repeated work justifies the additional state, invalidation rules, memory consumption, consistency risks, and operational complexity.

This learning artifact treats caching as a system-design concern rather than as a dictionary or map exercise.

## Why Caching Exists

A request may repeatedly perform work whose result changes less frequently than the request rate.

A repository governance service, for example, may evaluate whether a Pull Request can enter a protected branch. The evaluation can require reading reviews, approval states, status checks, branch protection rules, and the current Pull Request revision. If hundreds of users or automated systems ask for the same decision while none of those inputs changes, performing the same database reads repeatedly wastes resources.

Caching can reduce:

- database reads,
- network round trips,
- CPU spent recomputing expensive results,
- latency perceived by callers,
- load on downstream services,
- repeated serialization and deserialization work,
- pressure on rate-limited APIs.

Caching does not eliminate the underlying authoritative data source. It introduces another copy whose validity must be managed.

The basic relationship is:

`request -> cache lookup -> hit: return cached value`

`request -> cache lookup -> miss: authoritative read -> cache write -> return value`

The benefit appears when cache lookup is substantially cheaper than regeneration or retrieval and the cached result can safely be reused.

## Cache Hit, Cache Miss, and Hit Rate

A cache hit occurs when a requested key exists and the stored entry is valid under the cache's freshness policy.

A cache miss occurs when the requested key does not provide a usable value. A miss can happen because the value was never cached, expired, was evicted, or was explicitly invalidated.

The Python implementation records hits, misses, writes, evictions, expirations, and invalidations. The JavaScript implementation maintains similar operational statistics while using JavaScript's `Map` behavior to implement recency ordering.

A useful operational measure is:

`hit rate = cache hits / (cache hits + cache misses)`

A high hit rate is useful only if the cached values are still correct for their intended purpose. A cache that returns obsolete authorization or governance decisions with a high hit rate is not a successful cache.

## Cache-Aside

The Python product example uses the cache-aside pattern.

The application first checks the cache. On a miss, it reads the authoritative repository, stores the result, and returns it.

This pattern is attractive because the database remains the source of truth. The application decides which results deserve caching and controls when entries are removed.

The trade-off is that the application must manage invalidation. A database update does not automatically know that a particular application cache contains an obsolete copy.

The Python invalidation demonstration makes this visible by changing a product price in the repository while an older product remains cached. The cached value remains stale until the corresponding product tag is invalidated.

## Why Cache Invalidation Matters

Invalidation is the mechanism that removes or marks a cached value unusable after its source data changes.

There are several distinct causes for invalidation:

- a product price changes,
- a Pull Request receives or loses an approval,
- a required status check changes,
- a branch protection policy changes,
- a source revision changes,
- a user permission changes,
- a configuration value changes.

Time-to-live alone cannot guarantee immediate consistency. A value with a five-minute TTL can remain incorrect for nearly five minutes after its authoritative source changes.

The examples therefore combine TTL with explicit invalidation when the underlying mutation is known.

The repository governance scenario is particularly sensitive. If an approval is dismissed but an old merge-eligibility result remains cached, a system could incorrectly report that a protected-branch change is mergeable.

For such decisions, correctness has priority over maximizing cache reuse.

## TTL and Freshness

A time-to-live defines how long an entry may be considered usable.

The Python `LRUCache` stores an expiration timestamp with each entry. The JavaScript implementation uses an equivalent expiration timestamp in each `Map` entry. The Java implementation stores an immutable `CacheEntry` containing the value and expiration time.

TTL is useful when changes are difficult to observe directly or when bounded staleness is acceptable.

Typical examples include catalog metadata, aggregate dashboards, public configuration, or data that changes periodically.

TTL is not a universal consistency solution. A short TTL reduces staleness but can reduce the hit rate and increase regeneration traffic. A long TTL improves reuse but increases the maximum period during which stale data may be served.

The correct TTL is therefore a property of the data and business rule, not a universal performance setting.

## LRU and Memory Limits

Caching without a capacity policy can consume unbounded memory.

Least Recently Used, or LRU, removes entries that have not been accessed recently when the cache reaches its capacity.

The Python implementation uses `OrderedDict` to track recency. The JavaScript implementation uses `Map` insertion order and moves a recently accessed entry to the newest position. The C++ implementation maintains an explicit recency vector around an unordered map.

TTL and LRU address different problems.

TTL answers:

`How long may this value remain usable?`

LRU answers:

`Which value should leave when the cache is full?`

A cache can require both. A recently accessed item can still be expired, and an unexpired item can still be evicted because memory capacity has been reached.

## Cache Key Design

A cache is only as correct as its key.

Two requests that should receive different results must not accidentally map to the same key.

For a parameterized query, the key normally needs to incorporate every input that affects the result.

The Python implementation uses canonical JSON serialization and hashing to construct stable keys. The JavaScript implementation sorts parameter names before creating its canonical representation.

For example, these parameter objects represent the same logical query:

`{region: "eu-west-1", limit: 20, active: true}`

and:

`{active: true, limit: 20, region: "eu-west-1"}`

A deterministic key generator prevents their different insertion orders from creating unnecessary cache misses.

A production key may contain a namespace, operation name, tenant identifier, version, locale, authorization scope, and normalized request parameters when those attributes influence the result.

Keys also need boundaries. A shared key such as `profile:42` can be dangerous if the actual result differs by tenant or authorization context.

## Negative Caching

Caching does not have to store only successful results.

If a lookup repeatedly asks for a resource that does not exist, the system can temporarily cache the absence. This is called negative caching.

The Python implementation uses a sentinel object to distinguish a cached "not found" result from an ordinary cache miss.

Negative caching can protect an authoritative service from repeated requests for the same nonexistent identifier.

Its TTL should normally be conservative because a resource that does not exist now may be created later.

## Cache Stampede

A cache stampede occurs when a popular item expires or is absent and many callers simultaneously regenerate it.

Without protection:

`many requests -> same miss -> many expensive backend calls`

This can create a sudden load spike precisely when the application is already under pressure.

The Python implementation uses a lock around regeneration. It performs a second cache check after acquiring the lock because another request may have populated the cache while the current request was waiting.

The JavaScript implementation uses Promise coalescing. A `Map` of in-flight Promises associates a cache key with the regeneration already in progress. Concurrent callers await the same Promise instead of starting independent backend operations.

In a multi-process or distributed deployment, an in-process lock is insufficient because different application instances have separate memory. Distributed locking, request coalescing at a shared layer, or a cache system supporting coordinated regeneration may be required.

## Stale-While-Revalidate

Some workloads can tolerate serving a slightly stale value when doing so avoids request latency.

A stale-while-revalidate design separates the period during which a value is fresh from a period during which an older value remains usable while another process refreshes it.

Conceptually:

`fresh -> serve immediately`

`stale but acceptable -> serve stale value and refresh`

`expired beyond stale window -> regenerate before serving`

This is useful for data where a short period of staleness is preferable to exposing users to regeneration latency.

It should not be applied blindly to security-sensitive decisions, financial authorization, inventory guarantees, or other data where stale state can create unacceptable outcomes.

## Version-Aware Caching

Version information can make cache validity more explicit.

The Python product model carries a product version. The C++ governance engine includes Pull Request and state versions in its cache key. The Java enterprise model combines Pull Request number, policy version, and source revision.

This means a cached decision generated for one state is not automatically reused for a materially different state.

For governance decisions, a useful identity is conceptually:

`Pull Request + policy version + source revision`

If any of those changes, the previous decision may no longer be applicable.

Versioned keys do not eliminate the need for cleanup. Old entries still consume memory until expiration or eviction, so explicit invalidation and bounded capacity remain useful.

## Python Implementation

The Python script develops a complete in-process caching model around a product repository.

Its `LRUCache` combines:

- bounded capacity,
- TTL expiration,
- LRU eviction,
- cache statistics,
- tag-based invalidation,
- thread locking.

The `ProductRepository` represents a slower authoritative source. The application first checks the cache and only calls the repository on a miss.

The script then demonstrates why invalidation is necessary by changing a product price in the repository while an older cached product still exists. The stale result is removed using the product-specific tag before the fresh value is read.

The stampede example introduces regeneration locking and a second cache lookup inside the lock. That second lookup is important because another request can populate the cache while the current request waits.

The deterministic key function uses canonical JSON serialization followed by SHA-256 hashing. Sorting JSON properties ensures logically equivalent parameter dictionaries generate the same key.

The security example refuses to cache explicitly sensitive fields such as access tokens and private keys. This is intentionally a policy boundary rather than an attempt to claim that all sensitive data can be identified through a short field-name list.

## JavaScript Implementation

The JavaScript program models an asynchronous catalog service.

JavaScript is particularly useful for showing cache behavior around asynchronous I/O. The simulated repository returns Promises and uses a delay to represent an external data source.

The cache uses `Map`. JavaScript `Map` preserves insertion order, so deleting and reinserting a key moves it to the newest position. That behavior supports the LRU-like policy implemented in `TTLCache`.

The most important JavaScript-specific mechanism is Promise coalescing.

When several callers request the same missing product at nearly the same time, the first caller starts repository retrieval and stores its Promise in `inFlight`. Other callers find the existing Promise and await it. This avoids duplicate backend requests without blocking the JavaScript event loop.

The program also demonstrates mutable-object risk. Returning the same mutable object reference from a cache allows one consumer to alter the value seen by subsequent consumers. Defensive cloning or immutable representations provide a stronger boundary.

## C++ Governance Case Study

The C++ program models a repository governance engine that determines whether a Pull Request is eligible for merging.

The authoritative state contains:

- protected branch policy,
- required approval count,
- required status checks,
- reviewer decisions,
- Pull Request version information.

The `MergeEligibilityEngine` evaluates these inputs and stores the resulting decision in an LRU cache.

The cache key incorporates the Pull Request identifier and its version. This is significant because the cached result represents a decision about a particular state rather than an eternal property of the Pull Request.

The program also supports tag-based invalidation. When an approval is revoked, the corresponding Pull Request cache entries can be invalidated before the next evaluation.

The C++ cache uses `shared_mutex` to distinguish read-oriented access from exclusive mutations. Its implementation demonstrates that caching is also a concurrency problem: multiple threads may inspect and update shared cache state simultaneously.

The case study intentionally keeps the authoritative governance store separate from the cache. A cached merge decision is an optimization, not the source of truth.

## Java Enterprise Model

The Java implementation models the same broad domain from an enterprise application perspective without simply translating the C++ implementation.

Domain rules are represented through records and enums.

`Review` distinguishes `COMMENTED`, `CHANGES_REQUESTED`, `APPROVED`, and `DISMISSED`. `StatusCheck` distinguishes `PENDING`, `PASSED`, and `FAILED`. `BranchProtectionPolicy` contains explicit policy rules instead of relying on loosely structured maps.

The `GovernanceCache` stores immutable `CacheEntry` records with expiration and tags.

The `MergeEligibilityService` retrieves the current Pull Request and policy state, builds a version-aware `CacheKey`, checks the cache, and performs authoritative evaluation only after a miss.

Approval dismissal demonstrates a critical invalidation boundary. A previously eligible result cannot safely remain authoritative after a required approval has been dismissed.

The Java implementation uses `ConcurrentHashMap` and atomic counters to support concurrent application access without introducing an unnecessary third-party cache library.

## SQL Data Model

The PostgreSQL script treats caching as part of a relational governance system.

The authoritative model contains repositories, branches, contributors, commits, Pull Requests, reviews, review comments, status checks, branch-protection policies, and required checks.

The `merge_decision_cache` table is intentionally separate from those authoritative entities.

Important integrity rules are enforced through database constraints:

- repository and branch names have uniqueness constraints,
- Pull Requests reference valid repositories, branches, authors, and commits,
- review states are restricted to defined values,
- status checks use explicit state constraints,
- policy versions must be positive,
- required approval counts cannot be negative,
- cache decisions are restricted to `ELIGIBLE` or `BLOCKED`.

Indexes target the access paths used by the governance queries, particularly Pull Request state, review state, status checks, and cache validity.

The merge-eligibility query uses common table expressions to separately calculate approvals, unresolved discussions, and status-check state. This keeps those policy dimensions distinct instead of hiding them in a single unstructured condition.

The cache lookup requires the cached entry to remain unexpired and to match the current policy version and Pull Request head commit. This demonstrates a relational expression of version-aware cache validity.

The transaction at the end changes an approval to `DISMISSED` and invalidates associated cached merge decisions in the same transaction. The database therefore exposes the mutation and cache invalidation as one atomic operation.

## Pull Request Caching

A Pull Request can be cached at several different levels, and those levels should not be confused.

The Pull Request metadata itself may be cached.

A rendered Pull Request summary may be cached.

A list of changed files may be cached.

A merge-eligibility decision may be cached.

These values have different consistency requirements. A rendered summary may tolerate a short delay, while a security-sensitive merge decision can require immediate invalidation when an approval or required status changes.

The cache key and invalidation policy must therefore correspond to the specific result being cached.

## Code Review and Cache Boundaries

Code-review comments are mutable collaboration state. A reviewer can add a comment, request changes, resolve a discussion, or replace a previous review state.

Caching a static representation of review activity can reduce repeated reads, but a cached review state must not be treated as permanent.

A review-related cache should distinguish between presentation-oriented data and policy-relevant review decisions.

For example, a cached count of historical comments is fundamentally different from a cached statement that all required review discussions are resolved.

The latter directly affects merge eligibility and needs a stronger invalidation model.

## Approvals and Stale Decisions

An approval is not merely a count.

Approval semantics can depend on reviewer identity, review state, branch policy, changed commits, dismissal rules, and repository configuration.

A cached approval-derived decision can therefore become stale after:

- an approval is dismissed,
- a reviewer changes their review,
- the Pull Request receives new commits,
- the required reviewer count changes,
- a protection policy changes.

The C++ and Java examples address this through versioning and invalidation.

A high cache hit rate is not a sufficient success metric for approval data. The system must measure whether the consistency model matches the policy's risk.

## Branch Protection and Cache Correctness

Branch protection is a repository-level enforcement mechanism. It can require reviews, status checks, conversation resolution, linear history, or restrictions on direct and force pushes.

Caching a branch protection policy can reduce repeated policy reads, but a cached policy must carry an explicit version or expiration rule.

Suppose a repository changes its required approvals from two to three.

A cache that still evaluates Pull Requests using the previous two-approval policy can incorrectly classify a Pull Request as mergeable.

That makes policy version part of the correctness boundary.

The enterprise examples therefore use a policy version in the cache key rather than relying only on Pull Request number.

## Cache Invalidation Strategies

Different data relationships lead to different invalidation strategies.

**TTL invalidation** is simple and useful when bounded staleness is acceptable. It does not require the application to observe every mutation.

**Explicit invalidation** is appropriate when the application knows that a mutation makes a cached result obsolete.

**Versioned keys** allow new source states to produce distinct cache entries without trusting the old entry for the new state.

**Tag-based invalidation** allows related entries to be removed together. A product tag can invalidate every cached representation associated with one product.

**Write-through designs** update the cache during writes. They can provide tighter cache consistency but couple writes to cache availability and behavior.

The implementations primarily use TTL, explicit invalidation, tags, and versions because these mechanisms directly illustrate the selected scenarios.

## Performance Considerations

Caching changes the cost structure of a system.

A cache hit usually requires a fast local or network lookup. A miss can require the full backend path.

The practical value depends on:

`cache lookup cost + memory cost + invalidation complexity`

versus:

`backend retrieval cost + computation cost + network cost`

The value is strongest when the cached result is expensive to regenerate and reused frequently.

A cache can make performance worse when entries are rarely reused, values are very large, serialization is expensive, or invalidation causes constant regeneration.

The cache itself also requires memory, CPU, synchronization, network bandwidth when distributed, monitoring, and operational maintenance.

## Distributed Caching

The examples primarily use process-local caches because they expose the core mechanisms without requiring external infrastructure.

A distributed application has a different problem.

If four application instances each maintain their own cache, a mutation on one instance does not automatically remove the value stored in the other three.

A shared cache can provide a common view, but introduces network latency, serialization, availability concerns, connection management, and its own failure modes.

A distributed cache also changes the meaning of locking. A process-local mutex cannot coordinate regeneration across different machines.

The architectural choice is therefore not simply "local cache versus distributed cache for speed". It is a consistency, latency, availability, and operational decision.

## Security Considerations

Caches can accidentally become data-exposure mechanisms.

A cache key that omits tenant identity can cause one tenant's result to be returned for another tenant.

A cache that stores authorization decisions too long can continue granting access after permissions change.

A cache that stores credentials or access tokens unnecessarily increases the impact of memory disclosure, debugging exposure, or accidental persistence.

User-specific content should not be placed under a globally shared key.

Authorization-sensitive values should have a consistency model that reflects the security consequences of stale state.

The Python example therefore rejects several explicitly sensitive fields at the cache boundary, while the governance examples avoid treating cached merge decisions as permanent authority.

## Common Failure Modes

A cache stampede creates simultaneous backend regeneration.

A stale cache returns a value that is no longer authoritative.

A cache key collision returns a valid value for the wrong request.

Unbounded caching causes memory pressure.

Poor invalidation produces correctness bugs that can be difficult to reproduce because they depend on timing.

Caching mutable object references can allow one consumer to alter data observed by another.

Caching an authorization or governance decision without accounting for policy changes can create a security or compliance failure.

Negative caching can hide newly created resources if its TTL is too long.

A very short TTL can produce low hit rates and turn the cache into an expensive layer that provides little benefit.

## Production Considerations

A production cache requires observability beyond a single hit-rate number.

Useful measurements include:

- hit and miss counts,
- hit rate by key class,
- eviction counts,
- expiration counts,
- regeneration latency,
- backend load before and after caching,
- cache memory consumption,
- serialization cost,
- invalidation frequency,
- stale-response frequency where measurable,
- error rates during cache outages.

A cache should also have a defined failure policy.

If the cache is unavailable, the application may fail open to the authoritative source, fail closed for security-sensitive decisions, or return a degraded response depending on the data being requested.

The appropriate behavior is determined by the consequence of stale or unavailable data.

## Relationship Between the Six Implementations

The six files deliberately approach caching from different technical perspectives.

| Implementation | Main caching perspective |
| --- | --- |
| Python | Cache-aside, TTL, LRU, tags, invalidation, stampede protection, deterministic keys, negative caching, and security boundaries |
| JavaScript | Asynchronous I/O, Promise coalescing, `Map` ordering, mutable-object hazards, invalidation, and event-loop-friendly cache regeneration |
| C++ | Repository governance decision caching, concurrent access, LRU state, versioned keys, and explicit invalidation |
| Java | Enterprise domain modeling, immutable records, policy objects, concurrent maps, version-aware cache keys, and governance state transitions |
| PostgreSQL | Relational representation of authoritative repository state, policy constraints, cache validity, version matching, and transactional invalidation |
| README | Technical relationships among performance, freshness, invalidation, governance, and consistency |

The four repository concepts remain distinct within the governance examples. A Pull Request represents the proposed change and its lifecycle. Code Review evaluates the proposed changes through comments and review states. Approvals represent specific review decisions that may contribute to merge eligibility. Branch Protection defines repository-level rules that determine which conditions must be satisfied before protected-branch changes can proceed.

Caching sits across those mechanisms as an optimization layer. It does not replace the Pull Request, review, approval, or branch-protection state that determines the authoritative answer.

The most important design principle is therefore:

`cache for speed, authoritative state for correctness, and explicit validity rules to connect the two`
