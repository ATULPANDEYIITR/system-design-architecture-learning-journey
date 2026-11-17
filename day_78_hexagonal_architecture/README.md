# Hexagonal Architecture: Ports and Adapters

## 1. Architectural Overview

Hexagonal Architecture is an application design approach that separates business behavior from external technologies.

It is also known as Ports and Adapters Architecture. Its central objective is to ensure that business rules do not depend directly on databases, web frameworks, message brokers, user interfaces, or external services.

The architecture treats the application as an independent component surrounded by interfaces through which external systems interact.

The application communicates through ports. Adapters translate between these ports and particular technologies or external actors.

### Architectural structure

    External Actors
         |
         v
    Primary Adapters
    (HTTP, CLI, User Interface)
         |
         v
    Primary Input Ports
         |
         v
    Application Services
         |
         v
    Domain Model
         |
         v
    Secondary Output Ports
         |
         v
    Secondary Adapters
    (Database, Payment, Inventory, Events)

The diagram represents logical dependencies rather than a mandatory physical deployment structure.

The application core contains the domain model and application services. External components implement the interfaces required by the core.

## 2. Fundamental Concepts

### Application Core

The application core contains the business rules and use-case coordination.

It should not require knowledge of:

- Database vendors.
- HTTP request formats.
- Cloud infrastructure.
- Message broker implementations.
- External payment provider SDKs.
- Specific user-interface frameworks.

For example, an order-processing application should define when an order can be confirmed without depending on whether the request originated from an HTTP endpoint or a command-line program.

### Ports

A port defines a contract between the application and another component.

It describes the capability required or exposed by the application without specifying its implementation.

There are two primary categories.

| Port category | Purpose | Example |
|---|---|---|
| Primary input port | Exposes an application use case | `PlaceOrderPort` |
| Secondary output port | Defines an external capability required by the core | `InventoryPort` |
| Secondary output port | Defines persistence requirements | `OrderRepositoryPort` |
| Secondary output port | Defines payment requirements | `PaymentPort` |
| Secondary output port | Defines event publication | `EventPublisherPort` |

A port should describe business-relevant operations rather than reproduce the entire API of an external technology.

For example, an inventory port can expose `reserve` and `release` operations instead of exposing the methods of a particular warehouse SDK.

### Adapters

An adapter implements or invokes a port and translates between the application's contract and an external interface.

Two directions are important.

**Primary adapters**

Primary adapters initiate application operations.

Examples:

- REST controllers.
- Command-line interfaces.
- Graphical interfaces.
- Message consumers.
- Scheduled jobs.

**Secondary adapters**

Secondary adapters provide external capabilities to the application.

Examples:

- PostgreSQL repositories.
- Inventory service clients.
- Payment gateway integrations.
- Event publishers.
- File-system storage.

A REST controller is not the application service. It is an adapter that translates an HTTP request into an application command.

Likewise, a PostgreSQL repository is not the domain model. It implements a persistence contract.

## 3. Dependency Inversion

Dependency Inversion is the central dependency-management principle used in this architecture.

High-level business logic should not depend directly on low-level infrastructure implementations.

Instead, both interact through abstractions.

A conventional dependency arrangement might look like:

    OrderService
        |
        v
    PostgreSQLRepository
        |
        v
    PostgreSQL Database

This arrangement directly couples the business service to a persistence implementation.

A hexagonal arrangement looks like:

    OrderService
        |
        v
    OrderRepositoryPort
        ^
        |
    PostgreSQLRepositoryAdapter

The application defines the required persistence contract. The infrastructure adapter implements it.

This changes the direction of source-code dependencies without requiring the runtime request to flow in the same direction.

The distinction is important:

- Runtime control flow describes which component calls another.
- Source-code dependency describes which component knows about another component's types and interfaces.

A secondary adapter can be called by the application while its implementation depends on an interface owned by the application.

## 4. Domain Modeling

The five implementations use an order-processing domain.

The main entities and values are:

| Domain element | Responsibility |
|---|---|
| Order | Represents a customer order |
| OrderItem | Represents a product and requested quantity |
| Money | Represents a monetary value |
| OrderStatus | Defines permitted order states |
| OrderCreatedEvent | Represents an integration event |
| OrderPolicy | Defines application-level order limits |

### Order state

An order supports three states:

| State | Meaning |
|---|---|
| PENDING | Order has been created but not confirmed |
| CONFIRMED | Required processing operations succeeded |
| CANCELLED | Pending order was cancelled |

The permitted state transitions are:

    PENDING
       |
       +------> CONFIRMED
       |
       +------> CANCELLED

Confirmed and cancelled orders cannot return to pending through the implemented domain operations.

The domain model enforces these rules independently of the delivery mechanism.

### Money and quantity validation

The implementations validate monetary values and quantities before processing.

The Java implementation uses `BigDecimal` to represent decimal currency values.

The JavaScript, C++, and PostgreSQL implementations use integer minor currency units or fixed-precision database values where appropriate.

These approaches avoid relying on binary floating-point arithmetic for financial calculations.

Currency consistency is also enforced. An order containing different currencies must not be calculated by directly adding their amounts.

## 5. Application Services and Use Cases

An application service coordinates a business operation.

It defines the sequence of operations required to complete a use case while delegating infrastructure operations to secondary ports.

The `PlaceOrderService` and `PlaceOrderUseCase` implementations coordinate the following workflow:

    Customer Request
          |
          v
    Validate Command
          |
          v
    Create Order
          |
          v
    Reserve Inventory
          |
          v
    Charge Payment
          |
          v
    Confirm Order
          |
          v
    Persist Order
          |
          v
    Publish Integration Event

The application service does not need to know how inventory is stored, how payments are transmitted, or how events are delivered.

It only needs the contracts defined by the secondary ports.

### Application-level validation

The Java implementation includes an `OrderPolicy` object.

It checks:

- Maximum number of order lines.
- Maximum quantity per line.
- Maximum permitted order value.

These are application policies rather than external adapter responsibilities.

The distinction is useful because domain invariants, application policies, and infrastructure constraints have different scopes.

| Validation category | Example |
|---|---|
| Domain invariant | Quantity must be positive |
| Application policy | Maximum order value |
| Infrastructure validation | Payment gateway authentication |
| Database constraint | Foreign key must reference an existing customer |

## 6. Primary Adapters

Primary adapters translate external requests into application commands.

The implementations contain console adapters and, in JavaScript, an HTTP-style adapter.

### Console adapter

The console adapter constructs an order command and invokes the primary input port.

It does not calculate inventory availability or implement payment rules.

### HTTP adapter

The JavaScript HTTP adapter receives a request-like object and translates it into the command expected by the application service.

It maps application failures into response status codes.

In a production HTTP implementation, the adapter would also need:

- Authentication.
- Authorization.
- Request-size restrictions.
- Input schema validation.
- Safe error responses.
- Request correlation identifiers.
- Rate limiting.

These concerns belong at the appropriate application boundary rather than being embedded in the domain entity.

### Multiple adapters for one port

The same application input port can be invoked through different delivery mechanisms.

For example:

    HTTP Adapter --------+
                         |
    CLI Adapter ---------+----> PlaceOrderPort
                         |
    Message Adapter ----+

All three adapters can invoke the same use case.

This makes the application independent of its delivery mechanism.

## 7. Secondary Adapters

Secondary adapters implement the capabilities required by the application.

### Repository adapter

The repository adapter persists and retrieves orders.

The implementations provide in-memory repositories using dictionaries, maps, hash maps, or concurrent maps.

The repository interface isolates the application from the storage implementation.

A production PostgreSQL adapter would translate between domain objects and relational records.

### Inventory adapter

The inventory adapter provides reservation and release operations.

The reservation operation checks availability before reducing stock.

A reservation must not reduce available inventory below zero.

The implementations demonstrate validation and state consistency.

Concurrent production systems require atomic database updates, locking, or an equivalent concurrency-control mechanism.

### Payment adapter

The payment adapter exposes charging and refund operations.

The implementations also demonstrate idempotency.

An idempotency key identifies a logical payment operation. Retrying the same operation should not create another charge.

An in-memory implementation demonstrates the concept but does not provide durable idempotency across process restarts.

### Event publisher adapter

The event publisher communicates completed business events to external consumers.

The order-processing workflow publishes an `OrderConfirmed` event.

Events allow other applications to respond without requiring the order-processing service to know their internal implementations.

A production implementation should use durable event delivery, retry handling, duplicate detection, and appropriate event versioning.

## 8. Dependency Injection and the Composition Root

Dependency injection supplies concrete adapter implementations to the application service.

The composition root is the location where these dependencies are assembled.

The five implementations demonstrate this mechanism through their main functions or application factory.

The structure is:

    Create Repository Adapter
              |
    Create Inventory Adapter
              |
    Create Payment Adapter
              |
    Create Event Adapter
              |
              v
    Inject Dependencies
              |
              v
    Application Service
              |
              v
    Primary Adapter

The application service receives interfaces rather than constructing concrete infrastructure objects internally.

This provides several benefits:

- Different implementations can satisfy the same port.
- Tests can use controlled adapters.
- Infrastructure can change independently of business rules.
- Configuration is concentrated at the application boundary.
- External services can be replaced without rewriting the domain model.

Dependency injection does not require a dependency injection framework. Constructor injection and explicit object composition are sufficient.

## 9. Transaction Management and Compensation

Hexagonal Architecture does not automatically provide distributed transaction management.

The example order workflow interacts with multiple systems:

- Inventory.
- Payment.
- Order persistence.
- Event publication.

A database transaction cannot normally make an external payment gateway operation atomic with a PostgreSQL transaction.

The implementations therefore demonstrate compensation.

If payment succeeds but a later operation fails, the application attempts to refund the payment and release previously reserved inventory.

The compensation sequence is:

    Inventory Reserved
          |
          v
    Payment Charged
          |
          v
    Persistence Failure
          |
          v
    Refund Payment
          |
          v
    Release Inventory

Compensation is not equivalent to rolling back a database transaction.

A refund can fail. An inventory service can become unavailable. A network timeout can leave the payment result uncertain.

A production implementation should use:

- Durable operation records.
- Idempotent commands.
- Retry policies.
- Compensation state tracking.
- Reconciliation jobs.
- Transactional outbox processing.
- Monitoring of incomplete workflows.

The saga pattern is an appropriate approach when a business operation spans multiple independently managed services.

## 10. Python Implementation

The Python implementation provides a complete object-oriented simulation of the architecture.

### Main components

| Component | Implementation |
|---|---|
| Domain | `Order`, `OrderItem`, `OrderStatus` |
| Input port | `PlaceOrderPort` |
| Persistence port | `OrderRepositoryPort` |
| Inventory port | `InventoryPort` |
| Payment port | `PaymentPort` |
| Event port | `EventPublisherPort` |
| Application service | `PlaceOrderService` |
| Repository adapter | `InMemoryOrderRepository` |
| Inventory adapter | `InMemoryInventoryAdapter` |
| Payment adapter | `InMemoryPaymentAdapter` |
| Event adapter | `InMemoryEventPublisher` |
| Primary adapter | `ConsoleOrderAdapter` |

### Technical mechanisms

Python abstract base classes define the port contracts.

Dataclasses represent order items and domain structures.

Enums provide explicit order states.

`Decimal` supports monetary calculations.

Dictionaries store adapter state.

`RLock` protects in-memory repository and inventory operations against concurrent access.

Exceptions distinguish domain failures from application failures.

The `build_application()` function acts as the composition root.

The test routine verifies:

- Successful order processing.
- Correct order totals.
- Inventory reduction.
- Repository persistence.
- Event publication.
- Insufficient inventory handling.
- Invalid quantity rejection.
- Invalid state transitions.

### Design limitation

The repository and payment adapters are in-memory implementations.

They are intended to demonstrate dependency boundaries and application behavior rather than durable transaction processing.

The compensation mechanism is best-effort and requires durable recovery operations in a production environment.

## 11. JavaScript Implementation

The JavaScript implementation provides an asynchronous, event-driven perspective.

### Main components

| Component | Implementation |
|---|---|
| Domain values | `Money`, `OrderLine`, `Order` |
| Input port | `PlaceOrderUseCase` |
| Repository port | Structural method contract |
| Inventory port | Structural method contract |
| Payment port | Structural method contract |
| Event port | Structural method contract |
| Repository adapter | `MemoryOrderRepository` |
| Inventory adapter | `MemoryInventoryAdapter` |
| Payment adapter | `MemoryPaymentAdapter` |
| Event adapter | `MemoryEventAdapter` |
| Primary adapters | `ConsoleAdapter`, `HttpOrderAdapter` |

### Technical mechanisms

JavaScript does not require interface declarations to implement the ports.

The implementation uses structural validation through `requireMethods()`.

Classes encapsulate state.

`Map` maintains repository and payment data.

`EventEmitter` demonstrates event-driven integration.

Promises and `async` functions allow adapters to represent asynchronous infrastructure operations.

Private class fields restrict direct access to internal state.

`Object.freeze()` provides shallow immutability for selected values and records.

The `Money` class uses integer minor units to avoid floating-point currency calculations.

The inventory adapter serializes operations through a promise-based exclusive execution mechanism.

### HTTP boundary

The HTTP adapter translates incoming request data into application commands and maps application errors to response objects.

It does not perform persistence or payment operations directly.

### Design limitation

The promise-based locking mechanism is appropriate for the demonstration but is not a distributed lock.

In-memory maps do not provide durability, and event emission is not equivalent to reliable message delivery.

## 12. C++17 Implementation

The C++ implementation emphasizes explicit interfaces, ownership boundaries, domain types, and controlled state changes.

### Main components

| Component | Implementation |
|---|---|
| Domain | `Order`, `OrderItem`, `Money` |
| Input port | `PlaceOrderPort` |
| Repository port | `OrderRepositoryPort` |
| Inventory port | `InventoryPort` |
| Payment port | `PaymentPort` |
| Event port | `EventPublisherPort` |
| Application service | `PlaceOrderService` |
| Repository adapter | `MemoryOrderRepository` |
| Inventory adapter | `MemoryInventoryAdapter` |
| Payment adapter | `MemoryPaymentAdapter` |
| Event adapter | `MemoryEventAdapter` |
| Primary adapter | `ConsoleAdapter` |

### Technical mechanisms

Abstract classes provide polymorphic port contracts.

Virtual destructors support safe destruction through base-class pointers.

Structs represent individual order items.

STL containers provide storage and collection management.

`std::optional` represents a potentially absent repository record.

References inject adapter dependencies into the application service without transferring ownership.

Exceptions communicate domain and application failures.

The implementation checks integer overflow during monetary calculations and inventory updates.

The composition root constructs adapters and injects them into the service.

### Complexity considerations

| Operation | Expected complexity |
|---|---|
| Inventory lookup | Average O(1) |
| Inventory reservation | Average O(1) |
| Repository lookup | Average O(1) |
| Repository insertion | Average O(1) |
| Order total | O(n), where n is the number of lines |
| Compensation | O(n) for reserved lines |

The in-memory hash-based implementation is efficient for small simulations.

A production implementation must consider synchronization, persistent storage, transaction isolation, and external service availability.

## 13. Java 17 Implementation

The Java implementation models an enterprise application with explicit domain types, application policies, and service boundaries.

### Main components

| Component | Implementation |
|---|---|
| Domain values | `Money`, `OrderLine`, `Order` |
| Input port | `PlaceOrderPort` |
| Generic persistence port | `RepositoryPort<T, ID>` |
| Inventory port | `InventoryPort` |
| Payment port | `PaymentPort` |
| Event port | `EventPublisherPort` |
| Application service | `PlaceOrderService` |
| Policy | `OrderPolicy` |
| Repository adapter | `MemoryOrderRepository` |
| Inventory adapter | `MemoryInventoryAdapter` |
| Payment adapter | `MemoryPaymentAdapter` |
| Event adapter | `MemoryEventAdapter` |
| Primary adapter | `ConsoleOrderAdapter` |

### Technical mechanisms

Java records represent immutable value objects and command structures.

Interfaces define the contracts implemented by infrastructure adapters.

Generic repository interfaces provide reusable persistence abstractions.

Enums define explicit order states.

Streams calculate order totals and validate collection contents.

`BigDecimal` provides decimal monetary calculations.

`ConcurrentHashMap` supports concurrent in-memory access.

`compute()` and `merge()` provide atomic map operations for individual keys.

`OrderPolicy` separates application-specific constraints from domain invariants.

The service uses dependency injection through its constructor.

### Enterprise considerations

The Java implementation demonstrates a separation between:

- Domain invariants.
- Application-level policies.
- Infrastructure responsibilities.
- External integration behavior.

Its custom exceptions distinguish business failures from application and infrastructure failures.

The policy object makes business restrictions explicit and testable.

The implementation remains independent of any specific persistence framework.

## 14. PostgreSQL Implementation

The PostgreSQL script models the relational infrastructure surrounding a hexagonal order application.

It includes the application contracts, adapter registrations, use cases, and operational data.

### Relational model

| Table | Purpose |
|---|---|
| `customers` | Customer records |
| `products` | Product catalog |
| `orders` | Order aggregates |
| `order_items` | Order line items |
| `architecture_ports` | Registered port contracts |
| `adapters` | Adapter implementations |
| `adapter_port_bindings` | Port-to-adapter relationships |
| `use_cases` | Application operations |
| `use_case_port_dependencies` | Required port dependencies |
| `use_case_executions` | Execution records |
| `inventory` | Inventory quantities |
| `inventory_reservations` | Reservation history |
| `payments` | Payment operation records |
| `integration_outbox` | Durable integration events |
| `domain_audit_log` | Order change history |

### Port and adapter registry

The `architecture_ports` table records the logical contracts exposed by the application.

The `adapters` table records concrete implementations.

The `adapter_port_bindings` table connects implementations to their contracts.

This relational representation illustrates the relationship between ports and adapters.

A port may have multiple adapters.

For example, the same primary input port can be invoked through a REST adapter and a command-line adapter.

The registry is an architectural inventory, not a runtime dependency injection container.

### Database integrity

Primary keys uniquely identify records.

Foreign keys enforce relationships between customers, orders, products, ports, adapters, and use cases.

Check constraints validate quantities, amounts, currencies, and execution timestamps.

Unique constraints prevent duplicate business identifiers and duplicate order-product combinations.

Partial indexes support queries against active bindings and unpublished events.

### Stored functions and procedures

`calculate_order_total()` calculates an order's total.

`validate_order_currency()` ensures order and product currencies match.

`enforce_order_state_transition()` restricts invalid order transitions.

`reserve_inventory()` performs transactional stock reservation.

`release_inventory()` restores stock for active reservations.

`order_is_mergeable()` evaluates whether an order satisfies the implemented workflow conditions.

These database routines demonstrate persistence-level enforcement. They do not replace the application's complete business orchestration.

### Triggers

The order-state trigger validates permitted transitions and increments the order version.

The audit trigger records order changes.

The outbox trigger inserts an `OrderConfirmed` event when an order is confirmed.

The outbox trigger ensures that the event record participates in the same database transaction as the order update.

### Transactional outbox

The transactional outbox addresses the dual-write problem.

Without an outbox, an application could update an order successfully and fail while publishing its event.

The database transaction can instead persist both the order update and its corresponding event record.

A separate publisher reads unpublished records and sends them to external consumers.

    Application Service
           |
           v
    Database Transaction
           |
           +------> Order Update
           |
           +------> Outbox Event
                         |
                         v
                  Event Publisher
                         |
                         v
                  External Consumer

The publisher must handle retries and duplicate delivery.

Consumers should use event identifiers to make processing idempotent.

### Reporting and validation

The SQL script includes:

- Order summary reporting.
- Adapter and port mapping.
- Port binding validation.
- Required dependency validation.
- Execution success and failure aggregation.
- Workflow eligibility checks.
- Common table expression reporting.
- Unpublished outbox retrieval.
- Query-plan inspection.

The database uses `FOR UPDATE SKIP LOCKED` to support concurrent outbox workers without repeatedly selecting rows already locked by another transaction.

## 15. Relationship Between the Five Implementations

All implementations follow the same architectural principle while using language-specific mechanisms.

| Concern | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Domain modeling | Dataclasses | Classes | Structs and classes | Records and classes | Relational tables |
| Port contracts | ABC | Structural contracts | Abstract classes | Interfaces | Port registry |
| Application service | Service class | Async use case | Service class | Service class | Execution records and procedures |
| Dependency injection | Constructor injection | Object composition | References | Constructor injection | Adapter bindings |
| Repository | Dictionary | Map | Unordered map | Concurrent map | Relational tables |
| Inventory | In-memory adapter | Async adapter | STL adapter | Concurrent adapter | Transactional procedures |
| Payment | Payment port | Payment port | Payment port | Payment port | Payment records |
| Events | Publisher port | EventEmitter | Publisher interface | Publisher interface | Transactional outbox |
| Validation | Exceptions | Custom errors | Exceptions | Custom exceptions | Constraints and triggers |

The implementations are independent examples rather than one distributed application sharing a common runtime.

Their common structure is the separation of application behavior from infrastructure details.

## 16. Testing Strategy

Testing hexagonal architecture focuses on contracts and behavior at different boundaries.

### Domain tests

Domain tests validate business invariants without requiring infrastructure.

Examples:

- A quantity cannot be zero.
- An order must contain at least one line.
- Monetary amounts must be positive.
- An invalid order transition must fail.
- Different currencies cannot be combined directly.

### Application service tests

Application service tests use controlled port implementations.

Examples:

- A valid order reserves inventory and charges payment.
- Insufficient inventory prevents order confirmation.
- A payment failure triggers inventory compensation.
- A persistence failure triggers compensation.
- A successful operation produces an integration event.

### Adapter tests

Adapter tests verify translation and integration behavior.

Examples:

- Repository records can be retrieved.
- Inventory updates preserve nonnegative quantities.
- Payment retries use the same idempotency key.
- HTTP requests are translated into valid application commands.
- Database triggers enforce permitted state transitions.

### Contract tests

Contract tests verify that each adapter correctly implements the operations and behavior expected by its port.

This is especially important when replacing one infrastructure implementation with another.

For example, an in-memory repository and a PostgreSQL repository should satisfy the same repository contract.

## 17. Security and Production Considerations

Hexagonal Architecture provides separation of responsibilities. It does not automatically guarantee application security.

Production systems require explicit security controls.

### Authentication and authorization

Primary adapters should authenticate external callers and authorize requested operations.

The application should enforce business permissions where necessary.

### Input validation

Adapters should validate external input before constructing domain commands.

The domain model must still enforce its own invariants because application services may also be called from non-HTTP adapters.

### Database security

Database adapters should use:

- Restricted database roles.
- Parameterized SQL.
- Least-privilege permissions.
- Protected credentials.
- Appropriate transaction isolation.
- Auditable database operations.

### External service security

Payment and inventory adapters should use secure transport, protected credentials, timeouts, retry limits, and appropriate error classification.

Sensitive payment credentials should not be stored in application logs.

### Failure isolation

An adapter failure should not expose internal implementation details to external callers.

Application errors should be translated into appropriate external responses.

### Observability

Useful operational information includes:

- Request identifiers.
- Use-case execution identifiers.
- Adapter response times.
- Failure classifications.
- Retry counts.
- Compensation failures.
- Event publication status.

Logging should avoid sensitive personal and financial data.

## 18. Architectural Limitations and Trade-offs

Hexagonal Architecture introduces additional abstractions.

For a very small application, separate ports and adapters can create more code than a direct implementation.

The architecture is most useful when business behavior must remain independent of infrastructure, when multiple delivery mechanisms exist, or when external systems are likely to change.

Important trade-offs include:

| Design decision | Benefit | Cost |
|---|---|---|
| Explicit ports | Clear dependency boundaries | Additional interfaces |
| Adapter isolation | Replaceable infrastructure | Translation code |
| Dependency injection | Testability | Composition complexity |
| Separate application services | Explicit use cases | More classes |
| Domain modeling | Centralized business invariants | Modeling effort |
| Transactional outbox | Reliable event recording | Additional operational processing |
| Compensation | Recovery across services | More workflow states |

The architecture should be applied according to actual application complexity rather than by introducing an interface for every class.

A useful port represents a meaningful boundary or capability.

A port that simply duplicates a concrete implementation without providing architectural value can create unnecessary abstraction.

## 19. Important Terminology

| Term | Definition |
|---|---|
| Hexagonal Architecture | Architecture separating application behavior from external systems |
| Port | Contract defining an application capability or required dependency |
| Adapter | Component translating between a port and an external interface |
| Primary Adapter | Component initiating an application use case |
| Secondary Adapter | Component providing an external capability to the application |
| Input Port | Contract through which an application operation is invoked |
| Output Port | Contract through which the application accesses an external capability |
| Domain Model | Representation of business concepts and invariants |
| Application Service | Coordinates an application use case |
| Dependency Inversion | Principle that high-level policy should not depend directly on low-level implementation |
| Dependency Injection | Supplying required dependencies from outside a component |
| Composition Root | Location where application components and adapters are assembled |
| Repository | Abstraction for retrieving and persisting domain data |
| Idempotency | Property that repeated execution of the same logical operation does not create unintended duplicate effects |
| Compensation | A corrective operation used when a distributed workflow cannot complete |
| Transactional Outbox | Database-backed mechanism for reliably recording events with business updates |
| Contract Test | Test verifying that an adapter satisfies its port's expected behavior |

## 20. Execution Requirements

| Deliverable | Runtime | Execution |
|---|---|---|
| Python | Python 3.10+ | `python hexagonal_architecture.py` |
| JavaScript | Node.js 18+ | `node hexagonal_architecture.js` |
| C++17 | C++17 compiler | Compile and execute `hexagonal_architecture.cpp` |
| Java | Java 17 | Compile `HexagonalArchitecture.java` and execute `HexagonalArchitecture` |
| PostgreSQL | PostgreSQL 15+ | Execute the SQL script using a database client |

The Python, JavaScript, C++17, and Java implementations use standard language facilities without third-party dependencies.

The PostgreSQL script uses native database functionality and the `pgcrypto` extension functionality supplied by PostgreSQL's `gen_random_uuid()`.

The implementations demonstrate the same application boundary principles through different programming-language and persistence mechanisms.
