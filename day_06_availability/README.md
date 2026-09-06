# System Design Foundations: Availability

## Topic Scope

This document explains availability as a foundational system-design concept, progressing from basic uptime and downtime calculations to SLI, SLO, SLA, error budgets, redundancy, failure domains, failover, observability, incident response, and production availability engineering.

The accompanying Python script is a self-contained educational implementation. It demonstrates the mathematical models, measurement techniques, architectural calculations, operational mechanisms, edge cases, and practical decision models discussed here.

---

## 1. What Is Availability?

Availability describes whether a system is usable when users or dependent systems need it.

At its simplest, time-based availability is:

**Availability = (Total Time − Downtime) / Total Time**

For example, if a service is expected to operate for 100 hours and is unavailable for 1 hour:

**Availability = 99 / 100 = 99%**

Availability can also be defined in terms of requests or operations:

**Request Availability = Successful Requests / Valid Requests**

The appropriate definition depends on what the service is supposed to provide.

A web server that responds to TCP connections may technically be reachable while every application request returns an error. Measuring only network reachability would therefore produce a misleading availability result.

---

## 2. Uptime and Downtime

### Uptime

Uptime is the amount of eligible time during which the service satisfies the defined availability criterion.

### Downtime

Downtime is the amount of eligible time during which the service fails that criterion.

The terms are useful but incomplete without a measurement definition.

For example, consider a service that responds to every request but returns incorrect results. Whether that is considered available depends on the SLI definition.

This is why modern availability engineering focuses on measurable service behavior rather than simply asking whether a server is running.

---

## 3. Availability as a Percentage

Availability is normally expressed as a percentage:

- 90%
- 99%
- 99.9%
- 99.99%
- 99.999%
- 99.9999%

The difference between these values is more significant than it initially appears.

For example:

- 99% availability allows 1% unavailability.
- 99.9% availability allows 0.1% unavailability.
- 99.99% availability allows 0.01% unavailability.
- 99.999% availability allows 0.001% unavailability.

Every additional nine reduces the permitted unavailability by approximately a factor of ten.

---

## 4. Availability and Downtime Budgets

A target availability percentage can be converted into an allowed downtime budget.

The formula is:

**Allowed Downtime = Measurement Period × (1 − Availability Target)**

For a 30-day period:

- 99% allows substantially more downtime than 99.9%.
- 99.9% allows roughly 43.2 minutes.
- 99.99% allows roughly 4.32 minutes.
- 99.999% allows roughly 25.92 seconds.
- 99.9999% allows roughly 2.592 seconds.

The exact result depends on the measurement period and the organization's definition of eligible time.

This conversion is essential because a percentage by itself can be difficult to interpret operationally.

---

# 5. SLI, SLO, and SLA

The three terms are related but represent different concepts.

## 5.1 SLI: Service Level Indicator

An SLI is a measurement.

It answers:

> What is the service actually doing?

Examples:

- Successful API requests / valid API requests
- Successful checkout attempts / valid checkout attempts
- Requests completed under 300 ms / eligible requests
- Available seconds / eligible seconds

An SLI should be measurable, reproducible, and closely connected to user experience.

---

## 5.2 SLO: Service Level Objective

An SLO is a target for an SLI.

It answers:

> What level of service do we intend to provide?

Example:

**99.9% of valid API requests should succeed during the measurement window.**

The 99.9% is the objective.

The SLI is the actual measured value.

If the measured SLI is 99.95%, the SLO is satisfied.

If the measured SLI is 99.8%, the SLO is not satisfied.

---

## 5.3 SLA: Service Level Agreement

An SLA is generally an external or contractual commitment.

It answers:

> What service level has the organization formally committed to customers?

An SLA may define:

- Availability target
- Measurement methodology
- Measurement window
- Maintenance exclusions
- Customer eligibility
- Reporting rules
- Service credits
- Exceptions
- Contractual remedies

An SLA should not be treated as merely another name for SLO.

An organization may intentionally maintain an internal SLO that is stricter than its external SLA.

For example:

**Internal SLO = 99.95%**

**External SLA = 99.9%**

The stricter internal target provides operational headroom before the contractual commitment is violated.

---

# 6. SLI → SLO → SLA Relationship

A useful conceptual hierarchy is:

**SLI → SLO → SLA**

The SLI measures actual behavior.

The SLO establishes an engineering target.

The SLA establishes an external commitment when applicable.

Example:

- SLI: successful checkout attempts / valid checkout attempts
- SLO: at least 99.95%
- SLA: at least 99.9% under defined contractual measurement rules

The Python script implements this relationship through explicit data structures and calculations.

---

# 7. Designing a Good Availability SLI

A good SLI should represent meaningful service behavior.

A request-based availability SLI can be written as:

**SLI = Good Requests / Valid Requests**

The most important question is often:

> What counts as a good request?

For an API, a simple definition could be:

- HTTP 2xx = good
- HTTP 3xx = good
- HTTP 5xx = bad

But real services require more precise rules.

Potentially relevant categories include:

- Authentication failures
- Invalid input
- Rate-limited requests
- Client cancellations
- Internal service failures
- Dependency failures
- Health checks
- Synthetic monitoring
- Internal administrative requests
- Load-test traffic

The denominator must be explicitly defined.

Changing the denominator can substantially change the reported SLI.

---

# 8. Time-Based vs Request-Based Availability

There are two important measurement approaches.

## Time-Based Availability

This measures eligible service time.

**Available Time / Eligible Time**

It is useful for systems with a meaningful continuously observable state.

## Request-Based Availability

This measures user operations.

**Good Requests / Valid Requests**

It is often more meaningful for APIs and transactional systems.

### Why the distinction matters

Consider an API that is reachable 99.99% of the time but returns HTTP 500 for 20% of checkout operations.

A network-level uptime monitor could report excellent uptime while customers experience a severe business outage.

Request-based SLIs can reveal this problem.

---

# 9. Partial Availability

Availability is not always binary at the whole-system level.

A service may have:

- Login working
- Search working
- Product pages working
- Checkout failing
- Recommendations unavailable

Calling the entire system simply "up" or "down" can hide important customer impact.

A mature availability model can measure critical user journeys independently.

Examples include:

- Login availability
- Search availability
- Checkout availability
- Payment authorization availability
- File-upload availability

This produces a more accurate representation of customer experience.

---

# 10. Error Budget

An error budget is the amount of unreliability permitted by an SLO.

The fundamental relationship is:

**Error Budget = 1 − SLO**

For a 99.9% SLO:

**Error Budget = 0.1%**

For 1,000,000 eligible requests:

**Allowed Bad Requests = 1,000,000 × 0.001 = 1,000**

If the service experiences 700 bad requests, 300 requests of budget remain.

If it experiences 1,500 bad requests, the budget is exhausted and the SLO is violated.

The Python script implements request-based and time-based error budgets.

---

# 11. Error Budget as Time

For a time-based SLO:

**Error Budget Time = Measurement Period × (1 − SLO)**

A 99.9% monthly SLO therefore provides a finite amount of downtime that can be consumed before the objective is missed.

This gives engineering teams a concrete way to reason about operational risk.

An outage is not merely "17 minutes of downtime." It consumes part of the service's reliability budget.

---

# 12. Error Budget and Engineering Decisions

Error budgets can connect reliability to development decisions.

If a service is comfortably within its error budget, the team may have room for:

- Feature releases
- Architecture changes
- Controlled experimentation
- Performance work

If the error budget is being consumed rapidly, the team may need to prioritize:

- Reliability fixes
- Incident prevention
- Capacity improvements
- Dependency remediation
- Safer deployments
- Recovery automation

The exact policy depends on organizational practice.

The important principle is that SLOs should influence engineering decisions rather than exist only as dashboards.

---

# 13. Burn Rate

Burn rate describes how quickly an error budget is being consumed relative to its sustainable rate.

Conceptually:

**Burn Rate = Observed Bad Fraction / Allowed Bad Fraction**

A burn rate of:

- 1× means budget is being consumed at the sustainable rate.
- 2× means budget is being consumed twice as quickly.
- 10× means budget is being consumed ten times as quickly.
- 20× indicates severe consumption.

High burn rates are useful for alerting because they identify incidents that can exhaust the error budget long before the measurement period ends.

---

# 14. Multi-Window Burn-Rate Alerting

A single measurement window can produce noisy results.

A more robust alerting strategy can examine multiple windows.

For example:

- A short window detects severe recent problems.
- A longer window confirms that the problem is sustained.

The Python script demonstrates a simplified multi-window burn-rate model.

Production systems can implement substantially more sophisticated alert policies.

---

# 15. Availability of a Single Component

If a component has availability `A`, its availability can be represented directly as a probability between 0 and 1.

Examples:

- 99% = 0.99
- 99.9% = 0.999
- 99.99% = 0.9999

This representation makes architectural calculations easier.

---

# 16. Serial Dependencies

Suppose a request requires both component A and component B.

If the components are independent and both must be available:

**System Availability = A × B**

For three required components:

**System Availability = A × B × C**

Example:

- API = 99.9%
- Database = 99.9%

Approximate combined availability:

**0.999 × 0.999 = 0.998001**

That is approximately:

**99.8001%**

This illustrates a fundamental distributed-system principle:

> Every required synchronous dependency can reduce end-to-end availability.

---

# 17. Why More Dependencies Can Hurt Availability

Suppose a critical user operation requires:

- Web service
- API service
- Authentication service
- Database
- Payment service

Even if each component has excellent availability, requiring all of them to work simultaneously can reduce the end-to-end probability of success.

This is why critical paths should avoid unnecessary synchronous dependencies.

Non-critical work can sometimes be moved to asynchronous processing.

---

# 18. Redundancy

Redundancy allows a system to continue operating when one component fails.

For two independent replicas with availability `A`:

**Redundant Availability = 1 − (1 − A)²**

For N replicas:

**Availability = 1 − (1 − A)^N**

The Python script calculates this relationship for multiple replicas.

For example, two independent components that are each 99% available provide approximately:

**1 − 0.01² = 99.99%**

This can be a dramatic improvement.

---

# 19. Independence Assumption

Redundancy calculations depend heavily on independence.

Two servers are not truly independent if they share:

- The same host
- The same power source
- The same network switch
- The same storage subsystem
- The same availability zone
- The same control plane
- The same faulty deployment
- The same external dependency

If a common dependency fails, all replicas may fail simultaneously.

Therefore, availability engineering focuses on **failure domains**, not merely replica count.

---

# 20. Failure Domains

A failure domain is a group of resources that can be affected by the same failure.

Typical levels include:

1. Process
2. Host
3. Rack
4. Availability zone
5. Region
6. Cloud provider or infrastructure provider

For example:

Two replicas on one physical machine do not provide meaningful host-level redundancy.

Two replicas on separate hosts provide stronger protection.

Replicas in different availability zones provide protection against certain zone-level failures.

Multi-region deployments provide protection against larger regional failures.

The larger the failure domain being protected against, the greater the cost and operational complexity.

---

# 21. Availability Trees

Complex architectures can be represented as logical availability trees.

For an AND relationship:

**System Available = A × B**

Every required component must be available.

For an OR relationship:

**System Available = 1 − (1 − A)(1 − B)**

At least one independent component must be available.

The Python script implements an `AvailabilityNode` structure supporting both AND and OR relationships.

This provides a simplified reliability-block-diagram style representation.

---

# 22. N+1 Redundancy

N+1 redundancy means a system has:

- N units required for normal operation
- One additional unit for redundancy

The extra unit can compensate for one failure while preserving required capacity.

Examples include:

- Application servers
- Power supplies
- Network links
- Compute nodes
- Storage components

Redundancy must consider both availability and capacity.

A backup instance that has no capacity to handle production traffic is not meaningful failover capacity.

---

# 23. Capacity and Availability

Capacity failures are availability failures when overload prevents successful service.

Potential bottlenecks include:

- CPU
- Memory
- Database connections
- Network bandwidth
- Storage I/O
- Thread pools
- File descriptors
- Queue capacity
- External API quotas

Horizontal scaling can improve availability, but it does not automatically solve every bottleneck.

A service may scale application servers while a database remains saturated.

---

# 24. Backpressure

Backpressure prevents uncontrolled accumulation of work.

Possible mechanisms include:

- Queues
- Rate limits
- Admission control
- Request rejection
- Load shedding
- Prioritization

Controlled rejection of low-priority work can protect critical operations.

For example, an e-commerce platform might preserve payment and checkout operations while temporarily disabling recommendation requests during severe overload.

---

# 25. Load Shedding

Load shedding deliberately rejects or disables lower-priority work when resources become constrained.

This is often preferable to allowing every request to become slow until the entire service collapses.

Typical priorities might be:

1. Payment
2. Checkout
3. Search
4. Recommendations

The exact ordering depends on business requirements.

Load shedding should be deliberate and observable.

---

# 26. Graceful Degradation

Graceful degradation means preserving important functionality while reducing or removing non-critical features.

Examples:

- Serve cached catalog information when recommendations are unavailable.
- Queue asynchronous processing instead of blocking the customer.
- Disable personalization while preserving search.
- Use cached data during temporary dependency failures.

The purpose is to preserve the most important customer journeys.

Graceful degradation can be a powerful availability technique because it reduces the number of dependencies that must succeed for the core service to remain useful.

---

# 27. Synchronous vs Asynchronous Dependencies

A synchronous dependency must respond before the current operation can complete.

An asynchronous dependency can process work later.

### Synchronous example

Checkout waits for an external recommendation service before completing.

If the recommendation service fails, checkout may fail.

### Asynchronous example

Order completion publishes an event for recommendation processing.

If recommendation processing fails, the order can still complete.

Asynchronous architecture can improve availability but introduces additional complexity:

- Eventual consistency
- Duplicate messages
- Ordering
- Retry handling
- Dead-letter processing
- State management
- Observability

---

# 28. Timeouts

Timeouts limit how long a request waits for a dependency.

Without appropriate timeouts, a failed dependency can cause:

- Thread exhaustion
- Connection exhaustion
- Queue growth
- Memory pressure
- Cascading failure

A timeout should reflect the actual end-to-end request budget.

For example, if a user-facing operation has a 2-second deadline, individual downstream calls cannot each independently consume multiple seconds.

Timeouts should be coordinated across the request chain.

---

# 29. Retries

Retries can improve availability for transient failures.

Examples:

- Temporary network error
- Connection reset
- Short-lived dependency overload

But retries can also reduce availability.

If a dependency is overloaded:

1. Dependency becomes slow.
2. Caller times out.
3. Caller retries.
4. Dependency receives more traffic.
5. Dependency becomes slower.
6. More callers retry.

This is a retry storm.

Retries should generally use:

- Limited retry counts
- Exponential backoff
- Jitter
- Deadlines
- Idempotency
- Retryable-error classification
- Circuit breakers where appropriate

---

# 30. Exponential Backoff

Exponential backoff increases the delay between retry attempts.

A simple sequence can be:

- Attempt 1: 1 second
- Attempt 2: 2 seconds
- Attempt 3: 4 seconds
- Attempt 4: 8 seconds

A maximum delay should normally be imposed.

The Python implementation also supports jitter.

---

# 31. Jitter

Without jitter, many clients can retry at approximately the same moment.

This can create synchronized retry spikes.

Jitter introduces controlled randomness into retry delays.

It reduces the probability that thousands of clients simultaneously issue their next retry.

---

# 32. Circuit Breakers

A circuit breaker protects a service from repeatedly calling an unhealthy dependency.

Common states are:

### CLOSED

Requests are allowed normally.

### OPEN

Requests are blocked because the dependency has exceeded failure thresholds.

### HALF_OPEN

A limited number of test requests are allowed to determine whether the dependency has recovered.

The Python script implements a simplified circuit breaker.

Production circuit breakers require more sophisticated handling of time, concurrency, failure types, and recovery.

---

# 33. Idempotency

Retries are safer when operations are idempotent.

An idempotent operation can be repeated without producing unintended duplicate effects.

Example:

Setting an account status to `ACTIVE` multiple times results in the same intended state.

A payment operation is more complicated.

If a client submits the same payment request twice because the first response was lost, the system must avoid accidentally charging the customer twice.

Idempotency keys are commonly used for this purpose.

The Python script implements a small idempotency-key store to demonstrate the principle.

---

# 34. Health Checks

Two common health-check concepts are:

## Liveness

Liveness asks:

> Is the process alive?

## Readiness

Readiness asks:

> Is this instance capable of safely receiving traffic?

A process may be alive while:

- Its database connection is broken.
- It is still starting.
- Required configuration is missing.
- A critical dependency is unavailable.
- It is overloaded.

Routing traffic to an alive but unready instance can increase the scope of an incident.

---

# 35. Deployment Strategies

Deployment strategy has a direct relationship with availability.

Common approaches include:

### Rolling Deployment

Instances are replaced gradually.

Advantages:

- Incremental rollout
- Lower immediate blast radius

Risks:

- Old and new versions coexist
- Compatibility problems can occur

### Blue/Green Deployment

Two environments exist:

- Current environment
- New environment

Traffic is switched after validation.

Advantages:

- Fast rollback
- Strong isolation

Costs:

- Additional infrastructure
- More complex environment management

### Canary Deployment

A small percentage of traffic is sent to the new version.

Metrics are observed before increasing traffic.

Canary deployments can reduce the blast radius of faulty releases.

---

# 36. Canary Validation

A canary can be evaluated using:

- Availability
- Error rate
- p95 latency
- p99 latency
- Resource consumption
- Dependency failures
- Business success metrics

A deployment should not be considered safe merely because processes are running.

Customer-visible service behavior should be part of the decision.

---

# 37. Rollback

A fast rollback mechanism can substantially reduce MTTR.

A deployment that introduces a severe error is less damaging when the organization can:

1. Detect the problem.
2. Stop rollout.
3. Roll back automatically or safely.
4. Verify recovery.

Rollback mechanisms should themselves be tested.

---

# 38. Availability and MTBF

MTBF means:

**Mean Time Between Failures**

It describes the average interval between failures according to a defined measurement methodology.

Increasing MTBF generally means reducing failure frequency.

Examples:

- Better testing
- Safer configuration
- Better dependency management
- Capacity planning
- Preventive maintenance

---

# 39. Availability and MTTR

MTTR generally refers to:

**Mean Time To Repair** or **Mean Time To Recover**

Reducing MTTR means restoring service faster.

Common approaches include:

- Automated failover
- Automated rollback
- Good monitoring
- Clear runbooks
- Incident response procedures
- Health checks
- Operational automation

---

# 40. MTBF and MTTR Relationship

A simplified steady-state relationship is:

**Availability ≈ MTBF / (MTBF + MTTR)**

This equation illustrates an important principle.

Availability can improve through:

- Increasing MTBF
- Decreasing MTTR

A system does not necessarily need to eliminate every failure to achieve high availability.

Rapid recovery can compensate for some level of unavoidable failure.

---

# 41. Availability vs Reliability

Availability and reliability are related but distinct.

### Availability

Focuses on whether the service is operational and usable.

### Reliability

Focuses on the probability of operating correctly without failure over a specified period.

A service can experience frequent short failures and still maintain high availability if recovery is extremely fast.

A service can also fail rarely but remain unavailable for a very long time after each failure.

Therefore failure frequency and recovery time should both be considered.

---

# 42. Availability vs Durability

Availability asks:

> Can I use the system or data now?

Durability asks:

> Will the data survive failures?

A storage service can be highly durable but temporarily unavailable.

A service can remain reachable while data is lost or corrupted.

These properties must be designed and measured separately.

---

# 43. Availability vs Performance

A system can be technically available while being extremely slow.

For example:

- HTTP request succeeds
- Response arrives after 60 seconds
- Customer abandons the operation

An uptime monitor may count the request as successful.

The customer may consider it a failure.

This is why availability should normally be accompanied by latency SLIs.

---

# 44. Latency SLIs

Common latency percentiles include:

- p50
- p90
- p95
- p99
- p99.9

For example:

**99% of requests complete within 300 ms**

This can be represented as a latency SLI.

Latency objectives should be measured independently from availability when the service experience requires it.

---

# 45. Tail Latency

Average latency can hide extreme delays.

Suppose 99% of requests take 100 ms and 1% take 30 seconds.

The average alone may not communicate the user experience accurately.

Tail percentiles such as p95 and p99 reveal slow requests more clearly.

This is especially important for distributed systems because one slow dependency can affect an entire request path.

---

# 46. Composite SLOs

A service can have several objectives:

- Availability ≥ 99.9%
- 99% of requests under 300 ms
- Correctness ≥ 99.99%

Meeting one objective does not imply that all objectives are satisfied.

An API can have:

- Excellent availability
- Poor latency
- Incorrect data

Therefore a complete service-level framework can require multiple SLIs and SLOs.

---

# 47. Correctness

Correctness is distinct from availability.

An API returning HTTP 200 with incorrect data may be available according to a simplistic status-code SLI while failing its business purpose.

Correctness SLIs can be especially important for:

- Payments
- Financial calculations
- Inventory
- Authentication
- Data processing
- Order management

The definition of "good" should reflect the actual operation.

---

# 48. Maintenance Windows

Availability measurements must explicitly define maintenance treatment.

Possible policies include:

1. Count all maintenance as downtime.
2. Exclude approved maintenance.
3. Exclude maintenance only when contractual conditions are satisfied.
4. Measure customer-visible availability regardless of maintenance.

The correct policy depends on the service and contractual arrangement.

The key requirement is transparency and consistency.

Maintenance should not be used as an unrestricted mechanism for hiding avoidable failures.

---

# 49. Overlapping Incidents

Overlapping downtime must not be counted twice.

Consider:

- Incident A: 10:00–10:20
- Incident B: 10:10–10:30

Simply adding durations produces 40 minutes.

The actual affected interval is:

**10:00–10:30 = 30 minutes**

The Python script implements interval merging to calculate the union of downtime.

This is an important implementation detail for time-based availability systems.

---

# 50. Request-Based Error Rate

Error rate is:

**Error Rate = Failed Requests / Total Requests**

If:

- Total requests = 2,000,000
- Failed requests = 1,200

Then:

**Error Rate = 0.06%**

And assuming all non-failed requests are good:

**Availability = 99.94%**

Error rate and availability are complementary under a simple binary success/failure model.

---

# 51. Precision and Rounding

Availability values are extremely close to 100%.

Poor rounding can hide meaningful differences.

For example:

- 99.90%
- 99.99%
- 99.999%

should not all be displayed simply as "100%".

Operational systems should retain enough precision to distinguish the target from the actual measurement.

---

# 52. Regional Availability

Global availability can hide regional problems.

A service might have:

- India: 99.95%
- Europe: 99.99%
- North America: 99.85%

A global average may still appear healthy.

Regional SLIs are useful for detecting localized incidents.

Aggregation can be weighted by request volume when the SLO is intended to represent the average customer request.

---

# 53. Weighted vs Unweighted Availability

Suppose:

- Search: 1,000,000 requests at 99.9%
- Checkout: 10,000 requests at 99.99%

An unweighted average treats both endpoints equally.

A request-weighted calculation gives much more influence to search because it handles far more traffic.

Neither approach is automatically correct.

The aggregation method should match the SLO's intended meaning.

---

# 54. Customer-Centric Availability

Infrastructure health is not identical to customer experience.

Examples:

- Server is alive but login fails.
- DNS works but checkout fails.
- Database is healthy but payment authorization is broken.
- API returns 200 but produces incorrect results.
- Requests eventually succeed but take too long.

A mature availability program therefore measures important customer journeys.

---

# 55. User-Journey SLIs

A user journey may be represented as:

**Successful Checkout Attempts / Valid Checkout Attempts**

This is often more useful to a business than a generic "API uptime" metric.

Possible user journeys include:

- Login
- Search
- Checkout
- Payment
- File upload
- Order creation
- Message delivery

Critical journeys deserve explicit availability definitions.

---

# 56. Dependency Availability

A service's availability can be constrained by its dependencies.

Consider:

**Checkout → Payment API**

If payment authorization is mandatory for checkout, a payment-service outage can directly become a checkout outage.

The caller should therefore define:

- Timeout
- Retry policy
- Failure classification
- Fallback
- Circuit breaker
- Customer-visible behavior

Dependency contracts should be considered when setting end-to-end SLOs.

---

# 57. Dependency Failure Strategies

Common strategies include:

### Fail Fast

Return an error quickly rather than waiting indefinitely.

### Retry

Attempt the operation again for transient failures.

### Fallback

Use an alternative implementation or source.

### Cache

Serve previously stored data.

### Queue

Accept work and process it asynchronously.

The appropriate strategy depends on the operation.

---

# 58. Database Availability

Databases are often critical availability dependencies.

Techniques include:

- Replication
- Primary/replica architectures
- Automatic failover
- Multi-zone deployment
- Read replicas
- Backups
- Point-in-time recovery
- Sharding

Replication, availability, and durability are not identical.

A replicated database can still experience:

- Failover problems
- Network partitions
- Replication lag
- Quorum failures
- Shared-storage failures
- Configuration errors

---

# 59. Quorum

A quorum is the minimum number of participating replicas or votes required to make a distributed decision.

A common majority relationship is:

**Required Votes > Number of Replicas / 2**

For three replicas, a majority requires two votes.

For five replicas, a majority requires three.

Quorum choices influence:

- Availability
- Consistency
- Failure tolerance
- Write behavior
- Read behavior

The exact model depends on the distributed system.

---

# 60. Consistency and Availability Trade-Offs

Distributed systems can face difficult trade-offs during network partitions.

A system may need to decide whether to:

- Continue serving requests with potentially stale data.
- Reject operations until stronger consistency can be established.

The appropriate choice depends on business semantics.

For example:

Stale product recommendations may be acceptable.

Stale financial balances may not be.

Therefore availability cannot be evaluated independently from correctness and consistency requirements.

---

# 61. CAP-Style Reasoning

Distributed-system discussions often use the CAP theorem as a conceptual framework.

The central concern is behavior during network partitions.

During a partition, systems face trade-offs between continued availability and strong consistency guarantees.

Real systems are more nuanced than simply assigning one permanent label such as "available" or "consistent."

Different operations can have different requirements.

---

# 62. Failover

Failover moves service operation from a failed component or environment to another.

Examples:

- Primary database → standby database
- Instance A → instance B
- Availability Zone A → Availability Zone B
- Region A → Region B

Failover can significantly reduce MTTR.

But failover itself can fail.

---

# 63. Failover Pitfalls

Common problems include:

- Incorrect health checks
- DNS caching
- Insufficient standby capacity
- Replication lag
- Configuration differences
- Missing secrets
- Network isolation
- Broken automation
- Unreachable backup environment
- Untested procedures

Failover should be tested rather than assumed.

---

# 64. Failure Testing

Availability testing can include:

- Instance failure
- Database failure
- Dependency timeout
- Network failure
- Availability-zone failure
- Deployment failure
- Capacity overload
- Region failure
- Recovery testing

The goal is to validate both failure detection and recovery behavior.

A documented recovery procedure that has never been tested remains an assumption.

---

# 65. RTO

RTO means:

**Recovery Time Objective**

It describes the targeted maximum time to restore service after a disruptive event.

Example:

**RTO = 15 minutes**

This means the recovery strategy targets restoration within approximately 15 minutes under the defined conditions.

RTO is related to availability but is not the same as an SLO.

---

# 66. RPO

RPO means:

**Recovery Point Objective**

It describes the maximum acceptable amount of data loss measured in time.

Example:

**RPO = 5 minutes**

This means the organization targets losing no more than approximately five minutes of data under the defined recovery strategy.

RPO is primarily associated with data recovery and disaster recovery.

---

# 67. Availability vs RTO

Availability measures the service level across a measurement period.

RTO specifies a recovery target for a disruptive event.

A system can have a strong monthly availability target and still have a separate disaster-recovery RTO.

Both are useful but measure different dimensions.

---

# 68. Observability

Availability engineering depends on observability.

Three common observability pillars are:

- Metrics
- Logs
- Traces

### Metrics

Useful for:

- Error rates
- Availability
- Latency
- Saturation
- Queue depth
- Capacity
- Dependency failures

### Logs

Useful for understanding individual events.

### Traces

Useful for following a request through distributed services.

Metrics are especially important for long-term SLO calculations and alerting.

---

# 69. Synthetic Monitoring

Synthetic monitoring generates controlled requests to test a service.

A synthetic probe might:

1. Open the application.
2. Authenticate.
3. Search for an item.
4. Execute a test transaction.
5. Measure latency.
6. Record success or failure.

Synthetic monitoring can detect problems before normal user traffic exposes them.

It should complement, not replace, real customer-oriented SLIs.

---

# 70. Alerting

Availability alerts should be actionable.

Poor alerting can produce:

- False positives
- Alert fatigue
- Ignored incidents
- Operational overload

Useful alert conditions can include:

- Severe SLO burn
- Rapid error-budget consumption
- Critical user-journey failure
- Dependency outage
- Dangerous saturation
- Sustained regional failure

A dashboard is informational.

An alert should generally indicate that someone or something needs to act.

---

# 71. Alert Fatigue

Alert fatigue occurs when operators receive too many low-value alerts.

If every minor fluctuation generates an alert, important incidents can become difficult to distinguish.

Alerting should focus on conditions that represent meaningful customer impact or imminent reliability risk.

---

# 72. Deployment Risk and Availability

Software deployments are a major source of availability incidents.

Risk can be reduced with:

- Automated testing
- Canary releases
- Rolling deployments
- Blue/green deployment
- Feature flags
- Automated rollback
- Health checks
- SLO-aware release policies

The objective is to reduce blast radius and recovery time.

---

# 73. Availability and Security

Security incidents can directly become availability incidents.

Examples:

- DDoS attacks
- Resource exhaustion
- Ransomware
- Malicious configuration changes
- Credential compromise
- Supply-chain attacks
- Unauthorized deletion

Availability design should therefore include appropriate:

- Authentication
- Authorization
- Rate limiting
- Resource quotas
- Network controls
- Backups
- Recovery procedures
- Secrets management
- Auditing

Security controls can also introduce availability risks if they depend on unavailable systems or are incorrectly configured.

---

# 74. Rate Limiting

Rate limiting controls how much traffic a client can generate.

It can protect services from:

- Abuse
- Accidental traffic spikes
- Resource exhaustion
- Retry storms

A simple fixed-window limiter can enforce a maximum number of requests during a period.

Production systems may use more sophisticated algorithms such as token buckets or distributed rate limiting.

---

# 75. Availability and Backpressure

Backpressure prevents the system from accepting unlimited work.

Possible actions include:

- Queue requests
- Reject excess traffic
- Rate-limit clients
- Shed low-priority load
- Prioritize critical operations

The objective is to prevent overload from becoming a cascading failure.

---

# 76. Cascading Failures

A cascading failure occurs when one failure causes additional components to fail.

A common sequence is:

1. Dependency becomes slow.
2. Requests wait longer.
3. Threads and connections accumulate.
4. Resources become exhausted.
5. Caller becomes overloaded.
6. More requests fail.
7. Dependent services also become unhealthy.

Timeouts, backpressure, circuit breakers, bounded retries, and load shedding can reduce this risk.

---

# 77. End-to-End Availability

End-to-end availability considers the complete customer path.

For example:

**Web → API → Database → Payment Service**

If every component is required and independent:

**End-to-End Availability ≈ Web × API × Database × Payment**

This can produce a lower result than any individual component.

The architecture should therefore minimize unnecessary dependencies on critical paths.

---

# 78. Critical Path Design

A critical path is the sequence of operations required to complete an important customer operation.

For high-value workflows, the critical path should be:

- Simple
- Observable
- Capacity-aware
- Fault-tolerant
- Protected against dependency failure
- Recoverable

Non-critical operations should be candidates for asynchronous execution or graceful degradation.

---

# 79. Production Availability Architecture

A high-availability production architecture commonly considers:

- Multiple application instances
- Load balancing
- Health checks
- Multiple failure domains
- Database replication
- Dependency isolation
- Timeouts
- Bounded retries
- Circuit breakers
- Caching
- Queue-based asynchronous processing
- Capacity headroom
- Load shedding
- Controlled deployments
- Rollback
- Monitoring
- Alerting
- Incident response
- Disaster recovery

The exact architecture depends on the target SLO and business requirements.

---

# 80. Availability Is Not Free

Higher availability generally requires more:

- Infrastructure
- Replication
- Monitoring
- Testing
- Automation
- Operational expertise
- Complexity
- Network capacity
- Storage
- Deployment discipline

Moving from 99.9% to 99.99% reduces allowed unavailability by a factor of ten.

The final level of availability should therefore be justified by business value.

---

# 81. Business Criticality

Different features may legitimately have different availability objectives.

For example:

| Service | Example Target |
|---|---:|
| Marketing content | 99.0% |
| Internal analytics | 98.0% |
| Search | 99.9% |
| Checkout | 99.99% |
| Payment authorization | 99.99% or stricter |

These values are illustrative rather than universal requirements.

The correct target depends on:

- Revenue impact
- Customer expectations
- Safety
- Regulatory requirements
- Operational cost
- Recovery alternatives
- Business criticality

---

# 82. SLA, SLO, and Cost

A high availability target should be economically justified.

For example, moving from 99.99% to 99.999% may require:

- Additional regions
- More replicas
- More automation
- More operational staffing
- More complex testing
- More sophisticated failover
- Higher infrastructure cost

System design is therefore a trade-off between:

- Availability
- Cost
- Complexity
- Performance
- Consistency
- Security
- Operability

---

# 83. Common Availability Anti-Patterns

Important anti-patterns include:

1. Measuring only ping or TCP reachability.
2. Ignoring application-level failures.
3. Using averages that hide tail behavior.
4. Manipulating the denominator to improve reported availability.
5. Ignoring partial outages.
6. Counting overlapping incidents twice.
7. Assuming replicas have independent failures.
8. Using unlimited retries.
9. Using retries without backoff.
10. Deploying without rollback.
11. Relying on untested failover.
12. Alerting on every small fluctuation.
13. Ignoring regional differences.
14. Ignoring capacity limits.
15. Treating technical uptime as equivalent to customer success.

---

# 84. Best Practices

Strong availability engineering generally follows these principles:

- Define customer-oriented SLIs.
- Define the denominator explicitly.
- Establish measurable SLOs.
- Keep SLA rules separate from internal SLO policy.
- Track error budgets.
- Monitor SLO burn rate.
- Measure critical user journeys.
- Separate availability from latency and correctness.
- Use redundancy across meaningful failure domains.
- Implement health checks carefully.
- Use bounded timeouts.
- Use controlled retries.
- Add exponential backoff and jitter.
- Use idempotency for retry-sensitive operations.
- Use circuit breakers where appropriate.
- Maintain capacity headroom.
- Use load shedding when necessary.
- Use graceful degradation for non-critical features.
- Support safe rollback.
- Test failover.
- Test recovery.
- Monitor dependencies.
- Keep incident procedures current.

---

# 85. SLO Design Checklist

A well-defined SLO should answer:

- What is being measured?
- What is a good event?
- What is a bad event?
- Which events are eligible?
- What is excluded?
- What is the denominator?
- What is the measurement window?
- What is the target?
- Does the SLI represent customer experience?
- Can the measurement be trusted?
- What action should occur when the error budget is exhausted?

If these questions cannot be answered, the SLO is probably underspecified.

---

# 86. SLA Design Considerations

An SLA generally needs explicit rules concerning:

- Target
- Measurement period
- Measurement methodology
- Eligible traffic
- Maintenance
- Exclusions
- Customer eligibility
- Reporting
- Remedies or credits
- Exceptions

An SLA is an external commitment, so ambiguity in the measurement methodology can create operational and contractual problems.

---

# 87. Incident Management and Availability

An incident directly affects availability when customers cannot successfully use the service according to the SLI definition.

A practical response sequence is:

1. Detect impact.
2. Confirm scope.
3. Declare appropriate severity.
4. Stop harmful changes.
5. Reduce blast radius.
6. Restore service.
7. Communicate status.
8. Verify recovery.
9. Measure SLO impact.
10. Conduct a post-incident review.
11. Implement corrective actions.

Incident response is part of availability engineering because recovery speed directly affects downtime.

---

# 88. Detection Time, Mitigation Time, and Recovery Time

Incident analysis can separate:

### Detection Time

How long it takes to discover the problem.

### Mitigation Time

How long it takes to stop or reduce customer impact.

### Recovery Time

How long it takes to restore normal operation.

Improving each stage can reduce total customer impact.

---

# 89. Production Readiness

A service targeting meaningful availability should have evidence for:

- Defined SLI
- Documented SLO
- Understood SLA requirements
- Error-budget calculations
- Monitoring
- Actionable alerts
- Health checks
- Timeouts
- Retry policies
- Dependency failure handling
- Capacity planning
- Rollback capability
- Backup and recovery
- Failover testing
- Incident response
- User-journey monitoring

A high availability number without these supporting mechanisms is not sufficient evidence of resilience.

---

# 90. Measurement Uncertainty

An observed availability value is based on measured events.

Sample size matters.

One failed request out of:

- 100 requests = 99%
- 1,000 requests = 99.9%
- 10,000 requests = 99.99%

Small samples can therefore produce large percentage swings.

Availability measurement should use appropriate traffic volume and measurement windows.

---

# 91. Statistical and Operational Interpretation

An SLI is an observation, not an abstract guarantee.

For meaningful interpretation, consider:

- Sample size
- Traffic patterns
- Measurement window
- Regional distribution
- Endpoint distribution
- Customer segments
- Incident duration
- Failure correlation
- Exclusions

A single number without its measurement definition can be misleading.

---

# 92. Availability Review

A system-design availability review should ask:

### Measurement

- What is the SLI?
- Does it measure customer success?
- Is the denominator correct?

### Target

- What is the SLO?
- Why was that target selected?
- What is the error budget?

### Architecture

- Which components are required?
- Which components are redundant?
- What are the failure domains?
- Are there common dependencies?

### Operations

- How is failure detected?
- How is recovery performed?
- How fast is rollback?
- Has failover been tested?

### Capacity

- What happens during traffic spikes?
- What is the saturation point?
- Is there capacity headroom?

### Dependencies

- What happens when a dependency is slow?
- What happens when it is unavailable?
- Are timeouts bounded?
- Are retries controlled?

### Customer Experience

- What does the customer see?
- Can the service degrade gracefully?
- Which user journeys are critical?

---

# 93. Key Mathematical Relationships

## Time-Based Availability

**Availability = (Total Time − Downtime) / Total Time**

## Request-Based Availability

**Availability = Good Requests / Valid Requests**

## Unavailability

**Unavailability = 1 − Availability**

## Error Budget

**Error Budget = 1 − SLO**

## Allowed Bad Requests

**Allowed Bad Requests = Eligible Requests × Error Budget**

## Serial Availability

For required independent components:

**System Availability = A₁ × A₂ × ... × Aₙ**

## Independent Redundancy

For N independent replicas:

**System Availability = 1 − (1 − A)ᴺ**

## Approximate MTBF/MTTR Relationship

**Availability ≈ MTBF / (MTBF + MTTR)**

## Burn Rate

**Burn Rate = Observed Bad Fraction / Allowed Bad Fraction**

These formulas are implemented directly in the Python script.

---

# 94. Important Distinctions

| Concept | Meaning |
|---|---|
| Uptime | Time the service is considered operational |
| Downtime | Time the service is considered unavailable |
| Availability | Proportion of eligible service that succeeds |
| SLI | Measurement |
| SLO | Internal target |
| SLA | External/contractual commitment |
| Error Budget | Allowed unreliability |
| Burn Rate | Speed of error-budget consumption |
| Reliability | Likelihood of continued correct operation |
| Durability | Ability to preserve data |
| MTBF | Mean time between failures |
| MTTR | Mean time to repair/recover |
| RTO | Target recovery time |
| RPO | Target data-loss interval |
| Latency | Time required to complete an operation |
| Correctness | Whether the result is semantically correct |

---

# 95. Practical Example

Consider an e-commerce checkout API with:

- 10,000,000 valid checkout attempts
- 99.95% SLO
- 6,000 failed attempts

The allowed error budget is:

**1 − 0.9995 = 0.0005**

Allowed failures:

**10,000,000 × 0.0005 = 5,000**

Actual failures:

**6,000**

Therefore the request-based SLO is violated.

The example also demonstrates why availability must be measured according to the actual business operation.

A separate time-based uptime SLI might still show a strong value.

This means one service can satisfy one SLO while violating another.

---

# 96. Practical Architecture Example

Consider:

**Checkout → Order API → Database → Payment Service**

If all four components are synchronously required, their availabilities interact multiplicatively under a simplified independent-failure model.

This can create a lower end-to-end availability than the availability of any individual component.

Possible design improvements include:

- Redundant application instances
- Database failover
- Payment timeout
- Controlled retries
- Idempotency keys
- Circuit breaking
- Asynchronous processing where appropriate
- Graceful degradation for non-critical features
- Regional redundancy
- Capacity headroom
- Controlled deployments

The correct architecture depends on the required SLO and business semantics.

---

# 97. Security and Availability Relationship

Security and availability are not independent concerns.

A denial-of-service attack can create resource exhaustion.

A compromised administrative account can cause destructive configuration changes.

A ransomware incident can make systems unavailable.

A supply-chain compromise can introduce faulty software.

Availability planning should therefore consider security controls and recovery mechanisms together.

---

# 98. Implementation Considerations

The Python script demonstrates several implementation details that are easy to overlook:

- Input validation for availability values
- Handling zero-length measurement windows
- Preventing negative downtime
- Preventing downtime from exceeding total time
- Defining valid requests
- Tracking good and total events
- Calculating error budgets
- Merging overlapping downtime intervals
- Handling multiple failure domains conceptually
- Calculating serial dependencies
- Calculating redundant architectures
- Modeling retries
- Modeling circuit breakers
- Modeling idempotency
- Modeling capacity
- Modeling rate limits
- Measuring user journeys
- Testing calculations with `unittest`

These details demonstrate that availability is not merely a formula. It is also a measurement and implementation problem.

---

# 99. Edge Cases

Important edge cases include:

### Zero Measurement Time

Availability cannot be meaningfully calculated when the measurement period is zero.

### Negative Downtime

Negative downtime is invalid.

### Downtime Greater Than Total Time

This indicates invalid measurement data.

### No Valid Requests

A request-based SLI cannot be calculated when the denominator is zero.

### Overlapping Incidents

Intervals must be merged to prevent double-counting.

### Shared Failure Domains

Redundant components may fail together.

### No Remaining Error Budget

The budget is exhausted and reliability work may need to take priority.

### Small Sample Size

Observed availability may be statistically unstable.

### Partial Outage

A service may remain operational for some endpoints while critical operations fail.

### Slow Success

An HTTP success may still be unacceptable if latency violates the service objective.

---

# 100. Production Design Principles

The most important principles demonstrated by the script are:

1. Availability must be explicitly defined.
2. Customer-facing SLIs are usually more useful than infrastructure-only indicators.
3. SLOs must be measurable.
4. SLAs and SLOs are not identical.
5. Error budgets turn availability targets into operational budgets.
6. More nines require disproportionately stronger engineering.
7. Serial dependencies reduce end-to-end availability.
8. Redundancy helps only when failure domains are sufficiently independent.
9. Retries can improve transient-failure recovery but can also create cascading failures.
10. Timeouts prevent indefinite dependency blocking.
11. Circuit breakers can isolate unhealthy dependencies.
12. Idempotency makes retries safer.
13. Graceful degradation can preserve critical functionality.
14. Capacity planning is part of availability engineering.
15. Health checks must distinguish liveness from readiness.
16. Deployment safety directly affects availability.
17. Failover must be tested.
18. Observability must support customer-oriented measurement.
19. Incident response affects MTTR.
20. Availability targets should be justified by business value.

---

# 101. Conceptual Model

A useful mental model is:

**Availability**
→ measured through an **SLI**

**SLI**
→ evaluated against an **SLO**

**SLO**
→ produces an **error budget**

**Error budget**
→ monitored through **burn rate**

**Burn rate**
→ influences **engineering and operational decisions**

Those decisions are implemented through:

- Redundancy
- Failure-domain isolation
- Capacity planning
- Timeouts
- Retries
- Backoff
- Circuit breakers
- Caching
- Queues
- Load shedding
- Graceful degradation
- Safe deployment
- Rollback
- Failover
- Observability
- Incident response

This connects availability mathematics to actual system architecture and production operations.
