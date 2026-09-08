# Latency and Throughput

## Introduction

Latency and throughput are fundamental performance concepts used to evaluate software systems, distributed systems, web services, databases, message-processing systems, networks, data pipelines, and computing infrastructure.

The two concepts are closely related but measure different properties.

**Latency** measures how long one operation takes.

**Throughput** measures how much work a system completes during a unit of time.

A system can have low latency and low throughput, high latency and high throughput, or a combination of both depending on workload, concurrency, capacity, queueing, resource utilization, and system architecture.

This study file examines latency and throughput from basic definitions through queueing behavior, concurrency, capacity planning, bottlenecks, tail latency, load testing, caching, backpressure, scaling, production monitoring, and performance debugging.

---

# Fundamental Concepts

## Latency

Latency is the time required for an operation to complete.

Examples include:

- Time required for a web server to respond to a request.
- Time required for a database query.
- Time required to process a message.
- Time required to read data from storage.
- Time required for a network packet to travel through a system.

Latency is commonly measured in:

- Nanoseconds
- Microseconds
- Milliseconds
- Seconds

For interactive systems, milliseconds are commonly used.

A request taking 120 milliseconds has a latency of 120 ms.

Latency can be measured at different boundaries. Client-observed latency can include network communication and server processing, while server-side latency may measure only the time spent inside an application.

---

## Response Time

Response time is the total time observed from the beginning of a request until completion.

A simplified model is:

    Response Time = Waiting Time + Service Time

A more realistic distributed system can include:

    Response Time =
        Queue Waiting
        + Network Delay
        + Application Processing
        + Database Processing
        + External Dependency Delay
        + Serialization
        + Response Transfer

The script models response time as a collection of components using the `ResponseTimeBreakdown` data class.

This decomposition is important because reducing application CPU time does not necessarily reduce end-to-end response time if the dominant delay comes from a database, queue, network, or external service.

---

## Service Time

Service time is the amount of time during which a resource actively processes a request.

Examples:

- CPU computation time.
- Database execution time.
- Time required to write data to storage.
- Time spent executing application logic.

Service time does not necessarily include queue waiting.

A request can have a service time of 10 ms but a response time of 500 ms if it waits for 490 ms before processing begins.

---

## Waiting Time

Waiting time is the time spent waiting for access to a resource.

Requests can wait for:

- CPU resources
- Database connections
- Application workers
- Threads
- Network connections
- Disk access
- Locks
- Queue consumers

Waiting time is one of the main reasons latency increases rapidly when systems approach saturation.

---

# Throughput

## Definition

Throughput is the amount of completed work per unit of time.

The basic formula is:

    Throughput = Completed Work / Elapsed Time

Examples include:

- Requests per second
- Transactions per second
- Messages per second
- Jobs per hour
- Records processed per minute
- Bytes transferred per second

The Python script provides the `calculate_throughput` function to calculate throughput from completed operations and elapsed time.

---

## Requests per Second

Requests per second, commonly abbreviated as RPS, is a throughput metric.

For example:

    5,000 completed requests / 2.5 seconds
    = 2,000 requests per second

RPS is useful when requests have similar computational cost.

RPS alone can be misleading when request sizes or complexity vary substantially.

A system handling 1,000 large data-processing requests per second may process more bytes or consume more resources than another system handling 10,000 very small requests per second.

The script therefore also demonstrates data throughput based on bytes processed per second.

---

# Processing Capacity

## Definition

Capacity is the maximum amount of work a system can sustainably process.

A simple ideal estimate is:

    Capacity ≈ Number of Workers / Average Service Time

If eight workers each require approximately 25 milliseconds to process one request:

    Service time = 0.025 seconds

One worker can ideally process:

    1 / 0.025 = 40 requests/second

Eight independent workers can ideally process:

    8 × 40 = 320 requests/second

Real capacity is usually lower because of:

- Coordination overhead
- Resource contention
- Uneven request distribution
- Database limits
- Network delays
- Garbage collection
- Lock contention
- Context switching
- External dependencies

Capacity should therefore be interpreted as a system property rather than simply a multiplication of worker count and average processing speed.

---

# Latency and Throughput Are Different Metrics

Latency measures the duration of individual operations.

Throughput measures aggregate completed work.

Consider a service where every request requires approximately 100 milliseconds of processing.

One worker can ideally complete:

    1 / 0.1 = 10 requests per second

Ten independent workers can ideally complete:

    10 / 0.1 = 100 requests per second

The latency of one request can remain close to 100 milliseconds while aggregate throughput increases tenfold.

Concurrency can therefore increase throughput without reducing the intrinsic service time of an individual request.

---

# Measuring Latency

## Appropriate Timers

The script compares `time.time()` and `time.perf_counter()`.

`time.time()` represents wall-clock time and may be affected by changes to the system clock.

`time.perf_counter()` is a high-resolution monotonic timer intended for measuring durations.

For application benchmarking, `time.perf_counter()` is generally preferable.

---

## Latency Distribution

A single average latency value does not describe the full user experience.

Suppose:

- 990 requests take 10 ms.
- 10 requests take 1,000 ms.

The average latency is significantly larger than the latency experienced by most requests, but the average still does not fully communicate the existence of very slow requests.

Latency should therefore be examined as a distribution.

The script calculates:

- Minimum latency
- Mean latency
- Median or p50
- p90
- p95
- p99
- Maximum latency

---

# Percentiles and Tail Latency

## p50

p50 is the median.

Approximately half of observations are at or below this value.

---

## p90

p90 represents a value at or below which approximately 90% of observations fall.

---

## p95

p95 represents a high-percentile latency threshold covering approximately 95% of observations.

---

## p99

p99 represents the tail of the latency distribution.

A high p99 can indicate that a relatively small percentage of requests experience severe delays.

Common causes include:

- Garbage collection
- Lock contention
- Storage pauses
- Database contention
- Network delays
- Queue buildup
- Cache misses
- External service delays

The script implements percentile calculation using sorted data and linear interpolation.

---

# Why Average Latency Is Not Enough

An average can hide rare but severe events.

A system can report:

    Average latency: 20 ms

while also having:

    p99 latency: 2,000 ms

This means a small percentage of requests may experience delays that are unacceptable for the intended application.

For interactive applications, tail latency is often more important than average latency.

---

# Histograms

A histogram groups measurements into ranges.

For latency data, histograms can reveal:

- Multiple performance modes
- Long tails
- Outliers
- Clustering
- Periodic slow behavior

The script implements a simple histogram function that groups numeric measurements into configurable buckets.

---

# Sequential Processing

In sequential processing, one worker processes one request at a time.

If five requests each require approximately 50 ms:

    Total execution time ≈ 250 ms

Ideal throughput is approximately:

    5 requests / 0.25 seconds
    = 20 requests/second

Sequential systems are simple but can underutilize resources when requests spend significant time waiting for I/O.

---

# Concurrency

Concurrency allows multiple tasks to make progress during overlapping periods.

Concurrency can improve throughput when tasks spend time waiting.

A common example is network or storage I/O.

While one request waits for a response, another request may perform useful work.

The script demonstrates concurrency using `ThreadPoolExecutor`.

---

# CPU-Bound and I/O-Bound Work

## CPU-Bound Work

CPU-bound work spends most of its time performing computation.

Examples:

- Numerical algorithms
- Compression
- Encryption
- Image processing
- Large-scale data transformations

Adding Python threads does not necessarily increase CPU-bound performance in standard CPython because of the Global Interpreter Lock.

---

## I/O-Bound Work

I/O-bound work spends substantial time waiting for:

- Network communication
- Database responses
- Disk operations
- External services

Concurrency can improve throughput because other tasks can run while one task waits.

The script compares sequential and concurrent execution of simulated I/O work.

---

# Queueing

Queues form when work arrives faster than available resources can immediately process it.

A queue can be represented as:

    Incoming Requests
            |
            v
          Queue
            |
            v
         Workers
            |
            v
       Completed Work

Queueing is not inherently bad.

Queues can absorb short traffic bursts.

Persistent queue growth is a sign that incoming work may exceed sustainable processing capacity.

---

# Single-Server Queue Simulation

The script models a FIFO queue with one worker.

For each request:

    Start Time =
        max(Request Arrival Time, Server Available Time)

Completion time is:

    Completion Time =
        Start Time + Service Time

Waiting time is:

    Waiting Time =
        Start Time - Arrival Time

Response time is:

    Response Time =
        Completion Time - Arrival Time

The simulation demonstrates how requests arriving faster than the server can process them experience increasing waiting times.

---

# Queue Growth During Overload

Suppose:

    Arrival rate = 120 requests/second
    Service rate = 100 requests/second

The system receives 20 more requests per second than it can complete.

The queue therefore grows approximately by:

    20 requests/second

If the overload continues, response times can increase because each request waits behind a growing backlog.

An unbounded queue can eventually cause memory exhaustion.

---

# Multi-Server Processing

Adding workers can reduce queue waiting and increase capacity.

The script simulates multiple workers and assigns requests to the worker that becomes available first.

This illustrates an important principle:

Adding capacity can reduce queueing delay when the workload can be distributed effectively.

Scaling is not always linear because workers may share constrained resources.

---

# Little's Law

Little's Law is one of the most useful relationships in performance analysis.

The law is:

    L = λW

Where:

- `L` is the average number of items in the system.
- `λ` is the average throughput or arrival rate.
- `W` is the average time spent in the system.

Rearranging:

    W = L / λ

Example:

    L = 200 requests
    λ = 100 requests/second

Then:

    W = 200 / 100
    W = 2 seconds

Little's Law provides a useful way to connect concurrency, throughput, and latency.

---

# Utilization

Utilization measures how much of a resource's capacity is currently used.

A simple formula is:

    Utilization = Arrival Rate / Service Capacity

If a resource can process 1,000 requests per second and receives 800:

    Utilization = 800 / 1,000
    Utilization = 80%

As utilization approaches 100%, queueing delay can increase sharply.

A system operating permanently at maximum theoretical utilization has little capacity to absorb:

- Traffic bursts
- Uneven workloads
- Slow requests
- Retries
- Dependency failures

The script demonstrates utilization values for workloads ranging from light utilization to overload.

---

# Bottlenecks

The bottleneck is the resource limiting end-to-end capacity.

Consider:

    Load balancer:      10,000 requests/second
    Application:         2,000 requests/second
    Database:              500 requests/second
    External dependency:   800 requests/second

The database is the bottleneck.

End-to-end sustainable throughput cannot significantly exceed approximately 500 requests per second unless the bottleneck changes.

Optimizing a component that is not currently limiting performance may have little effect on the entire system.

---

# Batching

Batching groups multiple work items together.

Suppose each request has:

- Fixed overhead: 5 ms
- Processing time: 1 ms per item

Processing 100 items individually requires approximately:

    100 × (5 + 1)
    = 600 ms

Processing them in batches of 20 requires:

    5 batches × 5 ms overhead
    + 100 × 1 ms processing
    = 125 ms

Batching can improve throughput by amortizing fixed costs.

---

## Batching Trade-Off

Batching can increase latency.

An item may wait until:

- More items arrive.
- A batch reaches a configured size.
- A batch timeout expires.

Larger batches can improve efficiency while increasing waiting time and memory usage.

---

# Caching

Caching stores previously computed or retrieved data so repeated requests can be served more quickly.

The script implements a simple thread-safe Least Recently Used cache.

Benefits include:

- Lower latency for repeated requests
- Reduced database load
- Reduced CPU usage
- Higher effective throughput

Risks include:

- Stale data
- Memory consumption
- Invalid data
- Cache invalidation complexity

---

# Least Recently Used Eviction

An LRU cache removes the least recently used item when capacity is exceeded.

The script uses `OrderedDict` to maintain access order.

When an item is accessed:

    It becomes the most recently used item.

When capacity is exceeded:

    The least recently used item is removed.

---

# Cache Stampede

A cache stampede occurs when many concurrent requests miss the same cache entry and all perform the expensive computation.

This can create a sudden increase in:

- CPU usage
- Database load
- Network traffic

The script implements simplified single-flight behavior.

For a missing key:

1. One request becomes the computation leader.
2. Other requests wait.
3. The leader computes and stores the value.
4. Waiting requests receive the cached result.

This reduces duplicate work during concurrent cache misses.

---

# Backpressure

Backpressure prevents producers from creating work faster than consumers can safely process it.

The script demonstrates a bounded queue.

When the queue is full, new work can be:

- Rejected
- Delayed
- Redirected
- Throttled

Backpressure prevents unlimited accumulation of work.

Without it, overload can cause:

- Increasing memory usage
- Large queue delays
- Timeouts
- Cascading failures

---

# Rate Limiting

Rate limiting controls how frequently requests are allowed.

The script implements a token bucket.

A token bucket has:

- Maximum token capacity
- Refill rate
- Current token count

Each request consumes tokens.

Tokens replenish over time.

This allows controlled bursts while enforcing an average request rate.

---

# Connection Pools

Connection pools reuse expensive resources such as:

- Database connections
- Network connections

Without pooling, every request may need to create and destroy a connection.

Connection creation can increase latency and resource usage.

A pool limits the number of simultaneously active connections.

When all connections are busy, requests may wait.

Therefore, connection pools improve reuse but can also become queueing points.

The script demonstrates acquisition and release of pooled resources.

---

# Horizontal and Vertical Scaling

## Vertical Scaling

Vertical scaling increases the resources available to one machine.

Examples:

- More CPU
- More memory
- Faster storage

Advantages:

- Simple architecture

Limitations:

- Hardware limits
- Potentially expensive machines
- Single-machine failure boundaries

---

## Horizontal Scaling

Horizontal scaling adds more machines or service instances.

Advantages:

- Greater potential capacity
- Improved redundancy

Challenges:

- Load balancing
- Shared state
- Data consistency
- Distributed coordination
- Uneven traffic distribution

The script demonstrates round-robin load balancing.

---

# Load Balancing

A load balancer distributes incoming work among available servers.

## Round Robin

Requests are assigned in rotation.

Example:

    Request 1 -> Server A
    Request 2 -> Server B
    Request 3 -> Server C
    Request 4 -> Server A

Round-robin works best when requests have similar costs.

---

## Other Strategies

### Least Connections

Requests are directed toward servers with fewer active connections.

Useful when request duration varies.

### Weighted Routing

More capable servers receive more traffic.

### Hash-Based Routing

Requests are routed according to a stable key.

This can preserve affinity but may produce uneven distribution.

---

# Amdahl's Law

Amdahl's Law describes the maximum theoretical speedup of parallelization.

The formula is:

    Speedup =
        1 / ((1 - P) + P / N)

Where:

- `P` is the parallelizable fraction.
- `N` is the number of workers.

Suppose 90% of work is parallelizable.

The remaining 10% is sequential.

Even with infinitely many workers, the maximum speedup approaches:

    1 / 0.1
    = 10x

This explains why adding workers eventually produces diminishing returns.

---

# Throughput Does Not Always Scale Linearly

Doubling workers does not guarantee doubling throughput.

Scaling losses can result from:

- Locks
- Shared databases
- Shared caches
- Network coordination
- Context switching
- Memory bandwidth
- Load imbalance

The script demonstrates a simplified model where efficiency decreases as worker count increases.

---

# Lock Contention

A lock protects shared state.

Multiple workers attempting to acquire the same lock can wait for one another.

This creates:

- Queueing
- Reduced parallel efficiency
- Increased latency

The script demonstrates multiple threads incrementing a shared counter protected by a lock.

Correct synchronization may reduce performance, while removing necessary synchronization may introduce data races and correctness failures.

Performance optimization must preserve correctness.

---

# Head-of-Line Blocking

Head-of-line blocking occurs when one slow request delays unrelated requests behind it.

Example:

    Slow request: 1 second
    Fast request: 10 ms
    Fast request: 10 ms

With a single FIFO worker, the fast requests can wait behind the slow request.

Possible mitigation strategies include:

- Multiple workers
- Separate queues
- Priority classes
- Request size limits
- Workload isolation

These strategies introduce their own complexity and fairness trade-offs.

---

# Timeouts

Timeouts limit how long a request waits for an operation.

They protect systems from indefinitely slow dependencies.

The script demonstrates waiting for an operation through a future with a timeout.

A critical implementation detail is that timing out the wait does not necessarily stop the underlying operation.

Production systems should distinguish:

- Timing out the caller
- Cancelling the underlying work

---

# Retries

Retries can improve reliability for temporary failures.

Uncontrolled retries can worsen overload.

A safe retry design often considers:

- Maximum retry count
- Exponential backoff
- Random jitter
- Error classification
- Idempotency

The script implements exponential backoff with small random jitter.

---

# Retry Amplification

Suppose a dependency fails under load.

Clients retry.

The dependency receives additional traffic.

The increased traffic causes more failures.

This creates a feedback loop.

Retry behavior must therefore be part of capacity and overload design.

---

# Circuit Breakers

A circuit breaker prevents repeated requests to a dependency that is consistently failing.

A simplified state model includes:

- Closed
- Open
- Half-open

The script demonstrates a simplified breaker that opens after a configured number of consecutive failures.

When open, requests fail quickly instead of repeatedly waiting for a failing dependency.

---

# Latency Budgets

A latency budget divides an end-to-end latency target among internal components.

Suppose the system target is:

    p99 response time <= 200 ms

A budget might allocate:

- Network: 20 ms
- Authentication: 10 ms
- Application: 50 ms
- Database: 80 ms
- Serialization: 10 ms
- Safety buffer: 30 ms

Budgets help identify whether a component consumes too much of the available response-time allowance.

---

# Tail Latency Amplification

Distributed requests often depend on multiple services.

Suppose one request calls ten services in parallel.

The total response may depend approximately on the slowest dependency.

Even when each dependency is fast most of the time, the probability that at least one dependency experiences a slow event increases as fan-out increases.

The script simulates this effect using random dependency latencies.

---

# Serial and Parallel Dependencies

For serial dependencies:

    Total Latency ≈
        Dependency A
        + Dependency B
        + Dependency C

For ideal parallel dependencies:

    Total Latency ≈
        max(A, B, C)

Parallelism can reduce latency.

It can also increase:

- Resource usage
- Downstream load
- Tail-latency exposure

---

# Closed-Loop and Open-Loop Load Testing

## Closed-Loop Testing

A client:

1. Sends a request.
2. Waits for the response.
3. Sends the next request.

When the system slows, the client naturally sends fewer requests.

This can hide some overload behavior.

---

## Open-Loop Testing

Requests are scheduled according to a target arrival rate regardless of response completion.

Open-loop testing can reveal:

- Queue growth
- Saturation
- Latency increases under sustained arrival pressure

The script includes a simplified deterministic open-loop simulation.

---

# Coordinated Omission

Coordinated omission occurs when a benchmark underreports latency because the load generator stops generating work while the system is slow.

For example:

1. A request causes the system to pause for one second.
2. A closed-loop client waits.
3. The client sends no requests during that second.

A real production system may have continued receiving requests during the pause.

The benchmark therefore measures fewer affected requests than a real workload would experience.

---

# Priority Queues

Priority queues process higher-priority work before lower-priority work.

Benefits:

- Lower latency for critical operations

Risks:

- Starvation of low-priority work
- Reduced fairness

The script uses Python's `PriorityQueue` and an ordered request data structure.

---

# Fairness and Starvation

Scheduling policies must balance:

- Importance
- Latency
- Throughput
- Fairness

Strict priority can cause starvation.

FIFO provides ordering fairness but may delay urgent requests.

Weighted scheduling can balance competing workloads.

---

# Request Size and Capacity

Capacity is not fully described by requests per second.

A request may differ in:

- Payload size
- CPU cost
- Database queries
- Memory consumption
- Network traffic

A system capable of 10,000 small requests per second may be unable to process 10,000 large requests per second.

The script compares request throughput with byte throughput.

---

# Cost per Request

Performance and cost are related.

A basic cost calculation is:

    Cost per Request =
        Infrastructure Cost / Requests Processed

Higher throughput can reduce cost per request when fixed infrastructure is used efficiently.

Excessive utilization can increase tail latency and failure risk.

The lowest cost per request is not necessarily the best operating point.

---

# Capacity Planning

A simplified worker estimate is:

    Workers >=
        Target Throughput
        × Average Service Time
        / Target Utilization

For example:

    Target throughput = 1,000 requests/second
    Average service time = 0.02 seconds
    Target utilization = 70%

Estimated workers:

    1,000 × 0.02 / 0.70
    ≈ 28.57

Rounded upward:

    29 workers

Real capacity planning should also consider:

- Tail service time
- Bursts
- Redundancy
- Failure scenarios
- Deployment transitions
- Dependency limits

---

# Service-Level Metrics

A service-level indicator measures an observed property.

Examples:

- Request success rate
- p95 latency
- p99 latency
- Throughput

A service-level objective defines a target.

Examples:

    99.9% successful requests

or:

    99% of requests complete within 200 ms

The script models a simple service-level report containing success and latency compliance rates.

---

# Performance Regression Testing

Performance regression testing compares a candidate implementation with a baseline.

Example:

    Baseline p95 = 100 ms
    Candidate p95 = 120 ms

Regression:

    (120 - 100) / 100 × 100
    = 20%

Meaningful comparison requires similar:

- Hardware
- Software configuration
- Workload
- Concurrency
- Cache state

Noisy environments can produce misleading performance differences.

---

# Production Monitoring

A production performance view should usually consider multiple metrics together.

The script defines a `PerformanceSnapshot` containing:

- Request count
- Error count
- Average latency
- p95 latency
- p99 latency
- Queue depth
- CPU utilization
- Memory utilization

A high p99 latency without high CPU utilization may indicate:

- Slow dependencies
- I/O waiting
- Lock contention
- Network delays

High queue depth may indicate:

- Arrival rate exceeding service capacity

High CPU utilization combined with high latency may indicate:

- CPU saturation
- Inefficient algorithms
- Excessive contention

Metrics must be interpreted together.

---

# Debugging Performance Problems

A useful diagnostic process is:

1. Define the observed symptom.
2. Identify the measurement boundary.
3. Compare throughput and arrival rate.
4. Examine queue depth.
5. Check CPU, memory, and I/O utilization.
6. Inspect dependency latency.
7. Examine p95 and p99 behavior.
8. Identify bottlenecks.
9. Test changes under representative load.

The script contains simplified diagnostic logic demonstrating how different combinations of metrics can suggest different failure modes.

Real systems require more detailed evidence.

---

# Security and Performance

Performance controls can also provide security benefits.

## Rate Limiting

Helps reduce resource exhaustion caused by excessive request rates.

## Input Size Limits

Reduce risk of excessive CPU or memory consumption.

## Timeouts

Limit resource consumption caused by indefinitely slow operations.

## Bounded Queues

Prevent unlimited accumulation of work.

Security checks can add latency, but removing essential checks for performance is unsafe.

Performance optimization should preserve:

- Authentication
- Authorization
- Data protection
- Input validation

---

# End-to-End System Modeling

The script models a request path containing:

- API gateway
- Application
- Database
- Response encoding

For serial processing:

    Total service latency ≈
        Sum of stage service times

System throughput is constrained by the stage with the lowest sustainable capacity.

This demonstrates why improving a non-bottleneck component may not improve end-to-end throughput.

---

# Common Mistakes

## Using Only Average Latency

Average values can hide severe tail latency.

Use percentiles and distributions.

---

## Treating Peak Throughput as Sustainable Capacity

A short benchmark peak may depend on:

- Temporary buffering
- Cache state
- Resource bursts

Sustainable capacity must consider stability and error rates.

---

## Ignoring Queueing

A request may be computationally fast but operationally slow because of waiting.

---

## Adding Concurrency Without Identifying Bottlenecks

More workers may increase contention or overwhelm a shared dependency.

---

## Using Unbounded Queues

Unbounded queues can turn overload into increasing memory usage and extreme latency.

---

## Scaling the Wrong Component

Adding application servers does not solve a database bottleneck.

---

## Ignoring Cold Starts

First requests can behave differently because of:

- Initialization
- Cache population
- Connection creation

---

## Comparing Different Workloads

Throughput and latency comparisons require equivalent workloads.

---

# Best Practices

## Measure Distributions

Track:

- p50
- p95
- p99
- Maximum where useful

---

## Monitor Queue Depth

Queue depth is an early indicator of capacity pressure.

---

## Maintain Capacity Headroom

Operating continuously near maximum utilization increases sensitivity to traffic bursts and slowdowns.

---

## Use Bounded Resources

Bound:

- Queues
- Connection pools
- Request sizes
- Concurrency

---

## Identify the Bottleneck

Optimize the resource limiting the critical path.

---

## Apply Backpressure

Reject or slow incoming work before the system becomes unstable.

---

## Use Timeouts Carefully

Timeouts should be consistent with end-to-end latency budgets.

---

## Limit Retries

Use:

- Maximum attempts
- Backoff
- Jitter

Avoid retry storms.

---

## Test Under Representative Load

Include realistic:

- Request sizes
- Concurrency
- Dependency behavior
- Cache states
- Error conditions

---

# Important Formulas

## Throughput

    Throughput =
        Completed Work / Time

---

## Response Time

    Response Time =
        Waiting Time + Service Time

---

## Ideal Worker Capacity

    Capacity ≈
        Workers / Service Time

---

## Utilization

    Utilization =
        Arrival Rate / Service Capacity

---

## Little's Law

    L = λW

Where:

- L is average items in the system.
- λ is average throughput.
- W is average time in the system.

---

## Amdahl's Law

    Speedup =
        1 / ((1 - P) + P / N)

Where:

- P is the parallelizable fraction.
- N is the number of workers.

---

# Practical Applications

Latency and throughput analysis is relevant to:

- Web applications
- APIs
- Databases
- Distributed systems
- Cloud infrastructure
- Message queues
- Data pipelines
- Payment systems
- Streaming systems
- Network services
- Background job processing

In all of these systems, good performance design requires understanding both how long individual operations take and how much work the system can sustain.

The Python script provides executable demonstrations of these relationships through timing, queue simulations, concurrency, percentile analysis, load testing, caching, rate limiting, backpressure, scaling, capacity planning, and production-style monitoring.
