# Command Query Responsibility Segregation (CQRS)

## 1. Architecture and Design Objectives

Command Query Responsibility Segregation (CQRS) is an architectural pattern that separates operations which change application state from operations which retrieve application data.

A conventional application frequently uses the same domain model for both operations. CQRS assigns different responsibilities to two models:

- **Write model:** validates commands, enforces business rules, and changes application state.
- **Read model:** organizes information for retrieval, reporting, filtering, and aggregation.

The separation allows the two sides to evolve independently according to their operational requirements.

CQRS does not require event sourcing, separate databases, microservices, or message brokers. These are architectural choices that can complement CQRS but are not mandatory components of the pattern.

### Core architecture

    CLIENT
       |
       v
    APPLICATION INTERFACE
       |
       +-----------------------------+
       |                             |
       v                             v
    COMMAND SIDE                  QUERY SIDE
       |                             |
       v                             v
    COMMAND HANDLER              QUERY HANDLER
       |                             |
       v                             v
    WRITE MODEL                  READ MODEL
       |                             ^
       v                             |
    EVENT STORE ---------------------+
       |
       v
    EVENT PROCESSOR
       |
       v
    PROJECTION UPDATES

The command side is responsible for correctness and state transitions. The query side is optimized for efficient data access.

## 2. Commands and Queries

### 2.1 Commands

A command expresses an intention to change application state.

Examples:

- `CreateAccount`
- `DepositMoney`
- `WithdrawMoney`
- `UpdateCustomer`
- `PlaceOrder`
- `CancelOrder`

A command is not a statement that an operation has succeeded. It is a request for the application to perform an operation.

A command handler must validate the request before applying a state change.

The banking implementations use command identifiers, account identifiers, monetary values, command types, and expected aggregate versions.

### 2.2 Queries

A query requests information without intentionally changing application state.

Examples:

- Retrieve an account.
- Calculate total deposits.
- Find accounts with high balances.
- Retrieve transaction history.
- Generate a financial report.

Queries use the read model instead of directly invoking write-side business operations.

A query should not produce a domain event or change the write model.

### 2.3 Fundamental distinction

| Property | Command | Query |
|---|---|---|
| Purpose | Change state | Retrieve information |
| Responsibility | Write model | Read model |
| Validation | Business invariants | Query parameters and access rules |
| Result | Acceptance, rejection, or events | Requested data |
| Side effects | Expected | Not intended |
| Optimization | Transactional correctness | Retrieval performance |
| Examples | Deposit, withdraw | Account report, balance lookup |

A successful command and an immediately consistent query result are not necessarily the same event. When projections are processed asynchronously, the read model may temporarily represent an earlier state.

## 3. Write Model and Domain Aggregates

The write model is the authoritative application model responsible for business rules.

In the banking implementation, `BankAccount` and `AccountAggregate` represent account state.

The aggregate maintains:

- Account identity.
- Account ownership.
- Monetary balance.
- Aggregate version.
- Account status.

Its methods implement permitted state transitions.

For example, a withdrawal must satisfy these conditions:

1. The account exists.
2. The account is active.
3. The requested amount is valid.
4. The amount does not exceed the available balance.
5. The command does not use a stale aggregate version.

The write model rejects operations that violate these invariants.

### Aggregate boundaries

An aggregate is a consistency boundary within a domain model.

An account aggregate protects its own balance and state transitions. Its event stream is ordered by aggregate version.

A transfer involving two accounts requires stronger coordination because it affects two aggregates.

A production implementation should execute the debit, credit, and associated event writes within one database transaction or use a carefully designed distributed transaction workflow. Two independent event-store appends do not guarantee atomicity.

## 4. Event Sourcing and Event Storage

Event sourcing stores application state changes as an ordered sequence of events.

Rather than treating the latest account balance as the only record of a transaction, the system preserves events that explain how the account reached its current state.

Example:

| Version | Event | Amount |
|---:|---|---:|
| 1 | Account created | 0.00 |
| 2 | Money deposited | 15,000.00 |
| 3 | Money deposited | 5,000.00 |
| 4 | Money withdrawn | 3,000.00 |

The resulting balance is 17,000.00.

The event sequence provides an auditable history of state transitions.

### 4.1 Event structure

Each event contains:

- Event identifier.
- Event type.
- Aggregate identifier.
- Aggregate version.
- Event payload.
- Occurrence timestamp.

The PostgreSQL implementation stores these attributes in `cqrs_write.event_store`.

The event payload uses JSONB because different event types can have different domain attributes.

### 4.2 Append-only behavior

Historical events should not be silently modified or deleted.

The SQL implementation uses a trigger to reject updates and deletes on the event store.

Corrections should be represented through additional domain events rather than rewriting historical facts.

This supports auditability and reproducible projections.

### 4.3 Event sourcing versus CQRS

These concepts are related but distinct.

| CQRS | Event Sourcing |
|---|---|
| Separates write and read responsibilities | Stores state changes as events |
| Can use conventional relational tables | Requires an event history as the state source |
| Does not require event replay | Uses event replay to reconstruct state |
| Can use separate read models | Commonly uses projections |
| Focuses on model separation | Focuses on state persistence |

CQRS can operate without event sourcing. Event sourcing can also be implemented without adopting separate read and write models.

## 5. Read Models and Projections

A read model is a representation of application data optimized for queries.

It can contain denormalized information, calculated attributes, summaries, or precomputed aggregates.

The banking implementation uses two read models:

- `account_summary`
- `transaction_history`

The account summary contains account information and the current projected balance.

The transaction history provides an event-oriented retrieval structure for financial reporting.

### 5.1 Projection mechanism

A projection transforms events into query-oriented data.

Example:

    ACCOUNT_CREATED
          |
          v
    Create account summary
          |
          v
    MONEY_DEPOSITED
          |
          v
    Increase projected balance
          |
          v
    MONEY_WITHDRAWN
          |
          v
    Decrease projected balance
          |
          v
    Update transaction history

The Python implementation uses `AccountProjection`.

The JavaScript implementation uses `AccountReadModel`.

The C++ implementation uses `AccountProjection`.

The Java implementation uses `AccountProjection`.

The PostgreSQL implementation uses `cqrs_read.project_event()`.

Each implementation maintains a separate read representation rather than exposing the internal write aggregate as the query response.

### 5.2 Multiple projections

A single event stream can support several read models.

For a financial platform, separate projections may serve:

| Projection | Purpose |
|---|---|
| Account summary | Current account information |
| Transaction history | Chronological transaction retrieval |
| Financial analytics | Deposits and withdrawals |
| Customer dashboard | Customer-level account summaries |
| Audit projection | Event traceability |
| Risk projection | Transaction patterns and risk indicators |

Each projection has its own processing requirements and recovery strategy.

A failure in one projection does not necessarily require rebuilding every other projection.

## 6. Event Processing and Synchronization

A command-side event must reach the read-side projection before the corresponding query representation can be updated.

Two processing strategies are common.

### 6.1 Synchronous projection

The application updates the read model within the command-processing workflow.

Advantages:

- Immediate query consistency.
- Simpler operational behavior.
- Fewer moving components.

Limitations:

- Increased command latency.
- Tighter coupling between write and read processing.
- Projection failure can affect command completion.

### 6.2 Asynchronous projection

The application stores the event and processes it independently.

Advantages:

- Independent scaling.
- Lower coupling.
- Better isolation of reporting workloads.
- Independent projection recovery.

Limitations:

- Eventual consistency.
- Event delivery and retry requirements.
- Projection lag.
- Duplicate event delivery.
- More complicated operational monitoring.

The Python example explicitly calls `synchronize()` to demonstrate the separation.

The C++ example rebuilds its read projection from stored events.

The Java example supports both incremental synchronization and complete rebuilding.

The JavaScript example demonstrates asynchronous event subscriptions.

The PostgreSQL implementation uses an outbox table and a projection-processing procedure.

## 7. Eventual Consistency

Eventual consistency means that the read model may temporarily lag behind the authoritative write model.

Consider the following sequence:

1. A customer deposits 5,000.00.
2. The command handler validates the request.
3. The write model updates the account.
4. The event is stored.
5. A projection worker processes the event.
6. The read model displays the updated balance.

Between steps 4 and 5, the query may return the previous balance.

This is not necessarily a correctness failure. It is an expected consequence of asynchronous projection processing.

Applications should distinguish:

- Command acceptance.
- Event persistence.
- Projection processing.
- Query visibility.

Useful mechanisms include projection checkpoints, version comparisons, retry queues, and read-after-write synchronization options.

For operations requiring immediate confirmation, the application can return the committed write result rather than relying exclusively on a potentially delayed read model.

## 8. Optimistic Concurrency Control

Concurrent commands can attempt to update the same aggregate.

Without concurrency control, two requests might both read the same balance and overwrite each other's changes.

Optimistic concurrency control uses aggregate versions to detect conflicting updates.

Example:

| Operation | Version |
|---|---:|
| Account created | 1 |
| First deposit | 2 |
| Second deposit | 3 |
| Withdrawal | 4 |

A command based on version 2 must not silently overwrite state that has already advanced to version 4.

The event store therefore checks that the expected version matches the current stream version.

The PostgreSQL implementation additionally locks account rows using `SELECT ... FOR UPDATE` and enforces unique aggregate-version combinations.

These mechanisms protect concurrent updates through different layers.

A production system must define retry behavior. A rejected stale command should normally be reconsidered using the latest aggregate state rather than blindly resubmitted.

## 9. Idempotency

Idempotency prevents the same command or event from producing duplicate business effects when requests are retried.

It is important when clients experience network timeouts or message consumers receive repeated deliveries.

### 9.1 Command idempotency

Every command has a unique command identifier.

The application checks whether that identifier has already been processed.

If the same command is received again, the previous result should be returned instead of executing the operation again.

The Python, JavaScript, C++, and Java implementations use command registries.

PostgreSQL uses `cqrs_write.commands` with a primary key on `command_id`.

### 9.2 Event idempotency

Event consumers can receive an event more than once.

The read-side processor records processed event identifiers.

Repeated delivery of an already processed event should not change the projection.

The implementations use sets, primary keys, or existing history records for duplicate detection.

### 9.3 Idempotency limitations

A production command registry must retain results for an appropriate period and validate that a repeated command identifier represents the same request.

A durable implementation should use a transactional database constraint rather than relying only on an in-memory collection.

## 10. Transactional Outbox Pattern

The transactional outbox addresses a common problem: updating a write database and publishing an event are two separate operations.

If the database update succeeds but event publication fails, the read model may never receive the change.

The outbox pattern records the event publication request in the same database transaction as the business update.

The workflow becomes:

    COMMAND
       |
       v
    DATABASE TRANSACTION
       |
       +-----------------------+
       |                       |
       v                       v
    UPDATE ACCOUNT        INSERT EVENT
                               |
                               v
                         INSERT OUTBOX
                               |
                               v
                         COMMIT
                               |
                               v
                         OUTBOX WORKER
                               |
                               v
                         READ PROJECTION

The PostgreSQL implementation uses `cqrs_write.outbox`.

The processing procedure uses row-level locking and `SKIP LOCKED` to allow multiple workers to claim different records.

It also records delivery attempts, processing status, timestamps, and errors.

The outbox provides reliable publication coordination within a database transaction. It does not independently guarantee exactly-once delivery to external systems. Consumers still require idempotent processing.

## 11. Projection Rebuilding and Recovery

A projection may become corrupted, incomplete, or incompatible with a revised reporting requirement.

Event sourcing makes it possible to reconstruct a read model from historical events.

The rebuilding process is:

1. Select the required event history.
2. Order events by aggregate identifier and version.
3. Initialize the projection.
4. Apply each event.
5. Validate final aggregate versions and balances.
6. Compare projected state with authoritative write state.
7. Make the rebuilt projection available.

The Python and Java implementations clear the in-memory projection and replay events.

The C++ implementation uses an ordered event vector.

The JavaScript implementation resets its maps and replays the event store.

The PostgreSQL script demonstrates a transactional projection rebuild using historical events and window functions.

For large production systems, a shadow read model is preferable to deleting the live projection before rebuilding it. Once the new projection passes validation, readers can be switched to the rebuilt version.

## 12. Language Implementation Comparison

Each source file demonstrates the same architectural separation through a different engineering approach.

| Language | Main implementation focus | Important mechanisms |
|---|---|---|
| Python | Domain simulation | Dataclasses, aggregate state, event storage, projections, replay |
| JavaScript | Event-driven processing | Promises, event emitter, asynchronous handlers, keyed mutex |
| C++17 | Explicit domain and state management | STL containers, value objects, exceptions, event sequencing |
| Java 17 | Enterprise domain architecture | Records, interfaces, immutable collections, service classes |
| PostgreSQL | Persistent relational workflow | Schemas, procedures, transactions, triggers, outbox, indexes |

### 12.1 Python

The Python implementation emphasizes domain modeling and executable workflow simulation.

Important components:

- `Command`
- `DomainEvent`
- `BankAccount`
- `EventStore`
- `CommandHandler`
- `AccountProjection`
- `EventDispatcher`
- `CommandRegistry`

The `BankingCQRS` class coordinates the write and read sides.

`EventFileStorage` demonstrates newline-delimited JSON event persistence.

The implementation uses a process-local lock. Its in-memory event store is not a substitute for durable transactional storage.

### 12.2 JavaScript

The JavaScript implementation demonstrates event-driven application design.

Important components:

- `Command`
- `DomainEvent`
- `AccountAggregate`
- `EventStore`
- `CommandService`
- `AsyncEventBus`
- `AccountReadModel`
- `QueryService`
- `KeyedMutex`

The keyed mutex serializes operations for the same aggregate without requiring a global asynchronous lock.

The event bus uses `Promise.allSettled()` to identify subscriber failures.

A failed projection does not mean the event was not committed. A production application should use a durable outbox and independently retry failed consumers. The example intentionally keeps the in-memory event publication model small enough to inspect.

### 12.3 C++17

The C++ implementation emphasizes explicit domain types and controlled state transitions.

The `Money` class stores monetary values in integer cents instead of using floating-point arithmetic for balance calculations.

The event store uses:

- `std::map` for aggregate streams.
- `std::set` for event identifiers.
- `std::vector` for ordered events.
- `std::optional` for expected versions.

The command handler restores aggregate state when event persistence fails.

The implementation provides a deterministic executable scenario rather than introducing unnecessary external dependencies.

### 12.4 Java 17

The Java implementation emphasizes enterprise-oriented domain architecture.

Its major components are:

- Immutable records for commands and events.
- A `Money` value object.
- `EventRepository` abstraction.
- `InMemoryEventStore`.
- `CommandHandler`.
- `CommandRegistry`.
- `AccountProjection`.
- `QueryService`.
- `BankingApplication`.

The repository interface separates the event-store contract from its implementation.

The application service coordinates command processing and projection synchronization.

The Java implementation uses `ReentrantLock` for command serialization and synchronized event-store and projection operations.

A production deployment would replace the in-memory repository with a durable transactional adapter.

### 12.5 PostgreSQL

The PostgreSQL implementation models CQRS through two schemas.

| Schema | Responsibility |
|---|---|
| `cqrs_write` | Authoritative business state, commands, events, outbox |
| `cqrs_read` | Query projections, transaction history, checkpoints, reporting |

The principal database objects are:

| Database object | Purpose |
|---|---|
| `accounts` | Authoritative account state |
| `commands` | Command identity and processing results |
| `event_store` | Immutable historical events |
| `outbox` | Pending event publication |
| `account_summary` | Query-oriented account representation |
| `transaction_history` | Transaction retrieval |
| `projection_checkpoints` | Projection processing progress |
| `account_report` | Account retrieval view |
| `transaction_analytics` | Aggregated transaction reporting |
| `account_reconciliation` | Write/read consistency comparison |

The stored procedures handle account creation, monetary transactions, and outbox processing.

The database constraints enforce important integrity requirements independently of application-level validation.

## 13. Database Design and Integrity

### 13.1 Primary keys and unique constraints

The event store uses `event_id` as its primary key.

The combination of aggregate type, aggregate identifier, and aggregate version is unique.

This prevents two events from occupying the same position in an aggregate stream.

The command table uses `command_id` as its primary key to support idempotency.

### 13.2 Check constraints

The database enforces:

- Nonnegative account balances.
- Positive transaction amounts.
- Nonnegative aggregate versions.
- Valid account identifiers.
- Valid event payload structures.
- Nonnegative transaction counts.

These checks provide a second line of protection beyond command-handler validation.

### 13.3 Indexing

The implementation uses indexes based on expected access patterns.

Examples:

- Aggregate identifier and version for event replay.
- Event type and occurrence time for event reporting.
- Account status and balance for account dashboards.
- Account identifier and transaction time for history retrieval.
- Pending outbox records for event processing.
- JSONB GIN indexing for selected event-payload searches.

Indexes improve retrieval performance but increase write costs and storage requirements. They should be evaluated against actual query workloads.

## 14. Security and Operational Considerations

CQRS separates application responsibilities but does not automatically provide security.

A production implementation should address the following controls.

### Authorization

- Authenticate command and query callers.
- Apply role-based or attribute-based authorization.
- Verify ownership before exposing account information.
- Restrict administrative operations.
- Apply authorization independently to read and write interfaces.

### Data protection

- Encrypt sensitive data in transit and at rest.
- Avoid storing credentials or authentication secrets in event payloads.
- Apply appropriate retention and privacy policies.
- Control access to historical event records.
- Audit administrative access.

### Input validation

- Validate identifiers and monetary values.
- Reject unsupported commands.
- Enforce aggregate invariants.
- Validate event schemas.
- Reject unexpected event versions.

### Operational monitoring

Useful metrics include:

| Metric | Operational purpose |
|---|---|
| Command success rate | Detect write-side failures |
| Command rejection rate | Identify validation and business-rule failures |
| Event ingestion rate | Measure event-store activity |
| Projection lag | Identify delayed read-model updates |
| Outbox backlog | Detect publication bottlenecks |
| Retry count | Identify repeated processing failures |
| Projection failures | Monitor consumer health |
| Reconciliation mismatches | Detect read/write inconsistencies |

The event store should also have backup, recovery, retention, access-control, and schema-evolution procedures.

## 15. Failure Conditions and Recovery Strategies

| Failure | Impact | Appropriate handling |
|---|---|---|
| Invalid command | No valid state transition | Reject command |
| Insufficient balance | Withdrawal cannot proceed | Reject without committing |
| Stale aggregate version | Concurrent update conflict | Reload state and reconsider command |
| Duplicate command | Potential repeated transaction | Return stored command result |
| Duplicate event | Potential repeated projection | Check processed event identifier |
| Missing projection | Query unavailable or incomplete | Replay events |
| Projection version gap | Incorrect event ordering | Pause and recover missing events |
| Outbox failure | Delayed projection | Retry with backoff |
| Read/write mismatch | Inconsistent query result | Reconciliation and projection repair |
| Database transaction failure | Incomplete write operation | Roll back transaction |

The distinction between command failure and projection failure is particularly important.

A command can be committed successfully while a downstream projection fails. Such a failure should be monitored and repaired without automatically repeating the original financial transaction.

## 16. Performance and Scalability

CQRS enables independent optimization of read and write workloads.

### Write-side optimization

- Keep aggregate boundaries meaningful.
- Validate commands before expensive processing.
- Use optimistic concurrency.
- Use append-oriented event storage.
- Apply database transactions for related writes.
- Keep command processing independent of reporting queries.

### Read-side optimization

- Use denormalized query models.
- Precompute frequently requested aggregates.
- Create workload-specific indexes.
- Partition large transaction-history tables when justified.
- Cache suitable read responses.
- Scale projection workers independently.
- Track projection lag and processing checkpoints.

### Event replay complexity

If an aggregate has \(n\) events, a full replay requires \(O(n)\) event processing.

For \(m\) aggregates containing \(N\) total events, rebuilding all projections generally requires \(O(N)\) processing, excluding sorting and database access costs.

The implementations sort events by aggregate and version during replay. This provides correct ordering but adds sorting overhead when the event source does not already guarantee order.

Production systems can use snapshots to reduce repeated aggregate reconstruction costs.

A snapshot stores an aggregate state at a particular version. Reconstruction then starts from that snapshot and replays only subsequent events.

Snapshots are performance optimizations, not replacements for the historical event stream.

## 17. CQRS Versus Traditional CRUD

| Characteristic | Traditional CRUD | CQRS |
|---|---|---|
| Model structure | Common model for reads and writes | Separate models |
| Update operations | Direct record updates | Explicit commands |
| Query operations | Same persistence model | Query-specific read model |
| Business logic | Often distributed across services | Concentrated in command handling |
| Reporting | Frequently shares transactional schema | Can use independent projections |
| Complexity | Generally lower | Higher |
| Eventual consistency | Not inherently required | Common with asynchronous projections |
| Scaling | Often shared | Read and write workloads can scale separately |

CRUD is appropriate for applications with straightforward state transitions and limited read/write specialization.

CQRS becomes useful when command validation, domain complexity, reporting requirements, or read/write workload differences justify the additional architectural components.

## 18. CQRS and Related Architectural Patterns

| Pattern | Main responsibility | Relationship to CQRS |
|---|---|---|
| Domain-Driven Design | Models business domains and aggregates | Helps define write-side boundaries |
| Event Sourcing | Stores state changes as events | Can provide the authoritative event history |
| Transactional Outbox | Coordinates database changes and event publication | Supports reliable projection updates |
| Event-Driven Architecture | Communicates through events | Supports asynchronous processing |
| Microservices | Organizes independently deployable services | Can use CQRS within or across services |
| Read Replicas | Replicates database state | Can improve query scaling without full CQRS |
| Materialized Views | Stores precomputed query results | Can implement read-side projections |

These patterns solve different problems and should not be treated as interchangeable.

## 19. Limitations and Design Trade-offs

CQRS introduces additional responsibilities.

**Data duplication:** Read models may repeat information from the write model. This requires synchronization and consistency controls.

**Operational complexity:** Event processing, retries, monitoring, replay, and recovery require additional infrastructure.

**Eventual consistency:** Some queries may temporarily return outdated information.

**Schema evolution:** Historical events must remain readable when domain models change. Event versioning and explicit upcasting strategies become important.

**Cross-aggregate transactions:** Operations involving multiple aggregates require deliberate transaction boundaries or distributed workflow coordination.

**Overengineering:** Simple applications may not benefit from separate models and projection infrastructure.

The architecture should be adopted when its separation provides measurable value rather than simply because independent models are possible.

## 20. Practical Learning Outcomes from the Implementations

The five source files demonstrate a progression from domain-level separation to persistent enterprise workflows.

| Learning area | Demonstrated implementation |
|---|---|
| Command modeling | Typed command structures |
| Query modeling | Independent query services |
| Domain invariants | Account aggregate methods |
| Event representation | Immutable domain events |
| Event persistence | Append-only event stores |
| Concurrency | Expected aggregate versions |
| Idempotency | Command and event registries |
| Projection processing | Read-model updates |
| Eventual consistency | Explicit synchronization |
| Event-driven programming | Asynchronous JavaScript handlers |
| Enterprise architecture | Java interfaces and domain services |
| State management | C++ aggregate and projection classes |
| Database integrity | PostgreSQL constraints and triggers |
| Reliable publication | Transactional outbox |
| Recovery | Projection rebuilding |
| Reporting | Query views and aggregation |
| Validation | Negative amounts, stale versions, insufficient funds |
| Reconciliation | Comparison of write and read models |

## 21. Execution Requirements

| Deliverable | Runtime | External dependencies |
|---|---|---|
| Python | Python 3.10+ | None |
| JavaScript | Node.js 18+ | None |
| C++17 | C++17 compiler | None |
| Java | Java 17 | None |
| PostgreSQL | PostgreSQL 15+ | PostgreSQL database |

The Python and JavaScript implementations create local event-history files during execution.

The C++ implementation runs a deterministic banking scenario.

The Java implementation runs the enterprise account workflow.

The PostgreSQL script creates its schemas, database objects, sample records, projections, reporting views, validation cases, and reconciliation queries.

For production deployment, the in-memory event stores and registries must be replaced with durable storage and transactionally coordinated processing. The SQL implementation provides the persistent relational foundation for that transition.
