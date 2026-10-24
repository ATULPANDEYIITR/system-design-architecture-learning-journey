# Load Balancing Algorithms: Round Robin, Weighted, and Least Connections

## Scope

This project models three commonly used load-balancing algorithms:

| Algorithm | Selection rule | Main strength | Main limitation |
|---|---|---|---|
| Round robin | Select healthy servers sequentially | Simple and predictable distribution | Ignores server capacity and current workload |
| Weighted round robin | Select servers according to configured weights | Supports unequal server capacity | Does not directly measure active workload |
| Least connections | Select the healthy server with the fewest active connections | Adapts to current concurrency | Requires accurate connection state |

The implementations deliberately treat these algorithms as distinct scheduling policies rather than interchangeable variations of the same mechanism.

The domain model is:

`Load Balancer → Backends → Requests → Selection Policy → Connection State → Completion`

A load balancer receives a request, selects an eligible backend, updates backend state, and later releases the connection when the request completes.

## Core Concepts

### Load balancing

Load balancing distributes incoming work across multiple backend servers.

A backend can be represented by:

- a unique name
- an endpoint
- a health state
- a capacity weight
- active connections
- completed requests
- failed requests
- total assigned requests

The scheduler must not send new work to an unhealthy backend.

The three algorithms differ primarily in the information used to select the next backend.

### Round robin

Round robin maintains an ordered list of eligible servers.

For servers `A`, `B`, and `C`, the sequence is:

`A → B → C → A → B → C`

With equally capable servers, this gives approximately equal request counts.

The Python, JavaScript, C++17, and Java 17 implementations maintain an explicit scheduling position. The implementations also remove unhealthy servers from the candidate set without changing the backend's historical statistics.

Round robin is inexpensive because selection is normally `O(1)` after the eligible backend collection has been prepared.

Its weakness is that request counts do not necessarily represent workload. A server processing a long-running request can receive another request even when another server is almost idle.

## Weighted round robin

Weighted round robin assigns a positive integer weight to each backend.

For:

| Backend | Weight |
|---|---:|
| Server A | 1 |
| Server B | 2 |
| Server C | 3 |

An expanded conceptual schedule is:

`A → B → B → C → C → C`

Across many requests, the expected distribution approaches:

| Backend | Expected share |
|---|---:|
| A | 16.67% |
| B | 33.33% |
| C | 50.00% |

The Python implementation explicitly constructs a weighted schedule.

The JavaScript implementation rebuilds the schedule whenever health changes.

The C++ implementation stores backend indexes in a weighted schedule rather than copying complete backend objects.

The Java implementation encapsulates the schedule inside `WeightedRoundRobinPolicy`.

The PostgreSQL model stores weights as database constraints and uses them when evaluating candidate backends.

Weights are useful when machines have different CPU, memory, network, or application capacity.

A weight does not mean that a backend will receive exactly that percentage during every short request window. It represents the intended long-term scheduling ratio.

## Least connections

Least connections selects the healthy backend with the smallest number of active connections.

For example:

| Backend | Active connections | Weight |
|---|---:|---:|
| A | 4 | 1 |
| B | 1 | 2 |
| C | 2 | 3 |

The next request goes to B because B has the smallest active-connection count.

This algorithm responds to current concurrency rather than merely counting how many requests were assigned historically.

The implementations use weight as a tie-breaker. When two servers have the same active-connection count, the higher-capacity server is preferred.

This is a design decision rather than a universal property of least-connections algorithms. A production system may instead use additional measurements such as latency, CPU utilization, queue depth, connection age, or observed throughput.

## Why the Algorithms Are Distinct

The scheduling information differs:

| Mechanism | Primary input |
|---|---|
| Round robin | Position in an ordered sequence |
| Weighted round robin | Position in a capacity-weighted sequence |
| Least connections | Current active-connection count |

A request-count history cannot substitute for active-connection state.

For example, two servers can have processed the same number of requests while having very different current workloads because their requests have different durations.

## Backend Health

Health is treated separately from scheduling.

A backend can be:

- `healthy`
- `unhealthy`
- `draining` in the PostgreSQL domain model

Only healthy backends are eligible for new requests.

An unhealthy backend may still have active connections. Those existing connections should normally be allowed to finish rather than being silently discarded.

The Python, JavaScript, C++17, and Java 17 implementations therefore separate:

`healthy for new traffic`

from:

`currently processing existing traffic`

This distinction prevents a health transition from corrupting active connection accounting.

## Python Implementation

The Python file models the scheduling system using `Backend`, `Request`, and `LoadBalancer` classes.

`Backend` stores:

- health
- weight
- active connections
- request counters

`Request` validates request identifiers and durations.

`LoadBalancer` selects among three algorithms through an explicit `Algorithm` enumeration.

Round robin uses a rotating index.

Weighted round robin constructs a schedule containing each backend according to its weight.

Least connections evaluates active connections and then uses weight and name as deterministic tie-breakers.

The script also demonstrates backend failure. When the primary backend becomes unhealthy, new requests are directed to the remaining healthy backend.

Assertions verify the expected distributions:

- equal weights produce `20 / 20 / 20` for 60 requests
- weights `1 / 2 / 3` produce `10 / 20 / 30` for 60 requests

## JavaScript Implementation

The JavaScript file uses Node.js standard-library `EventEmitter` to model events generated by the load balancer.

Events include:

- request assignment
- request completion
- health changes

This provides an event-driven perspective that differs from the synchronous Python model.

The asynchronous scenario creates promises representing requests with different completion delays.

This matters for least connections because active-connection state changes while other requests are still running.

The implementation uses:

- `Map`-style data concepts through structured collections
- `Set` for healthy backend membership
- classes for backend and scheduler state
- promises for asynchronous completion
- event emission for operational state changes
- assertions for deterministic distribution checks

No external npm package is required.

## C++17 Implementation

The C++17 program treats the scheduler as a stateful systems component.

The `Backend` structure stores counters and connection state.

The load balancer maintains backend indexes rather than duplicating backend objects inside scheduling structures.

This is useful because selecting an element from a weighted schedule should not require copying a potentially large backend object.

The least-connections comparator orders candidates using:

1. active connections
2. descending weight
3. backend name

The explicit comparator gives deterministic behavior when multiple servers have equal connection counts.

The program also demonstrates exception-based failure handling and uses assertions to validate known distributions.

## Java 17 Implementation

The Java implementation uses explicit policy objects.

`SelectionPolicy` defines the scheduler contract.

Three concrete policy implementations provide:

- `RoundRobinPolicy`
- `WeightedRoundRobinPolicy`
- `LeastConnectionsPolicy`

This separates domain state from algorithm selection.

The `BackendSnapshot` record provides an immutable representation of operational state.

The `LoadBalancer` service manages:

- backend validation
- policy registration
- request dispatch
- completion
- health changes
- state reporting

Java streams are used for candidate filtering, immutable snapshot construction, and deterministic least-connections ordering.

The asynchronous example uses `CompletableFuture` and scheduled delays to demonstrate why active connections are different from historical request counts.

## PostgreSQL Model

The PostgreSQL implementation represents the load-balancing domain relationally.

The principal entities are:

| Table | Purpose |
|---|---|
| `repositories` | Groups load-balancing configurations |
| `load_balancers` | Stores algorithm selection and enablement |
| `backends` | Stores backend capacity and health |
| `requests` | Tracks request assignment and lifecycle |

The relationship is:

`Repository → Load Balancer → Backend`

and:

`Load Balancer → Request → Backend`

The database uses PostgreSQL-specific features including:

- enumerated types
- `BIGSERIAL`
- check constraints
- partial indexes
- PL/pgSQL functions
- triggers
- common table expressions
- window functions
- transactional statements

## Database Integrity

Backend weights are constrained to positive values.

Active connections cannot become negative.

Request counters cannot exceed the total request count.

A trigger validates that a request cannot reference a backend belonging to a different load balancer.

This is important because application-level validation alone does not guarantee relational integrity when multiple applications or database clients can modify the same tables.

The database also uses foreign keys with explicit deletion behavior.

## Request Lifecycle

A request progresses through:

`queued → active → completed`

or:

`queued → active → failed`

When an active request changes to a terminal state, the trigger decreases the backend's active-connection count.

Completion and failure counters are updated in the same database operation.

This makes the counters represent state transitions rather than independent manually maintained statistics.

## Least-Connections Query

The least-connections selection logic orders healthy candidates by:

`active_connections ASC`

followed by:

`weight DESC`

and then:

`backend_id ASC`

The first row is therefore the current least-loaded candidate, with deterministic tie-breaking.

The corresponding index places:

- load balancer
- active connections
- weight

in the index definition and restricts the index to healthy backends.

This reduces unnecessary index entries for unhealthy servers.

## Transactional Dispatch

The PostgreSQL dispatch function uses row locking before selecting a backend.

The purpose is to reduce race conditions when concurrent transactions inspect the same connection state.

Without suitable synchronization, two concurrent sessions could both observe the same backend as the least-loaded candidate and assign work based on stale information.

A relational database can provide strong consistency for state changes, but a high-throughput production load balancer would usually keep hot scheduling state in a purpose-built in-memory or distributed scheduling component rather than making every request depend on database locking.

## Distribution Versus Workload

Round robin and weighted round robin primarily control distribution.

Least connections attempts to control concurrent workload.

Consider three requests:

| Request | Duration |
|---|---:|
| R1 | 5 seconds |
| R2 | 50 milliseconds |
| R3 | 50 milliseconds |

A request-count algorithm treats the assignments as individual units.

A connection-aware algorithm can recognize that the backend processing R1 remains occupied much longer.

This distinction is important for APIs, database proxies, WebSocket services, and other systems where request duration varies substantially.

## Edge Cases

The implementations handle several important failure conditions.

### No healthy backends

If every backend becomes unhealthy, selection fails instead of silently routing traffic to an invalid destination.

### Invalid weight

Weights must be positive.

A zero or negative weight is rejected because it cannot represent a meaningful capacity factor in these implementations.

### Duplicate backend names

Backend names must be unique within a load-balancer configuration.

Duplicate identifiers would make health updates and statistics ambiguous.

### Completing a nonexistent connection

The implementations reject attempts to complete a request when the backend has no active connection.

This protects the active-connection counter from becoming negative.

### Backend failure

A failed backend is removed from new-request selection.

Existing connections remain represented by the backend state until completion.

### Equal connection counts

Least connections uses deterministic tie-breaking.

The higher weight is preferred before the backend identifier is considered.

## Performance Characteristics

Let `N` be the number of backends.

Basic round-robin selection is approximately `O(1)` when the healthy candidate collection is readily available.

Weighted round robin using an expanded schedule requires memory proportional to the sum of weights:

`O(W)`

where `W` is the total configured weight.

A production weighted scheduler can avoid expanded schedules by using algorithms such as smooth weighted round robin or another weighted-selection structure.

Least connections requires identifying the minimum active-connection count.

A simple scan is:

`O(N)`

for each selection.

A production implementation with a maintained priority structure can reduce selection cost, but every connection-count change must then update the structure correctly.

## Security Considerations

A load balancer is part of the traffic-control boundary.

Important controls include:

- validate backend endpoints
- do not accept arbitrary destinations from untrusted request data
- restrict administrative health changes
- authenticate configuration changes
- authorize weight changes
- protect management APIs
- avoid exposing internal backend addresses unnecessarily
- use TLS where traffic requires confidentiality
- validate health-check responses
- prevent request-routing data from becoming an SSRF mechanism
- record administrative changes for auditing

The examples use static backend configuration rather than allowing a client to supply arbitrary backend URLs.

## Operational Considerations

Real deployments normally add health checks, connection draining, timeouts, retries, circuit breakers, observability, and configuration management.

These mechanisms should not be confused with the selection algorithm itself.

For example:

`Health checking` determines whether a backend is eligible.

`Round robin` determines which eligible backend receives traffic.

`Retries` determine what happens after a request fails.

`Connection draining` controls how a backend leaves service.

`Observability` records whether the policy is achieving the desired operational behavior.

Keeping these concerns separate makes scheduler behavior easier to test and operate.

## Failure Handling

A robust load balancer must distinguish between:

- backend unavailable
- backend overloaded
- request failed
- scheduler has no candidate
- request completed successfully
- configuration is invalid

A backend failure should not be represented merely as a request failure.

The backend's health state determines future eligibility, while individual request status records what happened to a particular request.

This separation prevents historical request statistics from being incorrectly interpreted as current availability.

## Practical Comparison

| Requirement | Round Robin | Weighted Round Robin | Least Connections |
|---|---|---|---|
| Equal-capacity servers | Strong fit | Works | Works |
| Unequal server capacity | Weak | Strong | Strong with suitable tie-breaking |
| Variable request duration | Weak | Weak to moderate | Strong |
| Simple implementation | Excellent | Good | Good |
| Requires active connection state | No | No | Yes |
| Predictable traffic ratio | Strong | Strong | Not necessarily |
| Adapts to current load | No | No | Yes |
| Scheduler state | Position | Weighted position | Current workload |

No single policy is universally optimal.

Round robin is attractive when backends are similar and requests are relatively uniform.

Weighted round robin is useful when server capacity differs but traffic distribution should remain controlled.

Least connections is useful when concurrency and request duration vary enough that request count alone is a poor indicator of load.

## Architectural Relationship

The complete conceptual workflow is:

`Incoming Request`
  
`↓`

`Load Balancer`

`↓`

`Eligibility Check`
  
`├── Healthy Backend`
  
`└── Unhealthy Backend Excluded`

`↓`

`Selection Policy`

`├── Round Robin`
  
`├── Weighted Round Robin`
  
`└── Least Connections`

`↓`

`Backend`

`↓`

`Active Connection`

`↓`

`Completion / Failure`

`↓`

`Updated Backend State`

The algorithm chooses a destination. Health controls eligibility. Connection state records current workload. Completion updates the state used by future decisions.

That separation is the central design principle shared across the five implementations.
