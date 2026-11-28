# Metrics Engineering: Counters, Gauges, Histograms and SLIs

## 1. Metrics in Observability Engineering

Metrics are numerical measurements collected from applications, infrastructure, databases, networks and distributed services.

They provide an aggregated representation of system behaviour over time.

A production monitoring system uses metrics to answer questions such as:

- How many HTTP requests has a service processed?
- How many requests are currently active?
- What is the distribution of request latency?
- What percentage of requests completed successfully?
- Is the service meeting its availability objective?
- How much error budget remains?

Metrics are different from logs and traces.

| Observability signal | Primary purpose | Typical information |
|---|---|---|
| Metrics | Quantify system behaviour | Request rate, latency, CPU utilisation |
| Logs | Record individual events | Exceptions, authentication failures |
| Traces | Describe distributed execution | Service-to-service request paths |

Metrics are particularly useful for aggregation, alerting, capacity planning and service-level reporting.

## 2. Metric Fundamentals

A metric is identified by its name and associated attributes.

A metric time series consists of:

- Metric name
- Label values
- Timestamp
- Numerical measurement

For example:

`http_requests_total{method="GET",status="200"}`

This represents the number of successful GET requests.

A collection of measurements forms a time series.

Metric names should communicate the measured quantity. Units should be explicit where possible.

Common naming conventions include:

| Metric | Meaning | Unit |
|---|---|---|
| `http_requests_total` | HTTP request count | Requests |
| `http_request_duration_seconds` | Request duration | Seconds |
| `http_active_requests` | Active requests | Requests |
| `process_memory_bytes` | Memory consumption | Bytes |
| `database_connections_active` | Active connections | Connections |

A counter commonly uses the `_total` suffix. Duration metrics should specify their time unit.

## 3. Counters

A counter measures the accumulated number of occurrences of an event.

Its value increases monotonically during a process lifetime.

A counter must not decrease through normal application instrumentation.

Examples:

- HTTP requests received
- Database queries executed
- Authentication failures
- Payment transactions processed
- Messages successfully published

### 3.1 Counter mechanics

A counter maintains a numerical value.

For each qualifying event:

`counter = counter + increment`

For example:

| Event | Counter value |
|---|---:|
| Initial state | 0 |
| First request | 1 |
| Second request | 2 |
| Five additional requests | 7 |

Counters are appropriate for event totals, not current resource quantities.

### 3.2 Rates and counter resets

A counter value alone does not provide a request rate.

The average event rate over an interval can be calculated as:

`rate = change in counter / elapsed time`

For example, an increase from 1,000 to 1,600 requests over 60 seconds produces an average rate of 10 requests per second.

Monitoring systems must account for counter resets caused by application restarts.

For distributed services, measurements from different instances should be aggregated carefully to avoid duplicate counting.

### 3.3 Implementation

The Python implementation provides a thread-safe `Counter` class.

The JavaScript implementation uses a `Map` to maintain independent values for label combinations.

The C++ implementation uses ordered maps and mutex protection.

The Java implementation uses `ConcurrentHashMap` and `DoubleAdder` to support concurrent updates.

The PostgreSQL implementation stores increments in `metric_samples` and aggregates them through `counter_totals`.

## 4. Gauges

A gauge measures a value that can increase or decrease.

Unlike counters, gauges represent a current state or measurement.

Examples:

- Active HTTP requests
- Current database connections
- Queue depth
- CPU utilisation
- Memory consumption
- Number of active sessions

### 4.1 Gauge operations

A gauge generally supports three operations:

| Operation | Behaviour |
|---|---|
| Set | Replace the current value |
| Increment | Increase the value |
| Decrement | Decrease the value |

Consider a database connection pool.

| Event | Active connections |
|---|---:|
| Initial state | 0 |
| Connection opened | 1 |
| Another connection opened | 2 |
| Connection closed | 1 |

A gauge is appropriate because the measured quantity represents current state rather than accumulated activity.

### 4.2 Concurrency considerations

Concurrent requests may modify a gauge simultaneously.

An ordinary non-atomic read-modify-write operation can lose updates.

The implementations use:

- Python locks
- JavaScript's single-threaded event loop for synchronous metric updates
- C++ mutexes
- Java atomic references

For distributed services, a gauge is normally reported separately by each service instance. Summation, averaging and maximum aggregation must reflect the meaning of the measurement.

## 5. Histograms

A histogram represents the distribution of observed numerical values.

It is particularly useful for measuring latency, response time, payload sizes and processing durations.

A histogram generally maintains:

1. Observation count
2. Observation sum
3. Cumulative bucket counts

### 5.1 Bucket boundaries

Consider a request latency histogram with these boundaries:

`0.05, 0.10, 0.25, 0.50, 1.00, 2.00, 5.00`

The values represent seconds.

Suppose the observations are:

| Observation | Latency |
|---|---:|
| 1 | 0.04 |
| 2 | 0.08 |
| 3 | 0.12 |
| 4 | 0.30 |
| 5 | 0.80 |

The resulting cumulative histogram is:

| Upper boundary | Cumulative count |
|---|---:|
| 0.05 | 1 |
| 0.10 | 2 |
| 0.25 | 3 |
| 0.50 | 4 |
| 1.00 | 5 |
| 2.00 | 5 |
| 5.00 | 5 |
| +Inf | 5 |

Cumulative buckets include all observations less than or equal to the specified boundary.

The positive-infinity bucket includes every valid observation.

### 5.2 Histogram calculations

The observation count is:

`count = number of observations`

The observation sum is:

`sum = sum of all observations`

The arithmetic mean is:

`mean = sum / count`

Histograms provide more information than a simple average because they preserve distribution information through buckets.

### 5.3 Percentiles

A percentile identifies a position within an ordered distribution.

Common latency percentiles include:

- P50: median latency
- P90: latency below which approximately 90% of observations fall
- P95: latency below which approximately 95% of observations fall
- P99: latency below which approximately 99% of observations fall

A P95 latency of 250 milliseconds indicates that approximately 95% of measured requests completed within that duration.

Histogram buckets do not automatically provide exact percentiles. Estimation requires an appropriate quantile calculation.

The source implementations retain bounded local samples for percentile estimation. This is an educational implementation, not an exact long-term histogram storage strategy.

In a production monitoring system, histogram buckets are usually aggregated across instances. Quantiles should be calculated from the aggregated distribution rather than by averaging independently calculated instance percentiles.

### 5.4 Histogram versus summary

| Property | Histogram | Summary |
|---|---|---|
| Distribution buckets | Yes | Not necessarily |
| Cross-instance aggregation | Supported | Generally difficult |
| Quantile calculation | Centralised from buckets | Often calculated locally |
| Storage characteristics | Bucket counts and sum | Quantile estimates and statistics |
| Typical use | Distributed latency monitoring | Local distribution analysis |

Histogram bucket selection is an engineering decision.

Too few buckets reduce resolution. Too many increase storage, processing and cardinality costs.

## 6. Metric Labels and Cardinality

Labels provide dimensions for metric analysis.

For example:

`http_requests_total{method="POST",status="500"}`

This allows request counts to be separated by HTTP method and response status.

Useful dimensions include:

- Service
- Environment
- HTTP method
- HTTP status
- Region
- Operation type

### 6.1 Cardinality

Cardinality refers to the number of distinct metric time series.

If a metric has three label dimensions with 5, 6 and 4 possible values, its maximum theoretical combination count is:

`5 × 6 × 4 = 120`

Adding high-cardinality labels can cause significant resource consumption.

Avoid using:

- User IDs
- Session IDs
- Request IDs
- Email addresses
- Unrestricted URLs
- Arbitrary exception messages

These values can create enormous numbers of time series.

The Python, JavaScript, C++ and Java implementations validate metric labels and restrict their number.

The SQL implementation stores label schemas as JSONB and validates sample labels against their metric definitions.

Production systems should also impose retention limits, ingestion quotas and restrictions on metric creation.

## 7. Service Level Indicators

A Service Level Indicator (SLI) is a quantitative measurement of a service's performance against a particular reliability characteristic.

Examples include:

- Availability
- Successful request ratio
- Request latency
- Data processing correctness
- Message delivery success
- Storage durability

An SLI should define exactly what is measured, which events are eligible and the evaluation period.

### 7.1 Availability SLI

A common availability SLI is:

`Availability SLI = Good events / Total eligible events`

Suppose a service receives 10,000 eligible requests and 9,990 are successful.

The availability is:

`9,990 / 10,000 = 0.999`

Expressed as a percentage:

`99.9%`

The numerator and denominator must use consistent eligibility rules.

A request that is excluded from the denominator must not be counted as a good event in the numerator.

### 7.2 Latency SLI

A latency SLI measures the proportion of eligible requests satisfying a defined response-time threshold.

For example:

`Latency SLI = Requests completed within 300 ms / Total eligible requests`

If 9,600 of 10,000 requests complete within 300 milliseconds:

`Latency SLI = 96%`

This is different from average latency.

An average can conceal a small but important group of extremely slow requests.

## 8. Service Level Objectives

A Service Level Objective (SLO) is a reliability target defined for an SLI over a specified period.

Example:

| Property | Value |
|---|---|
| Service | Payment API |
| SLI | Successful request ratio |
| SLO target | 99.9% |
| Evaluation period | 30 days |
| Error budget | 0.1% |

The SLO defines the acceptable service performance.

A measurement that satisfies the target is compliant for the evaluated window.

A measurement below the target indicates an SLO breach.

An SLO is not the same as an SLA.

| Concept | Meaning |
|---|---|
| SLI | Actual quantitative measurement |
| SLO | Internal or operational reliability target |
| SLA | Formal service commitment, often involving contractual consequences |

## 9. Error Budgets

An error budget represents the permitted unreliability associated with an SLO.

The basic calculation is:

`Error budget = 1 - SLO target`

For a 99.9% availability target:

`Error budget = 1 - 0.999 = 0.001`

This represents 0.1% of eligible events.

For 100,000 eligible requests, the permitted unsuccessful requests are:

`100,000 × 0.001 = 100`

If 80 requests fail, 20 failures remain within the event-based error budget.

Error budgets support operational decisions about release frequency, reliability improvements and risk management.

An event-based error budget is different from a time-based availability budget. The measurement method must match the SLI definition.

## 10. Evaluation Windows

SLIs and SLOs must specify an evaluation period.

Common windows include:

- 5 minutes
- 1 hour
- 24 hours
- 7 days
- 28 days
- 30 days

A short window detects sudden deterioration.

A longer window provides a broader reliability assessment.

Rolling windows continuously evaluate the latest period.

For example, a rolling 30-day availability SLO evaluates the most recent 30 days rather than a fixed calendar month.

The JavaScript implementation includes an event-based rolling window with automatic expiry.

The SQL implementation stores evaluation start and end timestamps and maintains historical results.

## 11. Architecture and Workflow

The five source implementations represent a metrics collection and evaluation architecture.

    Application
        |
        v
    Instrumentation
        |
        +------------------+
        |                  |
        v                  v
    Counter              Gauge
        |                  |
        +---------+--------+
                  |
                  v
              Histogram
                  |
                  v
           Metrics Registry
                  |
                  v
           Metric Snapshot
                  |
                  v
            SLI Calculation
                  |
                  v
            SLO Evaluation
                  |
          +-------+-------+
          |               |
          v               v
       Healthy          Breached
          |               |
          v               v
     Normal service   Reliability review

The workflow separates measurement collection from reliability evaluation.

Application instrumentation records events and resource states.

The registry manages metric definitions and their observations.

SLI evaluation converts the collected measurements into service reliability indicators.

SLO policies determine whether the measured performance satisfies the required target.

## 12. Python Implementation

The Python file implements a complete metrics collection simulation.

### Main components

| Component | Responsibility |
|---|---|
| `Metric` | Common metric metadata |
| `Counter` | Accumulated event counts |
| `Gauge` | Current numerical state |
| `Histogram` | Observation distribution |
| `MetricsRegistry` | Metric registration and snapshots |
| `SLI` | Ratio-based reliability evaluation |
| `ServiceMetrics` | HTTP request instrumentation |

### Engineering decisions

The implementation uses dataclasses, enums, dictionaries and standard-library synchronization.

A registry prevents duplicate metric names.

Counters reject zero and negative increments.

Gauges permit positive and negative changes.

Histograms validate bucket boundaries and retain observations for percentile estimation.

The HTTP instrumentation measures execution duration with `time.perf_counter()`.

The active request gauge is decremented in a `finally` block, ensuring cleanup even when an operation fails.

The registry exports a JSON snapshot using an atomic file replacement pattern.

The script also includes unit tests for metric operations, invalid observations, percentile calculations and SLI evaluation.

Execution:

- Python 3.10 or later
- Standard library only
- Run the file directly using Python.

The demonstration creates `metrics_snapshot.json` in the working directory.

## 13. JavaScript Implementation

The JavaScript implementation adopts an event-driven architecture.

### Main components

| Component | Responsibility |
|---|---|
| `Metric` | Base validation and label management |
| `Counter` | Event accumulation |
| `Gauge` | State measurement |
| `Histogram` | Distribution tracking |
| `Registry` | Metric management |
| `SLIWindow` | Rolling-window SLI evaluation |
| `ServiceInstrumentation` | Asynchronous request monitoring |

The implementation uses `Map` for metric storage and `EventEmitter` for event-driven updates.

Request instrumentation supports asynchronous operations through `async` and `await`.

The `finally` block guarantees that active request counts are decremented after success or failure.

Request failures are emitted separately from completed-request measurements.

The rolling SLI implementation removes expired events before evaluating the current window.

Histogram sample retention is bounded to reduce unbounded memory growth.

The JSON export uses asynchronous file operations.

Execution:

- Node.js 18 or later
- Node.js standard library
- No npm dependencies

Run the file directly with Node.js.

## 14. C++17 Implementation

The C++ implementation focuses on explicit domain modelling and thread-safe metric storage.

### Main components

| Component | Responsibility |
|---|---|
| `Metric` | Shared metric definition |
| `Counter` | Monotonic event accumulation |
| `Gauge` | Current numerical state |
| `Histogram` | Cumulative bucket observations |
| `ServiceLevelIndicator` | Reliability ratio evaluation |
| `RepositoryMetrics` | Application instrumentation |

The implementation uses:

- STL maps
- Sets
- Vectors
- Optional values
- Mutexes
- Exceptions
- Enumerations

Mutexes protect mutable metric collections.

The histogram uses cumulative buckets and bounded local samples.

`std::optional` distinguishes unavailable percentile or SLI results from valid numerical zero values.

The implementation demonstrates explicit validation and exception handling.

Compilation:

- C++17 compiler
- No external libraries
- Compile using the C++17 language standard.

## 15. Java 17 Implementation

The Java implementation models metrics as enterprise monitoring components.

### Main components

| Component | Responsibility |
|---|---|
| `Metric` | Common metric interface |
| `MetricKey` | Immutable label identity |
| `Counter` | Concurrent event accumulation |
| `Gauge` | Atomic state updates |
| `Histogram` | Distribution measurements |
| `SLIPolicy` | SLI target evaluation |
| `ServiceLevelObjective` | SLO and error-budget rules |
| `MetricsRegistry` | Metric registration |
| `MonitoringService` | Application instrumentation |

Java records represent immutable metric keys and evaluation results.

`ConcurrentHashMap` provides concurrent metric-series storage.

`DoubleAdder` and `LongAdder` support concurrent numerical updates.

`AtomicReference` provides atomic gauge updates.

The monitoring service records elapsed execution time using `System.nanoTime()`.

The SLO policy validates that its error budget corresponds to the specified reliability target.

The evaluation model distinguishes:

- Healthy
- Breached
- No data

No data is not automatically treated as a successful SLO result.

Compilation and execution require Java 17.

The program has no third-party dependencies.

## 16. PostgreSQL Implementation

The PostgreSQL implementation provides a relational persistence model for observability data.

### Database entities

| Table | Purpose |
|---|---|
| `services` | Application service registry |
| `metric_definitions` | Metric metadata and label schemas |
| `metric_samples` | Timestamped metric observations |
| `histogram_buckets` | Histogram boundaries |
| `sli_definitions` | SLI measurement definitions |
| `slo_policies` | Reliability targets |
| `sli_evaluations` | Historical evaluation results |

### Integrity controls

The schema uses:

- Primary keys
- Foreign keys
- Unique constraints
- Check constraints
- Enumeration types
- Triggers
- Stored procedures
- JSONB validation
- Performance-oriented indexes

The `validate_metric_sample()` trigger verifies that metric observations conform to their registered label schema.

The histogram bucket trigger prevents bucket definitions from being assigned to non-histogram metrics and checks boundary ordering.

The `record_metric()` procedure centralises metric insertion.

### Reporting mechanisms

The implementation includes:

- `counter_totals` for event aggregation
- `latest_gauges` for current state retrieval
- `histogram_summary` for distribution statistics
- `histogram_bucket_counts()` for cumulative bucket analysis
- `evaluate_sli()` for reliability evaluation
- `slo_error_budget` for reliability reporting

The SQL model uses timestamp-based windows and persists historical evaluation results.

For a production deployment, metric ingestion should normally use partitioned tables, batch inserts, retention policies and appropriate aggregation intervals.

The sample schema uses one observation table for educational clarity. High-volume deployments require more specialised storage strategies.

## 17. Important Technical Distinctions

| Concept | Measurement behaviour | Primary application |
|---|---|---|
| Counter | Monotonically increasing | Event totals |
| Gauge | Increasing or decreasing | Current state |
| Histogram | Distribution of observations | Latency and size |
| SLI | Quantitative reliability measurement | Service performance |
| SLO | Defined reliability target | Operational governance |
| SLA | Formal service commitment | Contractual reliability |

These concepts are related but are not interchangeable.

Counters, gauges and histograms describe measurements.

SLIs interpret measurements as reliability indicators.

SLOs establish acceptable reliability thresholds.

SLAs establish formal service commitments.

## 18. Production Considerations and Limitations

### Data collection

Metrics should be collected at appropriate intervals and instrumented at meaningful application boundaries.

High-frequency collection increases processing and storage costs.

### Cardinality management

Unrestricted label values can produce excessive time-series growth.

Use controlled label dimensions and enforce ingestion limits.

### Counter resets

Counter resets must be handled when calculating rates across process restarts.

### Gauge semantics

A gauge should represent the intended measurement scope.

An instance-level connection count should not automatically be interpreted as a cluster-wide count.

### Histogram aggregation

Histogram buckets must use compatible boundaries before aggregation.

Do not average individual P95 values to calculate a fleet-wide P95.

### SLI eligibility

Define successful and eligible events consistently.

Different denominators produce different reliability measurements.

### Missing observations

Missing data should be represented explicitly.

A service without measurements cannot be assumed healthy.

### Storage and retention

High-volume systems require:

- Time-based partitioning
- Retention policies
- Downsampling
- Batch ingestion
- Query optimisation
- Historical aggregation

### Security

Metric labels and descriptions should not contain credentials, access tokens, personal information or confidential payloads.

Monitoring endpoints should have suitable authentication and network access controls.

### Operational alerts

Alerting should distinguish between temporary anomalies and sustained reliability degradation.

A breached SLO, an exhausted error budget and an immediate service outage represent different operational conditions.

## 19. Implementation Comparison

| Capability | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Counter | Yes | Yes | Yes | Yes | Yes |
| Gauge | Yes | Yes | Yes | Yes | Yes |
| Histogram | Yes | Yes | Yes | Yes | Yes |
| Percentile estimation | Yes | Yes | Yes | Yes | Bucket-based |
| SLI evaluation | Yes | Yes | Yes | Yes | Yes |
| SLO policy | Target | Target | Target | Explicit policy | Policy table |
| Error budget | Basic | Basic | Basic | Yes | Yes |
| Concurrency handling | Locks | Event loop | Mutexes | Concurrent collections | Transactions |
| Persistent storage | JSON | JSON | In-memory | In-memory | Relational |

The implementations use different engineering approaches while preserving the same underlying metric concepts.

The database implementation adds persistent historical records, while the programming-language implementations demonstrate in-process instrumentation, metric state management and reliability evaluation.
