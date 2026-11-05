# Modular Monolith: Boundaries, Modules, and Migration Strategy

## 1. Modular Monolith Architecture

A modular monolith is an application deployed as one independently executable application while maintaining internally separated business modules.

The architecture combines two properties:

- **Monolithic deployment:** Modules execute within one application process and generally share the deployment lifecycle.
- **Modular internal structure:** Each module owns a defined business capability, its domain rules, application services, and internal data responsibilities.

A modular monolith is not simply a collection of directories inside one codebase. Its defining characteristic is controlled interaction between independently organized business modules.

### Architectural structure

The implementations use an enterprise order-management domain.

| Module | Business responsibility | Data ownership |
|---|---|---|
| Shared | Common identities and domain conventions | Customer identities |
| Inventory | Product catalog and stock reservations | Products and reservations |
| Payments | Payment authorization and refunds | Payment records |
| Orders | Order creation and lifecycle | Orders |
| Notifications | Event delivery and notifications | Notification events |
| Architecture | Dependency governance and migration | Module metadata |

The logical architecture is:

    Enterprise Application
            |
            +-- Shared Kernel
            |
            +-- Inventory Module
            |       |
            |       +-- Product Catalog
            |       +-- Stock Reservations
            |
            +-- Payment Module
            |       |
            |       +-- Authorization
            |       +-- Refunds
            |
            +-- Order Module
            |       |
            |       +-- Order Lifecycle
            |       +-- Business Orchestration
            |
            +-- Notification Module
            |       |
            |       +-- Event Consumption
            |       +-- Notification Delivery
            |
            +-- Architecture Governance

All modules execute within one application deployment. Their internal separation does not require network communication.

## 2. Module Boundaries

A module boundary identifies which business responsibilities belong to a particular module and which operations other modules can request.

A well-designed boundary defines:

- Business ownership.
- Public application interfaces.
- Internal domain rules.
- Data ownership.
- Permitted dependencies.
- Transaction responsibilities.
- Events published to other modules.

### Inventory boundary

The inventory module owns product availability.

Its responsibilities include:

- Registering products.
- Maintaining stock quantities.
- Reserving stock.
- Committing reservations.
- Releasing reservations.
- Preventing negative stock.

The order module cannot directly change an inventory quantity. It must request a reservation through the inventory interface.

### Payment boundary

The payment module owns financial transaction state.

Its responsibilities include:

- Payment authorization.
- Payment identification.
- Refund processing.
- Payment state validation.
- Payment history.

An order does not independently determine whether a payment has been refunded. It requests the operation from the payment module.

### Order boundary

The order module owns the order lifecycle.

It coordinates other modules to complete a business operation.

Its responsibilities include:

- Validating customer and product references.
- Calculating order amounts.
- Requesting inventory reservations.
- Requesting payment authorization.
- Confirming orders.
- Initiating cancellations.
- Publishing order-related domain events.

The order module coordinates the workflow without taking ownership of inventory or payment internals.

### Notification boundary

The notification module reacts to published events.

It does not need direct access to the order module's internal objects or database tables.

For example:

- `OrderConfirmed` initiates a confirmation notification.
- `OrderCancelled` initiates a cancellation notification.

This reduces direct dependencies between business capabilities.

## 3. Encapsulation and Information Hiding

Encapsulation prevents one module from modifying another module's internal state.

A public interface exposes supported operations without exposing implementation details.

| Mechanism | Purpose |
|---|---|
| Private attributes | Protect internal state |
| Application services | Expose supported business operations |
| Domain objects | Enforce business invariants |
| Immutable responses | Prevent accidental external mutation |
| Explicit interfaces | Restrict module interactions |
| Dependency validation | Detect architectural violations |

Python uses module-specific classes and explicit service references.

JavaScript uses private class fields, including `#products`, `#orders`, and `#payments`.

C++ uses private class members and public operations.

Java uses nested domain types, private state, records, and service methods.

The implementations demonstrate different language-specific approaches to the same architectural principle.

## 4. Dependency Management

Module dependencies determine which modules can communicate with other modules.

A dependency should be justified by a business capability rather than convenience.

The example architecture uses the following dependency rules:

| Source module | Permitted dependencies |
|---|---|
| Orders | Inventory, Payments, Shared |
| Inventory | Shared |
| Payments | Shared |
| Notifications | Shared |

The notification module receives order events without depending on the order module's internal implementation.

### Dependency direction

    Orders
       |
       +------> Inventory
       |
       +------> Payments
       |
       +------> Shared

    Inventory ------> Shared

    Payments -------> Shared

    Notifications ---> Shared
          ^
          |
       Events

The event relationship represents runtime communication. It does not require a compile-time dependency on another module's private implementation.

### Circular dependencies

A circular dependency occurs when modules depend on one another directly or indirectly.

Example:

    Orders ------> Inventory
       ^               |
       |               |
       +---------------+

This creates unnecessary coupling.

Possible consequences include:

- Difficult testing.
- Complicated initialization.
- Unclear business ownership.
- Changes propagating across unrelated modules.
- Difficult extraction into separate services.

The architecture validators in all four application implementations identify dependencies that violate the defined rules.

A production architecture test should also inspect actual package or project dependencies rather than relying only on a manually supplied dependency list.

## 5. Domain Events and Cross-Module Communication

A domain event represents a meaningful business occurrence.

It communicates that something has happened rather than instructing another module to perform a particular implementation step.

Examples:

| Event | Meaning |
|---|---|
| `OrderConfirmed` | An order has been successfully confirmed |
| `OrderCancelled` | An order has been cancelled |
| `PaymentAuthorized` | A payment authorization succeeded |
| `StockReserved` | Inventory has been reserved |

### Event-driven interaction

    Order Module
         |
         | Creates and confirms order
         |
         v
    OrderConfirmed
         |
         v
    Event Dispatcher
         |
         +------> Notification Module
         |
         +------> Other permitted consumers

This model reduces direct communication between modules.

### Synchronous and asynchronous events

**Synchronous in-process events**

- Executed within the application process.
- Have low communication overhead.
- Can immediately expose handler failures.
- Can increase request latency.
- May introduce coupling through execution order.

**Asynchronous events**

- Stored for later processing.
- Allow consumers to operate independently.
- Support retry mechanisms.
- Require event delivery and duplicate-processing controls.

The Python and Java implementations demonstrate in-process dispatch.

The JavaScript implementation demonstrates asynchronous event handlers using promises.

The PostgreSQL implementation uses a transactional outbox.

### Transactional outbox

An outbox records an event in the same database transaction as the business change.

The order and its corresponding event are committed together.

    Database Transaction
          |
          +-- Insert Order
          |
          +-- Authorize Payment
          |
          +-- Confirm Order
          |
          +-- Insert Outbox Event
          |
          +-- COMMIT
                  |
                  v
             Outbox Worker
                  |
                  v
             Event Delivery

This avoids the failure scenario in which an order commits successfully but the application crashes before publishing its event.

Outbox processing still requires:

- Retry policies.
- Duplicate-event handling.
- Idempotent consumers.
- Monitoring.
- Dead-letter or terminal-failure handling.

The outbox does not automatically guarantee exactly-once delivery.

## 6. Transaction Management

A modular monolith commonly uses one relational database and can perform cross-module operations within a single database transaction.

This simplifies atomic business operations compared with independently deployed services.

The order workflow includes:

1. Validate customer and product.
2. Reserve inventory.
3. Create an order.
4. Authorize payment.
5. Commit the reservation.
6. Confirm the order.
7. Record the domain event.
8. Commit the database transaction.

### Atomicity

If a database operation fails before the transaction commits, the database can roll back all changes made within that transaction.

This protects consistency between related database records.

### Concurrency

Two customers might attempt to reserve the last available product simultaneously.

A stock check without concurrency control can produce overselling.

The PostgreSQL implementation uses `SELECT ... FOR UPDATE` to lock the selected product row while reserving inventory.

The stock quantity is then reduced within the same transaction.

The quantity constraint provides another layer of protection:

- Available quantity must be greater than or equal to zero.
- Reservation quantity must be positive.

### Compensation

A distributed payment provider cannot normally participate in a PostgreSQL transaction.

If an external payment authorization succeeds but a subsequent business operation fails, a compensating operation may be necessary.

For example:

- Reserve inventory.
- Authorize payment.
- Encounter a subsequent failure.
- Refund or void the authorization.
- Release the reservation.

This is a simplified form of a saga-style workflow.

A compensation is a new business operation, not a database rollback. It can itself fail and therefore requires durable retry and reconciliation mechanisms.

The in-memory language implementations demonstrate compensation concepts. Their state is not durable and they are not substitutes for production transaction management.

## 7. Modular Monolith Versus Microservices

Both architectures can use bounded contexts and domain-driven design.

Their main differences concern deployment, communication, infrastructure, and data ownership.

| Dimension | Modular Monolith | Microservices |
|---|---|---|
| Deployment | One application deployment | Independently deployed services |
| Execution | Usually one process | Separate service processes |
| Communication | In-process calls and events | Network calls and messaging |
| Database | Can share one database with module ownership | Usually independently owned databases |
| Transactions | Can use local ACID transactions | Often require distributed workflow patterns |
| Scaling | Usually scales application instances | Services can scale independently |
| Operations | Relatively centralized | Requires distributed operations |
| Failure isolation | Primarily process-level | Can provide service-level isolation |
| Testing | Module and application integration | Service and contract integration |

A modular monolith does not automatically become a microservice architecture simply because its code is divided into modules.

The critical distinction is the operational and deployment boundary.

## 8. Migration Strategy

A modular monolith can serve as a controlled starting point for a system that may eventually require independently deployed services.

Migration should be based on measurable requirements rather than automatically splitting every module.

Typical reasons for extraction include:

- Independent scaling requirements.
- Different availability requirements.
- Independent deployment schedules.
- Separate security boundaries.
- Distinct technology requirements.
- Different operational ownership.
- Excessive contention within a module.

### Progressive extraction

The implementations use five migration stages.

| Stage | Description |
|---|---|
| Monolith | Module is part of the original application |
| Boundaries Defined | Business ownership and interfaces are established |
| Module Isolated | Internal dependencies and data ownership are controlled |
| Contract Stable | External communication contracts are validated |
| Externalized | Module operates as an independently deployed service |

The transition is:

    Existing Monolith
          |
          v
    Define Business Boundary
          |
          v
    Isolate Module Internals
          |
          v
    Stabilize Application Contract
          |
          v
    Introduce External Service
          |
          v
    Gradually Transfer Traffic

### Strangler pattern

The strangler pattern replaces selected functionality gradually rather than rewriting the entire application.

An application gateway or adapter routes operations to either the original module or its external replacement.

    Application Clients
            |
            v
       Order Gateway
            |
       +----+----+
       |         |
       v         v
    Local     Remote
    Module    Service
       |         |
       +----+----+
            |
       Application
       Integration

The JavaScript implementation includes an `OrderGateway` that can switch between local and remote order processing.

The gateway represents the routing mechanism. A production implementation must also handle network timeouts, authentication, retries, observability, contract compatibility, and remote-service failures.

### Data migration considerations

Extracting a module requires a deliberate data migration strategy.

A typical process is:

1. Identify tables owned by the module.
2. Identify all existing readers and writers.
3. Establish a stable application contract.
4. Introduce a new service-owned database.
5. Backfill existing records.
6. Synchronize subsequent changes.
7. Verify record counts and consistency.
8. Switch reads and writes using controlled routing.
9. Remove obsolete access paths.
10. Monitor the new service independently.

Avoid allowing the old application and new service to independently write the same business data without a clearly defined ownership and synchronization strategy.

## 9. Python Implementation

The Python script demonstrates a domain-oriented modular monolith using standard-library features.

| Component | Implementation |
|---|---|
| Inventory | `InventoryModule` |
| Payments | `PaymentModule` |
| Orders | `OrderModule` |
| Notifications | `NotificationModule` |
| Event handling | `EventBus` |
| Shared domain | Dataclasses and enums |
| Architecture governance | `ArchitectureValidator` |
| Migration | `ModuleMigration` |

### Important mechanisms

**Dataclasses**

Product, reservation, order, payment, and domain event objects use dataclasses.

**Enums**

Order and payment states use explicit enumeration types.

**Event bus**

The event bus registers handlers by event type and dispatches business events.

**Validation**

Invalid identifiers, quantities, products, stock availability, and payment states generate domain exceptions.

**Compensation**

If payment authorization fails, the inventory reservation is released.

**Architecture validation**

The dependency validator checks module relationships against an allowed dependency map.

**Migration state**

The migration object prevents invalid transitions and requires an HTTPS endpoint before externalization.

### Limitations

The Python implementation uses in-memory dictionaries and synchronous event handlers.

It does not provide durable persistence, multi-process coordination, distributed locking, or crash recovery.

It is an executable domain model rather than a production financial application.

## 10. JavaScript Implementation

The JavaScript implementation emphasizes asynchronous application services and controlled module state.

| Component | Implementation |
|---|---|
| Inventory | `InventoryModule` |
| Payments | `PaymentModule` |
| Orders | `OrderModule` |
| Notifications | `NotificationModule` |
| Event dispatch | `DomainEventPublisher` |
| Architecture governance | `ModuleDependencyPolicy` |
| Extraction routing | `OrderGateway` |

### JavaScript-specific decisions

**Private class fields**

The inventory and payment modules use private `Map` instances.

Other modules cannot directly access these internal collections.

**Promises**

Payment authorization and event processing use asynchronous methods.

**EventEmitter**

Node.js event infrastructure dispatches events to registered subscribers.

**Integer currency representation**

Money is represented in integer minor units rather than floating-point decimal values.

For example, INR 75,000.00 is represented as 7,500,000 paise.

**Idempotency**

The order module stores an idempotency key and request fingerprint.

Repeating the same operation with the same key and parameters returns the original order.

Reusing the key with different parameters is rejected.

**Gateway routing**

The `OrderGateway` supports local and remote implementations through a common operation.

### Production considerations

The implementation uses in-memory state. It does not provide durable idempotency records or distributed concurrency control.

The event dispatcher uses `Promise.allSettled`, allowing all registered handlers to execute while making failures visible.

A transactional outbox and durable retry mechanism are required for reliable production delivery.

## 11. C++17 Implementation

The C++ program focuses on explicit domain types, private state, and controlled state transitions.

| Component | Implementation |
|---|---|
| Inventory | `InventoryModule` |
| Payments | `PaymentModule` |
| Orders | `OrderModule` |
| Product | `Product` struct |
| Reservation | `Reservation` struct |
| Payment | `Payment` struct |
| Order | `Order` struct |
| Architecture | `DependencyRegistry` |
| Migration | `ModuleMigration` |

### Engineering decisions

**STL containers**

- `unordered_map` provides average constant-time identifier lookups.
- `map` maintains ordered payment records.
- `set` stores permitted module dependencies.
- `vector` collects architecture violations.

**References between modules**

`OrderModule` receives references to inventory and payment modules.

This avoids creating duplicate module instances and makes dependencies explicit.

**Exception handling**

Domain failures use dedicated exception types derived from `runtime_error`.

**Currency**

Amounts use signed 64-bit integer minor units.

Overflow is checked before multiplication.

**Migration**

The migration object implements a controlled state machine.

An invalid state transition produces an exception.

### Performance

For the primary in-memory containers:

- Product lookup: average O(1).
- Payment lookup: O(log n).
- Order lookup: average O(1).
- Dependency validation: O(V + E), where V represents modules and E represents dependency relationships.

The implementation uses a single-process model and does not provide thread-safe concurrent stock reservations.

## 12. Java 17 Implementation

The Java implementation models enterprise application services and explicit domain ownership.

| Component | Implementation |
|---|---|
| Shared kernel | Domain exceptions, events, enums |
| Inventory | `InventoryModule` |
| Payments | `PaymentModule` |
| Orders | `OrderModule` |
| Notifications | `NotificationModule` |
| Architecture governance | `ArchitecturePolicy` |
| Migration | `ModuleMigration` |

### Java-specific decisions

**Records**

Immutable records represent products, reservations, payments, orders, and domain events.

**Enums**

Explicit enums represent payment, order, and migration states.

**Collections**

Hash maps maintain domain state, while immutable sets define permitted dependencies.

**Service classes**

Each module provides operations for its own business capability.

**Application composition**

The `Application` class constructs the modules and supplies their dependencies.

This is the composition root.

**Concurrency**

Synchronized operations protect selected in-memory inventory and order transitions within the single application instance.

These controls do not replace database-level concurrency management or distributed locking.

**State transitions**

Order cancellation is permitted only for confirmed orders.

Payment refunds are restricted to authorized payments.

**Event subscriptions**

The notification module registers handlers for order-confirmation and cancellation events.

### Enterprise implications

The design supports a clear separation between application orchestration and domain ownership.

A larger implementation could place each module in a separate Java package while exposing only its application interfaces.

This is important because Java package organization alone does not automatically prevent unwanted cross-module dependencies.

## 13. PostgreSQL Implementation

The SQL script represents the relational architecture using separate database schemas.

| Schema | Responsibility |
|---|---|
| `shared` | Customer identities |
| `inventory` | Products and stock reservations |
| `payments` | Payment records |
| `orders` | Order records and reservation relationships |
| `notifications` | Transactional event outbox |
| `architecture` | Module dependencies and migration states |

### Database ownership

PostgreSQL schemas provide logical namespace separation.

For example:

- `inventory.products`
- `payments.payment_records`
- `orders.order_records`
- `notifications.event_outbox`

This organization makes module ownership visible.

Schema separation alone is not a complete security boundary.

Production applications should also use database roles, schema-level privileges, restricted table access, and carefully controlled stored procedure permissions.

### Integrity constraints

The SQL implementation includes:

- Primary keys.
- Foreign keys.
- Unique constraints.
- Nonnegative stock constraints.
- Positive payment and product amounts.
- Valid state constraints.
- Migration endpoint validation.

These constraints enforce important business invariants at the database level.

### Stock reservation

The `inventory.reserve_stock` function uses row-level locking.

It prevents concurrent transactions from independently reserving the same available quantity.

The function:

1. Validates the requested quantity.
2. Locks the product record.
3. Reads available stock.
4. Rejects insufficient inventory.
5. Decreases stock.
6. Creates an active reservation.
7. Returns the reservation identifier.

The release function restores stock and prevents repeated releases.

### Order creation

The `orders.create_order` procedure coordinates the relational workflow.

It validates the customer and product, reserves inventory, creates the order, records payment authorization, commits the reservation, confirms the order, and inserts an outbox event.

The caller controls the transaction boundary.

### Transactional outbox

The outbox records business events as database rows.

A worker can claim pending events using `FOR UPDATE SKIP LOCKED`.

This supports concurrent event workers without having them claim the same locked rows.

The worker must still implement actual delivery, retries, duplicate detection, and terminal-failure handling.

### SQL reporting

The script contains:

- An order summary view.
- Revenue aggregation by product.
- Dependency evaluation using a CTE.
- Cancellation eligibility queries.
- Order status reporting.
- Event processing queries.
- Module migration reporting.

### Database limitations

The payment implementation simulates local payment authorization.

A real payment provider is an external system and cannot be atomically committed with a PostgreSQL transaction.

A production implementation should use an explicit payment workflow, durable provider references, idempotency keys, compensation, and reconciliation.

The example also retains order and payment records for demonstration rather than implementing a complete financial ledger.

## 14. Testing and Failure Scenarios

A modular monolith requires both business tests and architecture tests.

### Domain tests

| Scenario | Expected result |
|---|---|
| Valid product registration | Product created |
| Duplicate product | Validation failure |
| Positive stock reservation | Stock decreases |
| Reservation exceeding stock | Operation rejected |
| Valid payment authorization | Payment authorized |
| Invalid payment amount | Operation rejected |
| Valid order creation | Order confirmed |
| Payment authorization failure | Reservation compensated |
| Valid cancellation | Payment refunded |
| Repeated cancellation | No duplicate refund |
| Unknown order | Not-found exception |

### Architecture tests

| Scenario | Expected result |
|---|---|
| Orders depends on inventory | Allowed |
| Orders depends on payments | Allowed |
| Inventory depends on shared | Allowed |
| Inventory depends directly on orders | Violation |
| Notification handles an order event | Allowed |
| Module bypasses another module's public interface | Violation |

### Operational failure scenarios

Production systems should explicitly test:

- Database connection loss.
- Deadlocks.
- Concurrent reservations.
- Event publication failures.
- Duplicate event delivery.
- Payment-provider timeouts.
- Failed payment compensation.
- Expired stock reservations.
- Migration rollback.
- Incorrect service routing.
- Partially completed data migration.

## 15. Security and Operational Controls

A modular monolith simplifies some operational responsibilities because the application can be deployed and monitored as one unit.

It does not remove application security requirements.

### Security controls

- Authenticate application users.
- Authorize access to each business capability.
- Validate input at public module interfaces.
- Restrict database privileges by schema and responsibility.
- Keep credentials outside source code.
- Protect sensitive payment information.
- Use parameterized SQL.
- Audit financial state transitions.
- Avoid exposing internal domain objects through public APIs.
- Validate remote service authentication during module extraction.

### Observability

Useful production measurements include:

| Metric | Purpose |
|---|---|
| Request latency | Measure application responsiveness |
| Order failure rate | Detect order-processing problems |
| Reservation failure rate | Detect inventory contention |
| Payment authorization failures | Identify payment problems |
| Outbox backlog | Measure event-delivery delays |
| Event retry count | Identify unreliable consumers |
| Database lock wait time | Detect concurrency problems |
| Module-level error rate | Identify problematic business boundaries |

Structured logs should include correlation identifiers and relevant module names.

Sensitive information should not be written into application logs.

## 16. Performance Considerations

A modular monolith avoids many network calls between internal business modules.

Its performance still depends on database access patterns, locking, application concurrency, and module interactions.

| Concern | Engineering approach |
|---|---|
| Repeated database reads | Use appropriate indexes and query optimization |
| Stock contention | Use row-level locking and short transactions |
| Expensive event handlers | Move work to asynchronous consumers |
| Large shared collections | Use bounded queries and pagination |
| Slow external integrations | Use timeouts and controlled retries |
| Module coupling | Prefer stable interfaces and domain events |
| Large application deployment | Measure build and startup performance |

Module boundaries should not create unnecessary internal abstractions or excessive event chains.

A direct application-service call is appropriate when a caller requires an immediate result. Events are appropriate when communicating that a business occurrence has taken place.

## 17. Implementation Comparison

| Engineering aspect | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Module ownership | Classes | Private class fields | Encapsulated classes | Domain services | Schemas |
| State management | Dictionaries | Maps | STL containers | Collections | Relational tables |
| Validation | Exceptions | Validation functions | Domain exceptions | Custom exceptions | Constraints and functions |
| Communication | Event bus | EventEmitter | Explicit service calls | Event dispatcher | Outbox |
| Architecture checks | Validator | Policy class | Dependency registry | Architecture policy | Dependency view |
| Migration | State machine | Gateway | State machine | State machine | Migration function |
| Persistence | In-memory | In-memory | In-memory | In-memory | Durable relational storage |

## 18. Important Architectural Distinctions

The following concepts should not be treated as interchangeable.

| Concept | Meaning |
|---|---|
| Modular monolith | One deployment with internally separated modules |
| Module boundary | Division of business ownership and implementation |
| Bounded context | A domain-model boundary with consistent business terminology |
| Encapsulation | Restriction of access to internal implementation details |
| Shared kernel | A deliberately small set of shared domain concepts |
| Domain event | A record of a meaningful business occurrence |
| Application service | Coordinates a business operation |
| Repository | Provides controlled access to persisted domain data |
| Transaction | Defines an atomic unit of database work |
| Saga | Coordinates a business workflow using multiple transactions and compensations |
| Transactional outbox | Stores events alongside business changes for reliable publication |
| Anti-corruption layer | Translates between different models or system contracts |
| Strangler pattern | Replaces existing functionality incrementally |
| Microservice | An independently deployable service with its own operational boundary |

A modular monolith is an architectural organization strategy, not a restriction against using events, multiple database schemas, background workers, or external integrations.

Its central requirement is that business modules remain well-defined, independently understandable, and connected through controlled interfaces.
