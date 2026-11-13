# Event Sourcing: Events as the Source of Truth

## 1. Technical Overview

Event Sourcing is an architectural pattern in which an application's state is represented by an ordered sequence of events rather than being maintained exclusively as a collection of mutable current-state records.

Instead of storing only the latest account balance, an event-sourced system stores the business events that produced that balance.

For example:

| Version | Event | Amount | Resulting balance |
|---:|---|---:|---:|
| 1 | AccountOpened | - | 0 |
| 2 | MoneyDeposited | 10,000 | 10,000 |
| 3 | MoneyWithdrawn | 2,500 | 7,500 |
| 4 | MoneyDeposited | 500 | 8,000 |

The current balance is reconstructed by applying the events in their original order.

The event history is authoritative. Current-state tables, dashboards, search indexes, and analytical models are derived representations.

This distinction changes how persistence, auditing, transaction processing, recovery, and application state management are designed.

## 2. Core Architecture

<text></text>

                 COMMAND
                    |
                    v
             Command Handler
                    |
                    v
             Domain Validation
                    |
                    v
             Aggregate Root
                    |
                    v
              Event Creation
                    |
                    v
          Optimistic Concurrency
                    |
                    v
              EVENT STORE
          (Authoritative History)
                    |
           +--------+--------+
           |                 |
           v                 v
      Event Replay       Event Dispatcher
           |                 |
           v                 v
     Aggregate State    Read Projections
                             |
                    +--------+--------+
                    |        |        |
                    v        v        v
                  Search   Reports  Analytics

# Event Sourcing Architecture and Implementation in Python, JavaScript, C++17, Java 17, and PostgreSQL

## 1. Introduction

Event Sourcing is a software architecture pattern in which application state is stored as a sequence of events rather than being maintained only as the latest updated record.

Instead of overwriting an account balance whenever a transaction occurs, the system records every accepted business operation as an immutable event.

The current state is reconstructed by replaying these events in their original order.

For example, consider a banking application:

| Event | Amount | Balance |
|---|---:|---:|
| AccountOpened | 0 | 0 |
| MoneyDeposited | 10,000 | 10,000 |
| MoneyWithdrawn | 2,500 | 7,500 |
| MoneyDeposited | 500 | 8,000 |

The final balance is 8,000, but the complete transaction history remains available.

Event Sourcing provides:

- Complete business transaction history.
- Historical state reconstruction.
- Auditable business operations.
- Event replay and recovery.
- Multiple query-oriented projections.
- Improved traceability.
- Support for complex business workflows.
- Historical analysis and debugging.

It is particularly useful in banking, financial systems, healthcare, insurance, cybersecurity, supply chain management, and enterprise applications.

## 2. Architecture Overview

The architecture separates five responsibilities:

| Component | Responsibility |
|---|---|
| Command | Expresses an intended business operation |
| Aggregate | Validates domain rules and maintains business invariants |
| Event | Records a successfully accepted business fact |
| Event Store | Preserves the authoritative event history |
| Projection | Presents derived information for queries |

A command is an intention. An event is a fact.

For example:

- `WithdrawMoney` is a command.
- `MoneyWithdrawn` is an event.

A command may be rejected. A successfully persisted event represents an accepted state transition.

## 3. Fundamental Concepts

### 3.1 Events

An event records something that has already happened in the business domain.

Examples:

- `AccountOpened`
- `MoneyDeposited`
- `MoneyWithdrawn`
- `AccountFrozen`
- `AccountUnfrozen`

An event normally contains:

| Field | Purpose |
|---|---|
| Event ID | Globally unique event identity |
| Aggregate ID | Identifies the affected business entity |
| Aggregate Version | Position within the aggregate stream |
| Event Type | Identifies the business occurrence |
| Payload | Contains relevant business information |
| Timestamp | Records when the event occurred |
| Schema Version | Identifies the event structure version |

Events should be immutable after persistence.

If a historical transaction needs correction, the system should record a compensating event instead of silently modifying the original event.

For example:

```yaml
MoneyDeposited: 10000
MoneyWithdrawn: 10000


The second event corrects the business state without erasing the first transaction.

### **3.2 Event Store**

An event store is the authoritative persistence mechanism.

It maintains event streams associated with individual aggregates.

Example:

```text
ACC-1001
  |
  +-- Version 1: AccountOpened
  +-- Version 2: MoneyDeposited
  +-- Version 3: MoneyWithdrawn
  +-- Version 4: AccountFrozen

ACC-1002
  |
  +-- Version 1: AccountOpened
  +-- Version 2: MoneyDeposited
```

Each aggregate has an independent sequence.

An event store must preserve:

- Event identity.
- Aggregate identity.
- Event ordering.
- Version consistency.
- Event integrity.
- Durable persistence.
- Duplicate-command protection.

A relational database can implement an event store using an append-only table, unique constraints, transactions, and appropriate indexes.

### **3.3 Aggregate Roots**

An aggregate is a consistency boundary around related domain state.

An aggregate root controls the rules that must remain valid when a command is processed.

The banking implementations use an account aggregate.

Its state contains:

- Account identity.
- Account owner.
- Balance.
- Account status.
- Aggregate version.

The aggregate applies events sequentially.

It rejects invalid historical sequences, such as a withdrawal that produces a negative balance.

An aggregate should not allow unrelated aggregates to be modified as part of an uncontrolled state transition.

This keeps consistency boundaries manageable.

### **3.4 Aggregate Versions**

Every event in an aggregate stream receives a monotonically increasing version.

For example:

```text
Version 1 -> AccountOpened
Version 2 -> MoneyDeposited
Version 3 -> MoneyWithdrawn
Version 4 -> AccountFrozen
```

The version provides:

- Event ordering within an aggregate.
- Detection of missing events.
- Optimistic concurrency control.
- Projection synchronization.
- Snapshot positioning.

Aggregate versioning is different from timestamps.

Timestamps can be equal, affected by clock differences, or insufficient to establish a reliable global ordering.

The aggregate version establishes ordering within its own stream.

## **4. Event Persistence and Concurrency**

### **4.1 Append-Only Persistence**

An event should be added to the stream rather than used to overwrite an earlier event.

The normal write operation is:

1. Load the aggregate's current version.
2. Validate the requested command.
3. Construct the next event.
4. Verify that the expected version is still current.
5. Persist the event.
6. Advance the aggregate version.

The database transaction must commit the event and its associated authoritative metadata together.

### **4.2 Optimistic Concurrency**

Optimistic concurrency prevents two writers from independently extending the same stream using an outdated version.

Suppose two commands read version 5.

```text
Writer A reads version 5.
Writer B reads version 5.

Writer A appends version 6.
Writer B attempts to append version 6.

Writer A succeeds.
Writer B receives a concurrency conflict.
```

Writer B must reload the aggregate and reconsider its command.

This avoids silent overwriting of concurrent business decisions.

The implementations demonstrate different approaches:

- Python: Expected-version comparison.
- JavaScript: Promise-based write serialization.
- C++17: Expected-version validation.
- Java 17: Synchronized event-store operations.
- PostgreSQL: Row locking using `SELECT ... FOR UPDATE`.

### **4.3 Idempotency**

Idempotency prevents duplicate processing when a command is submitted repeatedly.

This is important when:

- A client retries after a timeout.
- A network connection fails after a successful transaction.
- A payment service resubmits a request.
- A message broker delivers a message more than once.

Each command receives a unique command ID.

The system records the original result and returns it when the same command is received again.

A command ID must not be reused for a different operation.

Idempotency does not mean that all events with identical payloads should be rejected. Two separate legitimate deposits can have the same amount.

The identity of the command determines whether it is a retry.

## **5. Event Replay and State Reconstruction**

Event replay reconstructs an aggregate by applying its historical events in sequence.

Example:

| Event | Operation | Balance |
|---|---|---:|
| AccountOpened | Initialize | 0 |
| MoneyDeposited | Add 10,000 | 10,000 |
| MoneyWithdrawn | Subtract 2,500 | 7,500 |
| MoneyDeposited | Add 500 | 8,000 |

The state is derived rather than independently treated as the historical truth.

A simplified reconstruction process is:

```text
Initial state
     |
     v
Apply Event 1
     |
     v
Apply Event 2
     |
     v
Apply Event 3
     |
     v
Apply Event 4
     |
     v
Reconstructed state
```

Replay supports:

- Recovery after projection failure.
- Verification of historical state.
- Rebuilding read models.
- Auditing business decisions.
- Testing changes to domain calculations.
- Reconstructing aggregate state after application restarts.

Replay must use the correct event ordering and event schemas.

An event stream with missing versions or invalid historical transitions should be treated as corrupted or inconsistent data.

## **6. Snapshots**

Snapshots preserve an aggregate's state at a particular event version.

For example:

```text
Events 1-100
      |
      v
Snapshot at version 100
      |
      v
Events 101-120
      |
      v
Current state
```

Without a snapshot, reconstructing the aggregate requires processing all 120 events.

With a snapshot, reconstruction starts at version 100 and processes only the remaining 20 events.

A snapshot contains:

- Aggregate ID.
- Snapshot version.
- Reconstructed state.
- Creation timestamp.

Snapshots are performance optimizations, not replacements for the event store.

The complete historical stream must remain available if full reconstruction and auditing are required.

A snapshot must be associated with the exact aggregate version from which it was generated.

## **7. Event Schema Evolution**

Events are long-lived data structures.

Application requirements can change while historical events remain in storage.

For example, an earlier version might represent a payment as:

```yaml
MoneyDeposited:
  amount: 1000
```

A later version might require:

```yaml
MoneyDeposited:
  amount: 1000
  currency: INR
  payment_reference: TXN-1001
```

Changing the interpretation of historical events without a migration strategy can break replay.

Three common techniques are:

| Technique | Mechanism | Consideration |
|---|---|---|
| Upcasting | Converts an older event representation when reading | Keeps original historical records unchanged |
| Event Versioning | Stores an explicit schema version | Requires version-aware consumers |
| Event Migration | Rewrites historical representations through a controlled process | More operationally complex |

The implementations demonstrate:

- Python: Schema-version metadata.
- JavaScript: Stored event structure validation.
- Java: Explicit upcasting boundary.

A production implementation should define compatibility rules for every event version.

## **8. CQRS and Read Projections**

Command Query Responsibility Segregation separates the write model from the read model.

Event Sourcing and CQRS are related architectural patterns, but they are not interchangeable.

Event Sourcing determines how state changes are persisted.

CQRS separates command handling from query handling.

An event-sourced system can use CQRS to maintain multiple projections from the same event history.

Example:

```text
                 EVENT STORE
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
      Account      Customer     Financial
      Projection   Projection   Projection
          |           |           |
          v           v           v
       Balance     Customer     Reports
       Queries     History      and Audit
```

The banking examples implement an account balance projection.

The projection stores:

- Owner.
- Current balance.
- Account status.
- Last processed aggregate version.

It can be discarded and rebuilt from the event history.

### **Projection Consistency**

A projection may temporarily lag behind the event store when event processing is asynchronous.

This is called eventual consistency.

For example:

```text
Event store version: 15
Projection version: 14
```

The projection has not yet processed the fifteenth event.

A query must account for this possibility if the business operation requires immediate consistency.

The PostgreSQL implementation updates its projection in the same transaction as event insertion. This provides transactional consistency for that particular database design rather than demonstrating asynchronous eventual consistency.

## **9. Distinguishing Event Sourcing from Conventional Persistence**

| Characteristic | Conventional State Persistence | Event Sourcing |
|---|---|---|
| Primary Storage | Current state | Historical events |
| Update Mechanism | Modify existing state | Append new events |
| Historical Changes | May require audit tables | Preserved in event history |
| State Reconstruction | Read stored state | Replay events |
| Audit Capability | Depends on additional mechanisms | Supported by event history |
| Storage Requirements | Usually lower | Usually higher |
| Read Performance | Direct state retrieval | Often requires projections |
| Schema Evolution | Primarily current records | Long-lived historical event schemas |
| Concurrency | Row-level or application controls | Stream-level version control |
| Recovery | Restore stored state | Rebuild derived state from events |

Event Sourcing introduces additional operational responsibilities.

It should be selected when historical business facts, traceability, reconstruction, or multiple derived views justify those responsibilities.

## **10. Python Implementation**

**File:** `event_sourcing.py`

The Python program demonstrates an in-memory event store and a banking aggregate.

### **Main Components**

| Component | Implementation |
|---|---|
| Domain Events | Frozen `DomainEvent` dataclass |
| Event Identity | Deterministic SHA-256 identifier |
| Event Persistence | `EventStore` |
| Aggregate | `BankAccount` |
| Command Handling | `BankingService` |
| Read Model | `AccountProjection` |
| Snapshot | `Snapshot` dataclass |
| File Persistence | JSON Lines |
| Recovery | Event deserialization and replay |

### **Important Mechanisms**

The `EventStore` maintains separate event streams for different aggregate IDs.

The `append()` method verifies the expected version before accepting an event.

The `BankingService` validates business commands before creating events.

The `BankAccount.rehydrate()` method reconstructs the aggregate from its event stream.

The `AccountProjection` independently rebuilds the current account state.

### **Failure Conditions**

The program tests:

- Duplicate command submission.
- Stale aggregate versions.
- Invalid monetary amounts.
- Insufficient funds.
- Invalid historical event sequences.
- JSON Lines persistence and recovery.

### **Performance Considerations**

Loading an aggregate requires processing its event history.

If an aggregate has thousands or millions of events, snapshots or optimized reconstruction become important.

The in-memory event store is useful for learning and testing, but it does not provide durable transactional storage or multi-process concurrency control.

## **11. JavaScript Implementation**

**File:** `event-sourcing.js`

The JavaScript implementation focuses on asynchronous event processing and event-driven architecture.

### **Main Components**

| Component | Responsibility |
|---|---|
| `EventJournal` | Manages the authoritative event streams |
| `AccountAggregate` | Reconstructs and validates business state |
| `AccountService` | Processes commands |
| `BalanceProjection` | Maintains query-oriented state |
| `subscribe()` | Registers event listeners |
| `persist()` | Writes the journal |
| `restore()` | Reconstructs and verifies stored events |

### **Asynchronous Processing**

Node.js provides a useful execution model for event-driven applications.

The implementation uses Promises to serialize event-store writes.

This prevents concurrent commands from bypassing aggregate-version checks within the same process.

Subscribers receive committed events.

Projection failures are reported separately because a projection failure should not invalidate an event already committed to the authoritative journal.

A production system should use durable projection checkpoints and retry mechanisms rather than relying exclusively on in-memory listeners.

### **Event Integrity**

The implementation uses a hash chain for the persisted journal.

Each event contains a reference to the previous event's hash.

The next event incorporates that reference into its own hash.

This makes unexpected changes detectable during journal restoration.

A simple hash chain is not equivalent to cryptographic signing, access control, or tamper-proof storage. An attacker with sufficient access may be able to rewrite the complete chain.

## **12. C++17 Implementation**

**File:** `event_sourcing.cpp`

The C++ implementation emphasizes explicit domain modeling, controlled state transitions, and efficient event-stream access.

### **Main Components**

- `Event`: Immutable-style event data structure.
- `EventStore`: Maintains aggregate event streams.
- `Account`: Aggregate root.
- `AccountService`: Validates and executes commands.
- `Projection`: Constructs query-oriented account records.
- Domain-specific exceptions: Distinguish concurrency, validation, and financial failures.

### **Engineering Decisions**

The event store uses an `unordered_map` to locate aggregate streams efficiently.

A `vector` stores events in their aggregate order.

A `set` prevents duplicate event identifiers.

A separate command-result map supports idempotent command processing.

The aggregate checks version continuity during reconstruction.

The implementation also protects against monetary balance overflow using integer arithmetic.

### **Complexity**

Let:

- E represent the total number of stored events.
- N represent the number of events in one aggregate stream.
- A represent the number of aggregate streams.

| Operation | Approximate Complexity |
|---|---|
| Aggregate Stream Lookup | Average O(1) |
| Append to Stream | Amortized O(1) |
| Duplicate Event Lookup | O(log E) |
| Aggregate Reconstruction | O(N) |
| Projection Rebuild | O(E) |
| Snapshot-Based Reconstruction | O(K), where K is the number of events after the snapshot |

The implementation uses in-memory structures. A persistent implementation would need transactional storage, durable writes, and synchronization across processes.

## **13. Java 17 Implementation**

**File:** `EventSourcingEnterprise.java`

The Java implementation models an enterprise-oriented event-sourced banking system.

It uses Java 17 records, immutable event data, collections, service classes, interfaces, and explicit domain exceptions.

### **Domain Model**

| Type | Purpose |
|---|---|
| `DomainEvent` | Immutable historical event |
| `Snapshot` | Aggregate state at a specific version |
| `Command` | Requested business operation |
| `BankAccount` | Aggregate root |
| `EventStore` | Authoritative event persistence abstraction |
| `EventDispatcher` | Event publication |
| `AccountProjection` | Read-side representation |
| `AccountCommandService` | Command execution |
| `EventSchemaUpcaster` | Schema compatibility boundary |

### **State Transitions**

The account supports:

```text
ACTIVE
  |
  | AccountFrozen
  v
FROZEN
  |
  | AccountUnfrozen
  v
ACTIVE
```

Financial commands are rejected while the account is frozen.

Each accepted event advances the aggregate version.

The command service checks existing command identifiers before processing a new command.

### **Enterprise Considerations**

The synchronized event-store operations demonstrate controlled in-process writes.

The event dispatcher demonstrates independent event consumers.

The read projection can be reconstructed from the complete event history.

The snapshot records the aggregate version associated with its state.

The implementation is an educational enterprise model, not a production distributed event-store implementation. Persistent transactions, external message delivery, distributed locks, and durable consumer checkpoints require additional infrastructure.

## **14. PostgreSQL Implementation**

**File:** `event_sourcing.sql`

The PostgreSQL implementation demonstrates how relational database features can support an event-sourced workflow.

It creates the dedicated schema:

`event_sourcing_demo`

### **Relational Model**

| Table | Purpose |
|---|---|
| `repositories_metadata` | Stores system metadata |
| `accounts` | Maintains aggregate identity |
| `aggregate_heads` | Stores current stream versions |
| `processed_commands` | Supports idempotency |
| `event_store` | Authoritative event history |
| `account_projection` | Current query-oriented state |
| `account_snapshots` | Stores aggregate snapshots |

### **Database Integrity**

The event store uses:

- Primary keys.
- Foreign keys.
- Unique aggregate-version constraints.
- Event-type validation.
- Positive version constraints.
- JSONB payload validation.
- Immutable-event triggers.

The unique constraint on `(aggregate_id, aggregate_version)` prevents duplicate positions in an aggregate stream.

The immutability trigger rejects updates and deletions to historical events.

Corrections must be represented by additional business events.

### **Transactional Command Processing**

The `append_account_event()` function performs command processing.

Its main responsibilities are:

1. Validate command identifiers.
2. Calculate a request fingerprint.
3. Check whether the command was previously processed.
4. Lock the aggregate-head row.
5. Verify the expected aggregate version.
6. Create the event.
7. Update the aggregate head.
8. Record the command result.

The event insertion, projection update, and aggregate-version update participate in the same database transaction.

If an operation fails, PostgreSQL rolls back the transaction.

### **Projection Mechanism**

The `update_account_projection()` trigger updates the account read model after an event is inserted.

For a deposit, the balance increases.

For a withdrawal, the balance decreases if sufficient funds exist.

For freezing and unfreezing, the account status changes.

This implementation uses synchronous projections within the database transaction.

A large distributed application may instead process projections asynchronously.

### **Reporting and Validation**

The SQL script includes:

- Complete aggregate history retrieval.
- Event counts.
- Event-type aggregation.
- Account balance reporting.
- Aggregate-version validation.
- Projection consistency checks.
- Withdrawal eligibility determination.
- Snapshot creation.
- Independent replay into a temporary projection.
- Operational queries for incomplete command records.

The independent replay query is especially important because it verifies whether the derived read model agrees with a separately reconstructed event history.

## **15. Event Sourcing and Related Architectural Concepts**

### **Event Sourcing vs. Event-Driven Architecture**

These concepts solve different problems.

| Event Sourcing | Event-Driven Architecture |
|---|---|
| Defines how state changes are persisted | Defines how components communicate through events |
| Requires an authoritative event history | Does not require permanent event storage |
| Supports state reconstruction | Supports asynchronous communication |
| Focuses on persistence and domain history | Focuses on component interaction |

An application can be event-driven without using Event Sourcing.

An event-sourced application can publish events to external consumers.

### **Event Sourcing vs. CQRS**

| Event Sourcing | CQRS |
|---|---|
| Stores state changes as events | Separates write and read models |
| Supports event replay | Supports specialized query models |
| Uses event streams | May use relational tables or other read stores |
| Can operate without multiple projections | Does not require event sourcing |

The combination of both patterns is useful when an application requires detailed historical records and multiple query-oriented views.

### **Event Sourcing vs. Database Audit Logs**

Database audit logs record changes or database operations.

Event Sourcing records domain-level business facts.

For example:

- An audit log may record that a balance column changed.
- An event-sourced application records that a customer deposited money.

Business events provide more meaningful domain information than low-level database modifications.

## **16. Practical Applications**

| Domain | Example Events | Practical Value |
|---|---|---|
| Banking | MoneyDeposited, MoneyWithdrawn | Transaction history and financial reconstruction |
| E-commerce | OrderPlaced, PaymentCaptured, OrderCancelled | Order lifecycle tracking |
| Healthcare | RecordCreated, ConsentGranted, ConsentRevoked | Traceable clinical information changes |
| Insurance | PolicyIssued, ClaimSubmitted, ClaimApproved | Claim history and decision auditing |
| Supply Chain | ShipmentCreated, ShipmentDispatched, ShipmentDelivered | Logistics traceability |
| Cybersecurity | LoginAttempted, AccessGranted, AccessRevoked | Security event investigation |
| Financial Markets | OrderSubmitted, OrderExecuted, TradeCancelled | Transaction reconstruction |
| Enterprise Systems | EmployeeAssigned, ApprovalGranted, RequestRejected | Workflow history |

In regulated environments, historical event preservation can support auditability.

It does not automatically establish regulatory compliance. Access controls, retention policies, encryption, privacy controls, and operational governance remain necessary.

## **17. Security and Reliability Considerations**

### **Event Integrity**

Historical events should not be casually modified.

Recommended controls include:

- Restricted database write privileges.
- Append-only database permissions.
- Immutable storage where appropriate.
- Event identity validation.
- Hash verification.
- Backup and recovery testing.
- Audited administrative operations.

### **Sensitive Information**

Event payloads may contain personal or confidential information.

Avoid storing unnecessary sensitive data in immutable event streams.

Potential approaches include:

- Data minimization.
- Encryption.
- Tokenization.
- Reference-based storage.
- Restricted access to historical records.
- Retention-aware event design.

A correction or deletion requirement can be difficult to satisfy when personal information is embedded in permanent events. This must be addressed during architectural design.

### **Delivery Guarantees**

Distributed event systems must account for:

- Duplicate delivery.
- Delayed delivery.
- Out-of-order processing.
- Consumer crashes.
- Partial failures.
- Network interruptions.
- Retry exhaustion.

Idempotent consumers and durable processing checkpoints are important.

Exactly-once processing should not be assumed simply because a message broker advertises delivery guarantees. End-to-end transactional behavior requires careful coordination between event delivery and consumer-side persistence.

### **Dead-Letter Processing**

An event that repeatedly fails processing may need to be isolated for investigation.

A dead-letter mechanism should retain:

- Original event identity.
- Aggregate identity.
- Failure reason.
- Retry count.
- Processing timestamp.
- Consumer identity.

Events should not be silently discarded when a projection fails.

## **18. Performance and Scalability**

Event Sourcing introduces a different performance profile from conventional state persistence.

| Challenge | Engineering Response |
|---|---|
| Long Aggregate Histories | Snapshots |
| Expensive Queries | Read Projections |
| Large Event Tables | Partitioning |
| High Write Contention | Appropriate Aggregate Boundaries |
| Slow Projections | Parallel Consumers Across Independent Streams |
| Duplicate Delivery | Idempotent Processing |
| Schema Changes | Versioning and Upcasting |
| Historical Investigations | Indexed Event Retrieval |
| Projection Recovery | Replay and Checkpoints |

### **Aggregate Boundaries**

An aggregate should represent a meaningful business consistency boundary.

Creating one enormous aggregate can increase write contention and reconstruction costs.

Creating excessively small aggregates can make business invariants difficult to enforce.

Aggregate boundaries should follow the consistency requirements of the business domain.

### **Storage Growth**

Event stores generally grow continuously.

A production design should account for:

- Retention requirements.
- Archival strategies.
- Index maintenance.
- Partition management.
- Backup volume.
- Replication.
- Historical replay costs.

Historical events should not be removed simply to reduce storage without evaluating audit, legal, and recovery requirements.

## **19. Limitations**

Event Sourcing is not appropriate for every application.

Important disadvantages include:

1. Greater architectural complexity.
2. More demanding event schema management.
3. Potentially expensive aggregate reconstruction.
4. Additional read-model maintenance.
5. Eventual consistency in asynchronous projections.
6. Increased storage requirements.
7. Complicated handling of sensitive historical information.
8. More difficult debugging when multiple consumers process events independently.
9. Operational requirements for replay, retries, monitoring, and recovery.
10. Challenges when external side effects cannot participate in the event-store transaction.

The pattern is most valuable when historical business facts are important enough to justify these additional responsibilities.

## **20. Implementation Comparison**

| Dimension | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Main Focus | Domain Simulation | Asynchronous Processing | Explicit State Management | Enterprise Domain Modeling | Transactional Persistence |
| Event Store | Dictionary | Map | Unordered Map | Concurrent Map | Relational Table |
| Concurrency | Version Validation | Promise Queue | Version Validation | Synchronized Writes | Row Locking |
| Replay | Aggregate Reconstruction | Aggregate Reconstruction | Aggregate Reconstruction | Aggregate Reconstruction | SQL Reconstruction |
| Projection | Dictionary | Map | Ordered Map | Concurrent Map | Projection Table |
| Snapshot | Dataclass | Object | Extendable State Structure | Record | JSONB Table |
| Persistence | JSON Lines | JSON Lines | In-Memory | In-Memory | PostgreSQL |

The implementations use different engineering techniques while preserving the same underlying principle: the event history is the source from which the current domain state is derived.

## **21. Execution and Verification**

### **Python**

File: `event_sourcing.py`

Run:

```bash
python event_sourcing.py
```

The demonstration validates account creation, deposits, withdrawals, snapshots, replay, idempotency, concurrency, and JSON Lines persistence.

### **JavaScript**

File: `event-sourcing.js`

Run:

```bash
node event-sourcing.js
```

The demonstration validates asynchronous command processing, event subscriptions, hash-chain verification, concurrent commands, and journal recovery.

### **C++17**

File: `event_sourcing.cpp`

Compile:

```bash
g++ -std=c++17 -O2 -Wall -Wextra -pedantic event_sourcing.cpp -o event_sourcing
```

Run:

```bash
./event_sourcing
```

The program validates domain transitions, stream versions, event replay, and read-model consistency.

### **Java 17**

File: `EventSourcingEnterprise.java`

Compile:

```bash
javac EventSourcingEnterprise.java
```

Run:

```bash
java EventSourcingEnterprise
```

The demonstration validates enterprise domain types, state transitions, event dispatching, snapshot creation, and projection reconstruction.

### **PostgreSQL**

File: `event_sourcing.sql`

Execute the complete SQL script against a dedicated PostgreSQL database.

The script recreates the `event_sourcing_demo` schema. Existing objects inside that schema will be removed.

The database demonstration creates independent aggregate streams, processes commands transactionally, maintains read projections, generates snapshots, and compares independently replayed state against the live projection.

## **22. Important Design Principles**

The five implementations demonstrate the following architectural principles:

1. **Events are facts:** Persisted events describe accepted business occurrences.
2. **History is authoritative:** Current state is derived from the event stream.
3. **Aggregates enforce invariants:** Commands must satisfy domain rules before persistence.
4. **Versions control concurrency:** A stale writer must not silently extend an outdated stream.
5. **Commands require idempotency:** Repeated delivery must not create unintended duplicate operations.
6. **Projections are derived:** Query models can be rebuilt from historical events.
7. **Snapshots optimize replay:** They reduce reconstruction work without replacing history.
8. **Event schemas evolve deliberately:** Historical data must remain interpretable.
9. **Transactions protect consistency:** Event persistence and associated database updates must commit or roll back together.
10. **Operational reliability matters:** Replay, recovery, security, monitoring, and retention are essential parts of an event-sourced system.
