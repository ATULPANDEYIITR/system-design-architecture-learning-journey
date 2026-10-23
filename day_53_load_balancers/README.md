# Load Balancers: Traffic Distribution and Health Checks

## Scope

This project models a load-balancing system that distributes application traffic across multiple backend servers while continuously evaluating backend health and capacity.

The five implementations use the same engineering domain but deliberately emphasize different mechanisms:

| File | Primary perspective | Main responsibility |
|---|---|---|
| Python | Operational simulation | Models backend state, routing algorithms, health thresholds, capacity, failover, and recovery |
| JavaScript | Event-driven service model | Uses asynchronous health probes and events to represent dynamic backend availability |
| C++17 | Governance and routing engine | Implements deterministic backend selection, health isolation, capacity constraints, and failure handling |
| Java 17 | Enterprise domain model | Represents routing policy, health services, domain states, validation, and eligibility decisions |
| PostgreSQL | Persistent operational model | Stores load balancers, backends, health observations, requests, routing decisions, and capacity state |

A load balancer sits between clients and a pool of service instances:

Client traffic  
→ Load Balancer  
→ Routing Policy  
→ Healthy Backend Pool  
→ Application Servers

Health information flows in the opposite operational direction:

Application Server  
→ Health Probe  
→ Health State  
→ Available Backend Pool  
→ Routing Decision

The central relationship is important: **traffic distribution decides where a request should go, while health checks determine which destinations are eligible to receive traffic.**

## Load Balancer Model

A backend is represented by an identity, network endpoint, routing weight, connection capacity, health state, and operational counters.

The implementations distinguish three important states:

| State | Meaning |
|---|---|
| `healthy` | Eligible for normal traffic when capacity is available |
| `unhealthy` | Removed from normal routing because health evidence exceeded the failure threshold |
| `draining` | Conceptual operational state for controlled removal while existing connections finish |

A healthy backend is not necessarily routable. It can be unavailable because its maximum connection capacity has been reached.

The effective routing condition is therefore:

`healthy AND available capacity`

This prevents the load balancer from treating health as the only availability signal.

## Traffic Distribution

### Round Robin

Round robin cycles through eligible backends in sequence.

For three healthy backends:

`backend-01 → backend-02 → backend-03 → backend-01`

The Python, C++, JavaScript, and Java implementations maintain routing position so that a failed backend can be skipped without permanently changing the configured backend list.

Round robin is simple and has predictable distribution when backend capacity and request cost are relatively uniform.

It becomes less suitable when:

- requests have very different processing costs;
- backend instances have different capacities;
- long-lived connections produce uneven load;
- some instances require more traffic than others.

### Weighted Round Robin

Weighted routing assigns a relative traffic share to each backend.

For weights:

| Backend | Weight |
|---|---:|
| `small` | 1 |
| `large` | 3 |

A simplified weighted schedule produces approximately:

`small → large → large → large`

The implementations use weights as routing capacity indicators rather than treating them as health information. A backend with a high weight still becomes ineligible when health checks mark it unhealthy.

Production systems often use smoother weighted algorithms rather than expanding a weighted list. Smooth weighted round robin reduces burstiness and provides more even short-term distribution.

### Least Connections

Least-connections routing chooses the eligible backend with the smallest number of active connections.

The selection rule used by the implementations is conceptually:

`minimum(active_connections, then prefer higher weight, then deterministic backend ID)`

This is useful for workloads in which connections remain open for different durations.

For example:

| Backend | Active connections |
|---|---:|
| `node-a` | 8 |
| `node-b` | 3 |
| `node-c` | 5 |

A new request should normally prefer `node-b`.

Least connections does not mean least CPU utilization. A backend can have few connections while still consuming substantial CPU or memory. Production systems may therefore combine connection count with latency, queue depth, resource utilization, or service-specific metrics.

## Health Checks

Health checks answer a different question from traffic distribution.

Routing asks:

> Which eligible backend should receive this request?

Health checking asks:

> Is this backend currently capable of serving requests?

The Python and JavaScript models use simulated health probes. The C++ implementation models the state transition without requiring network access. The PostgreSQL implementation records health observations and applies thresholds transactionally.

A real health checker might perform:

- TCP connection testing;
- HTTP readiness checks;
- HTTP liveness checks;
- TLS handshake validation;
- application-specific dependency checks.

A production health endpoint should generally represent the service's ability to handle the intended workload rather than merely proving that a process exists.

## Failure Thresholds

A single failed health probe does not always justify immediate removal.

The model uses consecutive failure thresholds.

Example:

`PASS → FAIL → FAIL`

With a failure threshold of two:

`healthy → healthy → unhealthy`

This avoids removing a backend because of a single transient network problem.

The same principle is used for recovery.

With a recovery threshold of two:

`unhealthy → PASS → PASS → healthy`

The backend is not immediately returned to service after the first successful probe.

This introduces hysteresis into the state machine and reduces repeated oscillation between healthy and unhealthy states.

## Active and Passive Health Signals

The implementations distinguish active health checking from passive failure observation.

### Active Checks

The load balancer explicitly probes a backend.

The result may contain:

- success or failure;
- response latency;
- diagnostic information;
- timestamp.

The PostgreSQL `health_check` table preserves these observations so operational history can be inspected later.

### Passive Failures

A request may fail even though the most recent active health check succeeded.

Examples include:

- application-level errors;
- connection resets;
- request timeouts;
- upstream dependency failures;
- overloaded workers.

The Python implementation can record passive failures and increase the failure counter.

A production load balancer can combine active and passive signals, but care is required because aggressive passive eviction can remove instances during temporary application-level spikes.

## Capacity and Connection Management

Health status alone does not determine routing eligibility.

Each backend has:

- `active_connections`;
- `max_connections`;
- request counters;
- failure counters.

The Python, C++, JavaScript, and Java implementations reject routing when every healthy backend has exhausted capacity.

The PostgreSQL schema enforces:

`active_connections >= 0`

and

`active_connections <= max_connections`

A PostgreSQL trigger prevents invalid connection counts from entering the database even when a caller bypasses application-level validation.

This is a database-level integrity boundary rather than merely an application convention.

## Python Implementation

The Python implementation is an operational simulator.

`Backend` encapsulates:

- endpoint information;
- health state;
- routing weight;
- active connections;
- capacity;
- request statistics;
- consecutive health results.

`HealthChecker` implements the failure and recovery threshold mechanism.

`LoadBalancer` separates backend selection from request lifecycle management.

The routing strategy is represented by `DistributionStrategy`, allowing the same backend pool to be evaluated under:

- round robin;
- weighted round robin;
- least connections.

The simulation includes:

- normal round-robin routing;
- health-check failure;
- automatic backend isolation;
- successful recovery;
- weighted distribution;
- least-connections selection;
- capacity exhaustion.

The implementation deliberately uses standard-library features such as dataclasses, enums, collections, exceptions, and type annotations.

## JavaScript Implementation

The JavaScript implementation emphasizes event-driven behavior.

`EventEmitter` is used to publish operational events:

- `backendUnavailable`;
- `backendAvailable`;
- `requestRouted`.

The `HealthMonitor` performs asynchronous probes. This represents the fact that real health checks are I/O operations and should not block the routing system.

The event flow is:

`Health Probe → State Transition → Event → Routing Pool Update`

This provides a useful distinction from the Python implementation. The routing model does not need to poll every other component after each state transition because availability changes are emitted as events.

The implementation also models request completion explicitly so active connections can influence least-connections routing.

## C++17 Implementation

The C++ implementation treats the load balancer as a deterministic routing engine.

The `Backend` class owns mutable operational state, while `HealthChecker` controls health transitions and `LoadBalancer` controls routing.

The implementation uses:

- `enum class` for constrained states;
- `std::vector` for the backend pool;
- `std::map` for uniqueness validation;
- algorithms such as `std::min_element`;
- exceptions for invalid configuration and impossible state transitions.

Least-connections selection is deterministic. If two backends have equal connection counts, the engine prefers the higher configured weight and then the lexicographically smaller backend identifier.

This deterministic tie-breaking is useful for repeatable testing and debugging.

The C++ program also separates health state from connection state. A backend may be unhealthy while still containing active connections, which reflects real draining and failure-isolation behavior.

## Java 17 Implementation

The Java implementation uses an enterprise-oriented domain structure.

The model contains explicit domain types for:

- backend state;
- routing strategy;
- failure reason;
- health results;
- branch-style operational policy;
- merge-style eligibility evaluation.

The central service objects are:

`HealthService`

and

`LoadBalancer`

The `Backend` class controls its own invariants. It refuses invalid connection transitions rather than allowing callers to manipulate internal counters directly.

Java records are used for immutable health-check results and policy values.

Collections are exposed through immutable copies where appropriate. This prevents callers from accidentally modifying the internal backend list maintained by the load balancer.

The design separates:

- domain state;
- health evaluation;
- routing selection;
- policy evaluation.

That separation makes the model easier to test and extend than a single procedural routing function.

## PostgreSQL Implementation

The PostgreSQL implementation treats load balancing as an operational data model.

The main relationships are:

`load_balancer`
→ `backend`

`backend`
→ `health_check`

`load_balancer`
→ `client_request`

`client_request`
→ `routing_decision`

This preserves the history necessary to answer operational questions such as:

- Which backends are currently healthy?
- How many health checks have failed?
- Which backend received a request?
- How much connection capacity remains?
- Which requests were rejected?
- What routing strategy is configured?

### Constraints

The schema uses database-level rules for:

- valid TCP ports;
- positive weights;
- positive connection capacity;
- non-negative counters;
- valid request/rejection combinations;
- unique backend names per load balancer.

These constraints protect the data model even if multiple applications write to the database.

### Health State Function

`record_health_check()` records the observation and updates consecutive success and failure counters.

The function locks the backend row before modifying its state.

This matters when multiple operational processes can report health simultaneously.

The function implements:

`healthy + repeated failures → unhealthy`

and:

`unhealthy + repeated successes → healthy`

### Routing Function

`route_request()` evaluates the available backend pool.

A candidate must be:

- attached to the requested load balancer;
- healthy;
- below maximum connection capacity.

The current SQL implementation provides explicit strategy branches and deterministic candidate selection. The database model is intended to demonstrate the relational representation of routing state rather than replace a specialized high-throughput network load balancer.

### Transactional Request Lifecycle

Routing and completion modify connection counters.

A routed request creates:

- a request record;
- a routing decision;
- an active connection on the selected backend.

Completion decrements the connection count and changes the request state to `completed`.

Transactions provide an atomic boundary around operations that must not leave partial routing state.

## Failure and Recovery State Machine

The operational state transition is:

`HEALTHY`
→ repeated failed probes
→ `UNHEALTHY`

`UNHEALTHY`
→ repeated successful probes
→ `HEALTHY`

Capacity introduces another routing condition:

`HEALTHY + capacity`
→ eligible

`HEALTHY + no capacity`
→ temporarily ineligible

An unhealthy backend can still have active connections. Removing it from new traffic does not imply that existing connections instantly disappear.

A production implementation may therefore use:

`HEALTHY → DRAINING → UNHEALTHY`

when controlled removal is required.

## Merge and Repository Governance Are Not Part of This Model

Pull Requests, code reviews, approvals, and branch protection are repository-development mechanisms rather than load-balancer mechanisms.

They are intentionally not used as abstractions for backend routing.

A load balancer has a different responsibility boundary:

| Repository governance | Load balancing |
|---|---|
| Change proposal | Request arrival |
| Code review | Backend health evaluation |
| Approval | Routing eligibility |
| Branch protection | Service availability policy |
| Merge eligibility | Request routing eligibility |

The relationship is conceptual rather than operational. Both domains enforce policies before an action is allowed, but their state, failure conditions, and decision criteria are different.

## Edge Cases

### No Healthy Backends

If every backend becomes unhealthy, the routing layer must reject new requests rather than send traffic to a known failing service.

The implementations raise or record an explicit failure.

### All Backends at Capacity

A backend can be healthy but temporarily unable to accept another connection.

The routing layer must distinguish this from health failure.

### Duplicate Backend Identity

Duplicate backend IDs make deterministic routing and operational reporting ambiguous.

The Python, JavaScript, C++, Java, and SQL models reject duplicate identities.

### Invalid Port

Ports outside `1..65535` are rejected during backend construction or database insertion.

### Connection Underflow

Completing a request when no active connection exists is rejected. Allowing the counter to become negative would corrupt capacity calculations.

### Flapping Backends

A backend alternating between success and failure can repeatedly enter and leave the routing pool.

Consecutive success and failure thresholds reduce this instability.

Production systems may also use cooldown intervals, exponential backoff, circuit breakers, or minimum healthy durations.

## Performance Characteristics

Let `B` be the number of configured backends.

Round-robin selection is approximately `O(B)` in the implementations because failed or capacity-exhausted nodes may need to be skipped.

Least-connections selection is `O(B)` because candidates are scanned.

The simplified weighted implementation constructs or evaluates weighted candidates. Its memory and selection behavior depend on the sum of backend weights.

Health checking is `O(B)` for a full backend-pool probe cycle.

The PostgreSQL indexes target common operational access paths:

- backend state and active connections;
- health history by backend and time;
- routing decisions by backend and time.

A production high-scale implementation would usually keep hot routing decisions in memory and use a database for configuration, durable telemetry, auditing, and historical analysis.

## Security Considerations

A production load balancer should not trust arbitrary client-provided routing information.

Important controls include:

- authenticated administrative access;
- authorization for backend registration;
- encrypted health-check traffic where required;
- TLS certificate validation;
- protection of management endpoints;
- rate limiting on administrative operations;
- audit logging for backend changes;
- strict validation of configured hosts and ports;
- prevention of health-check endpoints exposing sensitive diagnostic data.

Health endpoints should reveal only information necessary for availability evaluation.

The database layer should also use restricted service accounts. Applications that only perform routing reads should not automatically receive schema-administration privileges.

## Production Trade-offs

| Decision | Benefit | Trade-off |
|---|---|---|
| Round robin | Simple and predictable | Ignores request cost |
| Weighted routing | Supports unequal backend capacity | Requires meaningful weight management |
| Least connections | Adapts to connection distribution | Connection count does not equal workload |
| Active health checks | Detects failures before routing | Probe traffic consumes resources |
| Passive failure detection | Observes real request failures | Can react to transient errors |
| Failure thresholds | Reduces false eviction | Delays detection |
| Recovery thresholds | Reduces flapping | Delays reintegration |
| Connection limits | Protects overloaded services | Can increase rejected traffic |
| Persistent health history | Enables auditing and analysis | Adds storage and write overhead |

A robust production design normally combines several signals rather than assuming one routing algorithm is universally optimal.

## Executing the Implementations

The Python program runs with Python 3.10 or later.

The JavaScript implementation runs in a modern Node.js runtime.

The C++ source requires a C++17-compatible compiler.

The Java implementation requires Java 17 or later.

The PostgreSQL script requires PostgreSQL with support for enums, PL/pgSQL functions, triggers, CTEs, views, and standard transactional SQL.

No third-party library is required by the five implementations.

## Implementation Boundaries

The examples intentionally simulate routing rather than opening real sockets or becoming a production network proxy.

They provide executable models for:

- backend registration;
- routing decisions;
- health state transitions;
- failure isolation;
- recovery;
- capacity tracking;
- operational reporting.

A real deployment would add network I/O, connection pooling, TLS handling, request timeouts, observability pipelines, distributed configuration, graceful draining, retry policy, overload protection, and deployment-specific failure semantics.
