# Circuit Breaker: Failure Isolation and Graceful Degradation

## 1. Technical Overview

A Circuit Breaker is a fault-tolerance pattern used in distributed systems to prevent repeated requests to an unavailable or unhealthy dependency.

In a distributed application, one service frequently depends on other services, databases, payment providers, inventory systems, identity providers, and external APIs.

When a dependency becomes unavailable, repeated requests can consume application threads, connections, memory, and network resources. These requests may remain blocked until their timeouts expire. The resulting resource exhaustion can affect otherwise healthy services.

A Circuit Breaker addresses this problem by monitoring dependency failures and temporarily stopping requests when the dependency becomes unhealthy.

Its primary objectives are:

- Failure isolation between dependent services.
- Prevention of repeated unsuccessful requests.
- Reduction of unnecessary network traffic.
- Controlled recovery testing.
- Protection of application resources.
- Graceful degradation when dependencies fail.
- Improved availability of independent application components.

## 2. Fundamental Concepts

### 2.1 Circuit Breaker

A Circuit Breaker is a stateful control mechanism positioned between an application component and a remote dependency.

It evaluates whether a request should be forwarded to the dependency or rejected immediately.

The circuit maintains operational state independently for each dependency.

For example:

- A payment provider can be unavailable.
- The inventory service can remain healthy.
- The recommendation engine can operate using cached information.

An outage in one dependency should not automatically disable unrelated application functionality.

### 2.2 Failure Isolation

Failure isolation prevents an unhealthy component from propagating its failures throughout the application.

Consider an e-commerce application:

| Component | Dependency | Failure consequence |
|---|---|---|
| Checkout | Payment provider | Payment cannot be confirmed immediately |
| Product page | Inventory provider | Current inventory may be unavailable |
| Discovery | Recommendation engine | Personalized recommendations may disappear |
| Authentication | Identity provider | New authentication requests may fail |

Without isolation, repeated dependency failures can exhaust shared application resources.

With separate circuit breakers, each dependency has its own failure threshold, recovery timer, state, and fallback policy.

### 2.3 Graceful Degradation

Graceful degradation means preserving useful application functionality when some dependencies are unavailable.

The application does not necessarily provide its complete functionality during an outage. Instead, it provides a controlled reduced-capability response.

Examples include:

| Dependency failure | Degraded behavior |
|---|---|
| Payment provider | Store a payment request for reconciliation |
| Inventory provider | Return a cached inventory snapshot |
| Recommendation engine | Display general recommendations |
| Notification provider | Queue notifications for later delivery |
| Analytics provider | Disable nonessential analytics |

A degraded response must accurately represent its reliability.

For example, a queued payment must not be presented as a completed payment. Cached inventory must not be represented as guaranteed current inventory.

## 3. Circuit Breaker State Machine

The Circuit Breaker normally operates through three states.

### 3.1 CLOSED

<badge color="success">Normal operation</badge>

In the CLOSED state, requests are permitted to reach the dependency.

The circuit monitors failures.

A typical policy counts consecutive failures and opens the circuit when the configured threshold is reached.

Example:

- Failure threshold: 3.
- First failure: remain CLOSED.
- Second failure: remain CLOSED.
- Third consecutive failure: transition to OPEN.

A successful operation resets the consecutive failure counter in the implementations.

This approach distinguishes consecutive failures from total historical failures.

### 3.2 OPEN

<badge color="danger">Requests isolated</badge>

In the OPEN state, requests are rejected without contacting the dependency.

The application may execute a fallback response instead.

The circuit records the time at which it opened.

The recovery timeout determines when the circuit becomes eligible to enter HALF_OPEN.

For example:

| Parameter | Value |
|---|---:|
| Failure threshold | 3 |
| Recovery timeout | 30 seconds |
| Half-open probe limit | 1 |
| Dependency timeout | 2.5 seconds |

The OPEN state reduces unnecessary dependency requests and limits the impact of continuing failures.

### 3.3 HALF_OPEN

<badge color="warning">Recovery testing</badge>

After the recovery timeout, the circuit enters HALF_OPEN.

A limited number of requests are allowed to test whether the dependency has recovered.

The outcome determines the next state:

- Successful recovery probe: transition to CLOSED.
- Failed recovery probe: transition to OPEN.
- Additional requests beyond the probe limit: reject or degrade.

The half-open probe limit prevents a recovering dependency from immediately receiving the full application request volume.

### 3.4 State Transition Diagram

    +-----------------------+
    |                       |
    |        CLOSED         |
    |                       |
    +-----------------------+
       |                 ^
       | Failure         | Successful
       | threshold       | recovery probe
       v                 |
    +-----------------------+
    |                       |
    |         OPEN          |
    |                       |
    +-----------------------+
       |
       | Recovery timeout
       v
    +-----------------------+
    |                       |
    |       HALF_OPEN       |
    |                       |
    +-----------------------+
       |                 |
       | Success         | Failure
       |                 |
       v                 v
     CLOSED             OPEN

## 4. Failure Isolation and Request Processing

A typical request passes through the following workflow:

    Client Request
          |
          v
    Application Service
          |
          v
    Circuit Breaker
          |
          +---- CLOSED ------> Remote Dependency
          |                          |
          |                          v
          |                     Response
          |
          +---- OPEN ---------> Reject Request
          |                          |
          |                          v
          |                      Fallback
          |
          +---- HALF_OPEN ---> Limited Probe
                                     |
                            +--------+--------+
                            |                 |
                          Success           Failure
                            |                 |
                            v                 v
                          CLOSED             OPEN

The Circuit Breaker makes an admission decision before the dependency operation begins.

This distinction is important because an OPEN circuit should prevent unnecessary network calls rather than merely detect failures after they occur.

## 5. Circuit Breaker and Related Resilience Patterns

Circuit Breakers are frequently combined with other resilience mechanisms. Their responsibilities are different.

| Mechanism | Primary responsibility |
|---|---|
| Circuit Breaker | Stop requests to unhealthy dependencies |
| Timeout | Limit the duration of an individual operation |
| Retry | Repeat an operation after a potentially temporary failure |
| Bulkhead | Limit resource consumption by independent workloads |
| Fallback | Provide an alternative response |
| Rate Limiting | Restrict request volume |
| Health Check | Evaluate component health |
| Load Balancing | Distribute requests across available instances |

### 5.1 Circuit Breaker Versus Retry

Retry attempts another operation after a failure.

Circuit Breaker prevents repeated operations when failures indicate that a dependency is unhealthy.

Uncontrolled retries can increase dependency load during an outage.

A sensible workflow is:

1. Apply a small, bounded retry policy for appropriate transient failures.
2. Apply timeouts to individual attempts.
3. Report the final failed operation to the Circuit Breaker.
4. Use fallback behavior when the circuit is open or the operation fails.

Retries should use exponential backoff and jitter where appropriate.

Retries must also respect idempotency.

A payment request must not be submitted repeatedly without a reliable mechanism for identifying duplicate transactions.

### 5.2 Circuit Breaker Versus Bulkhead

A Bulkhead isolates resource consumption.

For example, payment processing and recommendation requests can use separate thread pools or concurrency limits.

A Circuit Breaker controls whether requests are admitted based on dependency health.

Both mechanisms are useful because an application can experience resource exhaustion even before a circuit reaches its failure threshold.

## 6. Failure Detection and Configuration

The Circuit Breaker must use an explicit failure-detection policy.

Common configuration parameters include:

| Parameter | Description |
|---|---|
| Failure threshold | Number of consecutive failures required to open the circuit |
| Recovery timeout | Minimum OPEN duration before recovery testing |
| Half-open limit | Maximum concurrent recovery probes |
| Request timeout | Maximum permitted duration for a dependency operation |
| Failure-rate threshold | Failure percentage required to open the circuit |
| Minimum sample size | Minimum number of observations before evaluating failure rate |
| History limit | Maximum retained operational events |

Two common failure-detection approaches are:

**Consecutive failure counting**

The circuit opens after a configured number of consecutive failures.

This approach is simple and useful for dependencies with relatively stable traffic.

**Rolling failure-rate evaluation**

The circuit evaluates failures within a defined time window or request sample.

For example, a policy can open a circuit when at least 20 requests have been observed and the failure percentage exceeds 50%.

Rolling windows are useful for high-volume systems where consecutive failure counting may react too slowly or too aggressively.

The Python, JavaScript, C++, and Java implementations use consecutive failure counting. The PostgreSQL configuration includes fields for extending the policy with rolling failure-rate evaluation.

## 7. Python Implementation

### 7.1 Design

The Python implementation provides a thread-safe simulation of a dependency resilience layer.

Its primary components are:

| Component | Responsibility |
|---|---|
| `CircuitState` | Defines the three operational states |
| `CircuitConfig` | Stores validated circuit parameters |
| `CircuitMetrics` | Tracks execution statistics |
| `CircuitEvent` | Represents an operational event |
| `CircuitBreaker` | Controls dependency request admission |
| `PaymentService` | Demonstrates payment degradation |
| `ProductCatalog` | Demonstrates cached responses |

### 7.2 State Management

The implementation uses an enumeration to represent circuit states.

A reentrant lock protects:

- State transitions.
- Failure counters.
- Recovery timestamps.
- Half-open probe admission.
- Operational metrics.
- Event history.

The dependency operation executes outside the lock.

This decision prevents a slow network operation from blocking unrelated state-management operations.

The half-open probe count is reserved before the remote operation begins.

This prevents concurrent requests from exceeding the configured probe limit.

### 7.3 Exception Handling

The implementation distinguishes expected operational exceptions from other failures.

The configured exception tuple determines which failures contribute to circuit health.

An OPEN circuit raises `CircuitOpenError` when no fallback is supplied.

A fallback can return a degraded result without contacting the failed dependency.

The implementation does not treat every application exception as a dependency failure.

For example, an invalid payment amount should be rejected by input validation rather than counted as a network outage.

### 7.4 Demonstrated Workflows

The payment service returns a PENDING response when the payment provider is unavailable.

The product catalog returns cached product information when its remote dependency fails.

The script also verifies:

- Circuit opening.
- Immediate request rejection.
- Fallback execution.
- Recovery timeout.
- Successful recovery probe.
- Return to CLOSED.
- Invalid configuration rejection.

### 7.5 Python Concurrency Consideration

The implementation protects state transitions using a lock, but it is not a distributed circuit coordinator.

Separate processes and application instances maintain independent breaker state.

A production multi-instance system may require centralized coordination or independently operated local breakers with carefully defined thresholds.

## 8. JavaScript Implementation

### 8.1 Event-Driven Architecture

The JavaScript implementation uses asynchronous operations and Node.js EventEmitter.

The `AsyncCircuitBreaker` class manages dependency admission and Promise-based execution.

The `DependencyRegistry` manages multiple independent breakers through a Map.

This architecture supports event-driven monitoring without coupling the dependency implementation to reporting logic.

### 8.2 Promise-Based Execution

The `execute()` method accepts:

- An asynchronous operation.
- An optional fallback.
- A request timeout.

The operation and timeout are evaluated through Promise-based execution.

A timeout failure contributes to circuit health.

A fallback can return a cached or degraded response.

### 8.3 Event Monitoring

The implementation emits `circuit-event` notifications.

Important events include:

- STATE_TRANSITION
- CALL_SUCCESS
- CALL_FAILURE
- FALLBACK_EXECUTED

Monitoring components can subscribe to these events to update dashboards, generate alerts, or record operational telemetry.

### 8.4 Timeout Limitation

`Promise.race()` determines which Promise settles first, but it does not cancel the underlying dependency operation.

Consequently, a timed-out operation may continue executing.

Production implementations should propagate cancellation using mechanisms such as `AbortController` when the underlying API supports it.

The original operation must also be prevented from producing duplicate side effects after a timeout.

### 8.5 Dependency Registry

The registry maintains independent circuit breakers.

This provides a clear separation between dependency configuration, runtime state, and operational health reporting.

An inventory outage does not require opening the payment circuit.

## 9. C++17 Implementation

### 9.1 Engineering Perspective

The C++ implementation models Circuit Breaker behavior through explicit domain types and a reusable class.

It emphasizes:

- Strong type definitions.
- STL containers.
- Template-based dependency execution.
- Exception handling.
- State transition validation.
- Resource-conscious operational history.
- Dependency-specific service objects.

### 9.2 Domain Model

The primary types are:

| Type | Responsibility |
|---|---|
| `CircuitState` | Operational state |
| `DependencyType` | Dependency classification |
| `CircuitConfig` | Configuration and validation |
| `CircuitMetrics` | Runtime statistics |
| `CircuitEvent` | State and event information |
| `CircuitBreaker` | Admission and failure management |
| `PaymentService` | Payment dependency integration |
| `InventoryService` | Cached inventory degradation |

### 9.3 Template-Based Execution

The `execute()` template accepts an operation and fallback.

The operation returns its result when successful.

An operational exception updates circuit health and invokes the fallback.

This design allows the same Circuit Breaker implementation to support different result types without requiring a separate execution class for every service.

### 9.4 STL Data Structures

The implementation uses:

- `std::vector` for bounded event history.
- `std::map` for cached inventory.
- `std::optional` for the OPEN timestamp.
- `std::chrono` for recovery timing.
- `std::function`-compatible callable behavior through templates.

The event history removes its oldest entry when the configured storage limit is exceeded.

### 9.5 Concurrency Limitation

The supplied C++ implementation is a single-threaded executable demonstration.

Its state-management operations are not protected by synchronization primitives.

A concurrent production implementation would require a mutex or another synchronization strategy around permission admission, state transitions, and metrics.

Network operations should execute outside the state-management lock.

## 10. Java 17 Enterprise Implementation

### 10.1 Enterprise Domain Modeling

The Java implementation separates configuration, operational state, dependency execution, and fallback policies.

It uses Java 17 records for immutable data structures.

Important records include:

- `CircuitConfig`
- `CircuitEvent`
- `ServiceResponse`
- `DependencyHealth`

Configuration validation occurs during record construction.

Invalid configurations cannot be created successfully.

### 10.2 Interfaces and Policy Objects

The `FallbackPolicy<T>` interface defines the contract for fallback behavior.

Different dependency services can provide different policies without modifying the Circuit Breaker implementation.

For example:

- Payment processing uses a local reconciliation queue.
- Recommendation processing uses cached recommendations.

This separates resilience policy from service-specific business behavior.

### 10.3 Thread Safety

The Circuit Breaker uses synchronized methods for state admission and transitions.

AtomicLong counters support operational metric collection.

The synchronized sections protect the state machine from concurrent modification.

The dependency operation executes outside synchronized methods.

This reduces the likelihood that a slow dependency blocks other requests from accessing the breaker.

### 10.4 Dependency Registry

The registry manages independent Circuit Breaker instances.

Its health report provides a consolidated view of dependency states and operational metrics.

This supports service-level monitoring and centralized reporting.

### 10.5 Enterprise Considerations

A production Java deployment should also consider:

- Dependency-specific executors.
- Connection pool isolation.
- Request cancellation.
- Distributed tracing.
- Structured logging.
- Bounded event storage.
- Alert thresholds.
- Circuit configuration management.
- Graceful application shutdown.
- Metrics export.

## 11. PostgreSQL Implementation

### 11.1 Relational Domain Model

The PostgreSQL implementation models the operational and audit information associated with circuit management.

The principal entities are:

| Table | Purpose |
|---|---|
| `services` | Application service registry |
| `dependencies` | External and internal dependencies |
| `circuit_configurations` | Failure and recovery parameters |
| `circuit_instances` | Current operational state |
| `circuit_events` | State transition history |
| `dependency_calls` | Individual execution outcomes |
| `fallback_policies` | Dependency degradation rules |

### 11.2 Entity Relationships

    services
       |
       | 1:N
       v
    dependencies
       |
       +----------------------+
       |                      |
       v                      v
    circuit_configurations  fallback_policies
       |
       |
       v
    circuit_instances
       |
       +----------------------+
       |                      |
       v                      v
    circuit_events       dependency_calls

A service can own several dependencies.

Each dependency has its own configuration, circuit instance, and fallback policy.

A circuit instance maintains current state and aggregate operational counters.

The event and call tables preserve historical information.

### 11.3 Constraints

The database uses:

- Primary keys for entity identification.
- Foreign keys for relationship integrity.
- Unique constraints for dependency configuration.
- CHECK constraints for positive thresholds.
- ENUM types for controlled state values.
- JSONB for structured event metadata and fallback payloads.

The circuit configuration rejects invalid recovery parameters.

The circuit state table enforces consistency between OPEN state and its opening timestamp.

### 11.4 Database Functions

The SQL implementation contains several operational functions.

| Function | Responsibility |
|---|---|
| `create_circuit()` | Initializes a dependency circuit |
| `acquire_circuit_permission()` | Atomically evaluates request admission |
| `record_circuit_success()` | Records successful execution |
| `record_circuit_failure()` | Updates failure state and opens the circuit when required |
| `record_fallback()` | Records fallback execution |
| `dependency_failure_report()` | Aggregates dependency failures |

### 11.5 Atomic Request Admission

The `acquire_circuit_permission()` function uses `SELECT ... FOR UPDATE`.

This locks the selected circuit row while evaluating and updating admission state.

It helps prevent multiple database transactions from simultaneously exceeding the configured half-open probe limit.

The lock is held only within the database transaction.

It should not be held while waiting for an external HTTP request.

A production request workflow should:

1. Begin a short database transaction.
2. Acquire circuit permission.
3. Commit the admission decision.
4. Execute the external operation outside the transaction.
5. Record the result in a separate transaction.

This avoids holding database locks during slow network operations.

### 11.6 Triggers and Auditing

The `audit_circuit_transition()` trigger records changes to the circuit state.

It creates an audit event whenever the state changes.

This provides historical visibility into circuit behavior.

Operational auditing is important when investigating recurring outages, unstable dependencies, and recovery problems.

### 11.7 Reporting and Aggregation

The SQL script includes:

- Current dependency health.
- State transition history.
- Dependency execution outcomes.
- Average request latency.
- Failure reports.
- Recovery probe eligibility.
- Missing configuration detection.

Indexes support dependency-specific historical retrieval and time-based reporting.

The operational call table can grow rapidly. Production deployments should introduce retention policies, time partitioning, and archival processes.

## 12. Four Distinct Resilience Responsibilities

The central distinction is between detecting failure, controlling access, and maintaining useful application behavior.

| Mechanism | Responsibility | Decision |
|---|---|---|
| Failure detection | Determine whether a dependency is unhealthy | Is the dependency failing? |
| Circuit Breaker | Control request admission | Should the dependency receive another request? |
| Fallback | Provide alternative behavior | What can the application return instead? |
| Graceful degradation | Preserve reduced application functionality | Which features can remain available? |

These mechanisms work together but should not be treated as interchangeable.

A fallback does not repair a failed dependency.

A Circuit Breaker does not guarantee that an alternative response is correct.

Graceful degradation does not imply that every operation can safely continue.

Business requirements must determine which operations can be delayed, cached, rejected, or completed locally.

## 13. Important Failure Scenarios

### 13.1 Dependency Timeout

A dependency accepts a request but does not respond within the configured time.

The timeout mechanism terminates the application's wait.

The failure is reported to the Circuit Breaker.

The fallback may provide an alternative response.

### 13.2 Connection Refused

The dependency endpoint is unavailable.

Repeated connection failures can open the circuit.

Subsequent requests are rejected before network execution.

### 13.3 Partial Dependency Failure

A dependency may respond successfully for some requests while failing for others.

A failure-rate policy may provide better detection than a consecutive-failure threshold.

The decision depends on traffic patterns and dependency behavior.

### 13.4 Recovery Instability

A dependency may recover briefly and fail again.

The HALF_OPEN state limits recovery traffic.

If the recovery probe fails, the circuit returns to OPEN.

### 13.5 Fallback Failure

A fallback can also become unavailable.

For example, a cache may be inaccessible during a database outage.

Fallback execution must therefore have its own error handling, timeout, resource limits, and monitoring.

A failed fallback must not be silently presented as a successful response.

### 13.6 Stale Cache Data

Cached information may become outdated.

Applications should define:

- Maximum permitted staleness.
- Cache refresh behavior.
- Data consistency requirements.
- Conditions under which stale data must be rejected.

Inventory and financial information require particular attention because stale values can create business consequences.

### 13.7 Non-Idempotent Operations

Payment processing and other state-changing operations require special treatment.

A timeout does not prove that the remote operation failed.

The dependency may have completed the operation while its response was lost.

Use idempotency keys, transaction identifiers, and reconciliation workflows to prevent duplicate side effects.

## 14. Security and Operational Considerations

### 14.1 Sensitive Information

Operational logs should not contain:

- Payment credentials.
- Authentication tokens.
- Private customer information.
- Database passwords.
- Complete sensitive request payloads.

Use correlation identifiers and sanitized error details.

### 14.2 Failure Injection

Failure testing should cover:

- Connection failures.
- Request timeouts.
- Partial responses.
- Dependency overload.
- Recovery instability.
- Fallback failures.
- Concurrent requests.
- Recovery probe races.

Failure injection must be performed in controlled test environments.

### 14.3 Monitoring Metrics

Important operational metrics include:

| Metric | Purpose |
|---|---|
| Circuit state | Current dependency health control state |
| Failure count | Number of dependency failures |
| Rejected requests | Requests blocked by the circuit |
| Fallback count | Requests handled through degraded behavior |
| Recovery attempts | Number of half-open probes |
| Request latency | Dependency response performance |
| Success rate | Successful operations among completed operations |
| State transitions | Frequency of circuit changes |

A circuit that repeatedly transitions between OPEN and CLOSED may indicate an unstable dependency or poorly selected thresholds.

### 14.4 Alerting

Alerting should consider both circuit state and business impact.

For example, an OPEN payment circuit is more critical than an OPEN recommendation circuit in an application where payments are essential.

Alerts should also consider the duration of the outage, affected traffic, fallback success, and dependency recovery behavior.

## 15. Performance and Complexity

| Operation | Expected complexity |
|---|---|
| State inspection | O(1) |
| Failure counter update | O(1) |
| Circuit transition | O(1) |
| Permission admission | O(1) |
| Fallback selection | O(1), excluding fallback execution |
| Bounded event insertion | O(1) amortized for deque-based implementations |
| Dependency registry lookup | O(1) average for hash-based registries |
| Historical database retrieval | Depends on index selectivity and retained records |

The primary performance benefit is avoiding unnecessary dependency operations during an outage.

The Circuit Breaker itself should remain inexpensive.

Monitoring and history collection must be bounded to avoid creating a new resource exhaustion problem.

## 16. Implementation Comparison

| Dimension | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Main perspective | Thread-safe simulation | Asynchronous execution | Typed state engine | Enterprise policy model | Relational operational model |
| State representation | Enum | Frozen object | Enum class | Enum | PostgreSQL ENUM |
| Configuration | Dataclass | Validated object | Struct | Record | Relational table |
| Event handling | Bounded deque | EventEmitter | Vector | Deque | Audit table and trigger |
| Execution model | Callable | Promise | Templates | Callable interface | Transactions and functions |
| Fallback | Callable | Promise callback | Template callable | Policy interface | Stored policy |
| Validation | Assertions and exceptions | Runtime validation | Exceptions | Record validation | Constraints and functions |
| Concurrency | Reentrant lock | Event loop | Single-threaded demonstration | Synchronization | Row-level locking |

## 17. Practical Design Limitations

The implementations are educational operational models, not complete distributed coordination platforms.

Their limitations are important:

- Python state is local to a process.
- JavaScript Promise timeouts do not automatically cancel underlying operations.
- C++17 synchronization must be added before concurrent execution.
- Java synchronization protects local state but does not coordinate separate application instances.
- PostgreSQL functions demonstrate atomic database state operations but do not replace application-level network execution.
- The SQL recovery example demonstrates an explicitly controlled state reset and is not a substitute for a real dependency recovery probe.
- None of the implementations provides a complete rolling-window statistical policy.
- None provides a complete distributed configuration propagation system.

A production architecture should combine local dependency isolation, bounded concurrency, timeouts, carefully controlled retries, suitable fallback behavior, operational monitoring, and reliable recovery testing.

The central design principle is to prevent one failing dependency from consuming the resources and availability of the rest of the application.
