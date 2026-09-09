# System Design Foundations: Back-of-the-Envelope Estimation

## Topic

This study file develops the quantitative reasoning required for system design, with particular emphasis on:

- Queries per second (QPS) and requests per second (RPS)
- Average, peak, and burst traffic
- User activity modeling
- Read/write workload estimation
- Storage growth
- Bandwidth
- Caching
- Fan-out and fan-in
- Database capacity
- CPU capacity
- IOPS
- Queue throughput and backlog
- Latency and concurrency
- Availability
- Replication
- Headroom
- Sharding
- Failure domains
- Retries
- Autoscaling
- Observability volume
- Production capacity planning

The Python script is deliberately executable. Each section implements a quantitative concept rather than presenting only prose.

---

## 1. Purpose of Back-of-the-Envelope Estimation

Back-of-the-envelope estimation is a first-order technique for converting vague product requirements into approximate engineering quantities.

A system-design problem often begins with statements such as:

- Hundreds of millions of users
- Tens of millions of daily active users
- Several actions per user per day
- Large media files
- High read/write ratios
- Multi-region replication
- Strict availability requirements

Those statements are not yet directly useful for capacity planning.

They need to become measurable quantities:

- Requests per day
- Average QPS
- Peak QPS
- Read QPS
- Write QPS
- Bytes per second
- Bytes per day
- Retained storage
- Physical replicated storage
- Database operations per second
- Number of application instances
- Number of partitions
- Number of concurrent requests

The purpose of estimation is not to produce an exact prediction. The purpose is to determine the approximate scale of the system and identify which architectural constraints are likely to matter.

---

# 2. Core Estimation Philosophy

A strong estimate has five properties:

1. The assumptions are explicit.
2. Units remain consistent.
3. Large calculations are decomposed into smaller steps.
4. Uncertain quantities are represented as ranges or multipliers.
5. The resulting magnitude is sanity-checked.

For example, a request estimate should not jump directly from "100 million users" to "some number of servers."

Instead:

1. Registered users
2. Active-user fraction
3. Active users
4. Actions per active user per day
5. Total actions per day
6. Average QPS
7. Peak multiplier
8. Peak QPS
9. Downstream amplification
10. Capacity per machine
11. Headroom
12. Redundancy

This chain makes the reasoning auditable.

---

# 3. Units and Conversions

The script uses decimal SI units for storage and networking:

- 1 KB = 1,000 bytes
- 1 MB = 1,000,000 bytes
- 1 GB = 1,000,000,000 bytes
- 1 TB = 1,000,000,000,000 bytes
- 1 PB = 1,000,000,000,000,000 bytes

There are:

- 60 seconds/minute
- 3,600 seconds/hour
- 86,400 seconds/day
- Approximately 31.5 million seconds/year

Network bandwidth is normally expressed in bits per second:

- bps
- Kbps
- Mbps
- Gbps

Storage and payload sizes are normally expressed in bytes.

Therefore:

- 8 bits = 1 byte
- 100 Mbps ≈ 12.5 MB/s

Confusing bits and bytes creates an eightfold error.

---

# 4. QPS, RPS, TPS, and EPS

Several rate terms occur in system design.

## QPS

QPS means Queries Per Second.

The term is commonly used for database queries or generic request rates.

## RPS

RPS means Requests Per Second.

It is frequently used for HTTP/API request traffic.

## TPS

TPS means Transactions Per Second.

The precise meaning depends on the system. A transaction may contain multiple lower-level operations.

## EPS

EPS means Events Per Second.

It is common in event-streaming and telemetry systems.

These terms describe rates, but they are not automatically equivalent.

One API request may trigger:

- Multiple database queries
- Several cache operations
- Multiple downstream API calls
- An event publication
- Logging operations
- Metrics operations

Consequently, system design requires estimates at multiple layers.

---

# 5. Converting Daily Traffic to QPS

The fundamental relationship is:

Average QPS = Requests per day / 86,400

For example:

10,000,000 requests/day

becomes approximately:

10,000,000 / 86,400 ≈ 116 QPS

Useful mental anchors include:

- 1 million/day ≈ 12 QPS
- 10 million/day ≈ 116 QPS
- 100 million/day ≈ 1,157 QPS
- 1 billion/day ≈ 11,574 QPS
- 10 billion/day ≈ 115,741 QPS

These are average rates.

They do not represent peak traffic.

---

# 6. Average Traffic Versus Peak Traffic

A production system rarely receives perfectly uniform traffic.

A simple estimate uses a peak multiplier:

Peak QPS = Average QPS × Peak Multiplier

If average traffic is 10,000 QPS and the peak multiplier is 5:

Peak QPS = 10,000 × 5 = 50,000 QPS

The multiplier represents traffic concentration.

It can be caused by:

- Time-of-day effects
- Business hours
- Product launches
- Notifications
- Sporting events
- Breaking news
- Marketing campaigns
- Flash sales
- Scheduled jobs
- Regional traffic overlap

The appropriate peak interval must be defined. A daily peak is different from a five-minute burst.

---

# 7. Registered Users Versus Active Users

A common mistake is to treat every registered user as an active user.

Suppose a service has:

- 100 million registered users
- 10% daily active users

Then:

Daily active users = 100 million × 10%

= 10 million DAU

If each active user performs 30 requests/day:

Requests/day = 10 million × 30

= 300 million requests/day

The resulting QPS is based on 300 million requests, not on 100 million users directly.

The active fraction is therefore a critical assumption.

---

# 8. User Activity Frequency

A general traffic model is:

Requests/day =
Active users × Requests/user/day

Then:

Average QPS =
Requests/day / 86,400

This relationship can be used for:

- Social networks
- E-commerce
- Messaging
- Search
- Maps
- Productivity software
- Financial applications
- Education platforms
- Streaming services
- Mobile applications

The activity rate should be estimated separately for different user behaviors when they have materially different workloads.

---

# 9. Read/Write Ratios

A workload is often described as a read/write ratio.

For example:

9 reads : 1 write

means:

- 90% reads
- 10% writes

For a total of 10,000 QPS:

- Read QPS = 9,000
- Write QPS = 1,000

Read-heavy systems and write-heavy systems have different architectural characteristics.

Read-heavy workloads may benefit from:

- Caches
- Read replicas
- CDNs
- Denormalized read models
- Precomputed results

Write-heavy workloads emphasize:

- Database write throughput
- Partitioning
- Append-only designs
- Batching
- Log throughput
- Replication cost
- Write amplification

---

# 10. Storage Estimation

A basic storage equation is:

Daily storage =
Records/day × Bytes/record

Retained logical storage:

Logical storage =
Daily storage × Retention days

Physical storage is larger when replication and overhead are included.

A more realistic first-order model is:

Physical storage ≈
Records/day × Record size × Metadata factor × Retention × Replication

Compression can reduce physical storage:

Compressed storage ≈
Uncompressed storage / Compression ratio

A compression ratio of 2 means the compressed representation is approximately half the original size.

---

# 11. Logical Storage Versus Physical Storage

Logical storage is the amount of application data.

Physical storage is what the infrastructure actually has to maintain.

For example, if logical data is 20 TB and the replication factor is 3:

Physical storage ≈ 20 TB × 3

= 60 TB

Real systems can require additional space for:

- Indexes
- Journals
- Write-ahead logs
- Compaction
- Temporary files
- Metadata
- Snapshots
- Backups
- Repair operations
- Rebalancing

Replication should therefore not be treated as the only storage multiplier.

---

# 12. Storage Growth From Write QPS

Write QPS can be converted directly into storage growth.

Writes/day =
Write QPS × 86,400

Then:

Storage/day =
Writes/day × Bytes/write

For retention:

Storage =
Write QPS × 86,400 × Bytes/write × Retention days

The script implements this calculation through `storage_from_write_qps()`.

This is particularly useful for:

- Event stores
- Audit logs
- Message systems
- Time-series databases
- User-generated content
- Transaction records

---

# 13. Bandwidth Estimation

A basic bandwidth equation is:

Bandwidth bytes/s =
QPS × Bytes/request

For example:

50,000 QPS × 100 KB

produces approximately:

5 GB/s

Network throughput in bits per second is eight times the byte rate.

Therefore:

5 GB/s × 8 ≈ 40 Gbps

The script also models:

- Protocol overhead
- Compression
- Request bandwidth
- Response bandwidth
- Daily transfer
- Monthly transfer

---

# 14. Request Bandwidth Versus Response Bandwidth

API requests and responses may have very different sizes.

For example:

- Request = 1 KB
- Response = 50 KB
- QPS = 20,000

Request bandwidth:

20,000 × 1 KB ≈ 20 MB/s

Response bandwidth:

20,000 × 50 KB ≈ 1 GB/s

The response path dominates.

This distinction matters in:

- Search APIs
- Feed systems
- Media metadata APIs
- Recommendation systems
- Data APIs

---

# 15. Cache Hit Rate

A cache hit rate determines how much traffic reaches the backend.

Backend QPS =
Total QPS × (1 − Cache hit rate)

At 100,000 QPS and a 95% hit rate:

Backend QPS =
100,000 × 5%

= 5,000 QPS

Caching can therefore dramatically reduce backend traffic.

The calculation assumes that the cached operation is equivalent to the modeled workload. Real systems need to distinguish:

- Read cache hits
- Read cache misses
- Writes
- Invalidations
- Stale data
- Cache warming
- Evictions

---

# 16. Cache Size

Cache capacity is influenced by:

- Number of hot objects
- Key size
- Value size
- Metadata
- Runtime overhead
- Eviction policy
- Replication

A first-order estimate is:

Cache memory ≈
Number of objects × Average object size × Overhead factor

The script demonstrates both object-level cache sizing and explicit key/value sizing.

---

# 17. CDN Offload

A CDN can serve cacheable content without requiring every request to reach the origin.

If:

- Content QPS = 50,000
- Cache hit rate = 90%

then:

CDN-served QPS = 45,000

Origin QPS = 5,000

The actual benefit depends on:

- Cacheability
- TTL
- Content popularity
- Geographic distribution
- Invalidation frequency
- Object size
- Request distribution

A CDN reduces origin load but does not eliminate the need to size the origin for misses and uncached traffic.

---

# 18. Fan-Out

Fan-out means one incoming request causes multiple downstream operations.

If:

- Incoming QPS = 10,000
- Downstream calls/request = 8

then:

Downstream QPS = 80,000

This is a major source of hidden load.

Fan-out can occur across:

- Microservices
- Databases
- Caches
- Search systems
- Recommendation services
- External APIs

The external API rate can therefore be much lower than the internal system rate.

---

# 19. Fan-In

Fan-in is the opposite pattern.

Many producers send data to a shared service.

If:

- 100,000 producers
- Each emits 0.2 events/s

then:

Aggregate rate =
100,000 × 0.2

= 20,000 events/s

Fan-in is common in:

- Telemetry
- IoT
- Event processing
- Logging
- Message ingestion

The aggregate rate is what the central system must process.

---

# 20. Broadcast Amplification

A publish/subscribe system can amplify traffic in the opposite direction.

If:

- 2,000 messages/s are published
- Each message has 500 subscribers

then:

Delivered message copies/s =
2,000 × 500

= 1,000,000

The publisher's rate is therefore not the same as the delivery workload.

This matters for:

- Live updates
- Notifications
- Chat
- Market data
- Multiplayer systems
- Real-time collaboration

---

# 21. Little's Law

Little's Law is one of the most useful quantitative relationships in system design:

L = λW

Where:

- L = average number of items in the system
- λ = throughput
- W = average time spent in the system

For requests:

Concurrent requests =
QPS × Average latency

If a service handles:

5,000 QPS

with:

100 ms average latency

then:

Concurrency =
5,000 × 0.1

= 500 requests

This is useful for estimating:

- In-flight requests
- Connection counts
- Queue populations
- Worker requirements

---

# 22. Latency Budgets

End-to-end latency often consists of several components:

- Client network
- Load balancer
- Application processing
- Cache
- Database
- Downstream services
- Serialization

For serial operations:

Total latency ≈ Sum of component latencies

For example:

30 + 2 + 15 + 2 + 20 + 25 + 6 = 100 ms

Parallel operations behave differently. If several downstream calls execute concurrently, their idealized contribution is closer to the maximum branch latency rather than their sum.

Real systems include:

- Scheduling overhead
- Network overhead
- Coordination
- Queuing
- Retries
- Timeout behavior

---

# 23. Percentiles and Tail Latency

Average latency is not sufficient for many production systems.

Common metrics include:

- p50
- p90
- p95
- p99
- p99.9

A p99 latency of 200 ms means approximately 99% of observations are at or below 200 ms, with the remaining tail above it.

Tail latency matters because:

- A user request may depend on several services.
- One slow dependency can delay the entire request.
- Parallel fan-out can make tail behavior more visible.
- Timeouts and retries can amplify tail load.

---

# 24. CPU Capacity

A first-order CPU model is:

CPU-seconds required per second =
QPS × CPU-seconds/request

If a request consumes 5 ms CPU and traffic is 20,000 QPS:

CPU demand =
20,000 × 0.005

= 100 CPU-seconds per second

This corresponds to approximately 100 fully utilized CPU cores before accounting for a utilization target.

If the target operating point is 65%, the required provisioned cores are larger.

Real CPU capacity depends on:

- CPU generation
- Instruction mix
- Memory access
- Garbage collection
- Lock contention
- I/O waits
- Serialization
- Runtime
- Workload variability

A benchmark must represent the actual workload.

---

# 25. Database Capacity

Database capacity is workload-specific.

Important dimensions include:

- Read QPS
- Write QPS
- Query complexity
- Row size
- Indexes
- Working-set size
- Cache hit rate
- Transactions
- Lock contention
- Replication
- Storage latency
- IOPS

The script uses a simplified model where each node has a maximum sustainable rate and a target utilization.

This is only a first-order capacity estimate. Real database capacity must be validated through workload-specific testing.

---

# 26. IOPS

Storage capacity and storage performance are separate constraints.

A storage system can have:

- Enough TB but insufficient IOPS
- Enough IOPS but insufficient capacity
- Enough raw IOPS but insufficient latency performance

If a workload requires 25,000 IOPS and each device is planned for 7,000 usable IOPS:

Required devices =
ceil(25,000 / 7,000)

= 4

The usable IOPS figure should account for operational headroom.

---

# 27. Queues and Backlog

A queue receives work at an arrival rate and processes work at a service rate.

If:

Arrival rate > Processing rate

the backlog grows.

For a simplified stable period:

Backlog growth =
Arrival rate − Processing rate

If:

- Arrival = 12,000 events/s
- Processing = 10,000 events/s

then backlog grows by:

2,000 events/s

After 300 seconds:

600,000 additional events

Queues absorb temporary bursts, but they do not eliminate sustained capacity requirements.

---

# 28. Queue Drain Time

If a backlog already exists, it can only drain when:

Processing rate > Arrival rate

The effective drain rate is:

Processing rate − Arrival rate

Drain time:

Backlog / Effective drain rate

For:

- Backlog = 1,000,000
- Arrival = 8,000/s
- Processing = 12,000/s

Effective drain rate:

4,000/s

Drain time:

250 seconds

---

# 29. Availability

Availability is commonly expressed as a percentage.

Examples include:

- 99%
- 99.9%
- 99.99%
- 99.999%

Higher availability corresponds to a smaller downtime budget.

The script calculates annual downtime for several availability levels.

Availability requirements have architectural consequences because higher availability may require:

- Redundancy
- Multiple failure domains
- Automated recovery
- Health checks
- Failover
- Data replication
- Operational monitoring
- Safer deployments

Availability is therefore an engineering constraint rather than merely a reporting metric.

---

# 30. Serial Availability

For independent serial components:

System availability ≈
A1 × A2 × A3 × ...

For example, if a request requires three independent components:

- 99.9%
- 99.95%
- 99.99%

then the combined availability is lower than each individual component.

Every mandatory dependency creates another availability opportunity for failure.

---

# 31. Parallel Redundancy

For independent replicas, if each replica has availability A, the probability that all replicas fail is:

(1 − A)^N

Therefore:

Parallel availability =
1 − (1 − A)^N

Two independent 99% replicas produce:

1 − 0.01²
= 99.99%

The independence assumption is critical.

Replicas may share:

- The same software bug
- The same network
- The same power infrastructure
- The same deployment
- The same region
- The same dependency

Correlated failures reduce the benefit of nominal redundancy.

---

# 32. Replication

Replication improves resilience and may improve read scalability, but it increases:

- Storage
- Network traffic
- Write work
- Recovery work
- Operational complexity

For logical storage L and replication factor R:

Physical storage ≈ L × R

Replication may be:

- Synchronous
- Asynchronous
- Semi-synchronous

The latency and consistency consequences depend on the replication protocol.

---

# 33. Write Amplification

A logical write can produce several physical operations.

Sources include:

- Replication
- Index updates
- Journaling
- Write-ahead logs
- Compaction
- Storage-engine metadata

A simplified model is:

Physical write work ≈
Logical writes × Replication × Index factor × Journal factor

This is useful when a workload appears small at the API layer but becomes large at the persistence layer.

---

# 34. Retention

Retention directly controls storage.

If a system ingests 500 GB/day and retains data for 30 days:

Approximate logical storage:

500 GB × 30
= 15 TB

If deletion takes an additional three days to become effective, a rough operational estimate may need to account for 33 days of resident data.

Retention policies are therefore capacity controls.

---

# 35. Time-Series Storage

For telemetry or IoT:

Samples/day =
Devices × Samples/device/second × 86,400

Storage/day =
Samples/day × Bytes/sample

Then multiply by:

- Retention
- Replication
- Metadata overhead

At very high device counts, even a small sample size can create large storage requirements.

---

# 36. Logging Storage

Logs are often underestimated.

If an application handles:

100,000 requests/s

and produces:

5 log lines/request

then:

Log lines/s =
500,000

At 500 bytes/log line:

Raw log bandwidth =
250 MB/s

Over 14 days, this becomes a very large storage workload before accounting for replication and indexing.

Important controls include:

- Log levels
- Sampling
- Aggregation
- Compression
- Retention
- Selective indexing

---

# 37. Media Storage

Media systems have different characteristics from transactional systems.

For example:

Uploads/day × Average file size × Retention

can quickly reach petabyte scale.

Important dimensions include:

- Original files
- Thumbnails
- Multiple resolutions
- Replicas
- Backups
- CDN copies
- Temporary processing files

Large media systems are frequently constrained by:

- Storage
- Network bandwidth
- Object-store operations
- CDN throughput

rather than raw CPU.

---

# 38. Load Balancer Capacity

A load balancer can itself become a capacity boundary.

A simple model is:

Instances =
ceil(Incoming QPS / Usable QPS per instance)

Usable QPS may be:

Benchmark QPS × Target utilization

For example, if a benchmark is 30,000 QPS but the desired operating point is 70%:

Usable capacity =
30,000 × 0.70
= 21,000 QPS

This is safer than assuming the benchmark represents sustainable production capacity.

---

# 39. Headroom

A system should generally not be planned exactly at its expected peak.

With 25% headroom:

Planning capacity =
Peak demand × 1.25

Headroom provides protection against:

- Estimation error
- Traffic variation
- Growth
- Deployment effects
- Failures
- Noisy neighbors
- Temporary bursts
- Unexpected workload changes

The appropriate amount depends on the system and operational model.

---

# 40. N+1 Capacity

N+1 means the system has enough additional capacity to tolerate one node failure.

If the workload requires four nodes:

N = 4

N+1 = 5 nodes

This is a simplified availability model.

Failure-domain requirements may require more capacity.

A system designed to survive loss of an entire availability zone must distribute sufficient capacity across the remaining zones.

---

# 41. Failure Domains

A failure domain is a group of resources that may fail together.

Examples include:

- Host
- Rack
- Availability zone
- Region
- Network segment

Redundancy is only meaningful relative to the failure being tolerated.

Three replicas on the same physical host do not provide host-level resilience.

Three replicas in independent regions provide a different failure model.

---

# 42. Sharding

Sharding distributes data and workload across partitions.

If total traffic is 100,000 QPS and there are 20 evenly balanced shards:

QPS/shard =
100,000 / 20
= 5,000 QPS

Similarly, 100 TB distributed uniformly across 20 shards gives approximately:

5 TB/shard

Real systems may not be uniform.

Sharding introduces:

- Routing
- Rebalancing
- Hot keys
- Cross-shard queries
- Cross-shard transactions
- Operational complexity

---

# 43. Hot Partitions

Average partition load can hide a hot partition.

Suppose:

- Total QPS = 100,000
- 100 partitions

Average:

1,000 QPS/partition

If one hot partition receives 25% of the total workload:

Hot partition:

25,000 QPS

The cluster average is therefore not enough to determine partition-level capacity.

Hot keys can occur in:

- Social feeds
- Popular products
- Celebrity accounts
- Trending content
- Tenant-based systems
- Geographic partitions

---

# 44. Cross-Region Replication

Cross-region replication creates network traffic.

For:

- 5,000 writes/s
- 10 KB/write
- 3 regions

there are two additional replication destinations in a simple model.

Approximate replication stream rate:

5,000 × 2 = 10,000 writes/s

Approximate cross-region data bandwidth:

10,000 × 10 KB
≈ 100 MB/s

Actual replication protocols may batch, compress, stream logs, or use other mechanisms.

---

# 45. Retry Amplification

Retries can increase effective load.

If 10% of requests retry and retried requests average 2.5 attempts:

Extra attempts =
Original retrying requests × (2.5 − 1)

Retries become especially dangerous during overload because failure causes retries, retries increase load, and increased load causes more failure.

Important controls include:

- Exponential backoff
- Jitter
- Deadlines
- Retry budgets
- Idempotency
- Circuit breakers
- Load shedding

---

# 46. Layered Retry Amplification

Retries can happen at multiple layers:

- Client
- API gateway
- Service
- Database client
- Message consumer

If multiple layers independently retry, the effective attempt rate can become multiplicative.

This is one reason retry policy must be designed as a system-wide behavior rather than independently at every layer.

---

# 47. Asynchronous Processing

Queues allow producers and consumers to operate at different instantaneous rates.

A consumer pool's simplified capacity is:

Workers × Processing rate/worker

If producers exceed that capacity, backlog grows.

Asynchronous architecture is useful for:

- Notifications
- Image processing
- Data pipelines
- Analytics
- Search indexing
- Email
- Background jobs

A queue absorbs bursts but cannot compensate for a permanently undersized consumer fleet.

---

# 48. Batching

Batching reduces per-operation overhead.

If:

100,000 records/s

are grouped into batches of 100:

Batch operations/s =
1,000

Batching can reduce:

- Network round trips
- Transaction overhead
- Function-call overhead
- Protocol overhead

Trade-offs include:

- Higher latency
- Larger failure domains
- More complex retries
- Larger memory buffers

---

# 49. Connection Pools

Little's Law can estimate in-flight work.

If:

5,000 QPS

and average database interaction latency is:

20 ms

then approximate concurrency is:

5,000 × 0.020
= 100

A connection pool should not necessarily be exactly 100 because utilization targets, spikes, and workload characteristics matter.

Connection counts can also explode across application fleets.

For example:

200 application instances × 50 connections

= 10,000 database connections

This may overwhelm the database even if the application QPS itself looks reasonable.

---

# 50. Backups

Backup storage can be estimated from:

- Number of full backups
- Full backup size
- Incremental backup volume
- Retention
- Replication

Backups are often overlooked when estimating total storage.

Production storage may therefore include:

- Primary storage
- Replicas
- Snapshots
- Full backups
- Incremental backups
- Disaster-recovery copies

---

# 51. RPO and RTO

RPO means Recovery Point Objective.

It describes the maximum acceptable data-loss interval.

If data is generated at 10 MB/s and the RPO is 60 seconds:

Potential unprotected data:

10 MB/s × 60
= 600 MB

RTO means Recovery Time Objective.

It describes the maximum acceptable recovery duration.

If 20 TB must be restored at 500 MB/s, the theoretical transfer duration is:

20 TB / 500 MB/s

Real recovery takes longer because of:

- Metadata
- Initialization
- Validation
- Network contention
- Parallelism
- Service startup
- Rebuilding indexes
- Catch-up replication

---

# 52. Significant Figures

Back-of-the-envelope calculations should avoid false precision.

If the assumptions are approximate, reporting:

123,456.789 QPS

is misleading.

A result such as:

approximately 120,000 QPS

often communicates the quality of the estimate more honestly.

The goal is to communicate scale and architectural consequences, not artificial numerical accuracy.

---

# 53. Estimation Ranges

A useful representation is:

Low
Expected
High

For example:

- Low = 30,000 QPS
- Expected = 50,000 QPS
- High = 100,000 QPS

The range exposes uncertainty.

It is especially useful when uncertain inputs include:

- User activity
- Payload size
- Peak multiplier
- Cache hit rate
- Retention
- Downstream amplification

The most sensitive assumptions deserve better measurement.

---

# 54. Sensitivity Analysis

Sensitivity analysis asks:

"What happens if an assumption is wrong?"

For a storage model:

Storage =
Records/day × Record size × Retention

Doubling any one of these variables doubles the storage estimate.

Doubling two variables simultaneously multiplies storage by four.

Sensitivity analysis helps identify which assumptions are worth validating before making expensive architectural decisions.

---

# 55. Multipliers

System estimates frequently contain several multipliers:

- Growth multiplier
- Peak multiplier
- Replication multiplier
- Fan-out multiplier
- Retry multiplier
- Headroom multiplier

They should represent distinct effects.

For example:

Base QPS = 10,000

Growth = 2x

Peak = 5x

Headroom = 1.25x

Planning capacity:

10,000 × 2 × 5 × 1.25
= 125,000 QPS

Multipliers compound uncertainty, so each one should have a clear explanation.

---

# 56. Request-to-Database Amplification

Suppose an API receives:

15,000 QPS

and each request causes:

4 database queries

Then:

Database QPS =
15,000 × 4

= 60,000 QPS

This is a key reason capacity should be estimated layer by layer.

A system may have modest external QPS but high internal load.

---

# 57. N+1 Query Pattern

A common database amplification pattern is:

1. One query retrieves N parent records.
2. One additional query is executed for each parent.

The total becomes:

1 + N queries

For 1,000 parent records:

1 + 1,000
= 1,001 queries

Batching, joins, prefetching, or alternative data-access patterns can reduce this amplification.

---

# 58. Search Index Storage

Search systems frequently maintain data structures separate from the original records.

If source data is 2 PB and the index multiplier is 1.8:

Primary index storage ≈ 3.6 PB

With two physical replicas:

Physical index storage ≈ 7.2 PB

The exact multiplier depends on:

- Indexed fields
- Tokenization
- Inverted indexes
- Stored fields
- Compression
- Segment structures
- Doc values
- Replication

---

# 59. Rate Limiter Capacity

A distributed rate limiter may need state for every active key.

A rough memory model is:

Memory =
Active keys × Bytes/key × Replicas

The key count can be large for:

- Users
- API keys
- IP addresses
- Tenants
- Devices
- Endpoints

A rate limiter can itself become a high-QPS dependency if every request performs a stateful decision.

---

# 60. Telemetry Volume

Observability creates its own workload.

A simplified model is:

Time series =
Services × Instances × Metrics × Environments × Regions

Adding dimensions multiplies cardinality.

For example, labels such as:

- Service
- Region
- Environment
- Instance
- Endpoint
- Status
- Customer

can create large numbers of unique series.

High-cardinality labels such as individual user IDs can be particularly expensive.

---

# 61. WebSocket and Long-Lived Connections

Persistent connections create a different capacity model from ordinary HTTP request/response traffic.

Important quantities include:

- Concurrent connections
- Memory per connection
- Messages/second
- Average message size
- Connection establishment rate
- Network bandwidth
- Fan-out

For one million clients sending 0.2 messages/s:

Messages/s =
1,000,000 × 0.2
= 200,000 messages/s

The message rate may be moderate while connection concurrency is very high.

---

# 62. Connection Memory

Per-connection memory becomes significant at large scale.

If:

- 2 million connections
- 20 KB state/connection

then:

Memory =
2,000,000 × 20 KB

≈ 40 GB

The actual memory requirement depends on:

- Runtime
- Socket buffers
- TLS state
- Application state
- Kernel structures
- Protocol buffers
- Event-loop structures

---

# 63. Lock Contention

A shared lock can turn parallel work into serialized work.

The script estimates concurrent lock holders using:

Concurrent lock holders =
Lock acquisition rate × Lock hold time

If:

2,000 lock acquisitions/s

and each lock is held for:

5 ms

then:

2,000 × 0.005
= 10 concurrent lock holders

A high rate or long hold time can make a shared resource a bottleneck.

---

# 64. Batched Network Transfer

Network traffic consists of payload and overhead.

If 100,000 records/s are sent individually, fixed protocol overhead can be significant.

Grouping them into batches reduces the number of protocol operations.

The script models:

- Payload bandwidth
- Batch count
- Batch overhead
- Total bandwidth

This illustrates why bandwidth is not always simply:

Records/s × Record size

Overhead may matter at high operation rates.

---

# 65. Traffic Spikes

A spike has two effects:

1. Higher instantaneous capacity requirement
2. Additional accumulated work

If baseline traffic is 20,000 QPS and a five-minute spike reaches 5x:

Spike rate =
100,000 QPS

The additional work above baseline is:

(100,000 − 20,000) × 300

= 24 million additional requests

Queues, caches, autoscaling, and rate limiting affect how that burst is absorbed.

---

# 66. Autoscaling Lag

Autoscaling is not instantaneous.

New instances may require:

- Scheduling
- Image download
- Initialization
- Configuration
- Health checks
- Cache warming
- Connection establishment

During this interval, a traffic spike can create backlog or elevated latency.

Therefore, systems with sharp bursts may require:

- Pre-scaling
- Overprovisioning
- Queue buffering
- Faster startup
- Predictive scaling
- Admission control

---

# 67. Utilization and Saturation

Utilization can be represented as:

Utilization =
Arrival rate / Service capacity

Examples:

- 5,000 / 10,000 = 50%
- 8,000 / 10,000 = 80%
- 9,500 / 10,000 = 95%
- 10,000 / 10,000 = 100%

Near saturation, queueing and latency can increase sharply.

Therefore, "the machine can theoretically process 100,000 QPS" does not imply that operating continuously at 100,000 QPS is a good production design.

---

# 68. End-to-End Estimation Workflow

A reusable workflow is:

## Step 1: Define the population

Estimate:

- Registered users
- Devices
- Tenants
- Documents
- Producers

## Step 2: Estimate active population

Determine:

- DAU
- MAU
- Concurrent users
- Active devices

## Step 3: Estimate activity

Determine:

- Requests/user/day
- Reads/user/day
- Writes/user/day
- Events/device/second

## Step 4: Convert to daily volume

Calculate:

Total actions/day

## Step 5: Convert to average QPS

Divide by:

86,400 seconds/day

## Step 6: Estimate peak

Apply:

Peak multiplier

## Step 7: Split the workload

Estimate:

- Reads
- Writes
- Queries
- Transactions
- Events

## Step 8: Trace amplification

Estimate:

- Downstream calls/request
- Queries/request
- Retry attempts
- Fan-out
- Broadcast

## Step 9: Estimate storage

Calculate:

- Record size
- Daily growth
- Retention
- Indexes
- Metadata
- Replication
- Compression

## Step 10: Estimate bandwidth

Calculate:

- Request bandwidth
- Response bandwidth
- Replication bandwidth
- Queue bandwidth
- Cross-region traffic

## Step 11: Estimate compute

Use:

- CPU/request
- Memory/request
- QPS/instance
- IOPS
- Connection limits

## Step 12: Add production constraints

Account for:

- Headroom
- Failure
- Redundancy
- Autoscaling lag
- Retries
- Uneven traffic

## Step 13: Perform sanity checks

Ask:

- Is peak greater than average?
- Are units consistent?
- Is physical storage greater than logical storage when replication exists?
- Does a 95% cache hit rate actually leave 5% backend traffic?
- Does downstream QPS reflect fan-out?
- Are partition-level hot spots possible?
- Is the result within a plausible order of magnitude?

---

# 69. Common Estimation Mistakes

## Mistake: Using registered users as traffic

Registered users do not necessarily represent active users.

Use an active fraction.

## Mistake: Ignoring peak traffic

Daily average traffic can dramatically understate instantaneous load.

Use a peak model.

## Mistake: Confusing bits and bytes

Network rates and storage rates use different units.

Always convert explicitly.

## Mistake: Ignoring replication

Logical storage and physical storage are different.

## Mistake: Ignoring indexes

Indexes can consume substantial storage and write bandwidth.

## Mistake: Assuming one API request equals one database query

Internal amplification can be significant.

## Mistake: Assuming perfect caching

Cache misses still reach the backend.

## Mistake: Ignoring retries

The service sees attempts, not merely original user requests.

## Mistake: Ignoring hot partitions

Average cluster load can hide a single overloaded shard.

## Mistake: Sizing at exactly the calculated demand

Capacity needs headroom.

## Mistake: Treating benchmark results as universal

Benchmark performance depends on workload and operating conditions.

## Mistake: Looking only at average latency

Tail latency often controls user experience and timeout behavior.

---

# 70. Limitations of Back-of-the-Envelope Estimates

These calculations are intentionally simplified.

They generally do not model:

- Detailed CPU instruction behavior
- Exact database query plans
- Garbage collection
- Network topology
- Packet-level behavior
- Kernel scheduling
- Storage-engine internals
- Cache eviction distributions
- Exact percentile behavior
- Correlated failures
- Real cloud pricing
- Detailed autoscaler behavior
- Protocol-specific replication algorithms

The estimates are therefore architectural approximations, not production benchmarks.

A useful estimate determines the scale of a problem. Benchmarking and load testing determine actual system behavior.

---

# 71. Production Considerations

A production capacity model should distinguish:

### Demand

What the workload requires.

### Effective capacity

What a resource can sustainably handle.

### Target utilization

How close the resource should operate to saturation.

### Headroom

Additional capacity for uncertainty and bursts.

### Redundancy

Capacity required to survive failures.

### Growth

Future expected workload.

A useful conceptual equation is:

Production capacity ≈
Future peak demand × Headroom + Failure capacity

The exact formula depends on the redundancy strategy.

---

# 72. Security Considerations Relevant to Capacity

Security controls can create additional system load.

Examples include:

- Authentication
- Authorization
- TLS
- Encryption
- Rate limiting
- Abuse detection
- DDoS protection
- Audit logging
- Fraud detection
- Token validation

Security should therefore be considered when estimating:

- CPU
- Memory
- Network
- Storage
- QPS
- Latency

Rate limiting also protects capacity by preventing abusive traffic from consuming all resources.

---

# 73. Reliability Considerations

Reliability mechanisms themselves consume resources.

Replication creates:

- Storage amplification
- Network amplification
- Write amplification

Retries create:

- Request amplification
- CPU amplification
- Database amplification

Monitoring creates:

- Metrics
- Logs
- Traces
- Storage
- Network traffic

Backups create:

- Storage
- Network traffic
- CPU
- Recovery work

A complete system estimate includes the cost of the mechanisms that make the system reliable.

---

# 74. Architectural Bottleneck Identification

Once estimates are calculated, compare the resulting requirements against each layer's capacity.

Potential bottlenecks include:

- CPU
- Memory
- Network
- Database writes
- Database reads
- Storage capacity
- Storage IOPS
- Cache memory
- Cache QPS
- Queue throughput
- Partition throughput
- Connection limits
- Cross-region bandwidth

The most important result of estimation is often not a server count. It is identifying which resource will become the bottleneck first.

---

# 75. Why Layer-by-Layer Estimation Matters

Consider a service receiving:

20,000 API requests/s.

Suppose every request causes:

- 4 database queries
- 2 cache operations
- 1 event
- 5 log lines

Then one external request creates a much larger internal workload.

Database:

20,000 × 4
= 80,000 queries/s

Events:

20,000 events/s

Logs:

20,000 × 5
= 100,000 log lines/s

The architecture must therefore be sized according to the workload generated at each layer.

---

# 76. Complete System Example

The final integrated example in the script models a global content application.

Its estimation chain is:

1. 500 million registered users
2. 10% daily active
3. 40 reads/user/day
4. 0.2 writes/user/day
5. 8x peak
6. 3 KB records
7. 50% metadata/index overhead
8. 3x replication
9. 365-day retention
10. 25 KB responses
11. Two downstream calls/request
12. 92% cache hit rate

The example calculates:

- Active users
- Read traffic
- Write traffic
- Average QPS
- Peak QPS
- Downstream QPS
- Cache-miss QPS
- Logical storage
- Physical storage
- Network bandwidth

This demonstrates the central discipline of system-design estimation: follow the workload through the architecture.

---

# 77. Practical Mental Models

Several relationships are especially valuable to remember.

## Daily volume to QPS

QPS ≈ Daily requests / 86,400

## Peak traffic

Peak ≈ Average × Peak multiplier

## Read/write split

Reads = Total × Read fraction

Writes = Total × Write fraction

## Storage

Storage ≈ Writes × Record size × Retention

## Replicated storage

Physical storage ≈ Logical storage × Replication factor

## Bandwidth

Bytes/s ≈ QPS × Bytes/request

## Cache miss traffic

Backend QPS ≈ Total QPS × (1 − Hit rate)

## Fan-out

Downstream QPS ≈ Incoming QPS × Calls/request

## Concurrency

Concurrency ≈ QPS × Latency

## Queue backlog growth

Backlog growth ≈ Arrival rate − Processing rate

## Utilization

Utilization ≈ Demand / Capacity

These relationships form the foundation for more detailed system models.

---

# 78. Implementation Structure of the Python Script

The script is organized from basic calculations toward increasingly complex models.

The early sections implement:

- Unit conversion
- QPS
- Storage
- Bandwidth
- Growth

Intermediate sections implement:

- Traffic models
- Read/write ratios
- Caching
- Fan-out
- Queues
- CPU capacity
- Database capacity
- IOPS
- Availability
- Replication

Advanced sections implement:

- Sharding
- Hot partitions
- Retry amplification
- Autoscaling lag
- Cross-region replication
- Telemetry cardinality
- WebSocket concurrency
- Connection memory
- Lock contention
- Batch transfer

The final examples combine multiple assumptions into integrated system estimates.

---

# 79. Validation and Testing

The script contains built-in tests for important formulas.

They verify:

- Unit conversion
- Daily-to-QPS conversion
- Peak multiplication
- Read/write splitting
- Storage calculations
- Bandwidth
- Little's Law
- Queue drain time
- Availability
- Percentiles
- Storage models
- Cache behavior

The tests use Python assertions and standard-library functionality, so no external testing package is required.

The script also explicitly tests invalid inputs such as:

- Negative QPS
- Invalid cache hit rates
- Negative retention
- Queues that cannot drain

Input validation is important because incorrect assumptions can otherwise silently produce nonsensical capacity calculations.

---

# 80. Edge Cases

Important edge cases include:

### Zero traffic

A zero workload should result in zero QPS rather than an error.

### Zero latency

Little's Law gives zero modeled concurrency when latency is zero.

### 100% cache hit

The modeled backend traffic becomes zero.

Real caches may still receive invalidation, refresh, management, and write traffic.

### 0% cache hit

All modeled traffic reaches the backend.

### Processing rate equal to arrival rate

The queue does not drain an existing backlog.

### Processing rate below arrival rate

The queue grows rather than draining.

### Negative quantities

Negative users, QPS, storage, or retention are invalid and should be rejected.

---

# 81. Estimation Versus Measurement

Estimation answers:

"Approximately what scale should I design for?"

Measurement answers:

"What does this implementation actually do under this workload?"

Estimation is appropriate for:

- Initial architecture
- Capacity discussions
- Design interviews
- Early feasibility analysis
- Identifying likely bottlenecks

Measurement is required for:

- Final capacity limits
- Production tuning
- Database benchmarks
- Latency objectives
- Hardware selection
- Performance regression detection

A sensible workflow is to estimate first, implement, benchmark, observe, and then refine the model.

---

# 82. Real-World Relevance

Back-of-the-envelope estimation is applicable to nearly every large-scale architecture.

It is useful when designing:

- URL shorteners
- Social feeds
- Messaging systems
- Search engines
- Video platforms
- File-sharing services
- E-commerce platforms
- IoT systems
- Monitoring systems
- Notification systems
- Payment platforms
- Recommendation systems
- Analytics pipelines
- Distributed databases
- Event-driven architectures

The same quantitative primitives recur even when the underlying technologies differ.

---

# 83. Central Engineering Distinctions

Several distinctions should remain explicit during system design.

| Concept | Distinction |
|---|---|
| Registered users vs active users | Population is not workload |
| Average QPS vs peak QPS | Average does not represent instantaneous load |
| Logical vs physical storage | Replication and overhead increase physical capacity |
| Bits vs bytes | Network and storage units differ |
| Request rate vs database rate | Internal amplification can be substantial |
| Cache hits vs cache misses | Only misses necessarily reach the modeled backend |
| Capacity vs utilization | Theoretical maximum is not necessarily sustainable production load |
| Availability vs redundancy | More replicas help only against failures they are independent of |
| Latency average vs percentile | Tail behavior can dominate user experience |
| Arrival rate vs processing rate | Persistent overload creates backlog |
| Storage capacity vs IOPS | Enough space does not guarantee enough performance |
| External QPS vs internal QPS | Fan-out can multiply internal traffic |

---

# 84. Quantitative Design Discipline

A reliable estimation process follows a simple discipline:

1. State an assumption.
2. Attach a unit.
3. Perform one transformation.
4. Record the result.
5. Propagate it to the next layer.
6. Check its magnitude.
7. Identify uncertainty.
8. Add production constraints.

For example:

Users
→ Active users
→ Actions/day
→ Average QPS
→ Peak QPS
→ Read/write QPS
→ Downstream QPS
→ Storage
→ Bandwidth
→ Compute
→ Replication
→ Headroom
→ Failure capacity

This structure makes complex system-design calculations manageable and reviewable.
