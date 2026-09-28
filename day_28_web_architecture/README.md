# Web Architecture: Synchronous vs Asynchronous Communication

## Scope

This study examines three closely related execution models used in web architecture:

- synchronous communication
- blocking and non-blocking execution
- asynchronous workflows

The implementations use Python, JavaScript, and C++ to demonstrate how these concepts affect request processing, concurrency, resource utilization, error handling, queues, retries, timeouts, event-driven systems, and production architecture.

The examples deliberately distinguish concepts that are often incorrectly treated as synonyms. Synchronous versus asynchronous describes how completion is coordinated between participants. Blocking versus non-blocking describes whether the current execution context is prevented from making progress while waiting. Concurrency describes overlapping progress, while parallelism describes simultaneous execution on separate computational resources.

---

## 1. Web Architecture Context

A web application normally contains multiple components:

1. a client
2. an HTTP interface
3. application logic
4. databases
5. caches
6. external APIs
7. background workers
8. message queues or event streams
9. observability infrastructure

A request may therefore cross several boundaries.

For example:

`Browser -> API Gateway -> Order Service -> Inventory Service -> Payment Service`

If every component waits synchronously for the next component, the request path can become long and resource-intensive. Asynchronous architecture can separate immediate request acceptance from work that can complete later.

The appropriate architecture depends on requirements such as:

- latency
- consistency
- failure behavior
- workload size
- dependency relationships
- throughput
- resource limits
- user experience
- transactional requirements
- operational complexity

Asynchronous processing is not automatically superior. It changes the execution model and introduces additional design concerns.

---

# 2. Fundamental Terminology

## 2.1 Synchronous communication

In synchronous communication, the caller requests an operation and waits for its response before proceeding with that particular flow.

Conceptually:

`Caller -> Request -> Service -> Response -> Caller continues`

A simple Python example is `synchronous_call(...)`. The function does not return until the simulated operation has completed.

Synchronous communication is straightforward because control flow closely follows business flow.

Typical examples include:

- a function call
- a database query where the caller waits for the result
- an HTTP request whose response is required before continuing
- a service-to-service call where downstream data is immediately required

Synchronous communication does not necessarily mean that the entire application is single-threaded or that the underlying implementation cannot use concurrency. It describes the interaction contract from the caller's perspective.

---

## 2.2 Blocking

An operation is blocking when the current execution context cannot make useful progress until the operation finishes or the blocking condition changes.

A blocking call may involve:

- waiting for a network response
- waiting for a file operation
- waiting for a lock
- sleeping
- waiting for a condition
- waiting for a worker result

The Python examples use `time.sleep(...)` to illustrate blocking.

The C++ implementation uses `std::this_thread::sleep_for(...)` to simulate blocking I/O.

Blocking is particularly important when the blocked resource is expensive or scarce.

For example, blocking 10,000 operating-system threads while waiting for remote services is substantially different from maintaining a smaller number of event-loop tasks that suspend during I/O.

---

## 2.3 Non-blocking execution

Non-blocking execution allows the current execution context to continue instead of waiting synchronously for an operation to finish.

A common pattern is:

`Start operation -> receive handle/future -> continue -> collect result later`

Python demonstrates this with `concurrent.futures.Future`.

C++ demonstrates it using `std::future`.

JavaScript demonstrates the concept using Promises.

Non-blocking does not mean that the underlying operation consumes no resources. The network connection, worker, operating-system resource, or runtime task still requires resources.

---

## 2.4 Asynchronous communication

Asynchronous communication separates initiation from completion.

A simplified model is:

`Client -> submit work -> acknowledgement`

followed later by:

`Client -> status/result retrieval`

or:

`Producer -> event -> consumer`

Long-running jobs commonly use this architecture.

For example:

1. client submits a report-generation request
2. server validates it
3. server creates a job identifier
4. server immediately acknowledges the request
5. worker performs the report generation
6. client polls status or receives an event
7. completed output becomes available

The Python `JobService`, JavaScript `JobService`, and C++ `JobManager` demonstrate this pattern.

---

# 3. Synchronous Does Not Mean Single-Threaded

A synchronous API can be implemented inside a multi-threaded server.

For example, a web server can have 100 worker threads and each request can still synchronously wait for its database call.

Therefore these are separate dimensions:

| Concept | Main question |
|---|---|
| Synchronous | Does this flow wait for the result before proceeding? |
| Asynchronous | Can completion occur independently of immediate invocation? |
| Blocking | Is the current execution context prevented from progressing? |
| Non-blocking | Can the current execution context continue while work is pending? |
| Concurrent | Can multiple operations overlap? |
| Parallel | Can multiple operations execute simultaneously? |

These terms should not be substituted for one another.

---

# 4. Blocking I/O

Consider an operation that requires 100 ms of network waiting.

A blocking implementation effectively does:

`send request`

`wait 100 ms`

`receive response`

`continue`

The waiting execution resource remains occupied.

This can be acceptable when:

- traffic is low
- the thread pool is sufficiently sized
- simplicity is more important than maximum concurrency
- the operation is short
- the downstream dependency is reliable

It becomes problematic when:

- request volume is high
- downstream latency is large
- many connections remain open
- worker pools become exhausted
- queueing latency grows

---

# 5. Non-Blocking I/O

A non-blocking architecture can instead perform:

`start network operation`

`return control`

`do other work`

`resume when network operation is ready`

Event loops and futures provide mechanisms for coordinating this behavior.

The JavaScript implementation is especially useful for understanding this model because JavaScript applications commonly use an event loop.

---

# 6. JavaScript Event Loop

JavaScript execution in a typical Node.js application includes an event loop.

A simplified sequence is:

1. execute synchronous JavaScript
2. encounter asynchronous operation
3. register its completion behavior
4. continue executing available synchronous work
5. process completed asynchronous operations according to runtime scheduling rules

A timer with a delay of zero does not execute in the middle of currently running JavaScript.

The JavaScript demonstration intentionally performs CPU work after scheduling a zero-delay timer. The timer callback cannot interrupt that synchronous CPU loop.

This distinction is critical:

**Asynchronous APIs do not make CPU-heavy JavaScript automatically non-blocking.**

A CPU-intensive synchronous loop can still prevent the event loop from servicing other work.

---

# 7. Callback-Based Asynchrony

Callbacks are one of the earliest common JavaScript asynchronous patterns.

The basic structure is conceptually:

`operation(input, callback)`

and later:

`callback(error, result)`

The JavaScript `callbackService(...)` demonstrates this model.

A callback commonly follows an error-first convention:

`callback(error, result)`

The advantages include direct control over completion behavior.

The disadvantages become apparent when many dependent operations are nested:

`request -> callback -> callback -> callback -> callback`

This can make control flow difficult to maintain.

---

# 8. Promises

A Promise represents the eventual result of an asynchronous operation.

A Promise can be:

- pending
- fulfilled
- rejected

The JavaScript implementation uses `promiseService(...)`.

Typical Promise operations include:

- `then(...)`
- `catch(...)`
- `finally(...)`
- `Promise.all(...)`
- `Promise.allSettled(...)`
- `Promise.race(...)`

Promises make asynchronous composition clearer than deeply nested callbacks.

---

# 9. `Promise.all`

`Promise.all(...)` is useful when multiple operations are independent.

For example:

`inventory check`

and

`fraud check`

may be performed concurrently if neither depends on the other.

The JavaScript implementation demonstrates:

`Promise.all([operationA, operationB, operationC])`

The result is available when all required operations have fulfilled.

A rejection normally causes `Promise.all(...)` to reject.

---

# 10. `Promise.allSettled`

`Promise.allSettled(...)` is useful when every result matters, including failures.

For example, a dashboard may request:

- service health
- database health
- cache health
- queue health

If one health check fails, the application may still need the results from the others.

The JavaScript implementation demonstrates this behavior.

---

# 11. Python `asyncio`

Python provides asynchronous programming through `asyncio`.

The core concepts include:

- coroutine functions
- `async`
- `await`
- tasks
- event loops
- Futures
- cancellation

The Python function `async_service(...)` is a coroutine.

`await asyncio.sleep(...)` suspends the coroutine rather than blocking the event loop.

This allows another ready coroutine to run while the current operation is waiting.

---

# 12. Coroutine

A coroutine is a computation that can suspend and later resume.

A Python coroutine is commonly defined with:

`async def function_name():`

A suspension point is commonly expressed using:

`await operation`

The important distinction is that `await` does not automatically make arbitrary code asynchronous.

For example, CPU-heavy code executed directly inside an asynchronous coroutine can still block the event loop.

Good asynchronous code therefore keeps blocking operations away from the event loop or moves them to appropriate workers.

---

# 13. Tasks

A task schedules a coroutine for execution.

The Python example:

`asyncio.create_task(...)`

starts a coroutine independently of the immediate sequential flow.

The caller can then perform other asynchronous work before awaiting the task.

A task should normally be retained or awaited when its result or failure matters.

Unobserved task failures can produce difficult operational problems.

---

# 14. Concurrency Versus Parallelism

Concurrency means multiple activities can make progress during overlapping periods.

Parallelism means multiple computations actually execute at the same time on different execution resources.

For I/O-bound workloads, concurrency is often particularly valuable because a program spends significant time waiting.

For CPU-bound workloads, parallel execution may require multiple cores and suitable runtime mechanisms.

The Python implementation demonstrates both:

- `ThreadPoolExecutor` for overlapping I/O-style work
- `ProcessPoolExecutor` for process-based CPU parallelism

The exact performance characteristics depend on the workload and runtime.

---

# 15. C++ Futures

The C++ case study uses `std::async` and `std::future`.

The pattern is:

1. submit a function
2. receive a future
3. perform other work
4. call `get()` when the result is required

`std::future::wait_for(...)` can perform a timed wait.

A timeout does not necessarily terminate the underlying computation.

This distinction is important in production systems because:

`stop waiting`

and

`stop the operation`

are different requirements.

---

# 16. Timeouts

Every remote dependency should be considered capable of taking longer than expected.

Without timeouts, a request can wait indefinitely.

A timeout provides a maximum waiting period.

The implementations demonstrate timeouts using:

- Python `asyncio.wait_for(...)`
- JavaScript `Promise.race(...)`
- C++ `future.wait_for(...)`

Timeouts should exist at appropriate layers.

Common examples include:

- connection timeout
- DNS timeout
- TLS handshake timeout
- request timeout
- database query timeout
- queue wait timeout
- overall workflow deadline

A timeout should not be selected arbitrarily. It should reflect the service's latency objectives and dependency behavior.

---

# 17. Timeout Versus Cancellation

These concepts are related but different.

A timeout means:

`The caller is no longer willing to wait.`

Cancellation means:

`The operation should stop if the implementation supports cancellation.`

The JavaScript example uses `AbortController` to demonstrate explicit cancellation.

A Promise timeout implemented with `Promise.race(...)` does not automatically cancel the losing Promise.

This is an important production concern.

---

# 18. Retries

Retries can recover from transient failures such as:

- temporary network problems
- overloaded dependencies
- brief connection failures
- temporary service unavailability

Not every failure should be retried.

Examples that often require different handling include:

- invalid authentication
- invalid request data
- authorization failure
- malformed requests
- permanent business-rule violations

Retrying a permanent error wastes resources.

---

# 19. Exponential Backoff

A basic exponential backoff policy might use:

`delay = baseDelay × 2^(attempt - 1)`

For example:

| Attempt | Approximate delay |
|---:|---:|
| 1 | 10 ms |
| 2 | 20 ms |
| 3 | 40 ms |
| 4 | 80 ms |

Real systems commonly add jitter.

Jitter prevents many clients that failed simultaneously from retrying at exactly the same time.

The Python, JavaScript, and C++ implementations demonstrate controlled retry behavior.

---

# 20. Retry Storms

Suppose a downstream service fails while 10,000 clients are waiting.

If all clients retry immediately, the recovery traffic can be larger than the original traffic.

This can produce a feedback loop:

`failure -> retries -> more load -> more failures -> more retries`

Backoff, jitter, rate limits, circuit breakers, and bounded concurrency can reduce this risk.

---

# 21. Long-Running Jobs

Some work should not occupy an HTTP request until completion.

Examples include:

- report generation
- video processing
- large data imports
- document conversion
- batch calculations
- model training
- large exports

A common architecture is:

`POST /jobs`

The server returns:

`202 Accepted`

with a job identifier.

The client can later request:

`GET /jobs/{id}`

Possible states include:

- queued
- running
- completed
- failed
- cancelled

The Python, JavaScript, and C++ implementations model this pattern.

---

# 22. Polling

Polling means repeatedly checking the status of asynchronous work.

A client might use:

`GET /jobs/123`

then wait and repeat.

Polling is simple, but excessive polling creates unnecessary traffic.

Approaches include:

- fixed polling intervals
- exponential polling intervals
- server-sent events
- WebSockets
- push notifications
- message subscriptions

The appropriate choice depends on latency requirements and system architecture.

---

# 23. Event-Driven Communication

In event-driven architecture, a producer publishes an event without requiring every consumer to complete before the producer continues.

Example:

`OrderCreated`

can be consumed by:

- audit service
- notification service
- analytics service
- fulfillment service

This creates loose coupling between producers and consumers.

The Python implementation provides an in-process `EventBus`.

The JavaScript implementation uses Node.js `EventEmitter`.

The C++ implementation provides an `EventDispatcher`.

These are educational models. Production systems normally require durable infrastructure when events must survive process failures.

---

# 24. Commands Versus Events

A command expresses an instruction:

`ChargePayment`

An event describes something that happened:

`PaymentAuthorized`

This distinction affects system coupling.

A command normally has a specific intended receiver.

An event can have multiple subscribers.

Event-driven systems therefore often provide greater decoupling, but they introduce challenges involving:

- eventual consistency
- ordering
- duplicate delivery
- replay
- schema evolution
- observability
- failure recovery

---

# 25. Message Queues

A queue separates producers from consumers.

Conceptually:

`Producer -> Queue -> Consumer`

The producer does not have to execute the work itself.

Queues can provide:

- buffering
- workload smoothing
- retry handling
- worker scaling
- producer-consumer decoupling

The Python example uses `asyncio.Queue`.

The JavaScript implementation contains a bounded `AsyncQueue`.

The C++ case study implements a thread-safe `BoundedQueue`.

---

# 26. Backpressure

Backpressure occurs when consumers cannot process incoming work as quickly as producers create it.

Without controls, pending work can consume:

- memory
- connections
- threads
- file descriptors
- database connections
- CPU
- queue storage

A bounded queue is one mechanism for controlling this.

The C++ queue blocks producers when capacity is reached.

The JavaScript queue suspends producers when its maximum size has been reached.

The Python `asyncio.Queue(maxsize=...)` provides equivalent bounded behavior.

Backpressure is a resource-management mechanism, not merely a performance optimization.

---

# 27. Worker Pools

A worker pool limits the number of concurrent workers.

Without a limit, a system may create excessive threads or tasks.

A worker pool provides controlled concurrency:

`queue -> worker 1`

`queue -> worker 2`

`queue -> worker 3`

The C++ case study includes a worker pool that consumes jobs from a bounded queue.

Important production parameters include:

- worker count
- queue capacity
- job timeout
- retry policy
- shutdown behavior
- maximum job duration
- memory usage
- CPU utilization

---

# 28. Dependency-Aware Workflows

Not every operation can run concurrently.

Suppose an order workflow is:

`validate -> authorize -> reserve -> charge`

Some steps have strict dependencies.

A different branch might be:

`authorize -> reserve`

and:

`authorize -> notify`

After `authorize` completes, `reserve` and `notify` can run concurrently if they are independent.

The Python and JavaScript workflow engines explicitly model dependencies.

The resulting execution resembles a directed acyclic graph.

A simplified graph is:

`validate`

`  |`

`authorize`

` /       \`

`reserve  notify`

`  |`

`charge`

This is a practical way to reason about concurrency safely.

---

# 29. Race Conditions

Concurrent execution can create race conditions when multiple operations access shared mutable state without correct synchronization.

For example:

1. request A reads balance = 100
2. request B reads balance = 100
3. request A subtracts 80
4. request B subtracts 80

If updates are not coordinated, the final state may be incorrect.

The C++ implementation uses mutexes for shared stores and queue state.

Python's and JavaScript's event-loop models reduce some categories of thread races within a single event loop, but asynchronous interleaving can still create logical races.

Concurrency should therefore be analyzed at the level of shared state and business invariants, not only at the thread level.

---

# 30. Idempotency

An operation is idempotent when repeating the same logical request does not produce unintended repeated effects.

This is especially important for network retries.

Consider a payment request.

If the client sends:

`POST /payments`

and receives no response because of a network failure, it may not know whether the payment succeeded.

It may retry.

Without idempotency protection, the customer could potentially be charged twice.

An idempotency key gives the server a way to associate repeated requests with one logical operation.

The Python `IdempotentPaymentProcessor`, JavaScript `PaymentProcessor`, and C++ `IdempotencyStore` demonstrate the principle.

A production implementation must handle concurrent duplicate requests atomically. A simple lookup followed by a later store can still contain a race if two identical requests arrive simultaneously.

---

# 31. Circuit Breakers

A circuit breaker protects an application from repeatedly calling a failing dependency.

Typical states are:

- `CLOSED`
- `OPEN`
- `HALF_OPEN`

### CLOSED

Requests are allowed.

Failures are counted.

### OPEN

Requests are rejected quickly without contacting the failing dependency.

This prevents repeated network attempts.

### HALF_OPEN

After a recovery period, a limited probe request tests whether the dependency has recovered.

A successful probe can return the breaker to `CLOSED`.

The Python, JavaScript, and C++ implementations demonstrate simplified circuit breakers.

Production implementations often need:

- atomic state transitions
- metrics
- configurable thresholds
- rolling failure windows
- concurrency limits
- carefully defined recovery behavior

---

# 32. Error Handling

Asynchronous errors require explicit observation.

Python uses exceptions from awaited coroutines.

JavaScript uses rejected Promises and `try/catch`.

C++ uses exceptions combined with future result retrieval.

Important failure categories include:

- validation failures
- authentication failures
- authorization failures
- network failures
- timeout failures
- dependency failures
- resource exhaustion
- business-rule failures
- cancellation

Error handling should preserve enough information for diagnosis without exposing sensitive information.

---

# 33. Eventual Consistency

Asynchronous workflows often mean that different services do not update at exactly the same time.

For example:

`Order Service: order accepted`

may occur before:

`Analytics Service: order recorded`

or:

`Notification Service: notification sent`

The system can therefore be temporarily inconsistent.

This is called eventual consistency when the architecture allows independent components to converge to the expected state later.

Applications must define which states are acceptable and how users should see intermediate states.

---

# 34. Exactly-Once Versus At-Least-Once Processing

Distributed systems frequently provide at-least-once delivery semantics.

That means a message can potentially be delivered more than once.

Consumers therefore commonly need:

- idempotency
- deduplication
- unique event identifiers
- transactional processing
- retry-safe operations

"Exactly once" is a stronger guarantee and is difficult to implement across independent systems.

A design should not assume exactly-once behavior without understanding the actual guarantees of every component.

---

# 35. Ordering

Asynchronous systems can change the order in which operations complete.

For example:

`Event A`

followed by

`Event B`

does not automatically guarantee that all consumers will process A before B.

Ordering may require:

- partitioning
- sequence numbers
- single-consumer processing
- explicit dependency tracking
- database constraints

Ordering guarantees usually reduce some forms of concurrency.

---

# 36. Concurrency Limits

Unlimited concurrency is rarely appropriate.

Suppose a service receives 100,000 requests and each request creates five downstream calls.

The resulting number of outstanding operations can become extremely large.

Concurrency limits protect:

- memory
- CPU
- network sockets
- database connection pools
- downstream services

Useful mechanisms include:

- semaphores
- bounded queues
- worker pools
- connection pools
- rate limiters

---

# 37. Connection Pools

Opening a new network connection for every operation can be expensive.

Connection pools allow existing connections to be reused.

Important limits include:

- maximum connections
- minimum idle connections
- idle timeout
- connection lifetime
- acquisition timeout

An asynchronous application can still exhaust a connection pool if concurrency is not controlled.

---

# 38. Security Considerations

Asynchronous architecture introduces several security concerns.

## Authentication

The system must establish who is making the request.

## Authorization

The system must verify what the caller is allowed to do.

## Transport security

Network communication should normally use TLS.

## Input validation

All external input should be validated at service boundaries.

## Rate limiting

Expensive asynchronous operations should be protected from uncontrolled request volume.

## Resource exhaustion

Queues, workers, connections, and memory should have bounded capacity.

## Secret protection

Credentials, API keys, session tokens, and other secrets should not be placed in ordinary logs or URLs.

## Replay protection

Retryable operations and event-driven systems may need unique identifiers, expiration windows, or idempotency controls to prevent unintended replay effects.

---

# 39. Observability

Asynchronous systems are harder to debug because execution is no longer a simple linear sequence.

Useful measurements include:

- request latency
- downstream latency
- queue depth
- worker utilization
- task duration
- retry count
- timeout count
- error count
- circuit-breaker state
- event-processing delay
- job completion time

Distributed tracing is particularly useful when a request crosses multiple services.

A trace can connect:

`HTTP request`

to:

`inventory call`

to:

`payment call`

to:

`database query`

to:

`event publication`

The Python, JavaScript, and C++ examples include lightweight timing instrumentation.

---

# 40. Python Implementation

The Python script begins with synchronous functions and progresses toward asynchronous architecture.

## Fundamental demonstrations

`demonstrate_basic_synchronous_communication()` shows sequential execution.

`demonstrate_blocking()` shows that a blocking function prevents its caller from progressing.

`demonstrate_non_blocking_submission()` uses `ThreadPoolExecutor` and `Future`.

## Asyncio

`async_service()` demonstrates coroutine suspension.

`demonstrate_asyncio()` uses `asyncio.gather(...)` to overlap independent waiting operations.

`demonstrate_create_task()` demonstrates explicitly scheduled tasks.

## Reliability

The Python implementation includes:

- timeouts
- cancellation
- retries
- exponential backoff
- jitter
- idempotency
- circuit breaking

## Workflow

`WorkflowEngine` builds a dependency-aware asynchronous workflow.

It finds ready steps whose dependencies have completed, runs independent steps concurrently, and then advances to the next dependency layer.

This models a common orchestration pattern.

## Queue

`asyncio.Queue(maxsize=2)` demonstrates bounded asynchronous work.

The maximum queue size provides a simple form of backpressure.

---

# 41. JavaScript Implementation

The JavaScript implementation focuses strongly on event-loop behavior and Promise-based application design.

## Event loop behavior

`blockingCpuWork(...)` deliberately consumes CPU synchronously.

The demonstration schedules a zero-delay timer before executing the CPU loop.

The timer cannot interrupt the currently executing synchronous JavaScript.

This illustrates why asynchronous APIs do not eliminate event-loop blocking caused by CPU-heavy code.

## Callback

`callbackService(...)` demonstrates traditional callback-based asynchronous programming.

## Promises

`promiseService(...)` demonstrates Promise fulfillment and rejection.

`Promise.all(...)` demonstrates concurrent independent operations.

`Promise.allSettled(...)` demonstrates collecting both successful and failed results.

## Cancellation

`AbortController` demonstrates explicit cancellation signaling.

## Long-running jobs

`JobService` models immediate job acceptance followed by background progress.

## Queue

`AsyncQueue` models bounded producer-consumer processing.

## Workflow

`WorkflowEngine` executes ready independent steps concurrently while preserving dependency requirements.

---

# 42. C++ Industry-Style Case Study

The C++ implementation models an order-processing gateway.

The business scenario is:

1. validate an incoming order
2. reserve inventory
3. perform fraud screening
4. authorize payment
5. return an order result
6. protect retryable operations
7. support asynchronous jobs
8. process domain events

The central domain object is `Order`.

It contains:

- `orderId`
- `customerId`
- `amount`

Validation occurs before downstream work.

---

# 43. C++ Architectural Components

## `BoundedQueue`

Provides thread-safe producer-consumer coordination.

Its capacity is fixed.

When full, producers wait until consumers create capacity.

This is an explicit backpressure mechanism.

## `WorkerPool`

Creates a controlled number of worker threads.

Jobs are submitted to the bounded queue.

This avoids creating an unlimited number of threads.

## `IdempotencyStore`

Stores previously completed logical requests.

A repeated idempotency key can return the previously stored result.

## `CircuitBreaker`

Implements:

- CLOSED
- OPEN
- HALF_OPEN

This protects the simulated payment service after repeated failures.

## `RemoteService`

Simulates a downstream network service.

It includes configurable failures and latency.

## `RetryPolicy`

Retries failures with exponential delays.

## `OrderProcessor`

Coordinates the complete business workflow.

Inventory and fraud screening are independent after validation, so they execute concurrently.

Payment depends on those results and therefore starts afterward.

---

# 44. Why the C++ Workflow Is Dependency-Aware

The order workflow cannot simply launch every operation simultaneously.

The logical structure is:

`validate`

then:

`inventory + fraud`

then:

`payment`

Inventory and fraud are independent of one another.

Payment depends on both.

Therefore the implementation uses:

`std::async(...)`

for the independent first-stage operations and calls `get()` before proceeding to payment.

This demonstrates an important rule:

**Concurrency should follow dependency relationships.**

Launching dependent work prematurely can produce incorrect business behavior.

---

# 45. Long-Running C++ Jobs

`JobManager` accepts work and submits it to `WorkerPool`.

The caller receives a job identifier immediately.

The worker updates progress:

`0% -> 20% -> 40% -> 60% -> 80% -> 100%`

The caller can inspect the job state separately.

This resembles an asynchronous HTTP job API.

---

# 46. Event-Driven C++ Processing

`EventDispatcher` supports subscription and publication.

An `order.created` event can trigger multiple independent consumers.

The demonstration includes:

- audit processing
- notification processing

The example intentionally notes that detached threads require careful lifecycle management.

A production system should use managed worker lifetimes and graceful shutdown instead of relying on detached threads for critical work.

---

# 47. Important Edge Cases

## Empty input

Identifiers should be validated before downstream operations.

## Invalid amount

A transaction amount of zero or less should be rejected.

## Excessive amount

Business limits should prevent unexpectedly large operations.

## Unknown job ID

A job lookup should fail explicitly rather than returning ambiguous state.

## Timeout

A caller may stop waiting even though the underlying operation continues.

## Cancellation

Cancellation requires explicit support from the operation.

## Dependency cycle

A dependency-aware workflow must detect when no remaining step is executable.

## Duplicate request

An idempotency mechanism should prevent unintended duplicate state changes.

## Queue saturation

A bounded queue must define what happens when capacity is exhausted.

## Downstream failure

Retry, timeout, fallback, or fast failure should be selected according to the type of failure.

---

# 48. Common Mistakes

## Mistake 1: Treating asynchronous as automatically faster

Asynchrony can improve resource utilization and throughput for suitable workloads, but it introduces scheduling and coordination overhead.

## Mistake 2: Blocking an event loop

Calling blocking operations from an event-loop thread can prevent unrelated tasks from progressing.

## Mistake 3: Running all operations concurrently

Dependencies still need to be respected.

## Mistake 4: Retrying every exception

Permanent failures should not normally be retried.

## Mistake 5: Retrying without backoff

Immediate retries can amplify an outage.

## Mistake 6: Retrying state-changing operations without idempotency

A timeout does not prove that the server failed to perform the operation.

## Mistake 7: Using unbounded queues

Unbounded queues can turn downstream slowness into memory exhaustion.

## Mistake 8: Ignoring cancellation

An application that stops waiting but leaves expensive work running can still waste resources.

## Mistake 9: Ignoring observability

Asynchronous execution can make failures difficult to reconstruct without timestamps, correlation identifiers, and traces.

## Mistake 10: Confusing parallelism and concurrency

Concurrency can exist without multiple CPU cores executing application code simultaneously.

---

# 49. Performance Considerations

Performance should be evaluated using measurements rather than assumptions.

Important metrics include:

- average latency
- median latency
- p95 latency
- p99 latency
- throughput
- CPU utilization
- memory usage
- queue depth
- connection utilization
- worker utilization
- downstream latency
- retry rate

For I/O-heavy workloads, concurrency can reduce the amount of time spent waiting sequentially.

For CPU-heavy workloads, increasing asynchronous tasks on a single event loop does not automatically create parallel CPU execution.

Excessive concurrency can cause:

- context-switch overhead
- memory growth
- connection exhaustion
- downstream overload
- increased queueing
- garbage-collection pressure
- synchronization overhead

The goal is controlled concurrency rather than maximum concurrency.

---

# 50. Synchronous and Asynchronous Trade-Offs

| Characteristic | Synchronous | Asynchronous |
|---|---|---|
| Control flow | Usually straightforward | More complex |
| Immediate result | Natural | May require future/task/job |
| Long-running work | Can occupy request resources | Can be moved to background processing |
| Failure propagation | Usually direct | Requires explicit coordination |
| Debugging | Often simpler | Requires stronger observability |
| Dependency handling | Naturally sequential | Must model dependencies carefully |
| Resource efficiency for I/O | Can be lower | Can be higher |
| Queueing | Usually less central | Often central |
| Eventual consistency | Less common in simple flows | Common in distributed workflows |
| Retry design | Important | Especially important |
| Cancellation | Usually direct | Requires explicit mechanisms |

These are architectural trade-offs rather than universal rules.

---

# 51. When Synchronous Communication Fits

Synchronous communication can be appropriate when:

- the caller immediately needs the result
- the operation is short
- the dependency is reliable
- the workflow has strict immediate consistency requirements
- simple control flow is valuable
- the system has sufficient request capacity

Examples include:

- retrieving a small database record
- validating credentials
- calculating a small deterministic result
- reading a cache value

---

# 52. When Asynchronous Workflows Fit

Asynchronous workflows are particularly useful when:

- work is long-running
- immediate completion is unnecessary
- workloads arrive in bursts
- worker scaling is useful
- independent services should be decoupled
- event-driven processing is appropriate
- background processing can reduce request duration

Examples include:

- report generation
- media processing
- bulk imports
- notifications
- analytics pipelines
- batch processing

---

# 53. Production Design Checklist

A production asynchronous workflow should explicitly define:

- request timeout
- connection timeout
- cancellation behavior
- retryable errors
- maximum retry count
- retry backoff
- jitter
- idempotency strategy
- queue capacity
- concurrency limit
- worker count
- dead-letter behavior
- event ordering requirements
- duplicate-event handling
- authentication
- authorization
- input validation
- rate limiting
- logging
- metrics
- distributed tracing
- graceful shutdown
- data consistency requirements
- recovery behavior

A design that does not define these behaviors can become unpredictable under failure or load.

---

# 54. Practical Architectural Model

A robust order-processing architecture can be represented conceptually as:

`Client`

`  |`

`API Gateway`

`  |`

`Order Service`

`  |`

`Validation`

`  |`

`+----------------------+`

`|                      |`

`Inventory            Fraud`

`|                      |`

`+----------+-----------+`

`           |`

`        Payment`

`           |`

`       Order State`

`           |`

`      Domain Event`

`           |`

`+----------+----------+`

`|                     |`

`Audit              Notification`

For long-running work, another branch can be:

`Client -> Job API -> Queue -> Worker -> Result Store`

The client can then poll or subscribe for completion.

---

# 55. Implementation Mapping

| Concept | Python | JavaScript | C++ |
|---|---|---|---|
| Synchronous call | normal function | normal function | normal function |
| Blocking | `time.sleep` | synchronous CPU loop | `sleep_for` |
| Non-blocking handle | `Future` | `Promise` | `std::future` |
| Async workflow | `asyncio` | Promise/`async` | `std::async` |
| Timeout | `asyncio.wait_for` | `Promise.race` | `wait_for` |
| Cancellation | task cancellation | `AbortController` | application-specific coordination |
| Retry | async retry function | retry function | `RetryPolicy` |
| Queue | `asyncio.Queue` | `AsyncQueue` | `BoundedQueue` |
| Worker execution | thread/process pools | event-loop tasks | worker pool |
| Event system | `EventBus` | `EventEmitter` | `EventDispatcher` |
| Idempotency | dictionary store | `Map` | synchronized store |
| Circuit breaker | `CircuitBreaker` | `CircuitBreaker` | `CircuitBreaker` |
| Workflow DAG | `WorkflowEngine` | `WorkflowEngine` | dependency-driven processor |
| Observability | `TraceRecord` | performance measurements | duration measurements |

---

# 56. Key Technical Distinctions

The following distinctions should remain explicit when designing or reviewing a web architecture:

1. **Synchronous is not identical to blocking.**
2. **Asynchronous is not identical to parallel.**
3. **Non-blocking is not identical to resource-free.**
4. **Concurrency is not identical to parallelism.**
5. **A timeout is not necessarily cancellation.**
6. **A retry is not automatically safe.**
7. **A queue is not automatically durable.**
8. **An event is not necessarily a command.**
9. **A successful HTTP acknowledgement is not necessarily completion of background work.**
10. **Higher concurrency is not automatically higher throughput.**
11. **An asynchronous workflow can still contain synchronous or blocking stages.**
12. **A synchronous API can internally use concurrent implementation techniques.**

Understanding these distinctions is essential when designing reliable distributed systems.

---

# 57. Real-World Relevance

Modern web systems frequently combine several models rather than selecting only one.

A single application can use:

- synchronous HTTP for request validation
- asynchronous database drivers for I/O
- concurrent calls to independent services
- queues for background processing
- events for cross-service notifications
- retries for transient failures
- circuit breakers for unhealthy dependencies
- idempotency for retryable writes
- bounded worker pools for controlled concurrency

The resulting architecture is usually a composition of execution models.

The important design question is not simply whether a system should be synchronous or asynchronous. The relevant questions are:

- Which operations are independent?
- Which operations have dependencies?
- Which results are needed immediately?
- Which operations can be delayed?
- Which resources can become exhausted?
- Which failures are retryable?
- What happens if a response is lost?
- Can the operation be safely repeated?
- What consistency level is required?
- How will operators observe and recover the workflow?

Those questions determine the appropriate communication and execution model for each part of a web system.
