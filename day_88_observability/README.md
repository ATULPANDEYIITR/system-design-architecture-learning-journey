# Observability, Structured Logging and Centralized Logging

## 1. Observability Fundamentals

Observability is the ability to understand the internal state of a software system through the information it exposes during execution.

It supports investigation of known failures and discovery of unexpected behavior without requiring direct access to the internal implementation of every component.

Observability is commonly built around three complementary signal categories:

| Signal | Information captured | Operational purpose |
|---|---|---|
| Logs | Discrete events and their context | Explain what happened |
| Metrics | Numerical measurements over time | Identify trends and abnormal behavior |
| Traces | Relationships between operations | Locate latency and failures across services |

These signals provide different perspectives. A log records an event, a metric describes a measured condition, and a trace connects operations belonging to a distributed request.

For example, a payment transaction may generate:

- A request counter indicating transaction volume.
- A trace connecting the API, payment processor, and database.
- A structured log identifying a gateway timeout.

The implementations in this project concentrate on logging and the operational analysis that can be derived from collected log events.

## 2. Logging Architecture

Logging is the process of recording application events during execution.

A logging architecture generally contains the following stages:

1. Instrumentation produces events inside an application.
2. Event construction attaches metadata and contextual identifiers.
3. A filtering policy determines which events should be emitted.
4. An ingestion mechanism transfers events to a collection service.
5. Centralized storage makes events available for investigation.
6. Analytics and alert policies evaluate operational conditions.
7. Retention processes control the lifetime of stored events.

### Centralized architecture

Application services  
↓  
Structured event creation  
↓  
Severity filtering and data protection  
↓  
Log transport or ingestion  
↓  
Centralized log collector  
↓  
Storage and indexing  
↓  
Search, reporting and alert evaluation

A centralized logging system provides a common investigation point across independently deployed services.

Without centralization, an operator may need to access multiple machines, containers, or application instances to reconstruct a single failure.

Centralization does not automatically guarantee reliability. Transport failures, collector saturation, indexing delays, access restrictions, and retention policies must also be addressed.

## 3. Structured Logging

Structured logging represents each event as a collection of named fields instead of relying exclusively on free-form text.

A representative event contains:

| Field | Purpose |
|---|---|
| `timestamp` | Time when the event occurred |
| `severity` | Operational importance |
| `service` | Originating application |
| `environment` | Deployment environment |
| `version` | Application release |
| `event_name` | Stable event classification |
| `message` | Human-readable description |
| `trace_id` | Distributed operation identifier |
| `span_id` | Individual operation identifier |
| `correlation_id` | Business or workflow correlation |
| `request_id` | Individual request identifier |
| `attributes` | Additional structured information |

JSON is a common representation because it supports nested attributes and can be processed by different applications and storage systems.

A structured event is easier to filter and aggregate than a message that embeds every value in an unstructured sentence.

For example, an event named `payment.failed` can be searched independently of the wording of its message.

### Stable event naming

Event names should describe application behavior rather than reproduce a complete sentence.

Examples include:

| Event name | Meaning |
|---|---|
| `payment.started` | Payment processing began |
| `payment.completed` | Payment processing succeeded |
| `payment.failed` | Payment processing failed |
| `authentication.success` | Authentication succeeded |
| `authentication.failure` | Authentication failed |

Consistent naming improves query reliability and makes dashboards less dependent on changes in message wording.

### Structured attributes

Attributes provide event-specific information.

Examples include:

- Payment amount.
- Transaction identifier.
- Error classification.
- Operation duration.
- Processing status.

Attributes should have predictable names and types. Unbounded or inconsistent attributes make aggregation and indexing less efficient.

## 4. Severity and Filtering

Severity communicates the importance of a recorded event.

| Level | Numeric value | Intended use |
|---|---:|---|
| DEBUG | 10 | Detailed diagnostic information |
| INFO | 20 | Normal application operations |
| WARNING | 30 | Unexpected but recoverable conditions |
| ERROR | 40 | Failed operations |
| CRITICAL | 50 | Severe failures requiring immediate attention |

Severity filtering reduces unnecessary ingestion and storage.

For example, a production service may retain WARNING and higher events while a development environment retains DEBUG events.

Filtering must be applied carefully. Excessive filtering can remove the evidence required to investigate incidents.

A severity value is not a complete incident classification. An ERROR event does not necessarily mean that a business transaction was lost, and a WARNING event may indicate an important security condition.

## 5. Distributed Tracing and Correlation

A distributed application may execute one request across several services.

Consider an online payment:

Customer request  
↓  
API gateway  
↓  
Identity service  
↓  
Payment service  
↓  
Database  
↓  
Notification service

A trace identifier connects operations belonging to the same distributed execution.

A span identifier identifies an individual operation within that trace.

A correlation identifier can connect technical events to a broader business process, such as an order or payment workflow.

A request identifier distinguishes an individual request.

### Identifier distinctions

| Identifier | Scope |
|---|---|
| Trace ID | Distributed execution |
| Span ID | Individual operation |
| Correlation ID | Business workflow or related activity |
| Request ID | Individual request |

A trace ID should remain consistent across the participating services. Individual spans receive their own identifiers.

The Python implementation explicitly supplies immutable context objects to instrumented operations.

The JavaScript implementation uses `AsyncLocalStorage` to propagate context across asynchronous operations.

The C++ implementation models explicit context passing.

The Java implementation uses immutable records and creates child spans while retaining the parent trace and correlation identifiers.

The PostgreSQL implementation stores trace metadata separately from individual events and links the records through foreign keys.

Context propagation requires careful handling at service boundaries. Identifiers received from external requests should be validated, and untrusted values should not be used as authorization credentials.

## 6. Centralized Logging

Centralized logging collects events from multiple applications into a common processing and storage environment.

### Main responsibilities

**Collection**

Receives events from application instances and validates their structure.

**Transport**

Moves events from the source application to the central service. Transport may be synchronous or asynchronous.

**Processing**

Applies normalization, filtering, redaction, and enrichment policies.

**Storage**

Persists events for retrieval and investigation.

**Indexing**

Creates searchable access paths for timestamps, services, severity, trace identifiers, and selected attributes.

**Retention**

Controls how long events remain available.

**Analysis**

Supports service health reporting, incident investigation, and alert evaluation.

### Synchronous and asynchronous ingestion

Synchronous ingestion attempts to transfer each event as part of the application's execution path.

Its advantage is simpler delivery coordination. Its disadvantage is that a slow collector can increase application latency.

Asynchronous ingestion places events in a buffer or queue for later processing.

Its advantages include reduced coupling and better tolerance of temporary downstream delays.

It also introduces additional requirements:

- Queue capacity management.
- Backpressure handling.
- Shutdown draining.
- Duplicate detection.
- Delivery guarantees.
- Retry policies.
- Dead-letter handling.

The Python collector uses a bounded in-memory deque and locking.

The JavaScript pipeline uses an event-driven bounded queue and asynchronous flushing.

The C++ collector uses a bounded vector-based storage model.

The Java implementation uses a bounded blocking queue and a dedicated processing thread.

The PostgreSQL implementation provides transactional ingestion directly into relational storage.

These are educational implementations, not replacements for a durable distributed message broker or production log platform.

## 7. Data Protection and Redaction

Logs can contain sensitive information even when the application does not intentionally store it as a business record.

Examples include:

- Passwords.
- Access tokens.
- Refresh tokens.
- Authorization headers.
- API keys.
- Payment card information.
- Personal identifiers.
- Email addresses.

Sensitive values should be removed or transformed before centralized persistence.

The implementations demonstrate key-based redaction for sensitive attributes.

For example:

| Attribute | Stored value |
|---|---|
| `username` | `analyst` |
| `password` | `[REDACTED]` |
| `access_token` | `[REDACTED]` |
| `amount` | Original numerical value |

The Python implementation also replaces email addresses in message text.

The JavaScript implementation recursively processes nested objects and arrays.

The C++ implementation applies a key-based redaction policy to string attributes.

The Java implementation combines redaction with an attribute allowlist.

The PostgreSQL implementation uses a JSONB transformation function and a trigger before insertion.

### Security considerations

Redaction should happen as early as practical, before data enters persistent storage.

It should not be assumed that every sensitive value can be identified through key names. Free-text messages, nested objects, encoded data, and unexpected fields can contain confidential information.

Production systems should apply field-level access restrictions, encryption in transit, encryption at rest, audit logging, and controlled retention.

Log access should be treated as a security-sensitive privilege.

## 8. Python Implementation

The Python program provides an end-to-end simulation of an instrumented payment service and centralized event collector.

### Main components

| Component | Responsibility |
|---|---|
| `Severity` | Defines ordered severity levels |
| `LogContext` | Stores request and trace identifiers |
| `LogEvent` | Represents a structured event |
| `SensitiveDataRedactor` | Removes sensitive values |
| `StructuredLogger` | Constructs and filters events |
| `CentralLogCollector` | Stores and queries events |
| `InstrumentedService` | Generates payment events |
| `LogAnalytics` | Computes service statistics |
| `AlertRule` | Defines alert conditions |
| `AlertEngine` | Evaluates alert conditions |

### Important mechanisms

The `dataclass` declarations provide explicit domain structures.

`StructuredLogger` separates event construction from event storage.

`CentralLogCollector` uses a reentrant lock to protect concurrent access.

Its bounded deque prevents unlimited memory growth. Oldest events are discarded when the capacity is exceeded.

The query operation supports filtering by service, severity, trace ID, and event name.

The analytics component derives an error rate from recorded events.

The alert engine evaluates a service-level error-rate threshold subject to a minimum event count.

The demonstration includes successful payments, gateway failures, invalid amounts, and a security event containing sensitive attributes.

Assertions validate redaction, trace correlation, and alert behavior.

### Complexity considerations

For `n` retained events:

- Event insertion is approximately O(1).
- A complete in-memory query is O(n).
- Event distribution is O(n).
- Error-rate computation is O(n).
- Export serialization is O(n).

The implementation prioritizes clarity and bounded memory over persistent storage and distributed throughput.

## 9. JavaScript Implementation

The JavaScript program presents an asynchronous event-driven architecture.

### Main components

| Component | Responsibility |
|---|---|
| `ObservabilityContext` | Propagates asynchronous request context |
| `RedactionPolicy` | Recursively sanitizes structured data |
| `EventFactory` | Creates immutable log events |
| `CentralLogPipeline` | Accepts and processes events |
| `PaymentApplication` | Instruments payment processing |
| `OperationalAnalytics` | Calculates operational statistics |
| `AlertPolicy` | Defines alert conditions |

### AsyncLocalStorage

Node.js asynchronous execution may involve promises, callbacks, and nested operations.

Passing identifiers manually through every function can make context propagation difficult.

`AsyncLocalStorage` allows related asynchronous operations to access the context associated with their execution.

The payment application retrieves the current context when generating each event.

### Event-driven ingestion

The central pipeline extends `EventEmitter`.

It exposes events for:

- Accepted events.
- Successfully ingested events.
- Backpressure conditions.
- Pipeline shutdown.

The queue has a fixed maximum capacity. When the queue is full, the pipeline rejects new events rather than silently consuming unlimited memory.

The implementation also supports asynchronous flushing and JSON Lines export.

### Deduplication

The pipeline constructs a deterministic event key using trace, request, event name, and timestamp information.

Repeated events with the same key are ignored.

This is an in-memory demonstration. A production deduplication key should generally be supplied by the originating event producer and persisted across restarts.

### Failure handling

Payment processing distinguishes validation failures from simulated gateway failures.

The application records failed operations before propagating the exception.

The central pipeline reports buffer saturation rather than accepting events beyond its configured capacity.

## 10. C++17 Implementation

The C++ program focuses on explicit domain modeling and efficient in-memory governance.

### Main components

| Component | Responsibility |
|---|---|
| `Severity` | Ordered event classification |
| `TraceContext` | Distributed request identifiers |
| `LogEvent` | Event domain structure |
| `RedactionPolicy` | Attribute protection |
| `JsonSerializer` | JSON serialization |
| `CentralCollector` | Bounded centralized storage |
| `StructuredLogger` | Event construction and filtering |
| `PaymentService` | Instrumented application workflow |
| `ObservabilityEngine` | Metrics and alert evaluation |

### Domain modeling

The program uses structures for event and context data and classes for behavior that requires state or policy enforcement.

The collector uses an STL vector with reserved capacity.

This provides efficient sequential access and low allocation overhead for the bounded demonstration.

Filtering uses STL algorithms rather than embedding query logic throughout the application.

The JSON serializer explicitly escapes characters that have special meanings in JSON strings.

### Tradeoffs

A vector-based collector is suitable for a small bounded simulation.

A production collector may require:

- Concurrent queues.
- Persistent storage.
- Batch transmission.
- Compression.
- Network retry handling.
- Multi-process ingestion.
- Distributed indexing.

The implementation rejects events when its capacity is reached. This avoids uncontrolled memory growth but means that the caller must handle ingestion failure.

### Complexity

For `n` retained events:

- Insertion is amortized O(1) within the reserved capacity.
- Filtering is O(n).
- Event distribution is O(n log k) with ordered-map updates, where `k` is the number of distinct event names.
- Serialization is proportional to the event's total encoded size.

## 11. Java 17 Enterprise Implementation

The Java implementation models centralized logging as an enterprise service with explicit domain types and lifecycle management.

### Main components

| Component | Responsibility |
|---|---|
| `Severity` | Event classification |
| `Environment` | Deployment environment |
| `PipelineState` | Ingestion lifecycle |
| `TraceContext` | Immutable trace context |
| `LogEvent` | Immutable structured event |
| `RedactionPolicy` | Security policy |
| `StructuredEventFactory` | Event construction |
| `CentralLogService` | Asynchronous centralized ingestion |
| `ApplicationLogger` | Application logging interface |
| `PaymentService` | Business workflow |
| `AlertPolicy` | Alert configuration |
| `ObservabilityAnalytics` | Operational evaluation |

### Records and immutability

Java records provide concise immutable domain structures.

`TraceContext` prevents empty identifiers.

`LogEvent` validates mandatory attributes and stores an immutable copy of its metadata.

Immutability reduces accidental modification after event construction and makes event ownership clearer.

### Centralized ingestion

`CentralLogService` uses `ArrayBlockingQueue` to enforce a fixed queue capacity.

A dedicated worker thread consumes queued events and stores them in a synchronized collection.

The service maintains explicit lifecycle states:

- `RUNNING`: Events can be accepted.
- `DRAINING`: New events are rejected while existing events are processed.
- `CLOSED`: Processing has completed.

The `close()` method requests worker termination and waits for processing to finish.

This makes shutdown behavior part of the service contract rather than an incidental application detail.

### Enterprise policy enforcement

The Java redaction policy uses two controls:

1. A sensitive-key set for direct replacement.
2. An allowlist for permitted non-sensitive attributes.

Unknown attributes are omitted rather than automatically trusted.

This is more restrictive than a simple denylist.

The alert policy checks both a minimum event count and an error-rate threshold.

Insufficient data should not automatically be interpreted as a healthy service.

## 12. PostgreSQL Data Model

The PostgreSQL implementation provides a relational model for centralized event ingestion, tracing, service registration, and alert reporting.

### Entity relationships

Services  
→ Service Environments  
→ Log Events  
→ Trace Contexts

Services  
→ Alert Rules  
→ Alert Evaluations

Log Events  
→ Ingestion Audit

### Principal tables

| Table | Responsibility |
|---|---|
| `services` | Application service registry |
| `service_environments` | Deployment-specific configuration |
| `trace_contexts` | Trace and correlation metadata |
| `log_events` | Centralized structured event storage |
| `ingestion_audit` | Accepted, rejected, and duplicate events |
| `alert_rules` | Operational alert configuration |
| `alert_evaluations` | Recorded alert decisions |

### JSONB storage

The `attributes` column uses PostgreSQL `JSONB`.

This supports structured event-specific attributes without requiring a new relational column for every possible event type.

The database also uses a GIN index to support JSONB containment queries.

Stable fields such as service, severity, event name, and timestamps remain separate relational columns because they are frequently used for filtering and aggregation.

### Referential integrity

Foreign keys connect log events to registered services, environments, and trace contexts.

These relationships prevent events from referencing nonexistent registered entities.

The trigger validates that an environment belongs to the service specified by an event.

It also enforces the configured severity threshold and applies redaction before storage.

### Idempotent ingestion

The `event_key` identifies an individual event within a service.

A unique constraint on `(service_id, event_key)` prevents duplicate storage.

The ingestion function uses `ON CONFLICT DO NOTHING` and records duplicate outcomes in the audit table.

This supports repeatable ingestion attempts.

### Reporting views

`v_log_event_details` joins event information with service, environment, and trace metadata.

`v_service_health` calculates service-level event counts and error rates.

`v_trace_timeline` presents trace-related events in chronological order.

These views separate common reporting requirements from repeated query construction.

### Alert evaluation

An alert rule defines:

- The monitored service.
- The minimum error rate.
- The minimum event count.
- Whether the rule is enabled.

The evaluation function calculates the current error rate and stores a corresponding status.

The three possible outcomes are:

| Status | Meaning |
|---|---|
| `NORMAL` | The observed error rate is below the threshold |
| `FIRING` | The observed error rate meets or exceeds the threshold |
| `INSUFFICIENT_DATA` | The minimum observation count has not been reached |

The minimum event requirement prevents very small samples from being treated as reliable operational evidence.

## 13. Operational Metrics Derived from Logs

Logs can support operational analysis, although they should not automatically replace purpose-built metrics.

The implementations demonstrate several derived measurements.

### Event volume

Counts events generated by a service or event category.

A sudden decrease may indicate an application outage, instrumentation failure, or ingestion interruption.

### Error count

Counts ERROR and CRITICAL events.

This provides a basic measure of recorded failures.

### Error rate

The demonstrated calculation is:

\[
\text{Error Rate} =
\frac{\text{Error Events}}
{\text{Total Events}}
\]

The ratio is meaningful only when event generation and collection are sufficiently consistent.

### Event distribution

Groups events by event name.

This helps identify the most common application operations and failure categories.

### Trace investigation

Retrieves all events associated with a specific trace identifier.

This helps reconstruct the sequence of operations responsible for a distributed failure.

## 14. Alert Evaluation and Operational Decisions

An alert is a policy-driven evaluation of observed system behavior.

A threshold alone may produce unreliable results when event volume is low.

For example, one error among two events represents a 50% error rate, but the observation may not be sufficient to establish a persistent service problem.

The implementations therefore use a minimum event count.

A practical alerting model may also include:

- Evaluation windows.
- Consecutive failure requirements.
- Recovery thresholds.
- Alert suppression.
- Notification routing.
- Maintenance windows.
- Escalation policies.

The current examples use cumulative in-memory or stored event populations. They do not implement rolling windows or a complete incident-management lifecycle.

## 15. Reliability and Failure Modes

Centralized logging introduces operational dependencies that must be managed explicitly.

| Failure mode | Possible effect | Relevant control |
|---|---|---|
| Collector unavailable | Events cannot be ingested | Retry and buffering |
| Queue saturation | New events rejected | Backpressure and capacity planning |
| Duplicate delivery | Repeated records | Idempotency keys |
| Malformed event | Ingestion failure | Schema validation |
| Missing trace context | Incomplete request investigation | Context propagation |
| Sensitive values in logs | Data exposure | Redaction and allowlisting |
| Excessive DEBUG events | Higher storage costs | Severity filtering |
| Storage growth | Increased operational cost | Retention and partitioning |
| Incorrect timestamps | Misleading event ordering | UTC timestamps and clock synchronization |
| Collector shutdown | Buffered events may be lost | Graceful draining and durable transport |

### Delivery guarantees

At-most-once delivery may lose events during failures.

At-least-once delivery can produce duplicates.

Exactly-once processing across distributed systems requires careful coordination and should not be assumed merely because an event identifier exists.

The database example demonstrates idempotent insertion, but this does not by itself establish exactly-once delivery from every producer.

## 16. Performance and Scalability

The cost of centralized logging depends on event volume, event size, indexing, retention, and query patterns.

Important engineering decisions include:

- Use bounded buffers to control memory consumption.
- Batch events to reduce transport overhead.
- Avoid excessively large structured payloads.
- Index frequently queried fields.
- Avoid indexing every arbitrary attribute.
- Partition high-volume event tables by time.
- Separate ingestion workloads from expensive analytical queries.
- Use asynchronous transport where appropriate.
- Apply retention and archival policies.
- Monitor the collector itself.

### PostgreSQL scaling considerations

The SQL implementation uses B-tree indexes for common relational filters and a GIN index for JSONB attributes.

For sustained high ingestion volume, time-based partitioning can reduce maintenance and improve retention operations.

The example uses a single relational event table for clarity.

A production deployment should also consider write throughput, partition pruning, vacuum behavior, index maintenance, replication, and storage growth.

## 17. Implementation Comparison

| Dimension | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Primary focus | Workflow simulation | Event-driven ingestion | Efficient domain engine | Enterprise service | Persistent relational model |
| Event structure | Dataclasses | Immutable objects | Structs | Records | Relational columns and JSONB |
| Context handling | Explicit context | AsyncLocalStorage | Explicit context | Immutable context records | Trace relationships |
| Storage | Bounded deque | Bounded in-memory pipeline | Reserved vector | Synchronized collection | Persistent tables |
| Concurrency | Locking | Asynchronous event loop | Sequential demonstration | Worker thread | Database transactions |
| Redaction | Recursive key handling | Recursive object handling | Attribute policy | Denylist and allowlist | JSONB trigger |
| Analytics | Python collections | Maps | STL algorithms | Streams | SQL aggregation |
| Alerting | Threshold engine | Policy object | Governance engine | Alert policy | Evaluation function |

## 18. Practical Limitations

These implementations demonstrate the mechanisms and relationships required for an observability and centralized logging architecture.

They intentionally use bounded local storage and simulated transport rather than external infrastructure.

They do not provide:

- Distributed durable message queues.
- Multi-node log replication.
- Production authentication and authorization.
- Full OpenTelemetry protocol compatibility.
- Distributed sampling.
- Complete trace reconstruction across network boundaries.
- Automated incident notification.
- Long-term object-storage archival.
- Advanced anomaly detection.
- Full-text search infrastructure.
- Production-grade schema evolution.
- Rolling-window alert evaluation.

The JSON serializers in the C++ and Java examples are designed for their demonstrated event structures rather than being general-purpose JSON libraries.

The PostgreSQL trigger and ingestion function enforce database-level rules, but database permissions must also prevent unauthorized callers from bypassing approved ingestion procedures.

## 19. Execution Requirements

| Deliverable | Runtime | External dependencies |
|---|---|---|
| Python | Python 3.10+ | None |
| JavaScript | Node.js 18+ | None |
| C++17 | C++17 compiler | None |
| Java | Java 17 | None |
| PostgreSQL | PostgreSQL 15+ | None |

The implementations are independent and demonstrate the same observability domain through different engineering approaches.

The central distinction is that structured logging defines how events are represented, centralized logging defines how events are collected and made accessible, and observability uses the resulting signals to understand application behavior.
