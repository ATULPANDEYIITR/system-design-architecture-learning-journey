# Monolith Architecture

## Project Overview

This project demonstrates monolithic software architecture through five executable implementations using Python, JavaScript, C++17, Java 17, and PostgreSQL.

The central scenario is an enterprise business application containing user management, product catalog, inventory, order processing, and payment functionality.

All modules belong to one application and share a common deployment lifecycle. Internal module boundaries organize responsibilities without requiring each module to run as an independently deployable service.

The implementations demonstrate the architectural structure, transactional workflows, scaling decisions, operational monitoring, and limitations of a monolithic application.

## 1. Monolith Architecture Fundamentals

A monolith is an application deployed as one integrated software unit.

Its business capabilities can be separated into internal modules, but these modules normally execute within the same application process or deployment artifact.

Typical structure:

    Enterprise Application
    |
    +-- User Management
    |
    +-- Product Catalog
    |
    +-- Inventory Management
    |
    +-- Order Processing
    |
    +-- Payment Processing
    |
    +-- Reporting
    |
    +-- Shared Infrastructure
         |
         +-- Database
         +-- Configuration
         +-- Logging
         +-- Monitoring

The modules communicate through internal function calls, classes, shared application services, and database operations.

A monolith does not require poorly structured or tightly coupled code. Modular monolithic design establishes clear internal responsibilities while retaining a unified deployment model.

### Important terminology

| Term | Meaning |
|---|---|
| Monolith | An application deployed as one integrated unit |
| Module | An internally separated business responsibility |
| Shared database | A database used by multiple application modules |
| Deployment artifact | The executable application package released together |
| Application instance | One running copy of the application |
| Vertical scaling | Increasing resources assigned to an application instance |
| Horizontal scaling | Running additional complete application instances |
| Coupling | The degree of dependency between application components |
| Cohesion | The degree to which a module's responsibilities belong together |
| Shared transaction | A database transaction spanning multiple business operations |

## 2. Internal Module Architecture

The project uses five principal business modules.

| Module | Responsibility | Main operations |
|---|---|---|
| Users | Customer registration | Validate and register users |
| Catalog | Product information | Maintain product details |
| Inventory | Stock management | Reserve and validate quantities |
| Orders | Order lifecycle | Create and process orders |
| Payments | Payment records | Record payment outcomes |

Each module owns a distinct business responsibility.

For example, the order module coordinates inventory reservation and payment processing. It does not need to duplicate the inventory calculation or payment implementation.

### Internal communication

A typical order workflow is:

    Customer Request
          |
          v
    Order Module
          |
          v
    User Validation
          |
          v
    Inventory Module
          |
          v
    Stock Reservation
          |
          v
    Payment Module
          |
          v
    Payment Confirmation
          |
          v
    Order Completion

Communication occurs inside the application rather than through independent network services.

This reduces network overhead, simplifies debugging, and makes synchronous business workflows easier to implement.

The tradeoff is that internal modules share the application's execution environment and deployment lifecycle.

## 3. Advantages

### Simpler development and deployment

A monolith generally requires fewer deployment components than a distributed system.

A single application package can contain the complete business functionality.

This reduces the number of independently managed application releases, service endpoints, deployment configurations, and network communication paths.

### Efficient internal communication

Modules can communicate using ordinary function calls and shared objects.

This avoids the serialization, network latency, authentication, retry, and service-discovery overhead associated with many distributed service interactions.

### Easier transactional consistency

Modules using the same relational database can participate in one database transaction.

For example, order creation can coordinate:

- Inventory reservation.
- Order creation.
- Order-item insertion.
- Payment record creation.
- Order status updates.

If an operation fails before commit, the database transaction can roll back its changes.

This is particularly useful when multiple business operations require strong consistency.

### Centralized testing

The complete application can be tested using integration tests that exercise multiple modules together.

Developers can verify business workflows without deploying several independent services.

### Lower initial operational complexity

A small team can operate one application deployment and one logical database without immediately introducing service discovery, distributed tracing, inter-service authentication, and distributed transaction coordination.

## 4. Limitations

### Deployment coupling

All modules generally share a deployment lifecycle.

A change to one module can require rebuilding, testing, and deploying the complete application.

A module cannot ordinarily be released independently without introducing additional architectural mechanisms.

### Failure propagation

A serious process-level failure can affect every module running inside that process.

Examples include:

- Memory exhaustion.
- Unhandled application exceptions.
- Runtime deadlocks.
- Shared resource exhaustion.
- Application-wide configuration errors.

Internal module boundaries do not provide process-level fault isolation.

### Scaling limitations

Suppose inventory processing requires significantly more CPU than user registration.

In a conventional monolith, adding another application instance also adds the user, order, payment, and reporting modules.

The system cannot independently allocate additional application instances exclusively to inventory processing.

### Shared resource contention

Multiple modules may compete for:

- Database connections.
- CPU.
- Memory.
- Thread pools.
- Database locks.
- Storage bandwidth.
- Network connections.

A resource-intensive reporting query can affect transactional operations if resource management is inadequate.

### Increasing maintenance complexity

As an application grows, weak module boundaries can lead to:

- Circular dependencies.
- Shared mutable state.
- Duplicated business rules.
- Large application classes.
- Unclear ownership.
- Difficult regression testing.

A modular monolith addresses these problems through explicit module interfaces, controlled dependencies, and clear ownership of business rules.

## 5. Scaling Monolithic Applications

Scaling means increasing the system's ability to handle workload while maintaining acceptable response times, availability, and resource utilization.

Two principal approaches are implemented.

### Vertical scaling

Vertical scaling increases the resources assigned to an existing application instance.

Examples:

- Increasing CPU cores.
- Increasing RAM.
- Allocating faster storage.
- Increasing available database connection capacity where appropriate.

Illustration:

    Before:
    Monolith Instance
    CPU: 2 cores
    RAM: 4 GB

    After:
    Monolith Instance
    CPU: 8 cores
    RAM: 16 GB

Advantages:

- Relatively straightforward.
- No additional application instances are required.
- Shared in-memory state is easier to maintain.
- Operational configuration can remain simpler.

Limitations:

- Hardware capacity is finite.
- Larger instances can become expensive.
- A single instance remains a failure domain.
- Resource upgrades may require restarts or maintenance.

### Horizontal scaling

Horizontal scaling runs multiple complete instances of the same application.

    Client Requests
          |
          v
      Load Balancer
          |
          +----------------+
          |                |
          v                v
      Instance 1       Instance 2
          |                |
          +--------+-------+
                   |
                   v
             Shared Database

Advantages:

- More application request-processing capacity.
- Improved availability when instances are independently monitored.
- Traffic distribution across multiple instances.
- Possibility of rolling application deployment.

Limitations:

- Every instance contains the complete application.
- Shared database contention can remain.
- In-memory sessions cannot be assumed to exist on every instance.
- Application state should generally be externalized.
- Distributed locking and coordination may be necessary.
- Database connections can increase as application instances increase.

A load balancer should distribute requests across healthy instances.

Stateless application instances are easier to scale horizontally. Sessions, shared caches, and other persistent application state should use appropriately shared infrastructure.

### Scaling decision model

The Java implementation evaluates CPU utilization, memory utilization, request latency, and database saturation.

| Condition | Possible response |
|---|---|
| Low resource utilization | Retain current capacity |
| High CPU utilization | Investigate workload and consider scaling |
| High memory utilization | Increase memory or optimize memory usage |
| High request latency | Identify the bottleneck before scaling |
| Database saturation | Optimize database capacity and queries |
| High application workload | Consider additional complete instances |

Scaling decisions should be based on measured bottlenecks rather than CPU utilization alone.

## 6. Python Implementation

The Python script models a complete business application using standard-library features.

### Main components

| Component | Responsibility |
|---|---|
| `MonolithDatabase` | Shared application state |
| `UserModule` | User registration |
| `InventoryModule` | Product and stock management |
| `PaymentModule` | Payment processing |
| `OrderModule` | Business workflow coordination |
| `ApplicationMetrics` | Request and latency measurements |
| `MonolithicApplication` | Complete application instance |
| `MonolithCluster` | Multiple application instances |

### Important mechanisms

**Dataclasses**

`Product`, `Order`, and `ApplicationMetrics` provide structured domain models.

**Enums**

`ModuleName` and `OrderStatus` restrict application states to defined values.

**Exception handling**

Invalid requests, missing users, invalid quantities, and insufficient inventory produce explicit failures.

**Transactional simulation**

The database snapshot and restoration mechanism demonstrate rollback of in-memory state.

This is an educational simulation, not a replacement for database transaction isolation or durable transaction management.

**Horizontal scaling**

`MonolithCluster` creates multiple complete application instances that share one logical database.

The implementation demonstrates why adding instances does not independently scale one internal module.

### Complexity considerations

- Dictionary lookups for users, products, and orders are expected O(1).
- Product reservation is expected O(1).
- Snapshot creation is O(P + O + T), where P is the product count, O is the order count, and T is the payment count.
- Full-state snapshots become inefficient for large applications.

Production applications should use database transactions instead of copying the entire application state.

## 7. JavaScript Implementation

The JavaScript implementation emphasizes event-driven internal communication and asynchronous payment processing.

### Main components

| Component | Responsibility |
|---|---|
| `SharedDatabase` | Centralized application state |
| `EventBus` | Internal event distribution |
| `InventoryModule` | Stock reservation |
| `PaymentModule` | Asynchronous payment handling |
| `OrderModule` | Order orchestration |
| `Metrics` | Request and latency tracking |
| `MonolithDeployment` | Application instance management |

### Event-driven behavior

The application emits internal events such as:

- `inventory.reserved`
- `payment.completed`
- `order.paid`

These events allow other modules to react to business operations without requiring every internal interaction to be implemented as a direct function call.

The event bus remains inside the monolithic process. It does not create independently deployed services.

### Asynchronous processing

The payment module uses an asynchronous operation.

This models a dependency that can fail or take additional time.

The order module waits for the payment result before marking an order as paid.

### Idempotency

The order module accepts an idempotency key.

Repeated requests with the same key return the original order rather than creating another order.

A production implementation must persist idempotency keys and protect them against concurrent requests.

### Performance measurements

The metrics component records:

- Request count.
- Failure count.
- Failure rate.
- Average response time.
- 95th-percentile response time.
- Internal module call counts.

These measurements help identify performance degradation.

## 8. C++17 Implementation

The C++ implementation provides two distinct perspectives:

1. Transactional business application behavior.
2. Repository governance and merge eligibility.

The business application uses strongly typed structures, STL containers, references, and exception handling.

The repository governance engine models protected branch rules as a policy-evaluation problem.

### Business application

`MonolithDatabase` contains shared application state.

`InventoryModule`, `PaymentModule`, and `OrderModule` coordinate the business transaction.

The application restores its previous state if payment processing fails.

This demonstrates the relationship between shared state and transaction consistency.

### Repository governance engine

The governance engine evaluates:

- Pull Request state.
- Source and target branch names.
- Draft status.
- Synchronization with the target branch.
- Required approvals.
- Unresolved review conversations.
- Build status.
- Other failed status checks.
- Linear-history restrictions.

The engine distinguishes merge eligibility from the actual merge operation.

A Pull Request is eligible only when all configured requirements are satisfied.

The sample implementation uses an in-memory model. It does not connect to a Git hosting provider or perform real Git operations.

## 9. Java 17 Implementation

The Java implementation models an enterprise-oriented monolithic application.

It uses records, interfaces, enums, collections, immutable data structures, service classes, and explicit state transitions.

### Domain model

| Type | Purpose |
|---|---|
| `User` | Immutable customer information |
| `Product` | Product information and validation |
| `Payment` | Payment record |
| `Order` | Business transaction state |
| `ApplicationModule` | Common module contract |
| `SharedDatabase` | Centralized persistence simulation |
| `ScalingPolicy` | Infrastructure scaling decisions |
| `MonolithicApplication` | Complete application composition |

### State transitions

An order begins in `CREATED`.

After successful payment processing, it moves to `PAID`.

Invalid transitions are rejected by the order domain model.

### Enterprise design decisions

The implementation uses explicit service boundaries.

The order service coordinates inventory and payment operations while using a common database abstraction.

The synchronized order operation illustrates controlled access to shared in-memory state.

The implementation is intended for a single-process demonstration. A production multi-instance application needs database-level concurrency control rather than Java synchronization alone.

### Scaling policy

The scaling policy distinguishes:

- Single-instance operation.
- Horizontal application scaling.
- Vertical resource scaling.

Database saturation is treated separately because adding application instances may increase pressure on an already overloaded database.

## 10. PostgreSQL Database Design

The SQL implementation creates a dedicated `monolith` schema.

The schema separates business responsibilities through relational tables while preserving one logical database.

### Entity relationships

    applications
       |
       +---- application_modules
       |
       +---- application_instances
       |          |
       |          +---- application_metrics
       |
       +---- deployment_history
       |
       +---- scaling_events
       |
       +---- module_events

    users
       |
       +---- orders
                 |
                 +---- order_items
                 |        |
                 |        +---- products
                 |                  |
                 |                  +---- inventory
                 |
                 +---- payments

### Database integrity

The schema uses:

- Primary keys for entity identification.
- Foreign keys for referential integrity.
- Unique constraints for email addresses, SKUs, payment references, and idempotency keys.
- Check constraints for prices, quantities, resource measurements, and statuses.
- Indexes for frequently accessed relationships and reporting queries.
- Triggers for timestamp maintenance and order-state protection.

### Transaction processing

The `process_order` procedure coordinates:

1. User validation.
2. Product validation.
3. Idempotency checking.
4. Inventory reservation.
5. Order creation.
6. Order-item creation.
7. Payment record creation.
8. Inventory reservation completion.
9. Order state transition.

The inventory update uses a conditional SQL update to prevent two concurrent transactions from reserving the same unavailable stock.

PostgreSQL transaction boundaries provide atomicity when the procedure is called within a transaction.

The example records payment completion in the database. It does not perform an external payment-provider charge.

Real payment integrations require an outbox or equivalent reliable messaging mechanism, provider-side idempotency, and payment reconciliation.

### Database performance

The indexes support:

- User order history.
- Order status filtering.
- Product-based order retrieval.
- Payment status reporting.
- Module event retrieval.
- Application instance monitoring.

A GIN index supports queries involving JSONB event payloads.

Indexes improve suitable read queries but increase storage requirements and write overhead.

The application should be monitored for query latency, lock contention, connection saturation, and replication lag.

## 11. Architectural Comparison

| Criterion | Monolithic architecture | Microservices architecture |
|---|---|---|
| Deployment | One integrated application | Independently deployable services |
| Communication | Primarily in-process | Primarily service communication |
| Database | Often shared | Often separately owned |
| Initial complexity | Generally lower | Generally higher |
| Scaling | Complete application instances | Independent service instances |
| Transactions | Shared database transactions are practical | Distributed consistency requires additional design |
| Fault isolation | Limited within one process | Can be stronger between services |
| Release coordination | Usually centralized | Can be independent |
| Operational requirements | Fewer distributed components | More service infrastructure |
| Internal modularity | Possible and desirable | Required across service boundaries |

A monolith and a poorly structured monolith are not the same thing.

A well-designed monolith can have strong module boundaries, explicit interfaces, controlled dependencies, and clear ownership of business rules.

The primary distinction is the deployment and runtime boundary, not whether the application contains modules.

## 12. Production Considerations

### Security

A production monolith should implement:

- Authentication and authorization.
- Role-based access controls.
- Input validation.
- Secure secret management.
- TLS for network communication.
- Parameterized SQL statements.
- Audit logging.
- Rate limiting.
- Dependency vulnerability scanning.
- Least-privilege database accounts.

Internal module access should follow business authorization rules rather than relying solely on the fact that modules run in one process.

### Reliability

Important controls include:

- Health checks.
- Readiness checks.
- Graceful shutdown.
- Database connection pooling.
- Transaction rollback.
- Retry policies with bounded attempts.
- Idempotent operations.
- Backup and recovery procedures.
- Disaster recovery testing.
- Centralized error reporting.

Retries must be designed carefully. Retrying a payment or order request without idempotency protection can create duplicate business operations.

### Monitoring

Monitor the application at multiple levels.

| Layer | Measurements |
|---|---|
| Application | Request rate, errors, latency |
| Runtime | CPU, memory, thread usage |
| Database | Query latency, locks, connections |
| Business | Failed payments, pending orders |
| Deployment | Release status, instance health |
| Infrastructure | Storage, network, availability |

### High availability

Multiple complete monolith instances can improve application availability when deployed across independent failure domains.

A shared database remains a critical dependency.

High availability therefore also requires database replication, backup validation, failover planning, and recovery procedures.

A database replica is not automatically a complete disaster recovery solution.

## 13. Implementation Coverage

| Requirement | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Module boundaries | Yes | Yes | Yes | Yes | Yes |
| Shared application state | Yes | Yes | Yes | Yes | Yes |
| User validation | Yes | Yes | Yes | Yes | Yes |
| Inventory management | Yes | Yes | Yes | Yes | Yes |
| Order processing | Yes | Yes | Yes | Yes | Yes |
| Payment failure handling | Yes | Yes | Yes | Yes | Transactional model |
| Rollback demonstration | Yes | Yes | Yes | Yes | Yes |
| Horizontal scaling model | Yes | Yes | Architecture model | Policy model | Yes |
| Performance monitoring | Yes | Yes | Policy model | Policy model | Yes |
| Repository governance | No | No | Yes | No | No |
| Event-driven communication | No | Yes | No | No | Event records |

## 14. Execution and Validation

| File | Runtime | Execution |
|---|---|---|
| Python | Python 3.10+ | `python monolith.py` |
| JavaScript | Node.js 18+ | `node monolith.js` |
| C++17 | C++17 compiler | `g++ -std=c++17 -O2 monolith.cpp -o monolith` |
| Java 17 | JDK 17 | `javac Main.java` followed by `java Main` |
| PostgreSQL | PostgreSQL 14+ | Execute the SQL script using a PostgreSQL client |

The Python, JavaScript, C++17, and Java programs use standard-library functionality and do not require third-party packages.

The PostgreSQL script creates its own schema and sample business records. It should be executed in a database where the executing role has the required schema, table, function, and procedure permissions.

The examples use simulated application persistence in the programming-language implementations. PostgreSQL provides the relational transaction model.

## 15. Key Technical Distinctions

The following distinctions are central to understanding monolithic architecture:

- A monolith is a deployment model, not necessarily a single source-code file.
- Internal modules can have strong separation without being independent services.
- Shared database access can simplify consistency but create resource contention.
- Vertical scaling increases the resources available to an application instance.
- Horizontal scaling increases the number of complete application instances.
- Horizontal scaling does not independently scale internal modules.
- Multiple instances improve application availability only when failure domains and shared dependencies are addressed.
- Database replication improves certain availability and read-scaling scenarios but introduces consistency and failover considerations.
- Modular design reduces internal coupling but does not eliminate deployment coupling.
- A well-structured monolith can remain a practical architecture for complex enterprise applications.
