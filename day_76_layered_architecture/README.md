# Layered Architecture: Presentation, Application, Domain and Infrastructure

## 1. Architecture Overview

Layered Architecture is a software design approach that separates an application into logical layers. Each layer has a defined responsibility and communicates with other layers through explicit interfaces and contracts.

This implementation uses four principal layers:

1. Presentation Layer
2. Application Layer
3. Domain Layer
4. Infrastructure Layer

The architecture separates user interaction, workflow orchestration, business rules and technical implementation.

### Architectural Structure

+------------------------------------------------------+
| PRESENTATION LAYER |
| |
| CLI | Controllers | Request Validation |
+---------------------------+--------------------------+
|
v
+------------------------------------------------------+
| APPLICATION LAYER |
| |
| Use Cases | Services | Workflow Orchestration |
| Transaction Coordination | Command Handling |
+---------------------------+--------------------------+
|
v
+------------------------------------------------------+
| DOMAIN LAYER |
| |
| Entities | Value Objects | Business Rules |
| Aggregates | Domain Events | Invariants |
+---------------------------+--------------------------+
^
|
+------------------------------------------------------+
| INFRASTRUCTURE LAYER |
| |
| Database | File Storage | Repositories |
| External Services | Logging | Messaging |
+------------------------------------------------------+

The diagram describes logical responsibilities rather than a requirement that every dependency must point downward. In dependency-inverted designs, infrastructure implements interfaces defined by the application or domain-facing contracts.

## 2. Presentation Layer

The Presentation Layer is the application's external interaction boundary.

It receives input, validates request structure, invokes application operations and converts results into responses.

### Responsibilities

- Accept user or client requests.
- Validate input format and required fields.
- Perform request-level authorization checks.
- Invoke application services.
- Convert application results into display formats.
- Translate known application exceptions into appropriate response codes.
- Avoid implementing business rules.
- Avoid directly accessing database tables.

### Implementations

| Language | Presentation implementation |
|---|---|
| Python | `OrderCLI` |
| JavaScript | `OrderController` |
| C++17 | `Presentation::Console` |
| Java 17 | `ConsoleController` |
| PostgreSQL | Reporting views and application-facing procedures |

The Python CLI demonstrates user interaction. The JavaScript controller demonstrates HTTP-style response handling without requiring an external web framework.

### Presentation Validation

Presentation validation concerns request correctness.

Examples:

- Missing customer identifier.
- Incorrect request structure.
- Missing order items.
- Invalid request parameters.

The domain layer independently enforces business invariants. A client cannot bypass business rules merely by avoiding presentation-level validation.

## 3. Application Layer

The Application Layer coordinates operations that fulfil business use cases.

It determines the sequence of operations, invokes domain behavior and communicates with infrastructure through interfaces.

### Responsibilities

- Implement application use cases.
- Coordinate domain objects.
- Manage operation sequencing.
- Establish transaction boundaries.
- Invoke repository interfaces.
- Coordinate audit and event publication.
- Apply application-level authorization.
- Handle workflow failures.

### Example Workflow

An order creation operation follows this sequence:

1. Receive a create-order command.
2. Construct and validate domain objects.
3. Save the order through a repository interface.
4. Record an audit event.
5. Return an immutable or structured result.

Order confirmation follows a separate workflow:

1. Retrieve the order.
2. Invoke the domain confirmation operation.
3. Persist the updated aggregate.
4. Record the confirmation event.
5. Return the updated order state.

### Implementation Mapping

| Language | Application component |
|---|---|
| Python | `OrderApplicationService` |
| JavaScript | `OrderApplicationService` |
| C++17 | `Application::OrderService` |
| Java 17 | `OrderApplicationService` |
| PostgreSQL | `create_order` and `confirm_order` procedures |

### Command and Query Separation

Commands modify application state.

Examples:

- `create_order`
- `confirm_order`
- `cancel_order`

Queries retrieve information without intentionally changing business state.

Examples:

- `get_order`
- `list_orders`
- `customer_order_summary`

This separation makes workflows easier to test and maintain.

It is related to Command Query Responsibility Segregation (CQRS), but the implementation does not require a fully separate read and write database architecture.

## 4. Domain Layer

The Domain Layer represents the business concepts and rules that define the application.

It should remain independent of user interfaces, databases and infrastructure-specific implementation details.

### Responsibilities

- Define business entities.
- Represent value objects.
- Enforce business invariants.
- Control valid state transitions.
- Calculate business values.
- Define domain exceptions.
- Protect aggregate consistency.

### Domain Model

The order-management example uses the following relationships:

```text
Customer
|
v
Order
|
+---- OrderItem
| |
| +---- Product
|
+---- OrderStatus
|
+---- OrderTotal
```

An order contains one or more order items. Each item represents a product, quantity and unit price.

The order calculates its total from its items rather than accepting an arbitrary total from the presentation layer.

### Entity

An entity has an identity that remains stable during its lifecycle.

The `Order` entity contains:

- Order identifier.
- Customer identifier.
- Order items.
- Creation timestamp.
- Current status.
- Aggregate version.

Two orders with identical contents are still different entities if their identifiers differ.

### Value Object

A value object represents a value defined by its attributes rather than an independent identity.

`OrderItem` demonstrates this concept.

Its attributes include:

- Product identifier.
- Product name.
- Quantity.
- Unit price.

The Python implementation uses a frozen dataclass. The Java implementation uses a record. The JavaScript implementation freezes item objects.

### Aggregate and Aggregate Root

An aggregate is a group of related domain objects that must preserve consistency.

The `Order` is the aggregate root.

External application operations interact with the aggregate through its controlled methods.

For example, an order cannot be confirmed by directly changing an arbitrary status field through the application interface.

The aggregate enforces the transition:

`PENDING → CONFIRMED`

or:

`PENDING → CANCELLED`

The following transitions are prohibited:

- `CONFIRMED → CANCELLED`
- `CANCELLED → CONFIRMED`
- `CONFIRMED → PENDING`

### Business Invariants

| Invariant | Enforcement |
|---|---|
| Customer identifier is required | Domain validation |
| An order must contain items | Aggregate constructor |
| Quantity must be positive | Order item |
| Unit price must be positive | Order item |
| Duplicate products are prohibited | Aggregate validation |
| Only pending orders can be confirmed | Domain transition |
| Only pending orders can be cancelled | Domain transition |

### Domain Exceptions

Domain exceptions identify business-rule failures.

Examples:

- `ValidationError`
- `InvalidOrderStateError`
- `OrderNotFoundError`
- `InvalidStateException`

These exceptions distinguish invalid business operations from unexpected infrastructure failures.

## 5. Infrastructure Layer

The Infrastructure Layer provides technical implementations required by the application.

It contains mechanisms for persistence, external communication, file operations, event delivery and logging.

### Responsibilities

- Implement repository interfaces.
- Persist application data.
- Manage database connections.
- Provide external service adapters.
- Record audit events.
- Implement message delivery.
- Handle infrastructure failures.
- Support concurrency and persistence consistency.

### Repository Pattern

A repository provides an abstraction for retrieving and storing domain aggregates.

The application depends on the repository contract rather than a particular database implementation.

The Python implementation defines an `OrderRepository` protocol.

The Java implementation defines an `OrderRepository` interface.

The C++ implementation uses an abstract repository class.

The JavaScript implementation uses an asynchronous repository class backed by a `Map`.

The PostgreSQL implementation uses relational tables and procedures.

### Persistence Implementations

| Language | Infrastructure implementation |
|---|---|
| Python | JSON-backed repository |
| JavaScript | Asynchronous in-memory repository and JSON Lines event journal |
| C++17 | In-memory repository and audit file |
| Java 17 | Concurrent in-memory repository and file audit adapter |
| PostgreSQL | Relational tables, constraints, indexes, triggers and procedures |

### Atomic File Persistence

The Python repository writes data to a temporary file and replaces the original file after the write completes.

This reduces the risk of exposing partially written JSON data.

The lock protects concurrent operations inside one process. It does not provide cross-process locking or a full database transaction.

### Event Journal

The JavaScript implementation uses an event journal to record order operations.

Events contain:

- Event identifier.
- Event type.
- Aggregate identifier.
- Aggregate version.
- Event timestamp.

The event bus allows independent event subscribers to react to business operations.

The file journal and event bus demonstrate event-driven communication. They do not constitute a complete distributed transaction or durable message broker.

### Database Infrastructure

The PostgreSQL implementation uses:

- Primary keys.
- Foreign keys.
- Unique constraints.
- Check constraints.
- Partial indexes.
- Reporting views.
- PL/pgSQL procedures.
- Triggers.
- JSONB event payloads.
- Transactions.

The outbox table records events in the same database transaction as the corresponding order operation.

An independent publisher would retrieve unpublished events and deliver them to an external messaging system.

## 6. Communication Between Layers

The layers communicate through defined contracts.

| From | To | Communication |
|---|---|---|
| Presentation | Application | Commands and service methods |
| Application | Domain | Domain objects and business operations |
| Application | Infrastructure | Repository and audit interfaces |
| Infrastructure | Application | Persisted results and infrastructure exceptions |
| Application | Presentation | Results and application errors |

### Dependency Direction

A traditional layered implementation often follows:

`Presentation → Application → Domain`

Infrastructure provides technical implementations to the application.

A dependency-inverted implementation defines repository interfaces at the application boundary and implements them in infrastructure.

```text
PRESENTATION
|
v
APPLICATION
|
+------+------+
| |
v v
DOMAIN INTERFACES
^
|
INFRASTRUCTURE
```

This arrangement prevents the domain model from depending directly on database drivers, file formats or web frameworks.

### Why Dependency Direction Matters

Without dependency separation, business logic can become tightly coupled to infrastructure.

For example, an order entity that directly executes SQL statements becomes difficult to test independently.

Using repository contracts allows the same application service to work with an in-memory repository, JSON persistence or a relational database adapter.

## 7. Python Implementation

**File:** `layered_architecture.py`

### Design

The Python implementation uses four explicit layers.

| Component | Responsibility |
|---|---|
| `OrderItem` | Immutable item representation |
| `Order` | Aggregate and state transitions |
| `OrderApplicationService` | Use-case orchestration |
| `JsonOrderRepository` | File-backed persistence |
| `JsonAuditRepository` | Audit event persistence |
| `OrderCLI` | User interaction |

### Important Mechanisms

**Dataclasses**

The implementation uses dataclasses to represent order items, commands and results.

**Protocols**

Repository and audit protocols define infrastructure contracts without coupling application services to concrete implementations.

**Decimal Arithmetic**

`Decimal` represents monetary values to avoid binary floating-point inaccuracies.

**Enums**

`OrderStatus` limits order states to defined values.

**Atomic Replacement**

The repository writes a temporary JSON file and replaces the existing file.

**Version Management**

Aggregate versions help identify stale writes.

### Execution

Run the application using `python layered_architecture.py`.

Run automated assertions using `python layered_architecture.py --test`.

The tests cover:

- Order creation.
- Total calculation.
- Order confirmation.
- Invalid state transitions.
- Missing order handling.
- Persistence reconstruction.

## 8. JavaScript Implementation

**File:** `layered-architecture.js`

### Design

The JavaScript implementation emphasizes asynchronous operations, event-driven communication and request-response boundaries.

| Component | Responsibility |
|---|---|
| `OrderItem` | Validated item model |
| `Order` | Aggregate and state management |
| `AsyncMutex` | In-process serialized operations |
| `InMemoryOrderRepository` | Asynchronous persistence adapter |
| `FileEventJournal` | Durable event recording |
| `OrderEventBus` | Event notification |
| `OrderApplicationService` | Application workflows |
| `OrderController` | Presentation boundary |

### Important Mechanisms

**Promises and Async/Await**

Repository and application operations return promises, allowing asynchronous infrastructure operations.

**Map**

The repository uses a `Map` for direct identifier-based lookup.

**Set**

A `Set` prevents duplicate product identifiers.

**EventEmitter**

The event bus separates event publishers from event subscribers.

**Mutex**

The asynchronous mutex serializes operations within the same process.

**Response Mapping**

The controller translates validation errors into HTTP-style status codes.

### Execution

Run the application using `node layered-architecture.js`.

Run assertions using `node layered-architecture.js --test`.

The implementation requires Node.js 18 or later.

The in-memory repository is not persistent across application restarts. The event journal is file-backed, but restoring complete application state from that journal is not implemented.

## 9. C++17 Implementation

**File:** `layered.cpp`

### Design

The C++ implementation demonstrates explicit domain modeling, repository abstraction, state management and policy evaluation.

| Component | Responsibility |
|---|---|
| `OrderItem` | Validated product line |
| `Order` | Order aggregate |
| `OrderRepository` | Abstract persistence contract |
| `InMemoryOrderRepository` | Repository adapter |
| `AuditLogger` | File-based audit |
| `OrderService` | Application orchestration |
| `MergePolicy` | Repository governance evaluation |
| `Console` | Presentation |

### Additional Governance Model

The C++ program includes a separate Pull Request eligibility model.

It evaluates:

- Pull Request state.
- Draft status.
- Source and target branches.
- Merge conflicts.
- Base synchronization.
- Reviewer eligibility.
- Stale approvals.
- Requested changes.
- Required status checks.
- Resolved review conversations.

This demonstrates how policy evaluation can be isolated from application orchestration.

The governance engine does not implement an actual Git server or perform a merge. It evaluates whether the modeled conditions permit one.

### Execution

Compile using a C++17-compatible compiler.

The implementation uses:

- `std::vector`
- `std::map`
- `std::set`
- `std::optional`
- `std::unique_ptr`-compatible interface design
- Exceptions
- STL algorithms and containers

Integer cents are used for monetary calculations to avoid floating-point rounding errors.

## 10. Java 17 Implementation

**File:** `LayeredArchitecture.java`

### Design

The Java implementation uses explicit service boundaries, immutable data transfer structures, domain entities and infrastructure interfaces.

| Component | Responsibility |
|---|---|
| `OrderItem` | Validated Java record |
| `Order` | Domain aggregate |
| `OrderSnapshot` | Immutable result |
| `OrderRepository` | Persistence interface |
| `AuditPort` | Audit interface |
| `OrderApplicationService` | Application operations |
| `InMemoryOrderRepository` | Infrastructure adapter |
| `FileAuditAdapter` | Audit persistence |
| `ConsoleController` | Presentation |

### Important Mechanisms

**Records**

Records represent immutable order items, commands and snapshots.

**Collections**

Lists and sets maintain item collections and enforce uniqueness.

**BigDecimal**

`BigDecimal` provides decimal arithmetic for monetary values.

**ConcurrentHashMap**

The repository uses concurrent storage for identifier-based access.

**Streams**

Stream operations filter order snapshots for reporting.

**Interfaces**

Repository and audit interfaces separate application logic from infrastructure.

### Execution

Compile using Java 17:

`javac --release 17 LayeredArchitecture.java`

Run:

`java LayeredArchitecture`

Run the test workflow:

`java LayeredArchitecture --test`

The example uses in-memory persistence. A production implementation would replace the adapter with a transactional database repository.

## 11. PostgreSQL Implementation

**File:** `layered_architecture.sql`

### Relational Model

The database models the order-management domain using normalized entities.

| Table | Purpose |
|---|---|
| `customers` | Customer master records |
| `products` | Product catalogue |
| `orders` | Order aggregate state |
| `order_items` | Order line items |
| `app_users` | Application roles |
| `audit_events` | Historical event records |
| `outbox_events` | Pending integration events |

### Relationships

```text
CUSTOMERS
|
+------ ORDERS
|
+------ ORDER_ITEMS
|
+------ PRODUCTS

ORDERS
|
+------ AUDIT_EVENTS
|
+------ OUTBOX_EVENTS

APP_USERS
```

### Integrity Enforcement

Primary keys identify individual records.

Foreign keys enforce valid relationships between customers, orders, products and order items.

Unique constraints prevent duplicate business identifiers and repeated products within the same order.

Check constraints enforce valid monetary amounts and quantities.

Triggers enforce selected order state transitions and record audit information.

### Stored Procedures

`create_order` performs the order creation workflow.

It validates customer availability, processes product items, inserts order lines and calculates the total.

`confirm_order` locks the selected order and validates its current state before confirmation.

The procedures execute within PostgreSQL transaction boundaries.

### Reporting Views

`order_details` provides an order-level reporting structure.

`customer_order_summary` aggregates customer order counts and confirmed revenue.

The SQL script also demonstrates:

- CTE-based revenue ranking.
- Total reconciliation.
- Business validation.
- Audit retrieval.
- Outbox processing queries.
- Partial indexes.
- Transaction handling.

### Transactional Outbox

The transactional outbox pattern prevents a common consistency problem.

A database operation may succeed while an external message publication fails.

The outbox records the integration event in the same database transaction as the business operation.

A separate publisher can deliver the event and update its publication status.

The publisher must also implement retry handling and idempotency to handle repeated delivery safely.

## 12. Architectural Distinctions

The four layers have related responsibilities but are not interchangeable.

| Concern | Primary layer |
|---|---|
| User interaction | Presentation |
| Request formatting | Presentation |
| Use-case orchestration | Application |
| Transaction coordination | Application |
| Business validation | Domain |
| State transitions | Domain |
| Business calculations | Domain |
| Database access | Infrastructure |
| File persistence | Infrastructure |
| External messaging | Infrastructure |
| Audit storage | Infrastructure |

### Presentation Versus Application

Presentation translates external requests into application operations.

Application coordinates the work required to fulfil those requests.

### Application Versus Domain

Application determines which business operations must execute and in what sequence.

Domain determines whether those operations are valid.

### Domain Versus Infrastructure

Domain defines what the business means.

Infrastructure determines how technical operations are implemented.

### Application Versus Infrastructure

Application defines the required persistence and integration contracts.

Infrastructure implements those contracts using concrete technical mechanisms.

## 13. Architectural Styles and Related Concepts

Layered Architecture is related to several other architectural approaches.

| Approach | Main concern | Relationship |
|---|---|---|
| Layered Architecture | Separation of responsibilities | Organizes the application into logical layers |
| Clean Architecture | Dependency direction | Keeps business rules independent of external details |
| Hexagonal Architecture | Ports and adapters | Isolates application logic from external systems |
| Onion Architecture | Domain-centered dependencies | Places domain logic at the architectural center |
| MVC | Presentation organization | Separates models, views and controllers |
| Microservices | Independent deployable services | Can apply layered architecture within individual services |
| Modular Monolith | Module boundaries | Can use layers inside independently organized modules |

These approaches can coexist. They address different architectural concerns rather than representing mutually exclusive designs.

## 14. Testing Strategy

Testing should cover each layer independently and verify their integration.

| Test category | Target | Example |
|---|---|---|
| Unit testing | Domain | Invalid order transition |
| Application testing | Application services | Order confirmation workflow |
| Repository testing | Infrastructure | Persistence and retrieval |
| Presentation testing | Controllers | Request validation and response mapping |
| Integration testing | Multiple layers | Order creation and database persistence |
| Failure testing | Complete workflow | Missing product or persistence failure |

### Important Test Cases

- Create an order with valid items.
- Reject an order without items.
- Reject zero or negative quantities.
- Reject invalid prices.
- Reject duplicate products.
- Confirm a pending order.
- Reject confirmation of an already confirmed order.
- Reject cancellation of a confirmed order.
- Handle missing order identifiers.
- Detect stale aggregate versions.
- Validate audit event recording.
- Reconcile order totals against item totals.

## 15. Security Considerations

Layer separation does not automatically provide application security. Security controls must be implemented at the appropriate boundaries.

### Presentation

- Validate all incoming requests.
- Apply authentication.
- Enforce authorization.
- Avoid exposing internal exception details.
- Apply request size limits.

### Application

- Verify user permissions before sensitive operations.
- Enforce workflow-level authorization.
- Prevent unauthorized state transitions.
- Apply idempotency to retryable operations.

### Domain

- Enforce business invariants.
- Prevent invalid state transitions.
- Validate monetary values and identifiers.
- Avoid trusting externally supplied calculated totals.

### Infrastructure

- Use parameterized SQL.
- Apply least-privilege database permissions.
- Protect audit information.
- Secure credentials.
- Encrypt sensitive data in transit and at rest.
- Apply database backups and recovery procedures.
- Monitor failed persistence and integration operations.

## 16. Performance and Scalability

Layered Architecture introduces boundaries that can improve maintainability, but unnecessary indirection can increase complexity.

### Performance Considerations

| Area | Consideration |
|---|---|
| Presentation | Avoid unnecessary request processing |
| Application | Reduce repeated orchestration and redundant calls |
| Domain | Keep business operations deterministic and efficient |
| Infrastructure | Optimize database queries and persistence |
| Repository | Use appropriate indexes and efficient retrieval |
| Events | Use asynchronous delivery for independent operations |
| Concurrency | Use locking or optimistic version checks where necessary |

### Repository Complexity

The Python JSON repository reads the complete file for each operation. This is appropriate for a small demonstration, not a large transactional workload.

The JavaScript `Map` repository provides average constant-time key lookup but does not provide durable aggregate persistence.

The C++ and Java in-memory repositories are similarly limited to process memory.

PostgreSQL provides transactional persistence, indexing and concurrent access controls suitable for more demanding workloads.

## 17. Limitations and Production Considerations

The implementations are deliberately small architectural demonstrations.

They do not provide a complete enterprise deployment environment.

Important production concerns include:

- Database-backed repository adapters.
- Authentication and authorization integration.
- Distributed transaction management.
- Cross-process concurrency control.
- Database migration management.
- Retry policies.
- Idempotent event publication.
- Observability and distributed tracing.
- Centralized configuration.
- Secrets management.
- Automated integration testing.
- Backup and disaster recovery.
- API versioning.
- Rate limiting.
- Operational monitoring.

The JavaScript and Python examples use simplified persistence mechanisms. The C++ and Java examples use in-memory repositories. The PostgreSQL implementation demonstrates relational persistence and transactional database operations.

The distinction between logical architecture and concrete deployment remains important: four layers do not require four separate servers, processes or deployment units.
