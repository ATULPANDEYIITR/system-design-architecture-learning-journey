# Domain-Driven Design: Bounded Contexts, Aggregates and Entities

## 1. Introduction

Domain-Driven Design (DDD) is an approach to software development that places business concepts, business rules and domain behaviour at the centre of system design.

Instead of organizing an application entirely around technical components such as controllers, database tables and services, DDD organizes its structure around the business domain.

A domain represents the business area that an application addresses. For an enterprise procurement platform, the domain might include product management, inventory management, customer management, order processing and billing.

DDD provides a way to divide this complexity into smaller, understandable models.

Three important building blocks are:

- Bounded contexts define where a particular domain model applies.
- Aggregates protect business rules and consistency within a defined boundary.
- Entities represent objects that have identity and continue to exist as their attributes change.

These concepts solve different problems and should not be treated as interchangeable.

## 2. The Domain-Driven Design Structure

The implementations use an enterprise purchasing system as their business scenario.

The application supports product registration, stock management, order creation, order submission, invoice generation and payment.

The business domain is separated into independent bounded contexts.

| Bounded context | Responsibility | Main domain objects |
|---|---|---|
| Catalog | Product information and pricing | Product |
| Customer | Customer information | Customer |
| Inventory | Available and reserved stock | InventoryItem |
| Order Management | Purchasing and order lifecycle | Order, OrderLine |
| Billing | Invoice creation and payment | Invoice |

The logical relationship is:

    Enterprise Procurement Domain
                |
        Bounded Contexts
                |
       +--------+---------+
       |        |         |
     Catalog Inventory  Customer
       |        |         |
       +--------+---------+
                |
          Order Management
                |
             Billing
                |
         Domain Integration

Each context owns its own business language, rules and responsibilities.

For example, Catalog manages product pricing, while Inventory manages stock quantities. Order Management uses information from both contexts without taking ownership of their internal models.

## 3. Bounded Contexts

### 3.1 Meaning

A bounded context is an explicit boundary within which a particular domain model, terminology and set of business rules remain consistent.

The same business term can have different meanings in different contexts.

Consider the term Product.

In Catalog, a product represents an item available for purchase. It contains:

- Product identifier
- SKU
- Product name
- Description
- Selling price
- Currency
- Active status

In Inventory, the same product is represented through a stock-management perspective:

- Product identifier
- Available quantity
- Reserved quantity
- Stock version

In Order Management, a product is represented through a purchase snapshot:

- Product identifier
- Product name at purchase time
- Unit price at purchase time
- Ordered quantity

These representations serve different business purposes.

They should not be combined into one universal Product object.

### 3.2 Why bounded contexts matter

Without boundaries, different departments may develop conflicting rules for the same business object.

For example:

- Catalog changes a product price.
- Inventory records stock availability.
- Order Management calculates historical purchase values.
- Billing generates an invoice using the submitted order value.

If all four responsibilities depend on one shared mutable Product object, changing the price could unintentionally change an existing order.

Separate bounded contexts prevent this kind of model coupling.

### 3.3 Context ownership

A bounded context should control its own data and business decisions.

| Context | Owns | Does not own |
|---|---|---|
| Catalog | Product identity and current price | Order totals |
| Inventory | Stock quantities and reservations | Product descriptions |
| Order | Purchase decisions and order lines | Current catalog price |
| Billing | Invoices and payment status | Inventory availability |

The same identifier can be used to refer to an object across contexts.

For example, Inventory stores the Catalog product identifier but does not need to duplicate the complete Catalog model.

An identifier establishes a relationship without making two contexts share ownership.

### 3.4 Communication between contexts

The implementations demonstrate two forms of communication.

**Direct application coordination**

An application service obtains a product snapshot, coordinates inventory reservations and submits an order.

**Domain events**

An Order aggregate publishes events such as:

- `OrderCreated`
- `OrderSubmitted`
- `OrderConfirmed`
- `OrderCancelled`

Other contexts can react to these events without accessing the internal state of the originating aggregate.

In a distributed enterprise system, events should be published through a reliable messaging mechanism.

An in-memory event dispatcher is useful for demonstrating the concept but does not provide durable delivery.

## 4. Entities

### 4.1 Meaning

An entity is a domain object that has a distinct identity throughout its lifecycle.

Its identity remains stable even when its attributes change.

Consider a product with the identifier `PROD-001`.

Initially, its price is INR 45,000. Later, the price changes to INR 47,000.

The product remains the same entity because its identity has not changed.

    Product
      |
      +-- ID: PROD-001
      +-- Name: Security Appliance
      +-- Price: INR 45,000
               |
          Price Update
               |
      +-- ID: PROD-001
      +-- Name: Security Appliance
      +-- Price: INR 47,000

The identifier distinguishes the entity from another product with identical attributes.

### 4.2 Entity identity versus attribute equality

Two products may have identical names and prices but different identifiers.

They are still different entities.

| Product | Identifier | Name | Price |
|---|---|---|---:|
| A | PROD-001 | Security Appliance | 45,000 |
| B | PROD-002 | Security Appliance | 45,000 |

These products are equal in their displayed attributes but not in their identity.

This distinction is important when implementing:

- Database relationships
- Entity updates
- Object persistence
- Event tracking
- Audit records
- Domain operations

### 4.3 Entities in the implementations

| Entity | Bounded context | Identity |
|---|---|---|
| Catalog Product | Catalog | Product ID |
| Customer | Customer | Customer ID |
| Inventory Item | Inventory | Product ID |
| Order | Order Management | Order ID |
| Order Line | Order Management | Order ID and line number |
| Invoice | Billing | Invoice ID |

An entity can exist independently of an aggregate root, but an entity contained within an aggregate is controlled through that aggregate's rules.

### 4.4 Entity versus value object

An entity is identified by identity.

A value object is identified by its attributes and represents a descriptive value.

For example, Money represents an amount and currency.

Two Money objects with the same amount and currency represent the same value.

The implementations use immutable Money objects to prevent accidental modification of financial calculations.

| Characteristic | Entity | Value object |
|---|---|---|
| Identity | Has a unique identity | No independent identity |
| Equality | Based on identity | Based on attributes |
| Mutability | Can change | Preferably immutable |
| Lifecycle | Has a lifecycle | Usually replaced as a whole |
| Example | Product | Money |

A Product can change its price without becoming a different entity. A Money value is replaced when a different monetary amount is required.

## 5. Aggregates

### 5.1 Meaning

An aggregate is a group of related domain objects treated as one consistency boundary.

It contains an aggregate root and potentially several child entities and value objects.

The aggregate root is the main object through which external operations access and modify the aggregate.

The Order aggregate is the central example.

    Order Aggregate
          |
          v
       Order Root
          |
          +-- Order ID
          +-- Customer ID
          +-- Order Status
          +-- Order Version
          |
          +-- Order Line 1
          |       |
          |       +-- Product Snapshot
          |       +-- Quantity
          |       +-- Subtotal
          |
          +-- Order Line 2
                  |
                  +-- Product Snapshot
                  +-- Quantity
                  +-- Subtotal

The Order controls its Order Lines.

External application components should not directly modify an order line in a way that bypasses the aggregate's business rules.

### 5.2 Aggregate root

The aggregate root provides controlled access to the objects inside the aggregate.

In the implementations, the Order class acts as the aggregate root.

It controls:

- Product addition
- Quantity validation
- Currency consistency
- Order total calculation
- Order submission
- Order confirmation
- Order cancellation

The aggregate prevents invalid changes.

For example, an order cannot receive new lines after submission.

This rule is enforced by the Order aggregate rather than being left entirely to the user interface or application service.

### 5.3 Aggregate invariants

An invariant is a business rule that must remain true whenever an aggregate operation completes successfully.

The Order aggregate enforces several invariants.

| Invariant | Enforcement |
|---|---|
| An order must have an identifier | Constructor |
| An empty order cannot be submitted | Submission method |
| Quantity must be positive | OrderLine and aggregate |
| An order cannot mix currencies | Product addition |
| Only draft orders can be modified | Order state validation |
| Submitted orders cannot return to draft | State transition validation |
| Historical product prices remain stable | Product snapshots |

The aggregate is responsible for protecting these rules regardless of which application component calls it.

### 5.4 Aggregate boundaries

A common design mistake is creating excessively large aggregates.

For example, a procurement aggregate could contain:

- Customer
- Product catalog
- Inventory
- Order
- Invoice
- Payment
- Shipping information

This would create unnecessary coupling.

The implementations use smaller aggregates and independent bounded contexts.

Order Management owns the Order aggregate. Inventory owns stock management. Billing owns invoices.

The application service coordinates their operations.

### 5.5 Aggregate consistency

An aggregate should maintain its internal invariants consistently.

A change to an Order and its Order Lines belongs to the Order consistency boundary.

A stock reservation belongs to Inventory.

An invoice creation belongs to Billing.

When a business operation crosses several aggregate boundaries, the application may need a transaction, compensation, retry mechanism or event-driven workflow.

It should not assume that every business operation can be handled by one aggregate transaction.

## 6. Aggregate Design Rules

The implementations follow several important design rules.

### 6.1 Access through the aggregate root

External application components should request changes through the aggregate root.

For example:

- Call `order.addProduct()`.
- Call `order.submit()`.
- Call `order.confirm()`.

Avoid allowing external components to directly manipulate internal order-line collections.

This preserves the aggregate's control over its invariants.

### 6.2 Keep aggregates reasonably small

Only objects that require the same consistency boundary should normally be included in one aggregate.

An Order and its Order Lines are a suitable example.

The complete product catalog does not need to be part of the Order aggregate.

### 6.3 Use identifiers for external aggregate references

An Order can store a Customer ID instead of embedding the entire Customer aggregate.

This keeps aggregate boundaries explicit.

It also prevents one aggregate from becoming dependent on another aggregate's internal implementation.

### 6.4 Use snapshots for historical information

The Order aggregate stores a Product Snapshot.

A snapshot contains:

- Product ID
- Product name
- Purchase-time price

This protects historical purchase information from changes in the Catalog context.

The current Catalog price and the historical Order price serve different purposes.

## 7. Value Objects and Immutability

Value objects represent descriptive information rather than independently identifiable business objects.

The implementations use Money as a value object.

Money contains:

- Amount
- Currency

Its rules include:

- Negative amounts are rejected.
- Invalid currency codes are rejected.
- Addition requires matching currencies.
- Multiplication requires a positive integer quantity.
- Monetary calculations avoid floating-point arithmetic.

Python uses `Decimal`.

JavaScript uses integer minor currency units and safe-integer validation.

C++17 uses integer paise and overflow checks.

Java uses `BigDecimal`.

PostgreSQL uses `NUMERIC`.

These choices avoid common financial calculation errors associated with binary floating-point values.

Immutability makes value objects easier to validate, share and reason about.

## 8. Domain Events

### 8.1 Meaning

A domain event represents something meaningful that has already happened within the business domain.

Examples include:

- An order was created.
- An order was submitted.
- An order was confirmed.
- An invoice was paid.

A domain event is different from a command.

A command requests an operation. An event records a completed business occurrence.

| Command | Domain event |
|---|---|
| Submit Order | Order Submitted |
| Confirm Order | Order Confirmed |
| Cancel Order | Order Cancelled |
| Pay Invoice | Invoice Paid |

### 8.2 Event contents

A domain event normally contains:

- Event identifier
- Aggregate identifier
- Event type
- Occurrence timestamp
- Relevant business information

The Python, JavaScript and Java implementations model events directly.

The C++ implementation uses a lightweight event structure.

The PostgreSQL implementation includes a `domain_events` table.

### 8.3 Event-driven integration

The order-processing workflow can publish `OrderSubmitted`.

Billing can react by creating an invoice.

Other systems can react by initiating notifications, analytics or downstream processing.

The originating Order aggregate does not need to know how all subscribers implement their responsibilities.

### 8.4 Transactional outbox

The PostgreSQL implementation demonstrates a domain-event outbox.

An event is stored in the same database transaction as the business operation.

A separate publisher can retrieve pending events and deliver them to other systems.

The outbox helps prevent a situation where an order commits successfully but its integration event is lost because the application fails before publishing it.

The example includes event states:

- Pending
- Processed
- Failed

A production publisher should also implement retry limits, delivery monitoring, idempotent consumers and appropriate event retention.

## 9. Repository Pattern

A repository provides an abstraction for retrieving and storing domain aggregates.

The implementations use an Order Repository.

Its responsibilities include:

- Saving an Order aggregate
- Retrieving an Order by identifier
- Maintaining aggregate versions
- Detecting conflicting updates

The repository should return domain objects rather than expose database-specific implementation details throughout the domain model.

The PostgreSQL implementation uses relational tables and constraints to persist the model.

### Optimistic concurrency

Optimistic concurrency detects situations where multiple operations attempt to update the same aggregate using outdated information.

For example:

1. Transaction A reads Order version 5.
2. Transaction B reads Order version 5.
3. Transaction A saves a change and creates version 6.
4. Transaction B attempts to save using version 5.
5. The repository rejects the stale update.

The Python, JavaScript and Java examples demonstrate version checking.

The PostgreSQL model maintains version columns that can be used with conditional updates.

Production implementations should perform version checks atomically inside database transactions.

## 10. Application Services

An application service coordinates a business use case.

It does not replace the domain model or become the owner of all business rules.

The Order Application Service coordinates:

1. Retrieving product information.
2. Obtaining product snapshots.
3. Reserving inventory.
4. Submitting the order.
5. Creating an invoice.
6. Publishing domain events.

The distinction is important.

The Order aggregate decides whether an order can be submitted.

Inventory decides whether sufficient stock exists.

Billing decides whether an invoice can be created.

The application service coordinates these independent responsibilities.

### Compensation and failure handling

The examples reserve stock before completing order processing.

If a later operation fails, the application service attempts to release reservations that were already completed.

This is a compensating operation.

In a distributed application, this workflow may become a Saga.

A Saga coordinates a sequence of independent transactions and defines compensating operations when a later step fails.

Compensation does not provide the same guarantees as a single atomic database transaction.

Production systems must also consider failures during compensation, duplicate events, process restarts and partial delivery.

## 11. Implementation in Python

The Python implementation demonstrates a domain-oriented object model.

| Component | Implementation |
|---|---|
| Domain identity | Frozen dataclasses and UUID |
| Value object | Money |
| Domain events | DomainEvent |
| Aggregate root | AggregateRoot |
| Entity | Product |
| Catalog context | CatalogContext |
| Inventory context | InventoryContext |
| Order aggregate | Order |
| Child entity | OrderLine |
| Billing context | BillingContext |
| Repository | OrderRepository |
| Application service | OrderApplicationService |
| Event integration | EventBus |

Python-specific mechanisms include:

- Dataclasses for domain data.
- Enums for order and context states.
- Dictionaries for identifier-based storage.
- Frozen dataclasses for immutable value objects.
- Exceptions for invalid domain operations.
- Locks for protecting in-memory collections.
- Assertions for executable validation.

The Order class keeps its internal line collection private.

Its public methods control all meaningful modifications.

The demonstration also verifies that a Catalog price change does not alter an existing order's purchase snapshot.

## 12. Implementation in JavaScript

The JavaScript implementation emphasizes event-driven application behaviour.

| Component | Implementation |
|---|---|
| Identifiers | `crypto.randomUUID()` |
| Value objects | Frozen objects |
| Domain entities | Classes |
| Aggregate root | OrderAggregate |
| Internal collections | Map |
| Event processing | EventEmitter |
| Event handlers | Asynchronous functions |
| Repository | OrderRepository |
| Application service | OrderApplicationService |

JavaScript's `Map` provides efficient identifier-based lookup.

Private class fields protect internal aggregate state.

`Object.freeze()` provides shallow immutability for the demonstrated value objects and event payloads.

Promises and asynchronous event handlers illustrate how independent application components can react to business events.

The implementation also demonstrates event deduplication within the in-memory event bus.

This is not a durable event-processing guarantee. A production implementation requires persistent event identifiers and consumer-side idempotency.

## 13. Implementation in C++17

The C++ implementation emphasizes explicit domain modelling and resource-efficient data structures.

| Component | Implementation |
|---|---|
| Entity identifiers | String IDs |
| Value object | Money |
| Domain events | DomainEvent |
| Aggregate root | Order |
| Child entity | OrderLine |
| Catalog context | CatalogContext |
| Inventory context | InventoryContext |
| Billing context | BillingContext |
| Repository | OrderRepository |
| Application service | OrderApplicationService |

The implementation uses:

- Classes for domain objects.
- Structs for value-oriented data.
- Enums for lifecycle states.
- STL maps for identifier-based storage.
- Vectors for order lines and events.
- Exceptions for validation failures.
- Optional values for expected repository versions.
- Integer arithmetic for financial calculations.

The implementation checks integer overflow when multiplying monetary amounts and quantities.

Its associative containers provide logarithmic lookup and insertion complexity.

This is suitable for demonstrating explicit ownership and controlled domain operations without third-party dependencies.

## 14. Implementation in Java 17

The Java implementation uses an enterprise-oriented domain structure.

| Component | Implementation |
|---|---|
| Domain identity | UUID |
| Value objects | Records |
| Domain events | DomainEvent record |
| Aggregate root | AggregateRoot |
| Entity | CatalogProduct |
| Child entity | OrderLine |
| Bounded contexts | Dedicated context classes |
| Repository contract | Generic Repository interface |
| Repository implementation | OrderRepository |
| Event dispatch | DomainEventDispatcher |
| Application coordination | OrderApplicationService |

Java records provide concise data-oriented types.

The implementation uses `BigDecimal` for financial calculations.

`ConcurrentHashMap` supports concurrent identifier-based access to context storage.

Synchronized methods protect inventory updates.

Custom exceptions represent domain validation, missing entities and concurrency failures.

The repository interface separates the storage contract from the domain model.

The application service coordinates independent contexts while allowing each context to enforce its own business rules.

## 15. PostgreSQL Relational Design

The SQL implementation demonstrates how DDD concepts can be represented in a relational database.

The `ddd` schema contains the tables required by the enterprise purchasing scenario.

| Table | Responsibility |
|---|---|
| `catalog_products` | Product entities |
| `customers` | Customer entities |
| `inventory_items` | Stock records |
| `orders` | Order aggregate root |
| `order_lines` | Order child entities |
| `invoices` | Billing records |
| `domain_events` | Event outbox |

### 15.1 Aggregate persistence

The `orders` table represents the Order aggregate root.

The `order_lines` table stores its child entities.

The relationship is:

    orders
       |
       +---- order_lines
       |
       +---- order_lines
       |
       +---- order_lines

The order identifier connects the aggregate root with its child entities.

The database uses a composite primary key consisting of `order_id` and `line_number`.

This makes line identity specific to its parent aggregate.

### 15.2 Referential integrity

Foreign keys enforce relationships between tables.

For example:

- Order references Customer.
- Order Line references Order.
- Order Line references Catalog Product.
- Inventory Item references Catalog Product.
- Invoice references Order.

Foreign keys prevent invalid references.

Deletion restrictions protect records that are still needed by other business records.

### 15.3 Constraints

The SQL implementation uses:

- Primary keys
- Foreign keys
- Unique constraints
- Check constraints
- Generated columns
- Triggers
- Functions
- Procedures
- Indexes

Examples include positive order quantities, non-negative prices, valid currency codes and unique invoice ownership.

### 15.4 Triggers and aggregate invariants

The database includes triggers for important integrity rules.

The order-line trigger prevents modifications to lines belonging to submitted or later-stage orders.

The currency trigger ensures that the order and its lines use the same currency.

The total-recalculation trigger updates the aggregate's stored total after child-line changes.

The state-transition trigger restricts invalid order lifecycle transitions.

These controls provide database-level protection against operations that bypass application-level validation.

### 15.5 Transactions

The `process_order` procedure coordinates:

1. Order submission.
2. Inventory reservation.
3. Invoice creation.
4. Domain-event persistence.

The example executes the operation inside a transaction.

If an operation fails, the caller can roll back the transaction.

This provides atomicity for operations performed within the same PostgreSQL transaction.

Distributed systems require a different strategy when multiple services or databases participate.

## 16. Important Distinctions

### 16.1 Bounded context versus aggregate

A bounded context establishes a domain-model boundary.

An aggregate establishes a consistency boundary inside a domain model.

A bounded context can contain multiple aggregates.

For example, Order Management may contain Order, Return and Purchase Request aggregates.

An aggregate does not automatically require its own bounded context.

### 16.2 Aggregate root versus entity

An aggregate root is a specific entity that controls an aggregate.

Not every entity is an aggregate root.

Order is the aggregate root in the demonstrated Order model.

OrderLine is a child entity whose lifecycle and modification rules are controlled through Order.

### 16.3 Entity versus value object

An entity has a stable identity.

A value object represents a descriptive value and is normally immutable.

Product is an entity.

Money is a value object.

### 16.4 Domain model versus database model

A domain model represents business concepts and behaviour.

A database model represents persisted information and its relationships.

They can correspond closely, but they are not necessarily identical.

For example, an aggregate may contain several domain objects while its persistence uses multiple relational tables.

Database constraints complement domain validation but do not replace the need for a well-designed domain model.

### 16.5 Application service versus domain service

An application service coordinates a use case.

A domain service represents a business operation that does not naturally belong to a single entity or value object.

The OrderApplicationService is an application service because it coordinates Inventory, Order and Billing operations.

The business invariants remain inside their respective domain models.

## 17. Business Workflow

The example implements the following procurement workflow.

    Customer
       |
       v
    Create Order
       |
       v
    Retrieve Product Snapshot
       |
       v
    Add Order Lines
       |
       v
    Validate Order Aggregate
       |
       v
    Reserve Inventory
       |
       v
    Submit Order
       |
       v
    Publish OrderSubmitted
       |
       v
    Create Invoice
       |
       v
    Process Payment
       |
       v
    Update Billing State

Each step belongs to a defined responsibility.

Catalog supplies product information.

Order Management owns the purchasing decision.

Inventory owns stock reservations.

Billing owns invoices and payment status.

The workflow coordinates these responsibilities without combining their internal domain models.

## 18. Validation and Failure Scenarios

The implementations demonstrate several business failure conditions.

| Failure condition | Expected behaviour |
|---|---|
| Missing product | Reject product lookup |
| Inactive product | Reject purchase snapshot |
| Negative price | Reject value object |
| Invalid currency | Reject monetary value |
| Zero quantity | Reject order line |
| Mixed currencies | Reject order modification |
| Empty order | Reject submission |
| Insufficient stock | Reject reservation |
| Duplicate invoice | Reject invoice creation |
| Invalid order transition | Reject state change |
| Concurrent update | Reject stale repository version |
| Billing failure | Attempt inventory compensation |
| Duplicate event | Avoid repeated in-memory processing |

These failures are not merely technical exceptions.

They represent business conditions that the domain model must handle consistently.

## 19. Performance Considerations

DDD does not automatically make an application faster.

It provides a way to organize business complexity while allowing implementation choices to address performance.

Important considerations include:

| Area | Design consideration |
|---|---|
| Entity lookup | Use indexed identifiers |
| Aggregate loading | Load the required consistency boundary |
| Aggregate size | Avoid unnecessarily large aggregates |
| Database relationships | Index foreign keys where query patterns justify it |
| Event processing | Use asynchronous processing for independent consumers |
| Concurrency | Use optimistic locking where appropriate |
| Stock reservation | Use atomic conditional database updates |
| Reporting | Use dedicated reporting queries or read models |
| Historical information | Store purchase snapshots |
| Large collections | Avoid loading unrelated records into one aggregate |

The in-memory implementations use maps and dictionaries for direct identifier-based access.

The PostgreSQL implementation includes indexes for common order, product and event retrieval patterns.

A production application should measure query performance and aggregate loading costs using realistic workloads.

## 20. Security Considerations

Domain boundaries also support better security architecture.

Each context should have access only to the information and operations required for its responsibilities.

Important controls include:

- Use least-privilege database roles.
- Validate all externally supplied identifiers.
- Use parameterized database queries.
- Protect customer and payment information.
- Avoid placing confidential data in domain-event payloads.
- Restrict cross-context database access.
- Record sensitive business-state changes.
- Authenticate and authorize application operations.
- Protect event consumers against duplicate delivery.
- Use controlled retries for failed operations.

A bounded context is not automatically a security boundary.

Actual isolation requires appropriate application permissions, database privileges, network controls and operational policies.

## 21. Limitations of the Demonstrations

The five implementations are executable learning models, not complete distributed production systems.

The following limitations are important.

| Area | Demonstration limitation |
|---|---|
| Persistence | Most language implementations use in-memory storage |
| Concurrency | In-memory repositories do not provide distributed locking |
| Events | In-memory event dispatch is not durable |
| Transactions | Compensation does not guarantee atomic distributed execution |
| Inventory | Production reservations need expiration and release policies |
| Billing | Actual payment-provider integration is not implemented |
| Security | Production authentication and authorization are outside the examples |
| Database isolation | Production deployments must define appropriate isolation and retry policies |
| Event delivery | Production systems need durable publishing and idempotent consumers |

The PostgreSQL implementation provides relational persistence, database transactions and an event outbox structure.

It still requires a production event publisher and additional operational controls.

## 22. Final Conceptual Relationship

The three central concepts solve different structural problems.

| Concept | Main question | Responsibility |
|---|---|---|
| Bounded Context | Where does this domain model apply? | Model and language boundaries |
| Entity | Which business object is this? | Stable identity |
| Aggregate | Which objects must preserve consistency together? | Business invariants and controlled state changes |

Their relationship can be expressed as:

    Business Domain
          |
          v
    Bounded Context
          |
          +-------------------+
          |                   |
       Aggregate           Aggregate
          |                   |
      Root Entity          Root Entity
          |                   |
      Child Entities       Child Entities
          |
      Value Objects
          |
      Domain Events
          |
      Application Coordination
          |
      Persistence and Integration

The central design principle is to keep business models explicit, assign ownership to appropriate contexts, preserve aggregate invariants and coordinate independent business operations through well-defined interfaces.
