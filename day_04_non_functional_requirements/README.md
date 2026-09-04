# Non-Functional Requirements: Scalability, Availability, Reliability, Latency, and Security

## 1. Introduction

Non-functional requirements describe the qualities, constraints, and operational characteristics that determine how a system behaves rather than only what business functions it provides.

A functional requirement might state:

> The system shall allow a customer to place an order.

A non-functional requirement makes the quality of that capability measurable:

> At least 99.95% of valid order requests shall complete successfully each month, with p95 latency below 300 milliseconds under the defined production workload.

The distinction is important because a system can implement every required business feature and still be unsuitable for production.

A system may:

- work correctly but become unusably slow under load
- process requests correctly but become unavailable when one server fails
- remain reachable but frequently return incorrect results
- perform well for a small number of users but fail to scale
- provide useful functionality while exposing confidential information
- survive individual failures but collapse during a dependency outage
- meet average latency targets while having unacceptable tail latency

This topic therefore combines architecture, software engineering, operations, security, performance engineering, reliability engineering, capacity planning, and risk management.

The Python script accompanying this README turns these concepts into executable examples and simplified simulations.

---

## 2. The Five Core Non-Functional Requirements

The script focuses on five closely related but distinct dimensions.

### 2.1 Scalability

Scalability is the ability of a system to handle increasing workload by increasing available resources or improving resource efficiency.

Typical workload dimensions include:

- requests per second
- concurrent users
- transactions per second
- stored data volume
- messages per second
- number of tenants
- computational workload

A scalable system should have a predictable relationship between increasing demand and required resources.

### 2.2 Availability

Availability describes whether a service is accessible and operational when users need it.

A simplified availability equation is:

Availability = (Total Time - Downtime) / Total Time

For example, if a service is unavailable for 1 hour during a 30-day month, the availability is approximately:

99.86%

The exact definition of downtime must be established before an availability target becomes meaningful.

### 2.3 Reliability

Reliability describes the ability of a system to perform correctly and consistently over time under specified conditions.

Reliability is not synonymous with availability.

A system may be available but unreliable if it responds successfully while producing incorrect results.

For example, an account service that returns incorrect account balances is unreliable even if every HTTP request receives a successful response.

### 2.4 Latency

Latency is the elapsed time required for an operation.

For an API, latency might be measured from:

- request arrival at the edge
- load balancer receipt
- application receipt
- database query start
- complete response delivery

The measurement point must be explicitly defined.

Latency is usually measured as a distribution rather than a single number.

Important percentiles include:

- p50
- p90
- p95
- p99
- p99.9

### 2.5 Security

Security protects systems, data, users, and operations from unauthorized access, misuse, alteration, disclosure, and disruption.

Important security objectives include:

- confidentiality
- integrity
- availability
- authentication
- authorization
- accountability

Security is not an isolated feature. It affects architecture, latency, availability, operations, data handling, and deployment.

---

# 3. Functional vs Non-Functional Requirements

Functional requirements describe behavior.

Examples:

- create an account
- place an order
- search products
- generate an invoice
- upload a document

Non-functional requirements describe characteristics or constraints.

Examples:

- p95 API latency must remain below 300 ms
- service availability must be at least 99.95%
- the system must support 10,000 requests per second
- confidential data must be encrypted in transit
- unauthorized users must not access administrative resources

A strong system specification normally contains both.

A business feature without quality constraints is incomplete for production architecture.

---

# 4. Characteristics of a Good NFR

A useful NFR should be:

- specific
- measurable
- testable
- scoped
- realistic
- tied to workload
- associated with a measurement period where appropriate
- connected to business impact

Weak:

> The API should be fast.

Strong:

> For the checkout API, p95 successful-request latency shall remain at or below 300 ms at 2,000 requests per second.

Weak:

> The service should be highly available.

Strong:

> The public API shall achieve at least 99.95% monthly availability, excluding explicitly defined maintenance windows.

The script contains a `Requirement` model and a validation function demonstrating how NFRs can be represented as structured data.

---

# 5. Scalability

Scalability concerns how system capacity changes as workload changes.

There are two fundamental approaches.

## 5.1 Vertical Scaling

Vertical scaling increases the resources of an existing machine.

Examples:

- more CPU
- more memory
- faster storage
- greater network capacity

Advantages:

- relatively simple
- fewer distributed-system concerns
- convenient for stateful workloads
- often easier to operate

Limitations:

- hardware or instance-size limits
- increasingly expensive large machines
- potential single-machine failure domain
- maintenance may affect a large portion of capacity

---

# 6. Horizontal Scaling

Horizontal scaling adds more instances.

For example:

- 2 application servers
- 4 application servers
- 8 application servers
- 16 application servers

If each instance can sustainably process 500 requests per second, then a simplified cluster model is:

Total Capacity = Number of Instances × Capacity Per Instance

The Python script implements this through `ServiceCluster`.

Horizontal scaling generally requires architectural changes such as:

- stateless application servers
- load balancing
- shared or distributed state
- distributed caching
- database scaling
- idempotency
- failure handling
- observability

---

# 7. Elastic Scaling

Elasticity refers to dynamically adding or removing resources according to workload.

For example:

- 3 instances during normal traffic
- 8 instances during peak traffic
- 3 instances after traffic decreases

Elasticity reduces the need to permanently provision for maximum demand, but it introduces additional concerns:

- scaling delay
- incorrect scaling thresholds
- oscillation
- startup time
- cost
- insufficient capacity during sudden spikes

The script includes a simplified `AutoScaler`.

---

# 8. Throughput

Throughput represents how much work is completed per unit of time.

Examples:

- requests per second
- transactions per second
- messages per second
- records processed per minute

Throughput should always be interpreted together with workload characteristics.

A system capable of 10,000 requests per second under trivial requests is not necessarily capable of 10,000 requests per second for complex database transactions.

---

# 9. Capacity

Capacity is the amount of workload a system can sustainably handle under specified conditions.

Capacity depends on:

- hardware
- software
- algorithms
- database performance
- network
- dependency performance
- concurrency
- workload characteristics
- configuration

Capacity should be measured rather than guessed.

---

# 10. Utilization

A simplified utilization equation is:

Utilization = Offered Load / Capacity

For example:

- offered load = 700 requests/second
- capacity = 1,000 requests/second

Utilization = 70%

Operating continuously near maximum capacity can be dangerous because real systems experience:

- bursts
- uneven load
- dependency delays
- garbage collection
- background work
- deployments
- failures
- workload variability

A system with no spare capacity may technically satisfy average demand but fail under realistic conditions.

---

# 11. Little's Law

The script demonstrates Little's Law:

L = λW

Where:

- L = average number of items in the system
- λ = throughput
- W = average time spent in the system

If a service handles 100 requests per second and average latency is 0.2 seconds:

L = 100 × 0.2 = 20

Approximately 20 requests are in flight on average.

Little's Law is useful for reasoning about:

- concurrency
- queueing
- capacity
- request processing
- message systems

It is particularly useful because it connects throughput, latency, and concurrency mathematically.

---

# 12. Stateless Architecture

A stateless service does not depend on local memory from previous requests to correctly process a new request.

State can instead be stored in:

- databases
- distributed caches
- object stores
- message brokers
- external session stores
- signed client-side tokens

Stateless application servers make horizontal scaling easier because any healthy instance can process a request.

Stateful architectures are not inherently wrong. They simply require more deliberate handling of state ownership, replication, failover, and routing.

---

# 13. Load Balancing

A load balancer distributes requests among multiple backend instances.

The script demonstrates:

- round-robin
- least-connections selection

### Round Robin

Requests are distributed sequentially.

For three servers:

1. server A
2. server B
3. server C
4. server A
5. server B
6. server C

It is simple but does not necessarily account for different server capacities or current workloads.

### Least Connections

Requests are sent to the healthy backend with the fewest active connections.

This can be useful when requests have varying durations.

Other load-balancing strategies include:

- weighted round robin
- weighted least connections
- hash-based routing
- geographic routing
- latency-aware routing

---

# 14. Availability

Availability is normally expressed as a percentage.

Examples include:

- 99%
- 99.9%
- 99.99%
- 99.999%

Each additional nine represents a significantly smaller downtime budget.

For a fixed measurement period:

Allowed Downtime = Total Time × (1 - Availability Target)

Availability targets must specify:

- measurement interval
- endpoints
- failure definition
- maintenance treatment
- partial outage behavior
- dependency behavior
- measurement location

Without these definitions, two teams can calculate different availability numbers for the same system.

---

# 15. Availability Nines

A simplified hierarchy is:

| Availability | Unavailable Fraction |
|---|---:|
| 99% | 1% |
| 99.9% | 0.1% |
| 99.99% | 0.01% |
| 99.999% | 0.001% |

Moving from 99.9% to 99.99% is not a small improvement. It reduces the allowable downtime by an order of magnitude.

Higher availability normally requires greater investment in:

- redundancy
- monitoring
- failover
- automation
- testing
- infrastructure isolation
- operational maturity

---

# 16. High Availability

High availability is achieved through mechanisms such as:

- redundant servers
- multiple availability zones
- multiple regions
- health checks
- automated failover
- replicated databases
- load balancing
- resilient dependencies
- tested recovery procedures

Redundancy is useful only when failure domains are actually independent.

Three replicas on one physical host do not provide the same resilience as replicas distributed across independent failure domains.

---

# 17. Active/Passive and Active/Active

### Active/Passive

One component actively serves traffic while another waits for failover.

Advantages:

- simpler state management
- easier operational model

Limitations:

- standby capacity may be underutilized
- failover time can be significant

### Active/Active

Multiple instances actively serve traffic.

Advantages:

- better resource utilization
- greater aggregate capacity
- no need to maintain completely idle standby capacity

Challenges:

- distributed state
- synchronization
- consistency
- routing
- more complex failure behavior

---

# 18. Reliability

Reliability can be measured in terms of successful operations.

A simplified reliability rate is:

Reliability = Successful Operations / Total Operations

Reliability should be defined around the operation being evaluated.

Examples:

- successful payments
- correct search responses
- successful message processing
- correct database transactions

A successful HTTP status code does not necessarily imply a correct business result.

---

# 19. MTBF, MTTR, MTTD, and MTTA

### MTBF

Mean Time Between Failures.

It describes the average time between failures under a defined measurement model.

### MTTR

Mean Time To Repair or Restore.

It represents the time required to return the system to service.

### MTTD

Mean Time To Detect.

How long it takes to detect a failure.

### MTTA

Mean Time To Acknowledge.

How long it takes for an operational response to begin after detection.

A simplified availability relationship is:

Availability ≈ MTBF / (MTBF + MTTR)

This demonstrates an important operational principle:

Reducing recovery time can increase availability even when failure frequency does not change.

---

# 20. Reliability vs Availability

These concepts are related but different.

### Available but unreliable

A service responds to every request but frequently produces incorrect results.

### Reliable but temporarily unavailable

A service produces correct results whenever accessible but experiences an outage.

### Available and reliable

The service is accessible and consistently produces correct results.

This distinction is important in system design and incident analysis.

---

# 21. Latency

Latency is the time required to perform an operation.

An API request may involve:

1. DNS lookup
2. connection establishment
3. TLS negotiation
4. load balancer processing
5. application processing
6. cache access
7. database access
8. serialization
9. network transmission

The script includes a latency budget model that decomposes total latency into components.

---

# 22. Average Latency Is Not Enough

Suppose the following requests occur:

- most requests: 20 ms
- some requests: 100 ms
- a few requests: 2,000 ms

The average can conceal the slow tail.

Percentiles provide better insight.

### p50

Half of requests are at or below this latency.

### p95

95% of requests are at or below this latency.

### p99

99% of requests are at or below this latency.

### p99.9

99.9% of requests are at or below this latency.

Tail latency is particularly important in systems where a user operation depends on several downstream services.

---

# 23. Latency Budgets

A latency target should be decomposed.

For example:

| Component | Budget |
|---|---:|
| DNS | 10 ms |
| Connection | 20 ms |
| Application | 80 ms |
| Database | 100 ms |
| Serialization | 20 ms |
| Total | 230 ms |

If the end-to-end requirement is 300 ms, the architecture has approximately 70 ms of remaining budget.

Latency budgets make optimization more systematic because teams can identify which component consumes the available time.

---

# 24. Latency vs Throughput

Latency and throughput are not interchangeable.

Latency asks:

> How long does one operation take?

Throughput asks:

> How much work can the system complete per unit of time?

A system can have:

- low latency but low throughput
- high throughput but high latency
- both high throughput and low latency
- both low throughput and high latency

Concurrency and queueing make the relationship more complex.

---

# 25. Timeouts

Distributed operations should not wait indefinitely.

A timeout provides a boundary around waiting.

Examples:

- database timeout
- HTTP client timeout
- cache timeout
- queue polling timeout
- connection timeout

Timeouts should be based on the actual latency budget.

An excessively long timeout can consume resources while waiting for a dependency that is already failing.

An excessively short timeout can cause unnecessary failures.

Timeouts should also be propagated as deadlines through dependency chains where appropriate.

---

# 26. Retries

Retries can improve reliability when failures are transient.

Examples:

- temporary network failures
- temporary connection failures
- transient service unavailability

Retries can also make a failure worse.

If 10,000 clients simultaneously retry an overloaded service, the additional traffic can produce a retry storm.

Good retry design generally includes:

- bounded attempts
- exponential backoff
- jitter
- retryable error classification
- idempotency
- deadlines

The script implements exponential backoff with jitter.

---

# 27. Exponential Backoff

A simplified exponential backoff formula is:

Delay = Base Delay × 2^Attempt

For example, with a base delay of 100 ms:

- attempt 0: 100 ms
- attempt 1: 200 ms
- attempt 2: 400 ms
- attempt 3: 800 ms

A maximum delay should normally cap the result.

---

# 28. Jitter

Jitter introduces controlled randomness into retry delays.

Without jitter, many clients that failed simultaneously may retry at the same instant.

With jitter, retries become distributed over time.

This reduces synchronized retry bursts.

---

# 29. Idempotency

An operation is idempotent when repeating it produces the same intended effect as executing it once.

Examples of naturally idempotent operations can include certain reads.

Payment and order creation operations require special care.

Suppose:

1. Client submits payment.
2. Server processes payment.
3. Network response is lost.
4. Client retries.
5. Server receives a second request.

Without protection, the payment may be charged twice.

An idempotency key lets the server recognize that the second request represents the same logical operation.

The script implements an `IdempotencyStore` to demonstrate this concept.

---

# 30. Circuit Breaker

A circuit breaker protects callers from repeatedly invoking a failing dependency.

It normally has three states.

### Closed

Calls are allowed.

### Open

Calls fail fast without contacting the dependency.

### Half-Open

A limited test is performed to determine whether the dependency has recovered.

Circuit breakers can prevent:

- resource exhaustion
- long request queues
- cascading failures
- repeated timeouts

They must be tuned carefully because an incorrectly configured breaker can hide temporary failures or cause unnecessary rejection.

---

# 31. Bulkhead Pattern

The bulkhead pattern isolates resources.

Suppose an application has:

- payment calls
- recommendation calls
- search calls

If recommendation requests consume every worker, payment operations could also become unavailable.

A bulkhead limits how much capacity one dependency or workload can consume.

The script uses a semaphore-based implementation.

---

# 32. Asynchronous Processing

Queues can separate producers from consumers.

A request can place work into a queue instead of waiting for the full operation to complete.

Benefits include:

- workload smoothing
- independent scaling
- burst absorption
- asynchronous execution
- reduced synchronous dependency chains

Costs include:

- increased latency
- eventual consistency
- duplicate processing
- queue management
- monitoring complexity

Asynchronous architecture is especially useful for work that does not need to finish before responding to the user.

---

# 33. Backpressure

Backpressure prevents producers from overwhelming consumers.

An unbounded queue can continue growing until the process consumes excessive memory.

A bounded queue establishes a limit.

When the queue is full, the producer must:

- wait
- reject
- shed load
- degrade functionality
- route elsewhere

Backpressure is a reliability mechanism because uncontrolled backlog can turn temporary overload into system failure.

---

# 34. Caching

Caching stores frequently used data closer to consumers.

Caching can reduce:

- database load
- network calls
- CPU usage
- latency

Common cache characteristics include:

- TTL
- eviction
- cache hit rate
- cache miss rate
- capacity
- invalidation

The fundamental cache problem is that cached data may become stale.

---

# 35. Cache-Aside Pattern

The cache-aside pattern works as follows:

1. Check the cache.
2. If the data exists, return it.
3. If it does not exist, read the database.
4. Store the result in the cache.
5. Return the result.

This pattern is simple and widely applicable.

The script demonstrates this with `cache_aside_get`.

---

# 36. Cache Trade-Offs

Caching can improve latency and scalability but introduces risks.

### Benefits

- lower database load
- lower latency
- reduced repeated computation
- better burst handling

### Risks

- stale data
- invalidation complexity
- cache stampede
- memory pressure
- inconsistent views
- cache availability becoming a new dependency

Caching should be applied only where the freshness characteristics are acceptable.

---

# 37. Database Scalability

Databases frequently become critical scalability bottlenecks.

Common techniques include:

### Indexing

Indexes accelerate suitable query patterns.

### Read Replicas

Read workloads can be distributed to replicas.

### Partitioning

Data is divided into logical partitions.

### Sharding

Data is distributed across database nodes.

### Connection Pooling

Existing connections are reused rather than constantly recreated.

### Denormalization

Selected duplication can reduce expensive joins or repeated computation.

### Archiving

Cold data can be moved away from hot operational workloads.

Each approach has trade-offs involving:

- consistency
- complexity
- operational cost
- write performance
- failure handling
- data distribution

---

# 38. Consistency

Consistency describes how and when different observers see data.

### Strong Consistency

Reads provide strong guarantees regarding recent writes.

Advantages:

- easier reasoning
- predictable reads
- useful for critical invariants

Costs:

- coordination
- potentially higher latency
- reduced availability under certain distributed failures

### Eventual Consistency

Replicas may temporarily disagree but converge.

Advantages:

- high scalability
- reduced coordination
- useful for many read-heavy distributed systems

Costs:

- stale reads
- more complex application behavior
- reconciliation requirements

The correct model depends on the business operation.

---

# 39. Distributed-System Failure

Distributed systems have partial failures.

A dependency may be:

- completely unavailable
- intermittently available
- reachable but slow
- returning errors
- returning incorrect data
- reachable from one region but not another
- accepting work but failing to acknowledge it

This is why distributed applications require:

- timeouts
- retries
- circuit breakers
- fallback strategies
- idempotency
- observability
- isolation

---

# 40. Fault Injection

Fault injection deliberately introduces failures to test system behavior.

Examples include:

- network latency
- dropped connections
- dependency failures
- instance termination
- database unavailability
- queue failures
- regional failures

Testing only the healthy path gives incomplete evidence about reliability.

The script contains a small fault-injection simulation.

---

# 41. Security Fundamentals

The script introduces the major security principles.

## Confidentiality

Only authorized parties can access protected information.

## Integrity

Data and operations are protected from unauthorized modification.

## Availability

Authorized users can access services when required.

## Authentication

Determines who an actor is.

## Authorization

Determines what an authenticated actor may do.

## Accountability

Provides evidence about security-relevant actions.

Authentication and authorization are distinct.

Knowing who someone is does not automatically determine what that person may access.

---

# 42. Password Storage

Passwords should never be stored in plaintext.

Password-specific hashing mechanisms include:

- Argon2id
- scrypt
- bcrypt
- PBKDF2

A password hashing design should include:

- unique salts
- an appropriate work factor
- secure storage
- controlled authentication attempts
- secure secret handling

The script demonstrates PBKDF2 using Python's standard library.

The demonstration is educational. Production configurations should use a current security review and an appropriately selected password hashing scheme and work factor.

---

# 43. Authentication vs Authorization

Authentication:

> Who are you?

Authorization:

> What are you allowed to do?

For example:

A user may successfully authenticate but still lack permission to:

- access an administrative endpoint
- modify another user's account
- issue refunds
- change security settings

Authorization must be enforced on the trusted server side.

Client-side UI restrictions are not sufficient security controls.

---

# 44. Input Validation

Input validation belongs at trust boundaries.

Validation should consider:

- type
- size
- format
- allowed values
- normalization
- business rules

Allowlist-based validation is often preferable where the valid input space is known.

Validation does not replace:

- authorization
- parameterized queries
- output encoding
- secure transport
- rate limiting

The script validates usernames and demonstrates rejection of unsupported input.

---

# 45. SQL Injection and Parameterized Queries

Applications should not construct database statements by concatenating untrusted input into SQL syntax.

Unsafe conceptual pattern:

user input + SQL statement

Safe conceptual pattern:

SQL statement + separate parameters

The database driver then handles parameter binding.

The script demonstrates the structure of a parameterized query without requiring an actual database.

---

# 46. Rate Limiting

Rate limiting controls how much work an actor can submit during a period.

The script implements a token bucket.

Token bucket characteristics include:

- capacity
- refill rate
- request cost

Rate limiting is useful for:

- API protection
- login protection
- password reset endpoints
- expensive operations
- abuse prevention
- downstream protection

Different operations normally need different limits.

---

# 47. Security and Availability

Security and availability are interconnected.

Examples:

### Rate Limiting

Protects capacity but may reject legitimate traffic if configured too aggressively.

### Authentication

Protects access but can introduce latency and dependency requirements.

### Encryption

Protects confidentiality but introduces computational and operational overhead.

### External Identity Provider

Improves centralized identity management but can become an availability dependency.

The correct objective is not to eliminate security-related overhead. It is to design controls with appropriate resilience and measurable performance.

---

# 48. Transport Security

Sensitive network communication should normally use TLS.

Important considerations include:

- certificate validation
- hostname verification
- modern protocol configuration
- private key protection
- certificate rotation
- trust management

Encryption at rest may also be required for stored data.

For particularly sensitive information, application-level encryption can provide additional protection.

---

# 49. Defense in Depth

Defense in depth means using multiple independent security controls.

A layered architecture can include:

1. network controls
2. TLS
3. authentication
4. authorization
5. input validation
6. rate limiting
7. secure database access
8. audit logging
9. monitoring
10. incident response

The objective is to prevent a single control failure from becoming a complete security compromise.

---

# 50. Data Classification

Different data requires different protection levels.

A conceptual classification can be:

- public
- internal
- confidential
- highly sensitive

Controls may increase as sensitivity increases.

Possible controls include:

- encryption
- restricted access
- masking
- tokenization
- auditing
- retention limits
- deletion policies

Data classification is therefore a security design input, not merely a documentation exercise.

---

# 51. Observability

Observability allows engineers to understand internal system behavior from externally visible signals.

Three major mechanisms are:

### Metrics

Numerical measurements over time.

Examples:

- request rate
- error rate
- CPU utilization
- queue depth
- latency
- memory usage

### Logs

Records of events.

Useful logs should generally be:

- structured
- timestamped
- correlated
- appropriately redacted
- searchable

Sensitive information should not be unnecessarily logged.

### Traces

Traces follow a request through multiple services.

They are particularly valuable for identifying where distributed latency is being introduced.

---

# 52. The Four Golden Signals

The script demonstrates four commonly used operational signals.

## Latency

How long requests take.

## Traffic

How much demand the system is receiving.

## Errors

How often requests or operations fail.

## Saturation

How close resources are to their effective limits.

Together these signals provide a compact view of service health.

---

# 53. SLI, SLO, and SLA

## SLI

Service Level Indicator.

A measured quantity representing service behavior.

Example:

Successful requests / Valid requests

## SLO

Service Level Objective.

The desired target for an SLI.

Example:

99.95% successful valid requests per month.

## SLA

Service Level Agreement.

A contractual commitment that may define remedies or service credits if commitments are missed.

The terms are related but should not be treated as interchangeable.

---

# 54. Error Budget

If an availability SLO is 99.9%, the allowed error budget is:

1 - 0.999 = 0.001

or:

0.1%

An error budget turns reliability into a measurable quantity.

The budget can be expressed in:

- percentage
- minutes
- failed requests
- failed transactions

Error-budget thinking can help teams evaluate the risk of operational changes and deployments.

---

# 55. Graceful Degradation

Graceful degradation means preserving essential functionality when optional functionality fails.

For example, if a recommendation service fails, an e-commerce application may still display the product page using popular products instead of personalized recommendations.

This approach can protect core functionality during partial failures.

Fallbacks must not compromise:

- security
- data integrity
- authorization
- critical business rules

---

# 56. Redundancy

Redundancy means maintaining multiple resources capable of supporting a workload.

Examples:

- multiple application instances
- multiple database replicas
- multiple network paths
- multiple availability zones
- multiple regions

Redundancy is useful only when the replicas do not share the same failure mode.

Common-mode failures remain a major concern.

---

# 57. Dependency Availability

If a request requires several dependencies to succeed, the combined availability can be lower than the availability of any individual component.

For simplified serial dependencies:

A_total = A1 × A2 × A3 × ... × An

For example, if three required dependencies have availability:

- 99.9%
- 99.95%
- 99.99%

Their simplified combined availability is lower than each individual availability.

Architecture can reduce dependency impact using:

- caching
- asynchronous processing
- redundancy
- fallbacks
- isolation

---

# 58. Queueing Pressure

A simplified utilization equation is:

ρ = Arrival Rate / Service Rate

If arrival rate approaches service rate, queueing can become substantial.

If arrival rate permanently exceeds service rate, backlog grows.

This creates a fundamental scalability principle:

A system cannot sustainably process more work than its effective capacity.

Temporary bursts can be handled through:

- buffering
- queues
- autoscaling
- load shedding
- caching

Sustained overload requires additional capacity or reduced workload.

---

# 59. Autoscaling

Autoscaling adjusts instance counts according to observed workload or resource usage.

Possible scaling signals include:

- CPU
- memory
- requests per second
- queue depth
- latency
- custom business metrics

CPU-only autoscaling may be insufficient when the actual bottleneck is:

- database connections
- queue depth
- network
- external dependency latency

Scaling should use the metric most closely connected to capacity.

---

# 60. Capacity Planning

Capacity planning estimates future requirements.

A simplified model can be:

Required Capacity =
Expected Load × Peak Multiplier × Growth Factor × Safety Factor

For example:

Expected load = 5,000 requests/second

Peak multiplier = 2

Growth factor = 1.5

Safety factor = 1.2

Required capacity:

5,000 × 2 × 1.5 × 1.2 = 18,000 requests/second

The actual factors must come from historical data, forecasts, experiments, and business expectations.

---

# 61. Performance vs Scalability

Performance optimization focuses on how efficiently a system performs.

Examples:

- improve an algorithm
- optimize SQL
- reduce serialization overhead
- improve caching
- reduce unnecessary network calls

Scalability focuses on how capacity changes as demand or resources increase.

Examples:

- horizontal replication
- sharding
- partitioning
- queue-based processing
- distributed caching

A system can be highly performant on one machine but difficult to scale.

---

# 62. Deployment Strategies

The script introduces:

- rolling deployments
- blue-green deployments
- canary deployments

## Rolling Deployment

Instances are gradually replaced.

Advantages:

- lower infrastructure overhead

Risks:

- mixed versions
- partial rollout failures

## Blue-Green Deployment

Two environments are maintained.

Traffic can be shifted from the old environment to the new environment.

Advantages:

- relatively fast rollback
- isolated deployment environment

Cost:

- additional infrastructure

## Canary Deployment

A small percentage of traffic is exposed to the new version.

If health metrics remain acceptable, traffic gradually increases.

Canaries reduce blast radius but require strong observability and traffic control.

---

# 63. Blast Radius

Blast radius represents how much of a system is affected by a failure or change.

A deployment affecting 2 of 20 instances has a simple conceptual blast radius of:

2 / 20 = 10%

Blast radius can be reduced through:

- canary releases
- feature flags
- independent services
- regional isolation
- progressive deployment
- compartmentalization

Reducing blast radius is an important reliability principle.

---

# 64. Health Checks

Health checks help determine whether an instance is suitable for traffic.

Checks may evaluate:

- application process
- database connectivity
- critical dependencies
- internal readiness state

Health checks should be carefully designed.

A health endpoint that checks every external dependency can itself become misleading or expensive.

---

# 65. Liveness vs Readiness

These concepts are often separated.

### Liveness

Answers:

> Is the process alive?

### Readiness

Answers:

> Can this instance safely receive traffic?

A process may be alive but not ready because:

- initialization is incomplete
- dependencies are unavailable
- it is draining connections
- it is overloaded
- it is shutting down

Confusing liveness with readiness can cause unnecessary restart loops or traffic routing failures.

---

# 66. Non-Functional Requirement Testing

Different tests answer different questions.

## Load Testing

Tests expected workload.

## Stress Testing

Pushes the system beyond expected capacity.

## Soak Testing

Runs sustained workloads for long periods.

Useful for detecting:

- memory leaks
- resource degradation
- connection leaks
- gradual performance deterioration

## Spike Testing

Tests sudden changes in workload.

## Failover Testing

Tests component failure and recovery.

## Recovery Testing

Tests restoration following significant disruption.

## Security Testing

Tests security controls and identifies vulnerabilities.

A production NFR should be testable rather than merely stated.

---

# 67. Load Testing

A useful load test should define:

- workload
- concurrency
- duration
- request distribution
- expected throughput
- latency targets
- acceptable error rate
- environment
- data characteristics

Important outputs include:

- throughput
- p50 latency
- p95 latency
- p99 latency
- error rate
- resource utilization
- saturation

The simulation in the Python script intentionally models increasing latency and failure probability as load approaches and exceeds capacity.

It is educational rather than a substitute for a real load-testing platform.

---

# 68. Requirement Traceability

A strong NFR should have a chain such as:

Requirement  
→ Metric  
→ Test  
→ Dashboard  
→ Alert  
→ Owner  
→ Operational response

Example:

Requirement:

> Checkout p95 latency <= 300 ms.

Metric:

> checkout_latency_p95

Test:

> load test

Dashboard:

> checkout latency dashboard

Alert:

> p95 exceeds target

Owner:

> checkout platform team

This makes NFRs operational rather than purely documentary.

---

# 69. Major NFR Trade-Offs

NFRs frequently conflict.

### More Replicas

Improves:

- availability
- capacity

Costs:

- infrastructure
- operations
- synchronization complexity

### More Caching

Improves:

- latency
- scalability

Costs:

- stale data
- invalidation complexity

### More Retries

Improves:

- recovery from transient errors

Costs:

- retry storms
- higher latency
- increased downstream load

### Stronger Consistency

Improves:

- correctness guarantees

Costs:

- coordination
- latency
- possible availability impact

### Strict Rate Limiting

Improves:

- protection
- resource stability

Costs:

- legitimate traffic rejection

### Larger Instances

Improve:

- per-instance capacity
- sometimes latency

Costs:

- higher cost
- vertical scaling limits

There is no universally optimal configuration.

---

# 70. Common Anti-Patterns

## Vague Availability Requirements

Bad:

> The system must be highly available.

Better:

> The public API must achieve 99.95% monthly availability according to a defined measurement method.

## Average-Only Latency

Bad:

> Average latency is 100 ms, therefore performance is good.

Better:

Measure p50, p95, p99, and relevant tail behavior.

## Unlimited Retries

Retries should always have bounds and failure classification.

## Reactive Capacity Planning

Waiting until users experience failures is not an effective capacity strategy.

## Local-Only Application State

Local state can make horizontal scaling and failover more difficult.

## Single Failure Domain

Multiple replicas in one failure domain may all fail simultaneously.

## Client-Side Authorization

A UI restriction is not a security boundary.

## Unbounded Queues

Uncontrolled backlog can consume memory and destabilize the service.

## Untested Backups

A backup that cannot be restored is not sufficient evidence of recoverability.

---

# 71. Disaster Recovery

Disaster recovery addresses restoration after major disruptions.

Two important objectives are:

## RTO

Recovery Time Objective.

The targeted maximum time required to restore service.

## RPO

Recovery Point Objective.

The targeted maximum amount of data loss measured in time.

Example:

RTO = 30 minutes

RPO = 5 minutes

This means the organization targets service restoration within 30 minutes and aims to lose no more than approximately five minutes of data under the defined recovery model.

---

# 72. Backups

Important backup considerations include:

- frequency
- retention
- encryption
- access control
- geographic separation
- immutability
- integrity verification
- restoration testing

The relationship between backup frequency and RPO is particularly important.

A system requiring a five-minute RPO cannot depend on backups taken once every 24 hours.

Most importantly, restoration must actually be tested.

---

# 73. Security and Reliability Together

Security failures can become availability and reliability failures.

Examples:

- credential attacks consume authentication infrastructure
- denial-of-service traffic consumes capacity
- compromised credentials lead to unauthorized operations
- malicious input causes service crashes
- leaked secrets enable destructive operations

Therefore security controls should be treated as part of system reliability architecture.

---

# 74. Production Architecture Thinking

A production-grade architecture should consider the five core NFRs together.

### Scalability

Ask:

- What is expected traffic?
- What is peak traffic?
- What is the capacity of one instance?
- What is the scaling mechanism?
- What is the bottleneck?

### Availability

Ask:

- What happens if one instance fails?
- What happens if an availability zone fails?
- What happens if the database fails?
- What happens if a dependency becomes unavailable?

### Reliability

Ask:

- What can fail?
- Can requests be duplicated?
- Are operations idempotent?
- Are retries bounded?
- Are recovery procedures tested?

### Latency

Ask:

- What is the p95 target?
- What is the p99 target?
- Where is the latency budget spent?
- Which dependency dominates tail latency?

### Security

Ask:

- Who can access the system?
- What can each identity do?
- What data is sensitive?
- How is data protected?
- How are security events detected?

---

# 75. Integrated E-Commerce Example

The Python script includes a conceptual e-commerce scenario.

Suppose the system must support:

- 1,000 requests/second normally
- 4,000 requests/second at peak
- 99.95% monthly availability
- checkout p95 latency below 300 ms
- no duplicate payments
- authenticated and authorized customer access

A suitable architecture might use:

- horizontally scaled stateless API instances
- load balancing
- independent failure domains
- health checks
- automated failover
- caching for suitable reads
- database scaling
- timeout boundaries
- bounded retries
- idempotency keys
- circuit breakers
- rate limiting
- authentication
- authorization
- encryption
- monitoring
- alerting
- tested disaster recovery

The key point is that no single technique solves every NFR.

---

# 76. End-to-End NFR Relationship

The five requirements influence one another.

A simplified relationship is:

Higher workload  
→ higher resource utilization  
→ longer queues  
→ higher latency  
→ increased timeout probability  
→ more retries  
→ more load  
→ greater failure probability

This is why overload can become a feedback loop.

Similarly:

Dependency failure  
→ timeout  
→ occupied worker  
→ reduced capacity  
→ queue growth  
→ latency increase  
→ more timeouts

Circuit breakers, bulkheads, timeouts, backpressure, caching, and graceful degradation are techniques for breaking such failure chains.

---

# 77. Performance, Scalability, and Capacity Are Different

These terms should not be used interchangeably.

### Performance

Efficiency of a particular configuration.

### Capacity

Maximum sustainable workload under defined conditions.

### Scalability

How capacity or performance changes as resources or workload change.

A system can have excellent single-instance performance but poor scalability if adding additional instances provides little additional capacity.

---

# 78. Availability, Reliability, and Correctness

These concepts should also remain distinct.

Availability asks:

> Can I reach the service?

Reliability asks:

> Does the service consistently behave correctly?

Correctness asks:

> Does the implementation produce the intended result?

A system that is always reachable but computes incorrect financial transactions is not reliable.

---

# 79. Security, Availability, and Performance Trade-Off

Security controls have operational consequences.

For example:

- password hashing intentionally consumes computational resources
- authentication adds processing
- authorization requires policy evaluation
- encryption consumes CPU
- rate limiting may reject requests
- security monitoring consumes storage and processing

The solution is not to remove controls.

The solution is to:

- measure their cost
- optimize implementations
- cache appropriate information
- isolate security dependencies
- scale security infrastructure
- establish resilient authentication paths
- monitor security-related performance

---

# 80. Production NFR Checklist

## Scalability

- Expected workload defined
- Peak workload defined
- Capacity per instance measured
- Horizontal scaling tested
- Bottlenecks identified
- Database capacity evaluated
- Queue capacity evaluated
- Autoscaling behavior tested

## Availability

- Availability target defined
- Downtime measurement defined
- Failure domains identified
- Redundancy implemented
- Health checks implemented
- Failover tested
- Recovery process tested

## Reliability

- Failure modes documented
- Timeouts configured
- Retries bounded
- Retryable failures classified
- Idempotency considered
- Circuit breakers evaluated
- Backpressure implemented where required
- Recovery procedures tested

## Latency

- End-to-end target defined
- p50 monitored
- p95 monitored
- p99 monitored
- Latency budget defined
- Database latency measured
- Network latency measured
- Dependency latency measured
- Tail latency investigated

## Security

- Authentication defined
- Authorization enforced server-side
- Sensitive data classified
- Data encrypted appropriately
- Secrets protected
- Secrets rotated
- Input validated
- Rate limits defined
- Security events monitored
- Audit requirements identified

---

# 81. Python Script Structure

The Python file is organized progressively.

The major sections are:

1. Fundamental terminology
2. Measurable requirements
3. Capacity and utilization
4. Little's Law
5. Scalability
6. Vertical vs horizontal scaling
7. Load balancing
8. Stateless architecture
9. Availability
10. Availability nines
11. Failover
12. Reliability
13. MTBF and MTTR
14. Latency distributions
15. Latency budgets
16. Timeouts
17. Retries and exponential backoff
18. Idempotency
19. Circuit breakers
20. Bulkheads
21. Queues
22. Backpressure
23. Caching
24. Cache-aside
25. Database scalability
26. Consistency
27. Distributed failures
28. Fault injection
29. Security fundamentals
30. Password hashing
31. Authentication and authorization
32. Input validation
33. Rate limiting
34. Transport security
35. Observability
36. Four golden signals
37. SLI, SLO, SLA
38. Error budgets
39. Graceful degradation
40. Redundancy
41. Dependency availability
42. Queueing pressure
43. Autoscaling
44. Capacity planning
45. Performance vs scalability
46. Security and availability trade-offs
47. Defense in depth
48. Parameterized database access
49. Data classification
50. RTO and RPO
51. Backup strategy
52. Deployment strategies
53. Blast radius
54. Health checks
55. Liveness and readiness
56. NFR testing
57. Load testing simulation
58. Requirement traceability
59. Trade-off matrix
60. Requirement quality
61. End-to-end service simulation
62. Anti-patterns
63. Production checklist
64. Integrated case study
65. Availability vs reliability
66. Latency vs throughput
67. Security vs performance
68. Failure budgets
69. Rate-limit policy examples

The script is intentionally self-contained and uses Python's standard library so that the conceptual examples can be executed without a distributed infrastructure environment.

---

# 82. Important Quantitative Relationships

Several formulas in the script provide a foundation for reasoning about NFRs.

### Availability

Availability = (Total Time - Downtime) / Total Time

### Downtime Budget

Downtime = Total Time × (1 - Availability Target)

### Utilization

Utilization = Offered Load / Capacity

### Little's Law

L = λW

### Simplified Serial Availability

A_total = A1 × A2 × ... × An

### Simplified MTBF/MTTR Availability

Availability ≈ MTBF / (MTBF + MTTR)

### Error Budget

Error Budget = 1 - SLO

### Capacity Planning

Required Capacity =
Expected Load × Peak Multiplier × Growth Factor × Safety Factor

These equations are simplified models. Real production systems require workload-specific definitions and empirical measurements.

---

# 83. Important Design Principles

Several principles recur throughout the topic.

### Measure Rather Than Assume

NFRs should be supported by measurements.

### Design for Failure

Assume dependencies and infrastructure can fail.

### Bound Waiting

Use timeouts and deadlines.

### Bound Retries

Never retry indefinitely.

### Prevent Duplicate Effects

Use idempotency for operations that may be retried.

### Isolate Failure

Use bulkheads, independent failure domains, and controlled blast radius.

### Control Backlog

Use bounded queues and backpressure.

### Monitor Tail Behavior

Average latency is insufficient.

### Protect Trust Boundaries

Validate input and enforce authorization on trusted servers.

### Test Recovery

A theoretical failover design is not sufficient evidence of resilience.

### Make Trade-Offs Explicit

Improving one NFR often changes another.

---

# 84. Why NFRs Are Architectural Requirements

Non-functional requirements influence architecture from the beginning.

For example, a requirement for:

> 99.999% availability

has very different architectural consequences from:

> 99% availability.

Likewise:

> 100 requests/second

requires a different capacity model from:

> 100,000 requests/second.

And:

> p99 latency below 50 ms

requires different architectural decisions from:

> p95 latency below 2 seconds.

Therefore NFRs should be considered during:

- requirements analysis
- architecture design
- technology selection
- database design
- API design
- deployment planning
- security design
- capacity planning
- testing
- operations

They should not be added only after the functional implementation is complete.

---

# 85. Real-World Relevance

The concepts demonstrated by the script apply to systems such as:

- payment platforms
- banking systems
- e-commerce platforms
- cloud APIs
- SaaS applications
- social networks
- streaming systems
- logistics systems
- healthcare platforms
- enterprise applications
- data-processing systems
- cybersecurity platforms
- distributed microservices

The exact targets differ by business context.

A banking transaction may prioritize correctness, integrity, security, and reliability.

A social-media feed may prioritize scalability, latency, availability, and eventual consistency.

An emergency communication platform may place exceptionally high importance on availability and resilience.

A payment platform may require strict idempotency, authorization, auditability, and reliability.

The architecture must therefore emerge from the required quality attributes and business consequences rather than from technology preferences alone.
