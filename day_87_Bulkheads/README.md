# Bulkheads: Resource Isolation and Failure Containment

## 1. Technical Scope

The bulkhead pattern is a resilience and resource-management technique that separates an application into independent execution domains. Each domain receives a controlled allocation of resources, such as concurrent connections, worker threads, execution slots, memory, or queue capacity.

The principal objective is failure containment.

When one downstream dependency becomes slow, unavailable, or overloaded, its resource consumption should not exhaust the capacity required by unrelated application functions.

The implementations in this repository demonstrate:

- Independent resource pools.
- Bounded concurrency.
- Bounded request queues.
- Admission control.
- Load shedding.
- Circuit breakers.
- Failure tracking.
- Recovery probes.
- Request lifecycle management.
- Resource utilization monitoring.
- Operational reporting.

All implementations use synthetic application workloads.

## 2. Fundamental Concepts

### 2.1 Resource Isolation

Resource isolation assigns separate capacity limits to different application dependencies.

Consider an e-commerce application containing three services:

| Service | Dependency | Maximum concurrent operations | Queue capacity |
|---|---|---:|---:|
| Payment | Payment gateway | 2 | 3 |
| Inventory | Inventory database | 3 | 4 |
| Notification | Messaging provider | 1 | 2 |

If the notification provider becomes unavailable, its requests should not consume the execution capacity allocated to payment processing.

Without isolation, all three services might share one thread pool or connection pool. A large number of blocked notification requests could exhaust that shared resource.

With bulkheads, notification failures remain within the notification execution domain.

### 2.2 Failure Containment

Failure containment prevents a local dependency failure from becoming an application-wide failure.

A typical failure sequence is:

1. A downstream service becomes slow.
2. Requests remain active for longer than expected.
3. Execution capacity becomes occupied.
4. New requests accumulate in a queue.
5. The queue reaches its configured limit.
6. Additional requests are rejected.
7. Other independently allocated resource pools remain available.

The important distinction is between detecting a failure and containing its resource impact.

A timeout detects excessive execution duration. A bulkhead limits the amount of application capacity exposed to that execution.

### 2.3 Resource Exhaustion

Resource exhaustion occurs when demand exceeds available resources.

Relevant resources include:

- Worker threads.
- Database connections.
- HTTP connections.
- Memory.
- CPU capacity.
- File descriptors.
- Message-processing slots.
- External API quotas.

A bulkhead does not increase the underlying resource supply. It controls how that supply is allocated.

## 3. Bulkhead Architecture

The application is separated into independent execution domains.

Plain-text architecture:

Application
|
+-- Payment Service
|   |
|   +-- Payment Bulkhead
|   +-- Bounded Queue
|   +-- Payment Gateway
|
+-- Inventory Service
|   |
|   +-- Inventory Bulkhead
|   +-- Bounded Queue
|   +-- Inventory Database
|
+-- Notification Service
    |
    +-- Notification Bulkhead
    +-- Bounded Queue
    +-- Messaging Provider

Each bulkhead maintains its own execution capacity, queue, metrics, and failure-handling state.

The separation should extend to the underlying resources where necessary. Separate application-level semaphores alone do not guarantee database, memory, CPU, or connection-level isolation.

## 4. Capacity Management

### 4.1 Concurrency Limits

Concurrency limits define the maximum number of operations executing simultaneously.

For a pool with concurrency capacity \(C\):

\[
0 \leq ActiveRequests \leq C
\]

For example, a payment pool with a concurrency limit of two cannot execute more than two payment operations simultaneously.

The limit protects downstream services from excessive concurrent requests and protects the application from unbounded resource consumption.

### 4.2 Bounded Queues

A queue temporarily holds requests that cannot immediately obtain execution capacity.

Let:

- \(C\) = maximum concurrent operations.
- \(Q\) = maximum queued operations.
- \(A\) = currently active operations.
- \(W\) = currently waiting operations.

The admission conditions are:

\[
A < C \Rightarrow DirectExecution
\]

\[
A \geq C \land W < Q \Rightarrow Queue
\]

\[
A \geq C \land W \geq Q \Rightarrow Reject
\]

A queue is not an unlimited storage mechanism.

Large queues can increase latency and retain excessive memory. A request that waits longer than its business deadline may no longer be useful.

Queue capacity should therefore be designed around expected arrival rates, service times, memory constraints, and acceptable response latency.

### 4.3 Little's Law

Little's Law relates average concurrency, throughput, and response time:

\[
L = \lambda W
\]

Where:

- \(L\) is average work in the system.
- \(\lambda\) is average throughput.
- \(W\) is average time spent in the system.

For example, if a service processes 20 requests per second and the average time in the system is 0.25 seconds:

\[
L = 20 \times 0.25 = 5
\]

The expected average number of requests in the system is five.

This is an average, not a safe maximum concurrency setting. Capacity planning must also account for bursts, tail latency, dependency limits, and failure scenarios.

## 5. Admission Control and Load Shedding

Admission control decides whether a request can enter a resource pool.

The implementations use three admission outcomes:

| Decision | Meaning |
|---|---|
| Accepted | Execution capacity is available. |
| Queued | Execution capacity is occupied, but queue capacity remains. |
| Rejected | The pool or queue cannot accept additional work. |

Load shedding rejects work that cannot be processed safely.

It is preferable to controlled rejection over allowing unlimited queues and causing application-wide resource exhaustion.

A rejection should be observable and distinguishable from a downstream execution failure.

Typical rejection conditions include:

- Maximum concurrency reached.
- Queue capacity exhausted.
- Circuit breaker open.
- Pool administratively disabled.
- Request deadline already exceeded.

Priority-based admission can be useful for enterprise applications, but it should include fairness controls to prevent low-priority requests from experiencing indefinite starvation.

## 6. Circuit Breakers and Recovery

The circuit breaker complements bulkhead isolation.

It prevents repeated requests to a dependency that is already experiencing failures.

### 6.1 Circuit States

| State | Behavior |
|---|---|
| CLOSED | Requests are permitted normally. |
| OPEN | Requests are rejected without calling the dependency. |
| HALF_OPEN | A limited recovery probe is permitted. |

### 6.2 State Transitions

CLOSED
|
| Failure threshold reached
v
OPEN
|
| Recovery interval elapsed
v
HALF_OPEN
|
+-- Probe succeeds --> CLOSED
|
+-- Probe fails -----> OPEN

The failure threshold determines how many failures trigger circuit opening.

The recovery interval determines how long the system waits before attempting recovery.

A half-open state limits test requests. Allowing every waiting request to probe an unhealthy dependency could immediately recreate the original overload.

### 6.3 Bulkhead Versus Circuit Breaker

These mechanisms address different problems.

| Mechanism | Primary responsibility |
|---|---|
| Bulkhead | Restricts resource consumption. |
| Circuit breaker | Stops calls to an unhealthy dependency. |
| Timeout | Limits how long an operation may execute. |
| Retry | Attempts another execution after a failure. |
| Rate limiter | Controls request arrival frequency. |
| Load shedding | Rejects work that cannot be safely admitted. |

Combining these mechanisms creates a stronger resilience architecture.

Retries require particular care. Unrestricted retries can amplify an existing outage. Retry policies should use bounded attempts, backoff, jitter, deadlines, and idempotency where appropriate.

## 7. Python Implementation

### File: `bulkheads.py`

The Python implementation models asynchronous resource isolation using `asyncio`.

Its principal components are:

| Component | Responsibility |
|---|---|
| `PoolConfig` | Validates resource-pool configuration. |
| `PoolMetrics` | Stores execution and failure metrics. |
| `CircuitBreaker` | Controls dependency access during failures. |
| `BulkheadPool` | Manages concurrency, queue admission, and execution. |
| `BulkheadManager` | Maintains independent pools. |

### 7.1 Asynchronous Execution

`asyncio.Semaphore` limits simultaneous operations.

Each pool receives an independent semaphore. Payment operations therefore cannot consume inventory or notification semaphore capacity.

The implementation also uses an asynchronous lock to protect queue accounting.

### 7.2 Queue Management

Queue admission is checked before waiting for the semaphore.

The configured queue limit restricts waiting requests. Requests that cannot enter the queue are rejected immediately.

The implementation distinguishes:

- Queue-capacity rejection.
- Queue-wait timeout.
- Execution timeout.
- Downstream execution failure.
- Circuit-open rejection.

These conditions represent different operational events and should not be combined into one generic error.

### 7.3 Timeout Handling

`asyncio.wait_for()` enforces execution deadlines.

Cancellation is propagated to the asynchronous operation. Downstream clients should support cancellation or their own request deadlines to avoid continued resource consumption after the caller has timed out.

### 7.4 Metrics

The implementation tracks:

- Accepted operations.
- Rejected operations.
- Completed operations.
- Failed operations.
- Timed-out operations.
- Active operations.
- Queued operations.
- Average latency.

The reporting method provides a separate operational view for every resource pool.

## 8. JavaScript Implementation

### File: `bulkheads.js`

The JavaScript implementation uses Node.js asynchronous execution and event-driven monitoring.

Its architecture differs from the Python semaphore-based model.

| Component | Responsibility |
|---|---|
| `ResourcePool` | Maintains independent execution capacity. |
| `CircuitBreaker` | Manages dependency failure states. |
| `BulkheadRegistry` | Registers and retrieves pools. |
| `EventEmitter` | Publishes operational events. |

### 8.1 Event-Driven Monitoring

The resource pool emits events including:

- `queued`
- `started`
- `completed`
- `failed`
- `rejected`
- `shutdown`

These events allow monitoring components to observe resource behavior without coupling monitoring logic to execution logic.

### 8.2 Promise-Based Execution

The implementation uses Promises to represent asynchronous operations.

`Promise.race()` enforces a caller-visible timeout.

An important distinction is that a Promise timeout does not automatically terminate the underlying operation.

A production implementation should use `AbortController`, cancellable clients, or other dependency-specific cancellation mechanisms.

Otherwise, an operation may continue consuming resources after its caller has received a timeout.

### 8.3 Graceful Shutdown

The pool rejects new work after shutdown.

Queued operations receive an explicit failure instead of remaining indefinitely in memory.

A production shutdown procedure should also wait for active operations up to a configured grace period before terminating the process.

## 9. C++17 Implementation

### File: `bulkheads.cpp`

The C++ implementation provides a repository-style governance engine for independent resource pools.

Its components are:

| Component | Responsibility |
|---|---|
| `PoolConfig` | Stores capacity and recovery parameters. |
| `Metrics` | Tracks pool utilization and outcomes. |
| `Request` | Represents a resource-consuming operation. |
| `CircuitBreaker` | Evaluates dependency health. |
| `BulkheadPool` | Controls admission and queue processing. |
| `GovernanceEngine` | Manages named resource pools. |

### 9.1 Domain Modeling

Enumerations represent circuit states and request outcomes.

Structures represent configuration, metrics, and requests.

The governance engine stores independent resource pools in an STL `map`.

The request queue uses `std::queue`, while a `std::set` prevents duplicate processed request identifiers.

### 9.2 Resource Invariants

The engine verifies:

\[
ActiveRequests \leq MaxConcurrent
\]

It also checks that each resource pool maintains its own capacity configuration.

An invalid pool configuration is rejected before registration.

### 9.3 Queue Processing

The implementation processes waiting requests whenever execution capacity becomes available.

Requests are processed in FIFO order.

This approach is simple and predictable but does not implement priority scheduling or fairness across multiple queues.

The example is a deterministic simulation. It does not create actual operating-system threads or perform real network operations.

A production C++ implementation would require an execution scheduler, synchronization primitives, cancellation handling, and dependency-specific timeout management.

## 10. Java 17 Implementation

### File: `BulkheadEnterprise.java`

The Java implementation models resource isolation in an enterprise-oriented application.

It uses:

- Records for immutable domain data.
- Enums for request and circuit states.
- Custom exceptions for failure classification.
- Collections for pool and request management.
- Synchronized methods for shared-state protection.
- `AtomicInteger` for request identifier allocation.
- Service classes for resource management.

### 10.1 Enterprise Domain Types

`PoolPolicy` represents the configuration governing a resource pool.

It contains:

- Resource name.
- Concurrency limit.
- Queue limit.
- Failure threshold.
- Recovery interval.
- Execution timeout.

The record constructor validates the configuration before an instance can be created.

`Request` represents an individual business operation.

`PoolSnapshot` provides an immutable operational view of resource consumption.

### 10.2 State Management

The resource pool tracks request states:

SUBMITTED
|
+-- RUNNING
|   |
|   +-- COMPLETED
|   +-- FAILED
|
+-- QUEUED
|   |
|   +-- RUNNING
|   +-- REJECTED

A request is not permitted to execute twice under the same request identifier.

The pool synchronizes operations that modify shared state.

### 10.3 Enterprise Policy Separation

The implementation separates three responsibilities:

1. Pool policy defines resource allocation.
2. Circuit breaker policy controls dependency access.
3. Resource registry manages the lifecycle and lookup of pools.

This separation makes policy validation and operational monitoring easier to maintain.

The demonstration uses synchronous simulated operations. The configured execution timeout is part of the domain policy but is not enforced by the synchronous simulation.

A production Java implementation should enforce deadlines using bounded executors, timed acquisition, cancellable futures, and dependency-level timeouts.

## 11. PostgreSQL Implementation

### File: `bulkheads.sql`

The PostgreSQL implementation provides a relational model for resource isolation, request admission, failure recording, and operational reporting.

It creates the `bulkhead` schema.

### 11.1 Relational Model

The primary relationships are:

Applications
|
+-- Resource Pools
    |
    +-- Pool Policies
    |
    +-- Resource Requests
    |   |
    |   +-- Admission Decisions
    |   +-- Execution Attempts
    |
    +-- Failure Events
    |
    +-- Pool State History

### 11.2 Applications

The `applications` table identifies the application and its owning team.

The environment constraint distinguishes development, staging, and production deployments.

### 11.3 Resource Pools

The `resource_pools` table defines independent execution domains.

Important attributes include:

- `max_concurrent`
- `max_queue`
- `timeout_ms`
- `failure_threshold`
- `recovery_seconds`
- `current_state`
- `active_requests`
- `queued_requests`

Database constraints prevent invalid capacities and negative resource counters.

The active and queued request counts are bounded by the corresponding configured capacities.

### 11.4 Pool Policies

The `pool_policies` table stores additional admission and recovery behavior.

It separates operational policy from the basic pool definition.

This allows policy changes without changing the identity of the resource pool.

### 11.5 Resource Requests

The `resource_requests` table records individual operations.

A UUID correlation identifier supports distributed request tracing.

An idempotency key prevents duplicate request submissions within the same resource pool when supplied.

The request status is controlled through a PostgreSQL enum and a transition-validation trigger.

### 11.6 Admission Decisions

The `admission_decisions` table records whether each request was:

- Accepted.
- Queued.
- Rejected.

The decision reason provides an auditable explanation of the admission result.

### 11.7 Execution Attempts

The `execution_attempts` table stores execution timing and outcomes.

Multiple attempts can be represented through the unique combination of request identifier and attempt number.

The schema distinguishes request identity from execution-attempt identity.

### 11.8 Failure Events

The `failure_events` table records failure categories, associated requests, and timestamps.

Failure categories distinguish:

- Downstream errors.
- Timeouts.
- Capacity exhaustion.
- Circuit-open rejection.
- Queue exhaustion.
- Dependency unavailability.
- Administrative events.

These records support failure analysis and circuit-breaker evaluation.

### 11.9 State History

The `pool_state_history` table provides an audit trail of resource-pool state changes.

An `AFTER UPDATE` trigger records transitions automatically.

This separates the current operational state from its historical record.

### 11.10 Admission Function

`admit_request()` implements resource admission.

It obtains a row-level lock on the resource pool using `FOR UPDATE`.

The lock prevents two concurrent transactions from independently observing the same available capacity and exceeding the configured limit.

The function evaluates:

1. Whether the request is still submitted.
2. Whether the pool is available.
3. Whether execution capacity exists.
4. Whether queue capacity exists.
5. Whether the request must be rejected.

The admission decision and request state change occur within the calling transaction.

### 11.11 Completion Function

`complete_request()` releases execution capacity and records the terminal outcome.

It validates that the request is running.

It then:

- Updates the request status.
- Records the completion timestamp.
- Decrements the active-request counter.
- Updates the associated execution attempt.
- Records a failure event when execution fails or times out.

The function prevents arbitrary completion of requests that have not entered execution.

### 11.12 Circuit Breaker Evaluation

`evaluate_circuit_breaker()` evaluates failure events within a specified time window.

It compares the observed failure count with the configured threshold.

When the threshold is reached, the pool transitions to `OPEN`.

When the recovery interval has elapsed, the pool can transition to `DEGRADED`.

The database example models state evaluation, not a complete distributed circuit-breaker coordinator. Production deployments need explicit probe ownership, atomic probe limits, and reliable state synchronization.

### 11.13 Queue Promotion

`promote_queued_requests()` demonstrates controlled queue promotion.

It uses `FOR UPDATE SKIP LOCKED` to allow concurrent workers to claim different queued requests.

Requests are ordered by priority and submission time.

The procedure promotes only as many requests as the available execution capacity permits.

A production implementation should ensure that queue counters and request transitions remain consistent under every worker failure and transaction retry.

### 11.14 Operational Reporting

The `pool_operational_report` view aggregates:

- Total requests.
- Completed requests.
- Failed requests.
- Rejected requests.
- Timed-out requests.
- Active capacity.
- Queue utilization.

Additional queries calculate failure percentages, utilization categories, recent failure concentration, and counter consistency.

## 12. Failure Scenarios and Expected Behavior

| Failure scenario | Expected behavior |
|---|---|
| Notification provider unavailable | Notification pool records failures. |
| Notification queue full | New notification requests are rejected. |
| Payment gateway slow | Payment execution deadline is enforced. |
| Payment concurrency exhausted | Additional requests wait within the configured queue limit. |
| Repeated downstream failures | Circuit breaker opens. |
| Recovery interval elapsed | Limited recovery probing begins. |
| Recovery probe succeeds | Circuit returns to normal operation. |
| Recovery probe fails | Circuit returns to the open state. |
| Unknown resource pool | Request is rejected through validation. |
| Invalid capacity configuration | Configuration is rejected. |
| Duplicate request identifier | Duplicate execution is prevented. |

The central isolation requirement is that a failure in one pool must not directly modify the concurrency or queue allocation of another pool.

## 13. Security and Reliability Considerations

### 13.1 Resource Exhaustion Protection

Every externally accessible operation should have bounded resource consumption.

This includes:

- Maximum concurrent operations.
- Queue capacity.
- Execution deadlines.
- Request payload limits.
- Connection limits.
- Retry limits.

### 13.2 Dependency Isolation

Application-level bulkheads should be complemented by infrastructure-level controls.

For example, separate database connection pools may be required when two application functions access databases with different reliability or capacity characteristics.

### 13.3 Cancellation

A caller timeout does not always terminate the underlying operation.

Cancellation should propagate to database queries, HTTP requests, worker tasks, and other resource-consuming operations wherever supported.

### 13.4 Idempotency

Rejected or timed-out requests may be retried by callers.

Payment operations require particular attention because duplicate processing can create financial inconsistencies.

Idempotency keys, transaction identifiers, and deduplication controls should be applied to operations where repeated execution is unsafe.

### 13.5 Observability

A production implementation should monitor:

| Metric | Operational purpose |
|---|---|
| Active requests | Measures current resource consumption. |
| Queue depth | Identifies waiting work. |
| Queue rejection count | Identifies overload. |
| Execution latency | Measures service performance. |
| Timeout count | Identifies slow operations. |
| Failure rate | Identifies dependency instability. |
| Circuit state | Identifies unavailable dependencies. |
| Recovery probe results | Measures recovery behavior. |
| Resource utilization | Supports capacity planning. |

Correlation identifiers should be propagated across service boundaries to support distributed tracing.

Logs should not expose credentials, payment information, personal information, or other sensitive request data.

### 13.6 Fairness and Priority

Strict FIFO queues provide predictable ordering but cannot always satisfy business priorities.

Priority scheduling can protect critical operations, but starvation prevention and reserved capacity should be considered.

### 13.7 Distributed Deployments

An in-memory semaphore or queue protects only the process in which it operates.

If an application runs across several instances, each instance may independently enforce its own concurrency limit.

A global resource limit therefore requires coordinated admission control or a shared downstream capacity mechanism.

Distributed coordination introduces additional latency and availability tradeoffs.

## 14. Performance and Complexity

The implementations make different engineering tradeoffs.

| Implementation | Primary resource-control mechanism | Main consideration |
|---|---|---|
| Python | Asyncio semaphore and bounded admission | Cooperative asynchronous execution |
| JavaScript | Promise queue and event-driven dispatch | Cancellation of underlying operations |
| C++17 | STL queue and explicit state management | Real concurrency requires synchronization and scheduling |
| Java 17 | Synchronized enterprise resource pools | Blocking execution and synchronization overhead |
| PostgreSQL | Row-level locking and relational constraints | Transaction contention and counter consistency |

Typical algorithmic costs:

| Operation | Expected complexity |
|---|---|
| Resource pool lookup using a hash map | Average \(O(1)\) |
| Resource pool lookup using an ordered map | \(O(\log n)\) |
| FIFO queue insertion | \(O(1)\) |
| FIFO queue removal | \(O(1)\) |
| Set-based duplicate detection | \(O(\log n)\) |
| Circuit-state evaluation | \(O(1)\), excluding failure-window queries |
| Indexed request lookup | Depends on index structure and selectivity |
| Failure aggregation | Depends on indexed rows and time-window size |

The actual bottleneck may be a database, network dependency, thread scheduler, lock, or external API rather than the bulkhead implementation itself.

## 15. Implementation Limitations

The implementations are educational simulations and do not constitute a complete production resilience platform.

Specific limitations include:

- The Python demonstration does not provide persistent queues.
- The JavaScript Promise timeout does not forcibly terminate underlying operations.
- The C++ implementation does not create real concurrent workers.
- The Java implementation uses synchronous simulated execution.
- The Java execution-timeout policy is not enforced by the synchronous example.
- The PostgreSQL schema demonstrates relational admission and accounting but is not a complete distributed scheduler.
- Recovery coordination across multiple application instances requires additional infrastructure.
- Database resource counters require reconciliation if operational processes fail outside their transaction boundaries.

These limitations are important because resource isolation must remain effective during process crashes, network partitions, cancellation, deployment, and partial dependency failure.

## 16. Practical Engineering Principles

The following principles govern a reliable bulkhead implementation:

1. Allocate independent resources to critical dependencies.
2. Set explicit concurrency limits.
3. Bound every queue.
4. Reject excess demand predictably.
5. Apply execution deadlines.
6. Use circuit breakers for repeatedly failing dependencies.
7. Limit recovery probes.
8. Track resource consumption independently.
9. Propagate cancellation where possible.
10. Protect business-critical operations through appropriate capacity allocation.
11. Prevent duplicate processing through idempotency controls.
12. Monitor overload and failure conditions.
13. Reconcile resource accounting after abnormal termination.
14. Test failures independently for every resource pool.

The essential architectural distinction is that bulkheads limit the resources exposed to a failure. Circuit breakers control access to unhealthy dependencies, timeouts bound waiting and execution, and load shedding protects the application when demand exceeds available capacity.
