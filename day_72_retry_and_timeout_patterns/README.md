# Retry and Timeout Patterns

## 1. Technical Scope

Retry and timeout patterns provide resilience when applications communicate with remote services, databases, message brokers, payment gateways, and other dependencies.

A distributed request can fail because of temporary network interruptions, service overload, rate limiting, slow processing, or permanent application errors.

Retry mechanisms attempt an operation again when its failure is considered recoverable. Timeout mechanisms limit how long an application waits for a response. Backoff controls the interval between attempts. Jitter introduces randomness into those intervals to prevent synchronized retries.

This project implements five complementary engineering perspectives covering:

- Exponential backoff.
- Full jitter and equal jitter.
- Request deadlines and timeouts.
- Retry budgets.
- Circuit breakers.
- Retry storm simulation.
- Failure classification.
- Execution history and monitoring.
- Idempotency and database-level retry tracking.

## 2. Fundamental Terminology

| Concept | Description |
|---|---|
| Retry | Re-execution of a failed operation |
| Attempt | One execution of an operation |
| Timeout | Maximum permitted waiting duration |
| Backoff | Increasing delay between attempts |
| Exponential backoff | Delay increases exponentially |
| Jitter | Random variation in retry delays |
| Retry storm | Large synchronized volume of retries |
| Retry budget | Maximum aggregate retry allowance |
| Circuit breaker | Prevents calls to an unhealthy dependency |
| Idempotency | Repeated execution produces the same intended effect |
| Retry exhaustion | Maximum permitted attempts have been reached |
| Request deadline | Total time available for the complete operation |

### 2.1 Retryable and permanent failures

Failures must be classified before retrying.

| Failure | Typical retry decision |
|---|---|
| Connection reset | Retry |
| Temporary connection refusal | Retry selectively |
| Request timeout | Retry selectively |
| HTTP 429 | Retry according to rate-limit instructions |
| HTTP 502 | Usually retry |
| HTTP 503 | Usually retry |
| HTTP 504 | Usually retry |
| HTTP 400 | Normally do not retry |
| HTTP 401 | Do not retry without correcting authentication |
| HTTP 403 | Normally do not retry |
| Invalid request data | Do not retry |
| Business-rule rejection | Do not retry |

The classification depends on the operation and service contract. A timeout does not establish that the server failed to execute the operation.

For example, a payment request may have been successfully processed even though the response was lost.

## 3. Exponential Backoff

Exponential backoff increases the waiting period after successive failures.

The basic formula is:

\[
D_n = \min(D_{\max},D_0 \times B^n)
\]

Where:

- \(D_n\): Delay before retry \(n\).
- \(D_0\): Initial delay.
- \(B\): Backoff multiplier.
- \(D_{\max}\): Maximum permitted delay.
- \(n\): Zero-based retry number.

Example configuration:

| Parameter | Value |
|---|---:|
| Initial delay | 200 ms |
| Multiplier | 2 |
| Maximum delay | 3,000 ms |
| Maximum attempts | 4 |

The resulting delays without jitter are:

| Retry | Delay |
|---|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |

The initial request is not counted as a retry.

Capping the delay prevents exponential growth from producing excessively long waiting periods.

## 4. Jitter Strategies

Exponential backoff alone does not eliminate synchronized retries.

Consider 1,000 application instances that encounter the same outage. If they all use identical retry schedules, their requests may arrive at approximately the same time.

This creates repeated load spikes.

Jitter introduces randomized delays.

### 4.1 No jitter

\[
D_n = \min(D_{\max},D_0B^n)
\]

All clients calculate identical delays when their initial conditions are identical.

### 4.2 Full jitter

\[
D_n = U(0,\min(D_{\max},D_0B^n))
\]

The actual delay is selected uniformly between zero and the calculated backoff ceiling.

Full jitter distributes retry traffic across a wider interval.

### 4.3 Equal jitter

\[
D_n =
\frac{C_n}{2}
+
U(0,\frac{C_n}{2})
\]

Where \(C_n\) is the capped exponential delay.

Equal jitter maintains a minimum waiting period while still introducing randomness.

| Strategy | Behavior | Main consideration |
|---|---|---|
| None | Fixed exponential delay | Synchronization risk |
| Full jitter | Random delay from zero to ceiling | Strong spreading of retry traffic |
| Equal jitter | Random delay within upper half | Preserves a minimum delay |

Jitter reduces synchronized request concentration. It does not reduce the total number of logical retries by itself.

## 5. Timeout Management

Timeouts prevent an application from waiting indefinitely for an unavailable dependency.

A complete request can involve multiple stages:

1. Connection establishment.
2. DNS resolution.
3. TLS negotiation.
4. Request transmission.
5. Remote processing.
6. Response transmission.

A production system should distinguish relevant timeout categories.

| Timeout | Purpose |
|---|---|
| Connection timeout | Limits connection establishment |
| Read timeout | Limits waiting for response data |
| Request timeout | Limits an individual request |
| Attempt timeout | Limits one execution attempt |
| Total deadline | Limits the complete operation |

### 5.1 Individual timeout and total deadline

An individual timeout does not guarantee that the complete operation finishes within an acceptable duration.

For example:

- Attempt 1: 2 seconds.
- Backoff: 1 second.
- Attempt 2: 2 seconds.
- Backoff: 2 seconds.
- Attempt 3: 2 seconds.

The total operation can consume approximately nine seconds.

A total deadline must account for:

\[
T_{\text{total}} =
\sum T_{\text{attempts}}
+
\sum T_{\text{backoff}}
\]

A retry should not begin if the remaining deadline cannot accommodate the planned delay and another useful attempt.

### 5.2 Timeout cancellation

A timeout must ideally cancel the underlying operation.

In JavaScript, `AbortController` provides an abort signal. The remote operation must cooperate with that signal.

In Java, interruption and future cancellation can request termination of an operation. They do not guarantee that every blocking operation terminates immediately.

In C++, the example models a timeout parameter, but a production implementation needs a cancellable asynchronous transport or a client library that enforces request deadlines.

In Python, synchronous execution can block beyond a surrounding logical deadline. A production HTTP client should enforce connection, read, and total timeouts directly.

## 6. Retry Storms

A retry storm occurs when failed clients generate additional requests that overload an already unhealthy dependency.

### 6.1 Failure amplification

A typical sequence is:

1. A dependency becomes unavailable.
2. Multiple clients receive failures.
3. Clients immediately retry.
4. The dependency receives additional traffic.
5. Processing capacity decreases further.
6. More requests time out.
7. Additional retries increase load.

The retry mechanism becomes a source of additional instability.

### 6.2 Load amplification

Suppose 1,000 clients each issue one initial request and four retries.

\[
R = N(1+K)
\]

Where:

- \(N\): Number of clients.
- \(K\): Maximum retries per client.

Therefore:

\[
R = 1000(1+4)=5000
\]

The original 1,000 logical requests can generate 5,000 physical request attempts.

### 6.3 Storm prevention controls

| Control | Purpose |
|---|---|
| Exponential backoff | Spreads retries over time |
| Jitter | Reduces synchronized retries |
| Retry budgets | Limits aggregate retry volume |
| Circuit breakers | Stops requests to unhealthy dependencies |
| Concurrency limits | Restricts simultaneous requests |
| Rate limiting | Controls incoming request volume |
| Bulkheads | Isolates resource consumption |
| Deadlines | Prevents excessive request lifetimes |
| Load shedding | Rejects work when capacity is insufficient |

These controls address different failure mechanisms and should be combined where appropriate.

## 7. Retry Budgets

A retry budget limits the number of additional requests permitted within a defined operating period.

The implementations use token-bucket accounting.

The token balance increases according to:

\[
T_{\text{new}} =
\min(T_{\max},T_{\text{old}}+r\Delta t)
\]

Where:

- \(T_{\max}\): Maximum token capacity.
- \(r\): Refill rate.
- \(\Delta t\): Elapsed time.

Each permitted retry consumes one token.

If no token is available, the retry is rejected.

A shared retry budget is useful because independently configured clients can collectively overload a dependency even when each client has a small retry limit.

The Python and JavaScript implementations demonstrate local token buckets. The C++ implementation demonstrates synchronized local accounting. The SQL implementation records token-consumption events.

A production distributed retry budget requires atomic shared accounting or an equivalent centralized quota mechanism.

## 8. Circuit Breakers

A circuit breaker temporarily prevents requests from reaching an unhealthy dependency.

It has three primary states.

### 8.1 Closed

Requests are allowed.

Failures are counted. Once the configured threshold is reached, the circuit opens.

### 8.2 Open

Requests are rejected immediately.

The application avoids repeatedly contacting an unhealthy service.

After the recovery interval, the circuit can enter the half-open state.

### 8.3 Half-open

A limited number of test requests are allowed.

- Successful execution closes the circuit.
- Failure opens the circuit again.
- Concurrent probes are limited to prevent a new traffic surge.

State transitions:

`CLOSED → OPEN → HALF_OPEN → CLOSED`

An unsuccessful probe produces:

`HALF_OPEN → OPEN`

Circuit breakers and retries are separate mechanisms.

Retries attempt recovery within an operation. Circuit breakers control whether additional operations should be sent to a dependency.

## 9. Idempotency and Safe Retries

Retrying a request can duplicate side effects.

Consider a payment service:

1. A payment request reaches the gateway.
2. The gateway processes the payment.
3. The response is lost.
4. The client times out.
5. The client retries the same payment.

Without idempotency protection, the payment could be processed twice.

An idempotency key identifies a logical operation across repeated attempts.

A reliable implementation should:

- Generate a stable key for the logical request.
- Reuse the same key across retries.
- Associate the key with a request fingerprint.
- Reject reuse with a different request payload.
- Persist the operation result.
- Return the existing result for duplicate submissions.

The PostgreSQL implementation models idempotency keys and request fingerprints.

The retry engine examples focus on transport-level retry behavior. They do not implement a complete payment transaction or remote idempotency protocol.

## 10. Python Implementation

### Architecture

The Python implementation uses separate classes for:

- `RetryPolicy`
- `RetryExecutor`
- `RetryBudget`
- `CircuitBreaker`
- `SimulatedService`
- `AttemptRecord`
- `RetryResult`

The `RetryPolicy` validates the retry configuration and calculates delays.

`RetryExecutor` coordinates attempts, retry classification, elapsed-time limits, budget consumption, and circuit-breaker decisions.

`RetryBudget` uses monotonic time to calculate token replenishment.

`CircuitBreaker` manages closed, open, and half-open states.

`SimulatedService` provides deterministic temporary failures for testing.

### Execution workflow

`run_tests()` exercises:

1. Successful execution after temporary failures.
2. Permanent failure propagation.
3. Retry exhaustion.
4. Retry budget exhaustion.
5. Circuit opening.
6. Synchronized and randomized retry scheduling.

The script saves execution metrics to `retry_metrics.json`.

### Important limitation

The synchronous implementation measures elapsed time between operations but cannot forcibly terminate an arbitrary blocking Python function. Real network operations must use a client with actual request-timeout support.

## 11. JavaScript Implementation

The JavaScript implementation uses asynchronous programming and Node.js standard-library facilities.

Its principal components are:

- `RetryPolicy`
- `RetryExecutor`
- `RetryBudget`
- `CircuitBreaker`
- `DependencyService`

`Promise.race()` implements a timeout boundary around each operation.

`AbortController` signals cancellation when the timeout expires.

`setTimeout` and the promise-based timer API implement retry delays.

`performance.now()` provides monotonic elapsed-time measurement.

The implementation also produces a UUID for each successful execution and exports metrics as JSON.

### Event-driven considerations

The timeout wrapper cannot forcibly stop arbitrary JavaScript work.

The remote operation must observe the abort signal and terminate its underlying request.

An operation that ignores cancellation may continue consuming resources after the retry executor has moved on.

This is particularly important when using database drivers, HTTP clients, and long-running asynchronous tasks.

## 12. C++17 Implementation

The C++ implementation uses a domain-oriented approach.

Principal components:

- `RetryPolicy`
- `RetryExecutor`
- `RetryBudget`
- `CircuitBreaker`
- `SimulatedService`
- `Attempt`
- `Result`

The implementation uses:

- `std::chrono` for elapsed-time measurement.
- `std::thread` for retry delays.
- `std::random` for jitter generation.
- STL containers for retry scheduling.
- Exceptions for failure propagation.
- Templates for reusable operation execution.

The retry storm simulation aggregates retry events into time buckets.

This demonstrates how deterministic schedules concentrate requests into the same intervals, while randomized schedules distribute them.

The simulation does not model network queues, server capacity, or actual concurrent clients.

The C++ implementation passes a timeout value to the operation but does not enforce preemptive cancellation. Production systems should integrate asynchronous I/O and cancellation-aware transport operations.

## 13. Java 17 Implementation

The Java implementation models an enterprise payment gateway.

Its domain types include:

- `RetryPolicy`
- `AttemptRecord`
- `ExecutionResult`
- `RetryBudget`
- `CircuitBreaker`
- `RetryExecutor`
- `PaymentGateway`

Java records provide immutable policy and execution-result structures.

The retry executor uses an `ExecutorService` and `Future.get()` with a timeout.

A timed-out future receives a cancellation request.

The circuit breaker and token budget use synchronized methods to protect shared state.

`AtomicInteger` tracks payment gateway calls and simulated failures.

The payment example succeeds after two temporary failures.

### Enterprise considerations

An actual payment integration requires:

- Stable idempotency keys.
- Transaction reconciliation.
- Bounded executor pools.
- Connection pooling.
- Explicit error classification.
- Distributed circuit-breaker coordination where required.
- Structured logging.
- Deadline propagation.

The demonstration creates a dedicated executor for each attempt to illustrate timeout isolation. A production application should generally reuse bounded executor resources rather than creating a new executor for every request.

Cancellation remains cooperative for operations that do not respond to thread interruption.

## 14. PostgreSQL Data Model

The PostgreSQL implementation stores retry policies, executions, attempts, retry-budget events, and circuit-breaker history.

### Entity relationships

`services`
  → `service_policy_assignments`
  → `retry_policies`

`services`
  → `circuit_breakers`
  → `circuit_state_history`

`services`
  → `request_executions`
  → `retry_attempts`

`services`
  → `retry_budget_events`

### Main tables

| Table | Responsibility |
|---|---|
| services | Remote dependency registry |
| retry_policies | Retry and timeout configuration |
| service_policy_assignments | Policy-to-service mapping |
| circuit_breakers | Current circuit state |
| request_executions | Logical operation lifecycle |
| retry_attempts | Individual attempt history |
| retry_budget_events | Retry quota accounting |
| circuit_state_history | Circuit transition audit trail |

### Database mechanisms

The implementation includes:

- Primary and foreign keys.
- Unique constraints.
- Check constraints.
- Partial idempotency indexes.
- Performance-oriented indexes.
- Enumerated failure categories.
- Backoff calculation function.
- Retry eligibility function.
- Circuit transition trigger.
- Atomic retry-token accounting.
- Execution creation function.
- Execution finalization procedure.
- Transaction handling.
- Retry aggregation and storm-detection queries.

### Concurrency and consistency

The retry-budget function locks the associated service record before recording consumption.

This serializes budget updates for a particular service within the transaction.

The circuit-state trigger automatically records state changes.

The idempotency constraint prevents duplicate logical requests for the same service and key.

The SQL model records operational events but does not itself execute HTTP requests or implement a complete distributed retry scheduler.

A production token-bucket implementation must persist and calculate refill state consistently. The example token-consumption function accepts the current balance as an input and records an atomic consumption event; it is not a complete persistent refill engine.

## 15. Performance Considerations

### Retry latency

For \(K\) retries, total waiting time is:

\[
T_{\text{backoff}} =
\sum_{i=0}^{K-1}D_i
\]

The total operation duration must also include actual request-processing time.

### Retry amplification

\[
A = \frac{\text{Total physical attempts}}
{\text{Logical operations}}
\]

An increasing amplification factor can indicate dependency instability or overly aggressive retry configuration.

### Monitoring metrics

| Metric | Operational value |
|---|---|
| Retry count | Measures additional request volume |
| Retry rate | Identifies changes in failure behavior |
| Attempt latency | Measures individual request duration |
| End-to-end latency | Measures total operation duration |
| Timeout rate | Detects slow or unavailable dependencies |
| Retry exhaustion | Measures unsuccessful recovery |
| Circuit-open duration | Measures dependency unavailability |
| Retry-budget rejection | Identifies retry pressure |
| Concurrent requests | Indicates resource consumption |
| Success-after-retry rate | Measures recovery effectiveness |

Retry metrics should be segmented by dependency, operation, error category, and deployment version.

Avoid using request IDs or other high-cardinality values as metric labels.

## 16. Security and Reliability Considerations

Retry logic must not become a mechanism for repeating unsafe operations.

Important controls include:

- Do not retry authentication failures without correcting credentials.
- Do not retry permanent validation errors.
- Use idempotency keys for operations with side effects.
- Protect retry metadata against unauthorized modification.
- Avoid logging authentication tokens and sensitive request bodies.
- Validate remote rate-limit instructions.
- Apply bounded retry counts.
- Enforce total operation deadlines.
- Limit concurrent dependency requests.
- Use authenticated transport connections.
- Monitor unexpected retry-rate increases.

A timeout does not prove that a remote operation was unsuccessful. Systems handling payments, orders, or inventory changes must reconcile uncertain outcomes before issuing potentially duplicative operations.

## 17. Testing Scenarios

| Test | Expected behavior |
|---|---|
| Immediate success | One attempt |
| Temporary connection failure | Retry |
| Two failures followed by success | Third attempt succeeds |
| Permanent failure | Immediate propagation |
| Maximum attempts reached | Retry exhaustion |
| Retry budget empty | Additional retry rejected |
| Circuit open | Request rejected |
| Half-open successful probe | Circuit closes |
| Half-open failed probe | Circuit opens |
| Timeout | Attempt is cancelled where supported |
| Identical retry schedules | Concentrated retry events |
| Randomized schedules | Reduced synchronization |
| Reused idempotency key | Existing logical operation identified |
| Different payload with same key | Request rejected |

## 18. Implementation Limitations

These implementations are educational resilience models rather than production-ready distributed transport frameworks.

The examples do not provide:

- Distributed coordination across independent processes.
- A complete HTTP client integration.
- Persistent, globally synchronized retry budgets.
- A production-grade scheduler.
- Full asynchronous cancellation in every language.
- A complete distributed idempotency protocol.
- Real network failure injection.
- A production telemetry backend.

The distinction between logical operations and physical attempts must be preserved when extending the implementations.

A robust system treats retries as controlled recovery actions rather than an unconditional response to every failure.
