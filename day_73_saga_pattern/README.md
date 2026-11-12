# Saga Pattern: Distributed Transaction Management

## 1. Introduction

The Saga Pattern is a distributed transaction management technique used to maintain business consistency when a transaction spans multiple independent services.

In a traditional relational database, a transaction can use ACID properties to coordinate multiple database operations. In a microservices architecture, individual services frequently maintain separate databases and independently manage their transactions.

A single business operation may therefore require several local transactions.

For example, an e-commerce order can involve:

1. Reserving inventory.
2. Charging a customer.
3. Creating a shipment.

These operations may belong to three independently deployed services.

A single global database transaction is generally unavailable or undesirable across these services. The Saga Pattern coordinates their execution through a sequence of local transactions and corresponding compensating transactions.

## 2. Core Concepts

### 2.1 Distributed transaction

A distributed transaction is a business operation that requires coordinated changes across multiple independent services or transactional resources.

Each participating service controls its own local transaction.

For an order-processing workflow:

| Service | Local transaction |
|---|---|
| Inventory | Reserve product quantity |
| Payment | Charge customer |
| Shipping | Create shipment |

The overall business transaction is successful only when all required operations complete successfully.

### 2.2 Saga

A Saga is an ordered sequence of local transactions.

Each forward transaction has a corresponding compensating operation that attempts to reverse its business effect.

Let the forward transactions be:

- T1: Reserve inventory.
- T2: Charge payment.
- T3: Create shipment.

Their compensations are:

- C1: Release inventory.
- C2: Refund payment.
- C3: Cancel shipment.

The successful execution sequence is:

T1 → T2 → T3 → COMPLETED

If T3 fails after T1 and T2 succeed:

T1 → T2 → T3 (FAILURE)

The compensation sequence becomes:

C2 → C1 → COMPENSATED

Compensation proceeds in reverse order because later business operations may depend on earlier operations.

### 2.3 Local transaction

A local transaction is an atomic operation within one service's database.

For example, the payment service can atomically:

- Validate the payment request.
- Record a payment charge.
- Store its transaction identifier.
- Commit its local database transaction.

The inventory service independently commits its reservation.

These transactions are not part of one shared ACID transaction.

### 2.4 Compensating transaction

A compensating transaction is a new business operation that semantically counteracts an earlier operation.

It is not necessarily a literal database rollback.

Examples:

| Forward transaction | Compensation |
|---|---|
| Reserve inventory | Release reservation |
| Charge payment | Refund payment |
| Create shipment | Cancel shipment |
| Book hotel | Cancel booking |
| Allocate resources | Deallocate resources |

Compensation can have its own failure conditions.

For example, a payment refund may fail because an external payment provider is unavailable.

Such failures require retry scheduling, reconciliation, and potentially manual intervention.

## 3. Saga Architecture

The implementation models three independent services.

<escape>
                    ORDER REQUEST
                         |
                         v
                 SAGA ORCHESTRATOR
                         |
              +----------+----------+
              |          |          |
              v          v          v
          INVENTORY    PAYMENT   SHIPPING
           SERVICE     SERVICE    SERVICE
              |          |          |
              v          v          v
           Reserve     Charge     Create
           Inventory   Payment    Shipment
              |          |          |
              +----------+----------+
                         |
                    SAGA STATUS
                         |
              +----------+----------+
              |                     |
           SUCCESS                FAILURE
              |                     |
              v                     v
          COMPLETED            COMPENSATION
                                    |
                              Reverse Order
                                    |
                                    v
                               RECOVERY
</escape>

The orchestrator maintains transaction progress and determines which compensation operations must execute after a failure.

Each service remains responsible for its own business operations.

## 4. Saga Execution Models

### 4.1 Choreography

In choreography, services coordinate through events without relying on a central transaction orchestrator.

A typical workflow is:

1. Order service publishes `OrderCreated`.
2. Inventory service consumes the event and reserves inventory.
3. Inventory service publishes `InventoryReserved`.
4. Payment service consumes the event and charges the customer.
5. Payment service publishes `PaymentCompleted`.
6. Shipping service consumes the event and creates the shipment.

Failure handling also uses events.

For example, a payment failure may publish `PaymentFailed`, causing the inventory service to release its reservation.

**Characteristics:**

- Event-driven coordination.
- Reduced central orchestration.
- Loose coupling between participating services.
- Distributed workflow logic.
- Greater complexity in understanding complete transaction execution.

Choreography is appropriate when workflows are relatively independent and event-driven coordination is already established.

### 4.2 Orchestration

In orchestration, a central coordinator determines the execution sequence.

The orchestrator:

1. Starts the Saga.
2. Invokes the first service.
3. Records the successful operation.
4. Invokes subsequent services.
5. Detects failures.
6. Executes compensations in reverse order.
7. Records the final transaction state.

The Python, C++17, and Java 17 implementations use orchestration as their principal coordination model.

The JavaScript implementation provides an event-driven orchestrator.

**Characteristics:**

- Centralized workflow control.
- Explicit transaction state management.
- Easier visibility into execution progress.
- Direct management of retry and compensation policies.
- Potential concentration of workflow complexity.

### 4.3 Choreography versus orchestration

| Dimension | Choreography | Orchestration |
|---|---|---|
| Coordinator | No central coordinator | Central orchestrator |
| Communication | Primarily events | Commands and responses |
| Workflow logic | Distributed across services | Centralized |
| Dependency visibility | Less explicit | More explicit |
| Monitoring | Requires event correlation | Central execution history |
| Failure handling | Event-driven | Coordinator-managed |
| Suitable applications | Loosely coupled workflows | Complex business workflows |

Neither approach guarantees global ACID transactions.

Both require durable messaging, idempotency, and failure recovery.

## 5. Saga State Management

The implementations use explicit Saga states.

| State | Meaning |
|---|---|
| PENDING | Saga has been created but not started |
| RUNNING | Forward transactions are executing |
| COMPENSATING | Recovery operations are executing |
| COMPLETED | All required forward transactions succeeded |
| COMPENSATED | All required compensations succeeded |
| FAILED | Execution or compensation requires intervention |

The main state transitions are:

<escape>
PENDING
   |
   v
RUNNING
   |
   +----------------------+
   |                      |
   v                      v
COMPLETED              COMPENSATING
                          |
                 +--------+--------+
                 |                 |
                 v                 v
            COMPENSATED          FAILED
</escape>

A Saga must not be treated as completed simply because one participating service succeeded.

Its final status depends on the complete workflow.

## 6. Forward Execution and Compensation

Consider an order with three operations.

### 6.1 Successful execution

| Sequence | Service | Operation | Result |
|---|---|---|---|
| 1 | Inventory | Reserve inventory | Success |
| 2 | Payment | Charge payment | Success |
| 3 | Shipping | Create shipment | Success |

Final status: `COMPLETED`.

### 6.2 Failure during shipping

| Sequence | Operation | Result |
|---|---|---|
| 1 | Reserve inventory | Success |
| 2 | Charge payment | Success |
| 3 | Create shipment | Failure |
| 4 | Refund payment | Compensation |
| 5 | Release inventory | Compensation |

Final status: `COMPENSATED`, provided both compensations succeed.

### 6.3 Compensation failure

Consider a different situation:

- Inventory reservation succeeds.
- Payment charge succeeds.
- Shipment creation fails.
- Payment refund fails.
- Inventory release succeeds.

The payment remains charged.

The Saga must not report successful compensation.

Its state becomes `FAILED`, and the remaining payment recovery must be retried or handled through an operational recovery process.

This distinction is important because a compensation failure can leave the distributed business operation partially applied.

## 7. Retry Management

Distributed services can experience temporary failures caused by:

- Network interruptions.
- Service overload.
- Database connection failures.
- External provider timeouts.
- Temporary resource unavailability.

Retry policies attempt to recover from transient errors.

The implementations demonstrate bounded retries with exponential backoff.

The delay can be expressed as:

\[
D_n = \min(D_0 \times 2^{n-1}, D_{\max})
\]

Where:

- \(D_n\): Delay before retry \(n\).
- \(D_0\): Initial retry delay.
- \(D_{\max}\): Maximum permitted delay.

Retries must be bounded.

Uncontrolled retries can amplify service overload and create cascading failures.

Production implementations should distinguish transient errors from permanent business failures.

Examples of permanent failures include invalid payment information and insufficient inventory.

## 8. Idempotency

Idempotency ensures that repeating an operation with the same logical identifier does not produce an unintended duplicate business effect.

Consider a payment request:

`ORDER-5001:CHARGE`

If the payment service processes the request but its response is lost, the orchestrator may retry.

Without idempotency, the customer could be charged twice.

A service should therefore associate a unique idempotency key with the logical operation.

A simplified key structure is:

`Saga ID + Step ID + Operation Type`

The service checks the key before executing a new operation.

A durable implementation should atomically store:

- The idempotency key.
- The operation result.
- The relevant business state.
- The operation status.

An important distinction is that a timeout does not prove an operation failed. The service may have committed the transaction even though the caller never received its response.

Idempotency is therefore essential for reliable retry handling.

## 9. Implementation Analysis

### 9.1 Python implementation

The Python script models a Saga through dataclasses, enums, callbacks, and service classes.

Important components:

| Component | Responsibility |
|---|---|
| `SagaStep` | Represents a forward operation and compensation |
| `Saga` | Maintains transaction state and history |
| `InventoryService` | Manages reservations |
| `PaymentService` | Manages charges and refunds |
| `ShippingService` | Manages shipment creation and cancellation |
| `SagaOrchestrator` | Executes steps and compensations |

The orchestrator maintains a list of successfully completed steps.

During compensation, it traverses this list in reverse order.

The script demonstrates successful execution and shipping failure.

It uses in-memory service state, so its execution history and transaction records are not durable across process restarts.

### 9.2 JavaScript implementation

The JavaScript implementation uses Node.js asynchronous programming and event-driven execution.

Important components:

| Component | Responsibility |
|---|---|
| `EventEmitter` | Publishes Saga execution events |
| `RetryPolicy` | Controls asynchronous retries |
| `IdempotentService` | Maintains operation keys |
| `SagaStep` | Defines actions and compensations |
| `Saga` | Maintains workflow state and event history |
| `SagaOrchestrator` | Coordinates asynchronous execution |

The implementation demonstrates how an orchestrator can publish events without making every participating component directly dependent on its internal state.

The services use asynchronous methods and JavaScript collections.

The in-memory event history is suitable for demonstrating workflow behavior but is not a replacement for a durable event store.

### 9.3 C++17 implementation

The C++17 program emphasizes explicit domain modeling and transaction control.

It uses:

- Enumerations for transaction states.
- Structures for steps and audit events.
- Classes for independent services.
- `std::function` for forward and compensation operations.
- STL containers for transaction state.
- Exceptions for failure propagation.

The `Saga` class controls execution and reverse-order compensation.

The implementation is intentionally independent of external libraries.

Its service state is maintained in memory, and its retry policy demonstrates bounded attempts rather than production-grade distributed retry scheduling.

### 9.4 Java 17 implementation

The Java implementation models enterprise-oriented transaction management.

It uses:

- Records for immutable order and audit data.
- Enums for transaction states.
- Functional interfaces for transaction operations.
- Service classes for business responsibilities.
- A dedicated retry policy.
- A Saga orchestrator for workflow execution.

The separation between domain objects, service operations, and orchestration logic makes the implementation suitable for extending with additional enterprise policies.

The example uses synchronized service methods for in-process access. These locks do not provide distributed synchronization across independently deployed services.

### 9.5 PostgreSQL implementation

The PostgreSQL implementation models the relational side of Saga execution.

Its schema contains:

| Table | Purpose |
|---|---|
| `service_registry` | Participating services |
| `orders` | Business order information |
| `sagas` | Saga execution instances |
| `saga_steps` | Forward and compensation definitions |
| `idempotency_records` | Duplicate-operation prevention |
| `inventory_reservations` | Inventory service effects |
| `payments` | Payment service effects |
| `shipments` | Shipping service effects |
| `saga_outbox` | Events awaiting publication |
| `saga_events` | Execution history |

The implementation includes:

- Primary and foreign keys.
- Unique constraints.
- Check constraints.
- Operational indexes.
- PL/pgSQL functions.
- A stored procedure.
- A reporting view.
- JSONB event details.
- Idempotency records.
- Local transactional execution.

The SQL demonstrates local database state changes and compensation.

It does not provide an actual network-connected microservices deployment.

## 10. Transactional Outbox Pattern

A Saga commonly communicates through a message broker.

A potential failure occurs when a service commits a local database transaction but fails to publish its corresponding event.

For example:

1. Inventory reservation commits.
2. The service attempts to publish `InventoryReserved`.
3. The message broker is unavailable.
4. The database records the reservation, but downstream services never receive the event.

The Transactional Outbox Pattern addresses this problem.

The service stores its business change and outgoing event in the same local database transaction.

A separate publisher retrieves unpublished events and sends them to the message broker.

The PostgreSQL implementation includes the `saga_outbox` table.

A production publisher must also manage:

- Publication retries.
- Duplicate message delivery.
- Event ordering.
- Consumer deduplication.
- Dead-letter handling.

The outbox does not make message delivery globally exactly-once. It supports reliable delivery with appropriate deduplication.

## 11. Failure Handling and Recovery

Distributed transaction failures can occur at different stages.

| Failure | Required handling |
|---|---|
| Service unavailable | Bounded retry |
| Network timeout | Resolve operation outcome using idempotency |
| Duplicate request | Return previously recorded result |
| Database failure | Retry or recover local transaction |
| Forward operation failure | Start compensation |
| Compensation failure | Retry and escalate |
| Message delivery failure | Outbox retry |
| Process crash | Resume from durable Saga state |
| Duplicate event | Consumer deduplication |
| Permanent external failure | Reconciliation or manual intervention |

A production Saga should distinguish between a failed forward operation and a failed compensation.

These conditions have different operational consequences.

## 12. Concurrency and Consistency

Multiple Sagas may attempt to modify the same business resource.

For example, two customers may attempt to reserve the final available product.

A Saga orchestrator alone does not prevent this race condition.

The inventory service must enforce its own consistency rules through appropriate mechanisms, such as:

- Database row locking.
- Conditional updates.
- Optimistic concurrency control.
- Unique constraints.
- Atomic inventory allocation.

The PostgreSQL example uses unique constraints for individual order reservations and payments.

A production inventory system also requires stock-level validation and concurrency-safe quantity allocation.

### 12.1 Eventual consistency

Saga execution generally provides eventual consistency rather than immediate global consistency.

During execution, some services may have committed their local transactions while other services are still processing.

For example, inventory may be reserved before payment succeeds.

The business system must explicitly define whether this intermediate state is acceptable and how long it may remain unresolved.

### 12.2 Semantic locking

A business process can reserve a resource for a limited period rather than holding a database lock across multiple services.

For example, an inventory reservation may expire after a defined interval if payment does not complete.

This is a business-level reservation, not a conventional database lock.

It helps manage concurrent workflows without maintaining long-running distributed database transactions.

## 13. Saga Pattern Compared with Two-Phase Commit

Two-Phase Commit (2PC) and Saga solve different distributed transaction coordination problems.

| Dimension | Saga | Two-Phase Commit |
|---|---|---|
| Coordination | Sequential business operations | Prepare and commit phases |
| Transaction model | Local transactions | Distributed atomic commit |
| Rollback | Compensating operations | Transaction rollback |
| Resource locking | Generally avoids global locks | May retain prepared resources |
| Consistency | Eventual consistency | Atomic commit semantics |
| Service autonomy | Generally higher | Requires transaction coordination support |
| Long-running workflows | Suitable | Often less suitable |
| Compensation | Explicit business operations | Not the primary rollback mechanism |

A Saga does not provide the same atomicity guarantees as 2PC.

Its advantage is that it allows independently managed services to participate in long-running business processes without requiring a global transaction coordinator.

## 14. Performance Considerations

Saga performance depends on service latency, workflow length, retries, and communication overhead.

For a sequential Saga with three operations:

\[
T_{\text{total}} =
T_1 + T_2 + T_3 + T_{\text{communication}}
\]

If a failure occurs, compensation introduces additional latency:

\[
T_{\text{recovery}} =
T_{\text{failure}} +
\sum_{i=1}^{k} T_{C_i}
\]

Where \(k\) is the number of successfully completed forward operations requiring compensation.

Important performance considerations include:

- Keep local transactions short.
- Avoid unnecessary service calls.
- Use bounded retries.
- Apply exponential backoff with jitter.
- Index Saga identifiers and execution states.
- Archive old execution history.
- Process independent operations concurrently only when business dependencies permit it.
- Avoid uncontrolled compensation retries.
- Monitor long-running transactions.

The PostgreSQL indexes support Saga lookup, step execution, event retrieval, and pending outbox processing.

## 15. Security Considerations

Distributed transaction coordination introduces security requirements beyond ordinary database validation.

### Service authentication

Services should authenticate incoming commands and verify the identity of the requesting service.

### Authorization

A service must verify that a caller is authorized to execute the requested business operation.

### Message integrity

Events and commands should be protected against unauthorized modification.

### Sensitive data protection

Payment credentials and personal information should not be unnecessarily included in Saga event payloads.

### Idempotency protection

Idempotency keys must be scoped to the correct service, operation, and business transaction.

### Audit integrity

Execution history should record important state transitions, failure reasons, and compensation outcomes.

### Access control

Database permissions should prevent application services from modifying unrelated service-owned data.

The PostgreSQL demonstration shares tables within one schema for educational purposes. Independent production services should generally own their respective databases and expose controlled interfaces.

## 16. Practical Limitations

The five implementations demonstrate Saga concepts but do not constitute a complete production distributed transaction platform.

| Implementation | Demonstrated capability | Important limitation |
|---|---|---|
| Python | Orchestration and compensation | In-memory state |
| JavaScript | Asynchronous event-driven execution | In-memory event history |
| C++17 | Explicit state management | No persistent transaction recovery |
| Java 17 | Enterprise domain modeling | No distributed coordination infrastructure |
| PostgreSQL | Relational Saga workflow | No actual external service communication |

A production system needs durable state transitions, persistent idempotency, message delivery infrastructure, recovery workers, observability, and reconciliation.

The most important operational requirement is that a Saga must be recoverable after a process crash.

Persisting a Saga state alone is insufficient if the service cannot determine whether an external operation committed before the process failed.

The operation outcome must be reconciled using durable service-side transaction identifiers and idempotency records.

## 17. Execution Instructions

### Python

- Save the first source file as `saga_pattern.py`.
- Run `python saga_pattern.py`.
- Observe the successful order and compensated failed order.

### JavaScript

- Save the second source file as `saga_pattern.js`.
- Use Node.js 18 or later.
- Run `node saga_pattern.js`.
- Observe asynchronous events and compensation.

### C++17

- Save the third source file as `saga_pattern.cpp`.
- Compile using a C++17-compatible compiler.
- Execute the resulting program.

### Java 17

- Save the fourth source file as `SagaPattern.java`.
- Compile using `javac SagaPattern.java`.
- Execute using `java SagaPattern`.

### PostgreSQL

- Save the fifth source file as `saga_pattern.sql`.
- Execute using PostgreSQL 15 or later with permission to create schemas, tables, functions, and procedures.
- The script uses the PostgreSQL `psql` variable-substitution facility for the demonstration transactions.

## 18. Technical Concepts Demonstrated

| Concept | Practical application |
|---|---|
| Distributed transaction | Coordinating independent business services |
| Saga orchestration | Central workflow coordination |
| Choreography | Event-based service coordination |
| Local transaction | Atomic service-owned database operation |
| Compensation | Semantic reversal of business effects |
| Idempotency | Prevention of duplicate business operations |
| Retry policy | Recovery from transient failures |
| Exponential backoff | Controlled retry scheduling |
| Event sourcing concepts | Recording transaction execution history |
| Transactional outbox | Reliable publication of committed events |
| Eventual consistency | Managing intermediate distributed states |
| Semantic locking | Business-level resource reservation |
| Reconciliation | Resolving uncertain or incomplete operations |
| Recovery workflow | Handling failed compensation |

The Saga Pattern is particularly useful when a business operation spans multiple independently managed services and cannot reasonably be implemented as one global ACID transaction. Its effectiveness depends on well-defined compensation rules, durable execution records, idempotent operations, and reliable recovery mechanisms.
