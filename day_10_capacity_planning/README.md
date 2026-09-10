# Capacity planning: user growth, traffic projections, and infrastructure sizing

## Topic introduction

Capacity planning is the process of estimating how much computing, storage, network, database, caching, and processing capacity a system will require as workload changes.

The central problem is not simply determining how many servers are needed. A useful capacity plan connects several layers:

User growth → user behavior → workload → traffic → resource consumption → infrastructure capacity → performance → reliability → cost

A system can have a large user base and relatively low infrastructure demand if users are inactive. Conversely, a smaller user base can create substantial infrastructure demand if users generate frequent requests, perform expensive operations, upload large files, or trigger intensive background processing.

The Python script develops this relationship through executable examples and progressively more advanced capacity models.

## Fundamental terminology

### Workload

Workload represents the amount and type of work a system must perform.

Typical workload measurements include:

- Requests per second (RPS)
- Queries per second (QPS)
- Transactions per second (TPS)
- Jobs per second
- Messages per second
- Events per second
- Data processed per second
- Storage generated per day

Workload should be measured in units appropriate to the system being planned.

### Throughput

Throughput is the amount of work completed during a unit of time.

For a web API, throughput may be expressed as requests per second. For a database, queries per second or transactions per second may be more appropriate. For a background processing system, jobs per second may be the relevant measurement.

### Latency

Latency is the time required to complete an operation.

A service may have excellent average latency while still having poor tail latency. Capacity planning therefore commonly considers percentiles such as:

- P50
- P95
- P99

P95 means that approximately 95% of measured operations are at or below the reported latency, while the remaining approximately 5% take longer.

### Concurrency

Concurrency describes work being processed simultaneously.

A system handling 2,000 requests per second does not necessarily have 2,000 requests executing simultaneously. If requests complete quickly, concurrency can be much lower.

The relationship is illustrated by Little's Law:

L = λW

where:

- L is the average number of items in the system
- λ is the arrival rate
- W is the average time spent in the system

For example, 2,000 RPS with an average latency of 0.15 seconds corresponds to approximately:

2,000 × 0.15 = 300 concurrent requests

### Utilization

Utilization measures how much of an available resource is being consumed.

A simplified definition is:

Utilization = demand / capacity

A resource operating at 80% utilization is using approximately 80% of its available capacity.

Maximum theoretical utilization is generally not a good production target because workload varies and failures, bursts, scaling delays, and resource contention must be accommodated.

### Headroom

Headroom is deliberately unused capacity retained to handle uncertainty and changing demand.

For example, if expected demand is 5,000 RPS and a plan adds 25% headroom:

5,000 × 1.25 = 6,250 RPS

Headroom is not the same as failure redundancy. Headroom addresses demand uncertainty and operational variation, while redundancy addresses component failures.

### Saturation

Saturation occurs when a resource approaches its practical operating limit.

CPU, memory, network, disk I/O, database connections, connection pools, queue depth, and external service quotas can all become saturation points.

## User growth

User growth is the starting point for many capacity models, but user count alone is not sufficient to determine infrastructure requirements.

The script demonstrates two basic growth patterns.

### Linear growth

Linear growth assumes a constant absolute increase per period.

For example:

- Year 0: 100,000 users
- Year 1: 120,000 users
- Year 2: 140,000 users
- Year 3: 160,000 users

The increase is 20,000 users per period.

### Compound percentage growth

Percentage growth compounds over time.

With 20% annual growth:

- Year 0: 100,000
- Year 1: 120,000
- Year 2: 144,000
- Year 3: 172,800

This distinction is important because compound growth can cause infrastructure requirements to increase substantially over longer planning horizons.

### CAGR

Compound annual growth rate measures the annualized growth between two values.

The formula is:

CAGR = (ending value / starting value)^(1 / years) − 1

CAGR is useful for historical analysis and long-term planning, but it should not automatically be treated as a future prediction.

## Translating users into traffic

A capacity model becomes more useful when user counts are converted into actual activity.

A simple workload model is:

Daily requests = DAU × sessions per user per day × requests per session

For example:

- 250,000 DAU
- 2 sessions per user per day
- 25 requests per session

Daily requests become:

250,000 × 2 × 25 = 12,500,000 requests/day

Average RPS is then:

Average RPS = daily requests / 86,400

This produces approximately 145 RPS.

The script implements this relationship through the `UserBehavior` class.

## DAU, MAU, and user activity

Common user metrics include:

- DAU: Daily Active Users
- WAU: Weekly Active Users
- MAU: Monthly Active Users

MAU and DAU should not be treated as interchangeable.

The ratio:

DAU / MAU

is commonly used as an activity or engagement indicator.

Capacity planning needs the behavioral characteristics behind these metrics. Two applications with identical MAU can have dramatically different traffic if one has substantially more sessions and requests per session.

## Average traffic versus peak traffic

Average traffic is rarely sufficient for infrastructure sizing.

If average traffic is 1,000 RPS and historical behavior shows a 4× peak:

Peak RPS = 1,000 × 4 = 4,000 RPS

Peak-to-average ratios should ideally come from historical traffic measurements.

Important traffic dimensions include:

- Average load
- Daily peak
- Weekly peak
- Monthly peak
- Seasonal peak
- Launch events
- Marketing campaigns
- Flash sales
- Scheduled batch processing
- Unexpected bursts

The script demonstrates percentile calculations and peak multipliers.

## Percentiles

Percentiles provide a way to understand distributions.

P50 represents the median.

P95 represents a high-tail observation.

P99 focuses even more strongly on tail behavior.

Capacity analysis may use percentiles for both traffic and performance. For example, a planner may examine P95 RPS and P99 latency instead of relying only on averages.

Percentiles should be interpreted carefully because their accuracy depends on sampling methodology, aggregation interval, data quality, and the underlying monitoring system.

## Request mix

Not every request consumes the same amount of infrastructure.

A read endpoint might require:

- Low CPU
- Small memory footprint
- One database query
- One cache operation

A search endpoint might require:

- Higher CPU
- More memory
- Multiple database queries
- Multiple cache operations
- More network traffic

The script models request types using weighted request mixes.

If 70% of traffic is inexpensive and 10% is expensive, the total resource demand should be based on the weighted average rather than assuming every request has identical cost.

This is especially important when application functionality changes over time.

## Resource-based sizing

Infrastructure capacity is multidimensional.

Typical dimensions include:

- CPU
- Memory
- Disk
- Network
- Database capacity
- Database connections
- Cache capacity
- Queue capacity
- Worker capacity

A system can have sufficient CPU but insufficient memory.

It can have sufficient memory but insufficient database capacity.

It can have sufficient application servers but insufficient network bandwidth.

The effective infrastructure requirement is often determined by the binding constraint.

The script calculates required nodes independently for CPU, memory, disk, and network and then identifies the largest requirement.

## Sustainable capacity versus theoretical capacity

Infrastructure specifications often provide theoretical resource limits.

Production capacity should instead be based on sustainable performance under realistic conditions.

For example, a server might technically process 500 RPS, but if latency becomes unacceptable at 400 RPS, 500 RPS should not be considered the production operating capacity.

A load test should evaluate:

- Throughput
- P50 latency
- P95 latency
- P99 latency
- CPU utilization
- Memory utilization
- Error rate
- Database behavior
- Connection usage
- Network behavior
- Queue depth

The script uses these measurements to identify the highest tested point that remains within specified limits.

## Utilization targets

Suppose a server can sustainably process 300 RPS.

At a 70% utilization target:

Effective capacity = 300 × 0.70 = 210 RPS

If expected peak traffic is 1,000 RPS:

Required instances = ceil(1,000 / 210) = 5

The utilization target therefore converts theoretical or tested capacity into an operational planning capacity.

The appropriate target depends on workload characteristics.

CPU-intensive workloads, latency-sensitive applications, memory-sensitive applications, and bursty systems can require different operating margins.

## Headroom and safety margins

A plan can use headroom in several ways.

One approach is to increase expected demand:

Planned demand = expected demand × (1 + headroom)

Another approach is to reduce usable capacity:

Planned operating capacity = tested maximum × (1 − reserve)

These approaches represent slightly different planning perspectives.

Headroom should account for uncertainty such as:

- Forecast error
- Traffic variability
- Unexpected workload changes
- Deployment effects
- Dependency degradation
- Autoscaling delay
- Resource fragmentation
- Operational events

Excessive headroom can create unnecessary cost, while insufficient headroom can increase reliability risk.

## Seasonal capacity planning

Traffic may vary significantly by time of year.

Examples include:

- Holiday commerce
- Tax-related applications
- Education enrollment
- Travel
- Financial reporting
- Sporting events
- Product launches

A seasonal model can combine:

Current workload × growth factor × seasonal multiplier

The script demonstrates this approach.

Historical seasonal patterns are generally preferable to arbitrary multipliers.

## Database capacity

Application RPS does not equal database QPS.

If an application receives 5,000 RPS and each request generates three database queries, the database may receive 15,000 queries per second before considering caching.

Caching can substantially reduce database read traffic.

For example, with a 70% cache hit rate:

Database reads may be approximately:

Application read traffic × 30%

Writes may still reach the database even when reads are cached.

Database capacity planning should consider:

- Read QPS
- Write QPS
- Transaction rate
- Query complexity
- CPU
- Memory
- Buffer/cache effectiveness
- Connection count
- Lock contention
- Storage IOPS
- Storage capacity
- Replication
- Replication lag
- Backup workload
- Recovery requirements

## Cache capacity

Caching introduces its own capacity requirements.

A cache needs sufficient:

- Memory
- Network throughput
- Operations per second
- Connections
- Replication capacity

Memory estimation can begin with:

Object count × average object size × replication factor × overhead

The script includes an overhead factor to account for metadata and memory-management inefficiencies.

Actual cache memory efficiency should be measured because object layout and implementation details can materially change consumption.

## Storage planning

Storage capacity is influenced by:

- Records generated per day
- Average record size
- Retention period
- Replication
- Compression
- Metadata
- Indexes
- Backups
- Snapshots
- Temporary storage

A basic logical storage calculation is:

Records/day × record size × retention

Physical storage can then incorporate replication and compression.

Long retention periods can produce large capacity requirements even when daily data generation appears modest.

## Network capacity

Network planning should account for both request and response payloads.

A basic model is:

Requests/second × total payload size × 8

The result must be converted into appropriate units such as Mbps or Gbps.

Network capacity should consider:

- Inbound traffic
- Outbound traffic
- Internal service-to-service traffic
- Database traffic
- Cache traffic
- Replication traffic
- Monitoring traffic
- Backup traffic
- Encryption overhead
- Network protocol overhead

## Little's Law and concurrency

Little's Law provides a powerful relationship between throughput, latency, and concurrency:

L = λW

For example:

- 2,000 requests/sec
- 150 ms average latency

Concurrency:

2,000 × 0.15 = 300

This relationship is useful for understanding:

- Connection pools
- Worker pools
- Thread pools
- Concurrent requests
- Queue depth
- Background processing

It should be applied to stable systems and with awareness of what the measured latency represents.

## Load testing

Load testing provides empirical evidence for capacity planning.

A capacity plan based only on hardware specifications is weaker than a plan supported by realistic load testing.

A useful load test varies workload and observes the resulting system behavior.

Important test points include:

- Low load
- Expected load
- Expected peak
- Forecast peak
- Stress load
- Sustained load
- Burst load
- Failure scenarios

The script defines a `LoadTestPoint` structure and evaluates each point against:

- Maximum P95 latency
- Maximum CPU utilization
- Maximum memory utilization
- Maximum error rate

The highest passing load is treated as the sustainable tested capacity.

## Capacity headroom after load testing

A load test might show that an application remains within its SLOs up to 2,000 RPS.

Operating continuously at 2,000 RPS would leave no margin for variation.

With a 25% reserve:

2,000 × (1 − 0.25) = 1,500 RPS

The application should therefore be treated as having approximately 1,500 RPS of planned operating capacity under this simplified model.

## Failure-aware capacity

Normal-state capacity is not necessarily sufficient.

If a service requires eight instances under normal conditions and must tolerate the loss of two instances:

Planned instances = 8 + 2 = 10

This simplified model demonstrates the principle behind redundancy.

Real architectures may require more sophisticated calculations involving:

- Availability zones
- Regions
- Rack failures
- Host failures
- Network failures
- Dependency failures
- Load-balancing behavior
- Replica placement

The important distinction is that redundancy is designed around failure scenarios, not ordinary traffic growth.

## N+1 and N+2

N+1 means one additional component beyond the normal requirement.

If N is 10:

N+1 = 11

N+2 = 12

These models are useful for reasoning about component-level resilience.

The appropriate failure reserve depends on business criticality and the failure scenarios the system must survive.

## Autoscaling

Autoscaling adjusts infrastructure based on changing workload.

A simplified policy may define:

- Minimum instances
- Maximum instances
- Target capacity per instance
- Scale-up threshold
- Scale-down threshold

The script demonstrates a simple RPS-based scaling decision.

Production autoscaling is more complicated because infrastructure has startup and shutdown delays.

Important considerations include:

- Scale-up delay
- Scale-down delay
- Cooldown periods
- Stabilization windows
- Warm instances
- Health checks
- Multiple metrics
- Scaling oscillation
- Maximum scaling rate
- Dependency capacity
- Cost controls

A service that can create application instances rapidly can behave very differently from one whose instances take several minutes to initialize.

## Moving-average forecasting

A moving average smooths historical observations.

For a three-period moving average:

Average = (current + previous + prior) / 3

Moving averages can reduce the impact of short-term noise.

They can also hide sudden changes if the window is too large.

The appropriate window depends on the planning problem and workload characteristics.

## Exponential smoothing

Exponential smoothing gives different weights to recent observations.

The basic update is:

Smoothed = α × current + (1 − α) × previous smoothed value

A larger alpha responds more strongly to recent changes.

A smaller alpha produces greater smoothing.

The script demonstrates multiple alpha values so the effect can be observed directly.

## Scenario planning

A single deterministic forecast creates false precision.

The script demonstrates:

- Conservative scenario
- Expected scenario
- Aggressive scenario

Each scenario combines:

- User growth
- Activity growth
- Peak multiplier

This is important because infrastructure demand can grow faster than user count when users also become more active.

For example:

User growth = 50%

Activity growth = 30%

The resulting request workload grows by:

1.50 × 1.30 = 1.95

The workload is approximately 95% higher even though the user population increased by only 50%.

## Forecast uncertainty

Forecasts should be treated as estimates rather than guarantees.

A useful capacity plan may include:

- Point forecast
- Downside scenario
- Expected scenario
- Upside scenario

The script demonstrates a simple planning range.

The range is not a statistical confidence interval. It is a scenario-based operational planning tool.

## Forecast accuracy

Forecast quality should be measured.

The script implements:

- Mean Absolute Percentage Error (MAPE)
- Root Mean Squared Error (RMSE)

MAPE expresses average error as a percentage.

RMSE gives greater weight to large errors because errors are squared before averaging.

Forecast metrics have limitations. MAPE becomes problematic when actual values are zero or very close to zero, and different metrics can produce different assessments of forecast quality.

## Burst traffic

A system may experience short-lived bursts much higher than sustained traffic.

For example:

- Sustained traffic: 2,000 RPS
- Burst multiplier: 5×
- Burst duration: 30 seconds

Burst traffic:

2,000 × 5 = 10,000 RPS

The additional traffic above the sustained rate creates excess work that may need to be absorbed by:

- Extra application capacity
- Queues
- Buffers
- Caches
- Rate limits
- Load shedding

Burst handling is particularly important for systems with slow autoscaling.

## Background workers

Asynchronous systems require capacity planning for worker processes.

A basic relationship is:

Required concurrency ≈ job arrival rate × processing time

For 150 jobs/sec with an average processing time of 2.5 seconds:

150 × 2.5 = 375 concurrent jobs

If workers are operated at 70% target utilization, additional worker capacity is required.

This concept applies to:

- Message consumers
- Job queues
- Image processing
- Video processing
- Report generation
- Data pipelines
- Email systems
- Batch processing

## Rate limiting

Rate limiting is both a security mechanism and a capacity-management mechanism.

If 50,000 users are each permitted 20 requests per minute:

50,000 × 20 / 60 ≈ 16,667 requests/sec

This represents a theoretical upper bound under the simplified uniform model.

Real traffic will not be perfectly uniform, so capacity should not automatically be sized exactly to the rate-limit ceiling.

Rate limits can protect infrastructure from:

- Accidental traffic spikes
- Abusive clients
- Runaway clients
- Retry storms
- API misuse
- Certain classes of denial-of-service traffic

## Multi-tier capacity planning

Modern systems rarely consist of only one server tier.

A typical architecture may include:

- Load balancers
- API servers
- Application servers
- Caches
- Databases
- Message queues
- Background workers
- Search infrastructure
- Object storage

Each tier can have a different workload multiplier and capacity constraint.

The script models this through `TierPlan`.

For example, one application request might create:

- One API operation
- Two database operations
- 1.5 cache operations on average
- 0.2 asynchronous jobs

The infrastructure plan must account for these relationships.

## Hourly traffic profiles

Daily averages can hide significant hourly differences.

An hourly traffic profile allows capacity to be evaluated at each point in the day.

This can reveal:

- Morning ramps
- Lunch-time peaks
- Evening peaks
- Overnight troughs
- Scheduled batch effects

Hourly planning is especially useful for systems with predictable daily traffic patterns.

## Data quality

Capacity planning depends on measurement quality.

Potential data problems include:

- Missing observations
- Negative values
- Incorrect timestamps
- Duplicate samples
- Monitoring gaps
- Aggregation errors
- Changes in instrumentation
- Artificial traffic
- Genuine extreme events

Statistical outlier detection can help identify unusual observations, but unusual observations should not automatically be deleted.

A large traffic spike might be a data error, or it might represent the exact production event the system must survive.

## Bottleneck analysis

The bottleneck is the resource most likely to constrain additional workload.

Possible bottlenecks include:

- CPU
- Memory
- Database connections
- Database CPU
- Disk I/O
- Network
- Cache memory
- Queue consumers
- External API quotas

The script ranks resources by utilization.

A resource at 93% utilization should generally receive more attention than one at 55%, assuming the measurements are comparable.

## Infrastructure option comparison

Different infrastructure configurations can produce different cost and capacity characteristics.

For example:

- Small instances may be inexpensive individually but require many instances.
- Large instances may provide greater capacity per unit but cost more individually.
- Medium instances may offer a better balance.

Capacity planning should compare:

- Effective capacity
- Instance count
- Monthly cost
- Failure-domain requirements
- Scaling granularity
- Startup time
- Resource utilization
- Operational complexity

The cheapest configuration is not necessarily the best configuration.

## Cost modeling

Infrastructure capacity has a financial dimension.

A basic monthly model can include:

- Application instances
- Databases
- Caches
- Load balancers
- Storage
- Network
- Monitoring
- Backup infrastructure

The script models each as a `CostComponent`.

Total monthly cost is the sum of component costs.

Capacity planning therefore supports both engineering and financial decisions.

## Cost per active user

A simple operational metric is:

Cost per MAU = monthly infrastructure cost / monthly active users

This can help compare infrastructure efficiency as the product grows.

Cost per user should not be interpreted independently from reliability, performance, and product requirements.

## Cost per million requests

Another useful metric is:

Cost per million requests = monthly infrastructure cost / monthly requests × 1,000,000

This can reveal whether infrastructure efficiency is improving as traffic increases.

## Multi-year capacity planning

The script includes a complete capacity worksheet that combines:

- Current user count
- User growth
- Activity growth
- Requests per user
- Peak multiplier
- Utilization target
- Instance capacity
- Minimum instances
- Failure reserve
- Additional headroom

The result is a period-by-period infrastructure forecast.

This provides a more realistic model than simply projecting user numbers.

## Availability and capacity

Availability targets affect infrastructure planning.

An availability SLO can be translated into an approximate downtime budget.

For example, with a simplified 30-day month:

99.9% availability allows approximately 43.2 minutes of downtime.

99.99% allows approximately 4.32 minutes.

Higher availability targets generally require more careful redundancy, failure handling, monitoring, testing, and operational capacity.

Capacity planning and availability planning are therefore related.

## Queue stability

For a simplified single-server queue:

Utilization = arrival rate / service rate

If arrivals occur at 80 jobs/sec and the service rate is 100 jobs/sec:

Utilization = 0.80

If arrivals reach 120 jobs/sec while service remains 100 jobs/sec:

Utilization = 1.20

A basic stable queue requires the service rate to exceed the arrival rate.

When arrival rate persistently exceeds service capacity, backlog grows.

This principle applies to:

- Message queues
- Background jobs
- Data pipelines
- Batch processing
- Network buffers
- Asynchronous APIs

## Capacity alerts

Capacity monitoring should identify multiple operating states.

The script demonstrates:

- Normal
- Warning
- Critical

A simple model may classify:

- Below 70%: normal
- 70% to below 90%: warning
- 90% and above: critical

Production alerting should also consider:

- Duration
- Rate of increase
- Time of day
- Historical baseline
- Dependency state
- Error rate
- Latency
- Queue depth

A short 91% utilization spike may be less important than a sustained 85% utilization trend accompanied by rapidly increasing traffic.

## Security considerations

Security controls can change capacity requirements.

### TLS

Encryption and decryption consume CPU and can affect connection handling and throughput.

### Web application firewalls

WAF inspection adds processing work and may introduce additional latency.

### Authentication

Authentication can require cryptographic operations, token validation, identity-provider requests, or database access.

### Rate limiting

Rate limiting reduces uncontrolled workload and can protect capacity.

### Audit logging

Security logging increases:

- Network traffic
- Storage consumption
- Processing requirements
- Retention requirements

### DDoS protection

Large traffic attacks can overwhelm infrastructure before normal application capacity is reached.

Capacity planning should therefore consider where traffic filtering occurs and which components absorb unwanted traffic.

Security capacity planning should not be separated completely from performance and reliability planning.

## Common mistakes

### Planning only from average traffic

Average traffic can be substantially lower than peak traffic.

### Assuming users equal requests

User counts become meaningful only after user behavior is translated into workload.

### Treating every request as identical

Different endpoints can have radically different resource requirements.

### Running infrastructure at maximum utilization

Maximum theoretical utilization leaves little margin for workload variability or failure.

### Ignoring dependencies

An application tier cannot exceed the sustainable capacity of a database or another critical dependency.

### Ignoring autoscaling delay

Autoscaling cannot instantly respond to every traffic spike.

### Ignoring failure scenarios

A system that is sufficient during normal operation may become overloaded after losing a node or availability zone.

### Treating forecasts as facts

Forecasts are assumptions with uncertainty.

### Removing all outliers

Large observations may represent genuine production demand.

### Optimizing only for cost

Capacity decisions should balance:

- Cost
- Performance
- Reliability
- Availability
- Scalability
- Operational complexity
- Business impact

## Edge cases

The Python script explicitly demonstrates several edge conditions.

Important cases include:

- Zero workload
- Zero daily events
- Single-observation percentile calculations
- Zero cache hit rate
- 100% cache hit rate
- Negative user counts
- Invalid utilization targets
- Invalid request mixes
- Zero infrastructure capacity
- Invalid growth rates
- Empty forecasting inputs

Input validation prevents invalid assumptions from silently producing misleading capacity estimates.

## Implementation considerations

The script uses Python standard-library functionality so the examples can be executed without external dependencies.

The implementation uses:

- Functions
- Dataclasses
- Type hints
- Validation
- Lists and dictionaries
- Mathematical calculations
- Sorting
- Percentile calculations
- Forecasting algorithms
- Load-test models
- Cost models
- Assertions
- Exception handling

The examples are deliberately separated into small functions so individual capacity concepts can be studied and modified independently.

## Production considerations

A real production capacity-planning process should maintain a documented relationship between:

1. Business growth
2. User activity
3. Workload
4. Resource consumption
5. Tested capacity
6. Operational capacity
7. Failure capacity
8. Forecast uncertainty
9. Infrastructure cost

Important production measurements include:

- Requests per second
- Requests by endpoint
- Requests by status code
- CPU utilization
- Memory utilization
- Disk utilization
- Disk IOPS
- Network throughput
- Database QPS
- Database CPU
- Database connections
- Cache hit rate
- Cache memory usage
- Queue depth
- Worker utilization
- P50 latency
- P95 latency
- P99 latency
- Error rate
- Autoscaling events
- Instance startup time

Capacity plans should be updated as real workload data changes.

## Important distinctions

| Concept | Meaning |
|---|---|
| Average traffic | Typical workload over a period |
| Peak traffic | Highest or near-highest workload |
| Burst traffic | Short-lived rapid increase |
| Headroom | Reserved capacity for uncertainty |
| Redundancy | Extra capacity for component failure |
| Theoretical capacity | Maximum based on specification or simplified model |
| Tested capacity | Capacity demonstrated through testing |
| Sustainable capacity | Capacity that can be maintained within operational limits |
| Autoscaling | Dynamically changing resource quantity |
| Forecasting | Estimating future workload |
| Bottleneck | Resource limiting overall capacity |
| Utilization | Demand divided by available capacity |

These concepts should not be treated as interchangeable.

## Key formulas

### Daily requests

DAU × sessions per user per day × requests per session

### Average RPS

Daily requests ÷ 86,400

### Peak RPS

Average RPS × peak multiplier

### Effective instance capacity

Tested capacity × target utilization

### Required instances

ceil(required workload ÷ effective instance capacity)

### Concurrency

RPS × latency in seconds

### Queue utilization

Arrival rate ÷ service rate

### CAGR

(Ending value ÷ starting value)^(1 / years) − 1

### Storage

Records/day × record size × retention × replication ÷ compression

### Bandwidth

Requests/sec × payload size × 8

### Cost per active user

Monthly infrastructure cost ÷ monthly active users

### Cost per million requests

Monthly infrastructure cost ÷ monthly requests × 1,000,000

## Practical capacity planning sequence

A technically sound planning process can follow this order:

1. Define the planning horizon.
2. Establish current user and workload measurements.
3. Model user growth.
4. Model changes in user behavior.
5. Translate behavior into workload.
6. Separate average, peak, seasonal, and burst traffic.
7. Identify request and workload types.
8. Estimate CPU, memory, network, storage, cache, database, and queue requirements.
9. Load test realistic workloads.
10. Identify sustainable capacity.
11. Apply utilization targets and headroom.
12. Add failure-domain requirements.
13. Model autoscaling behavior.
14. Forecast multiple scenarios.
15. Estimate infrastructure cost.
16. Monitor actual capacity consumption.
17. Compare forecasts against actual workload.
18. Recalculate the plan as assumptions change.

## End-to-end model represented in the script

The final example connects the complete chain:

Current DAU → annual growth → future DAU → sessions → requests → average RPS → peak RPS → instance sizing → failure reserve → monthly infrastructure cost

This is the core structure of practical capacity planning.

The model becomes more reliable when each assumption is replaced with measured production data, realistic load-test results, explicit SLOs, documented failure scenarios, and continuously updated forecasts.
