# Software Design vs System Design: LLD vs HLD, Component Design and Architecture Decisions

## Introduction

This study material focuses on the relationship between software design and system design, with particular attention to Low-Level Design (LLD), High-Level Design (HLD), component design, architecture decisions, and the trade-offs involved in building maintainable software systems.

The Python program was designed to explain the subject progressively, starting from basic distinctions and moving toward practical architecture and detailed component-level design.

The central idea is that software design and system design operate at different levels of abstraction, but they are strongly connected.

**Software design** is mainly concerned with the internal organisation of software. It deals with classes, objects, interfaces, modules, responsibilities, dependencies, business rules and implementation structure.

**System design** looks at the complete system. It deals with applications, services, databases, caches, queues, external systems, communication, scalability, reliability, security, deployment and operational behaviour.

## High-Level Design and Low-Level Design

High-Level Design describes the major building blocks of a system and the relationships between them.

For example, an e-commerce platform may contain:

* User Service
* Product Service
* Order Service
* Payment Service
* Inventory Service
* Notification Service
* Database systems
* Cache
* Message broker
* API gateway

This is HLD because the focus is on the major components and how they interact.

Low-Level Design goes inside those components.

For an Order Service, an LLD may contain:

* Order
* OrderItem
* OrderService
* OrderRepository
* OrderValidator
* PricingService
* PaymentGateway
* InventoryGateway

LLD focuses on the internal responsibilities, interfaces, relationships and behaviour of these components.

HLD answers questions such as:

* What major components are required?
* Which component owns a particular responsibility?
* How do services communicate?
* Which database should be used?
* Where should caching be introduced?
* Which operations should be asynchronous?
* How will the system handle failures?
* How will the system scale?

LLD answers questions such as:

* Which classes are required?
* What responsibility belongs to each class?
* Which interfaces should exist?
* How should dependencies be injected?
* What state transitions are allowed?
* How should business rules be represented?
* What errors should a component produce?
* How can the component be tested?

A good HLD provides meaningful boundaries for LLD, while a good LLD ensures that those boundaries actually work in implementation.

## Requirements and Design

Design should begin with requirements rather than technology.

Functional requirements describe what the system must do.

Examples include:

* Creating an account
* Creating an order
* Processing a payment
* Reserving inventory
* Sending notifications

Non-functional requirements describe how the system should behave.

Examples include:

* Response time
* Availability
* Scalability
* Security
* Reliability
* Storage requirements
* Recovery requirements

Non-functional requirements can strongly influence architecture.

A system processing a few hundred requests per day can have a very different architecture from a system processing tens of thousands of requests per second.

This means that architecture cannot be evaluated without understanding the workload and business requirements.

## Abstraction Levels

Software design can be viewed as a hierarchy.

At the highest level are business requirements.

These are translated into system responsibilities, which are divided into components and services.

Those components are then decomposed into classes, objects and functions.

The major levels are:

1. Business requirements
2. System responsibilities
3. Major components
4. Internal component structure
5. Classes and objects
6. Functions and implementation details

Moving upward increases abstraction and system scope.

Moving downward increases implementation detail.

A good designer needs to move between these levels without confusing them.

## Decomposition

Decomposition means breaking a large problem into smaller, meaningful parts.

A system can be decomposed according to:

* Business capability
* Responsibility
* Data ownership
* Workflow
* Domain concepts
* Technical concerns

Simply identifying nouns such as User, Product and Order does not automatically produce good architecture.

A stronger approach asks:

* Who owns this behaviour?
* Who owns this data?
* Who is allowed to modify it?
* What happens when this rule changes?
* Which component should be responsible for this decision?

The objective is not to create as many components as possible. The objective is to create useful boundaries.

## Modules and Components

A module is a logical unit of software organisation.

A component is a coherent unit with a defined responsibility and interface.

A well-designed component normally has:

* A clear purpose
* Defined inputs
* Defined outputs
* Controlled dependencies
* Explicit ownership
* Predictable behaviour
* Defined failure behaviour

A component becomes difficult to maintain when unrelated responsibilities accumulate inside it.

For example, an OrderService that performs validation, database access, payment processing, email delivery, inventory management and reporting has too many unrelated responsibilities.

The problem is not simply that the class is large. The deeper problem is that several independent reasons for change have been combined.

## Cohesion

Cohesion describes how closely related the responsibilities inside a module or component are.

High cohesion means that the responsibilities strongly belong together.

A PaymentService responsible for payment authorisation, capture and refund has relatively high cohesion.

A generic utility component responsible for payments, image processing, email, tax calculations and reporting has low cohesion.

High cohesion generally improves:

* Readability
* Testability
* Maintainability
* Changeability

## Coupling

Coupling describes the dependency between software components.

Strong coupling means that changes in one component frequently require changes in another.

Low coupling means that components communicate through stable and controlled boundaries.

For example, an OrderService directly depending on a specific payment provider creates stronger coupling than an OrderService depending on a PaymentGateway abstraction.

The goal is not to eliminate coupling completely.

Components must communicate to perform useful work.

The goal is to keep coupling intentional and controlled.

## Encapsulation

Encapsulation means protecting internal state and implementation details.

A component should expose meaningful operations rather than allowing unrestricted modification of internal data.

This becomes particularly important when objects have invariants.

For an Order, possible invariants include:

* An order cannot be paid twice.
* A cancelled order cannot be shipped.
* An order cannot have a negative amount.
* An order cannot move from a completed state back to an earlier state.

Encapsulation allows the object to enforce these rules itself.

## Interfaces and Contracts

An interface defines what a component promises to provide.

For example, a payment system can expose a `PaymentGateway` abstraction.

Possible implementations include:

* StripePaymentGateway
* AdyenPaymentGateway
* MockPaymentGateway

The business logic can depend on the interface rather than a specific payment provider.

This creates a boundary between business logic and infrastructure.

A useful component contract defines:

* Inputs
* Outputs
* Preconditions
* Postconditions
* Errors
* Side effects

Clear contracts reduce ambiguity between components.

## SOLID Principles

The Python program covers the five SOLID principles.

### Single Responsibility Principle

A component should have a focused responsibility and a coherent reason to change.

An invoice class should not necessarily be responsible for calculation, PDF rendering, database storage and email delivery at the same time.

### Open/Closed Principle

Software should be designed so that stable behaviour can be extended without constantly modifying existing logic.

Strategies and polymorphic interfaces can be useful when behaviour varies.

### Liskov Substitution Principle

A subtype should preserve the behavioural expectations of the abstraction it replaces.

Inheritance is useful only when the behavioural relationship is valid.

### Interface Segregation Principle

Clients should not be forced to depend on methods they do not use.

Smaller and focused interfaces are often easier to understand and implement.

### Dependency Inversion Principle

High-level business logic should not depend directly on low-level implementation details.

Both should depend on appropriate abstractions.

This is one of the most important principles connecting LLD with larger architectural ideas.

## Composition and Inheritance

Inheritance represents an "is-a" relationship.

Composition represents a "has-a" or "uses-a" relationship.

For example:

* A Car is a Vehicle.
* A Car has an Engine.

Composition is often useful when behaviour needs to vary independently.

Instead of creating a large hierarchy of specialised classes, behaviour can be assembled through smaller components such as:

* PricingPolicy
* ShippingPolicy
* DiscountPolicy

This reduces unnecessary class hierarchies and keeps changing behaviour more independent.

## Domain Modelling

Domain modelling means representing important concepts and business rules from the problem domain.

An e-commerce system may contain:

* Customer
* Product
* Cart
* Order
* Payment
* Shipment
* Address

The purpose of domain modelling is not to create classes for every noun.

The purpose is to represent important business behaviour and rules clearly.

Examples include:

* An order can contain multiple items.
* Inventory cannot become negative.
* A payment cannot be captured before authorisation.
* A cancelled order cannot be shipped.

## Entities and Value Objects

An entity is generally identified by identity.

For example, a customer with ID 100 remains the same customer even if the customer's name changes.

A value object is identified by its value.

Examples include:

* Money
* Coordinates
* Email addresses
* Dates
* Addresses

This distinction affects equality, identity and persistence decisions.

## Design Patterns

The program covers common design patterns and their purpose.

### Creational Patterns

Examples include:

* Factory
* Abstract Factory
* Builder
* Singleton

### Structural Patterns

Examples include:

* Adapter
* Decorator
* Facade
* Composite
* Proxy

### Behavioural Patterns

Examples include:

* Strategy
* Observer
* Command
* State
* Chain of Responsibility
* Template Method

Patterns should be used to solve recurring design problems.

A pattern should not be introduced merely because it is available.

Unnecessary patterns can make simple software harder to understand.

## Factory Pattern

A factory centralises object creation when creation rules are complex or when the caller should not depend on concrete implementations.

For example, a notification factory can return an email or SMS notification implementation based on the requested channel.

## Adapter Pattern

An adapter converts one interface into another.

This is especially useful when integrating external systems.

The application can define the interface it wants while the adapter translates that interface into the API expected by the external provider.

## Decorator Pattern

A decorator adds behaviour around an existing component without modifying its core implementation.

Common applications include:

* Logging
* Caching
* Metrics
* Authorisation
* Retry handling

## Architecture Styles

Several architectural styles were explored.

### Layered Architecture

A common structure is:

* Presentation
* Application
* Domain
* Infrastructure

The purpose is to separate concerns.

### Clean Architecture

Clean Architecture places important business rules toward the centre and infrastructure details toward the outside.

The dependency direction generally points toward the more stable business logic.

### Hexagonal Architecture

Hexagonal Architecture, also called Ports and Adapters, separates the application core from external systems through explicit ports.

External systems connect through adapters.

This makes infrastructure implementations replaceable.

### Modular Monolith

A modular monolith can have strong internal boundaries while still being deployed as one application.

This can provide much of the organisational benefit of service boundaries without immediately introducing the operational complexity of distributed systems.

### Microservices

Microservices divide a system into independently deployable services.

Potential benefits include:

* Independent deployment
* Independent scaling
* Fault isolation
* Team autonomy

The costs include:

* Network failures
* Distributed transactions
* Service coordination
* Monitoring complexity
* Versioning
* Data consistency problems
* Greater operational overhead

Microservices are therefore a trade-off rather than an automatic improvement over a monolith.

## Event-Driven Architecture

Event-driven architecture allows components to communicate through events.

For example:

`OrderPlaced`

may be consumed by:

* Inventory
* Notifications
* Analytics

The producer does not necessarily need direct knowledge of every consumer.

This can reduce direct coupling, but it introduces additional concerns such as:

* Duplicate events
* Ordering
* Retries
* Event schema evolution
* Eventual consistency
* Debugging
* Replay

## Synchronous and Asynchronous Communication

Synchronous communication requires the caller to wait for the response.

Asynchronous communication allows work to continue independently.

For example, an order service does not necessarily need to wait for an email notification to complete before confirming an order.

Asynchronous processing can improve resilience and reduce latency, but introduces additional infrastructure and consistency considerations.

## Scalability

Scalability is the ability of a system to handle increasing workload.

Vertical scaling increases the resources of an existing machine.

Horizontal scaling adds more machines or instances.

Horizontal scaling introduces additional considerations around:

* Shared state
* Sessions
* Databases
* Caches
* Load balancing
* Concurrency

A service becomes easier to scale horizontally when important state is not tied to one process instance.

## Load Balancing

A load balancer distributes traffic across multiple instances.

Possible strategies include:

* Round Robin
* Weighted Round Robin
* Least Connections
* Consistent Hashing

Load balancers can also perform health checks so that unhealthy instances do not continue receiving traffic.

## Caching

Caching stores frequently accessed data closer to the consumer.

A cache can reduce latency and database load.

Common strategies include:

* Cache-aside
* Write-through
* Write-behind
* Refresh-ahead

The difficult part of caching is often not reading data from the cache. It is keeping cached data sufficiently accurate.

Cache invalidation is therefore an important architectural concern.

## Database Decisions

Database selection should be based on workload and requirements.

Important questions include:

* Are transactions important?
* Are relationships important?
* What is the read volume?
* What is the write volume?
* How large will the data become?
* What consistency is required?
* What are the main query patterns?

Relational databases are often useful when relationships, constraints and transactions are important.

Document databases can be useful for document-oriented workloads.

Key-value systems are often useful for simple high-speed lookups and caching.

The database should be selected according to the problem rather than popularity.

## Normalisation and Denormalisation

Normalisation reduces unnecessary duplication and improves consistency.

Denormalisation intentionally duplicates data when it improves read performance or simplifies access patterns.

Denormalisation can improve performance but creates additional responsibilities for keeping duplicated information consistent.

## Transactions

Transactions provide an atomic boundary around a group of operations.

The classic ACID properties are:

* Atomicity
* Consistency
* Isolation
* Durability

An important design question is where the transaction boundary should exist.

A transaction inside one database is much easier to manage than a business operation spanning several independent services.

## Distributed Transactions

In a distributed architecture, an operation may involve:

* Order Service
* Payment Service
* Inventory Service

These services may have separate databases.

A traditional single database transaction cannot simply cover all of them.

Distributed workflows therefore often use techniques such as:

* Saga
* Compensating actions
* Transactional messaging
* Eventual consistency

## Saga Pattern

A Saga divides a distributed business operation into local transactions.

For example:

1. Create order
2. Authorise payment
3. Reserve inventory
4. Create shipment

If a later step fails, earlier operations may require compensating actions.

For example:

* Cancel order
* Refund payment
* Release inventory

Sagas can be coordinated through choreography or orchestration.

## Consistency

Strong consistency provides stronger guarantees that reads reflect the latest committed state.

Eventual consistency allows temporary differences between components while data converges later.

The appropriate model depends on the business requirement.

Not every piece of data needs the same consistency guarantee.

## CAP Theorem

CAP concerns distributed systems during network partitions.

The three properties are:

* Consistency
* Availability
* Partition tolerance

During a network partition, a distributed system cannot guarantee both strong consistency and availability simultaneously.

The practical design question becomes which property should receive priority when communication between parts of the system is disrupted.

## Reliability

Reliable systems account for failure as a normal possibility.

Important techniques include:

* Redundancy
* Replication
* Timeouts
* Retries
* Circuit breakers
* Health checks
* Rate limiting
* Backups
* Disaster recovery
* Graceful degradation

Reliability is not just a property of individual components. The interaction between components also determines system reliability.

## Timeouts

Network calls should have meaningful timeouts.

Without timeouts, a dependency that stops responding can cause callers to hold resources indefinitely.

As blocked requests accumulate, a local dependency problem can become a broader system failure.

## Retries

Retries can recover from temporary failures.

They need careful control around:

* Maximum attempts
* Backoff
* Jitter
* Retryable failures
* Idempotency

Repeated immediate retries can create a retry storm and make an already failing system worse.

## Circuit Breakers

A circuit breaker prevents repeated calls to an unhealthy dependency.

Common states are:

* Closed
* Open
* Half-open

The circuit opens after sufficient failures and stops sending normal requests to the failing dependency.

After a recovery period, limited test requests can determine whether normal operation can resume.

## Rate Limiting

Rate limiting controls how frequently a client or identity can perform operations.

Common approaches include:

* Fixed Window
* Sliding Window
* Token Bucket
* Leaky Bucket

Rate limiting protects system resources and downstream dependencies.

## Observability

Observability helps engineers understand the internal behaviour of a system.

The three major signals are:

* Logs
* Metrics
* Traces

Useful metrics include:

* Request rate
* Error rate
* Latency
* Saturation
* Queue depth
* Database connections
* Cache hit ratio

Distributed tracing becomes particularly useful when one request crosses several services.

## Security

Security affects both HLD and LLD.

HLD security concerns include:

* Authentication architecture
* Authorisation architecture
* Network boundaries
* Encryption
* Secrets management
* Service-to-service trust
* Data isolation

LLD security concerns include:

* Input validation
* Access checks
* Secure defaults
* Error handling
* Sensitive data handling

Authentication answers:

> Who are you?

Authorisation answers:

> What are you allowed to do?

These are separate concerns.

## Defence in Depth

Security should not rely on one control.

A system may use several layers:

* Authentication
* Authorisation
* Input validation
* Network restrictions
* Encryption
* Auditing
* Monitoring

If one control fails, additional controls can still provide protection.

## Architecture Decisions

Architecture is largely the process of making trade-offs.

Common trade-offs include:

* Consistency vs availability
* Latency vs durability
* Simplicity vs flexibility
* Cost vs performance
* Centralisation vs autonomy
* Synchronous vs asynchronous processing
* Local transactions vs distributed workflows
* Operational simplicity vs independent scaling

There is rarely a single architecture that is correct for every system.

A good architecture is one that satisfies the important requirements while keeping unnecessary complexity under control.

## Architecture Decision Records

An Architecture Decision Record, or ADR, captures the reasoning behind an important architecture decision.

A useful ADR contains:

* Title
* Context
* Decision
* Alternatives
* Consequences

The reasoning is important because future engineers need to understand why a decision was made, not just what technology was selected.

## Dependency Injection

Dependency injection means supplying dependencies from outside rather than constructing them directly inside a component.

Instead of making an OrderService create a PostgreSQL repository itself, the repository can be supplied to it.

This provides:

* Explicit dependencies
* Better testability
* Easier replacement of implementations
* Lower coupling

It also supports the Dependency Inversion Principle.

## Testability

Good design makes important behaviour easy to test.

Components become easier to test when:

* Dependencies are explicit
* External systems are abstracted
* Business logic is separated
* State is controlled
* Inputs and outputs are predictable

For example, business logic should not require a real payment provider just to test whether an order is valid.

A fake payment implementation can be injected instead.

## Error Handling

Errors should communicate meaningful categories.

Examples include:

* Validation error
* Authentication error
* Authorisation error
* Not found
* Conflict
* Dependency failure
* Timeout
* Internal failure

External users should not receive unnecessary internal implementation details.

Business-specific failures can be represented using explicit domain errors such as:

* InsufficientInventory
* InvalidOrderState
* PaymentAlreadyCaptured
* OrderAlreadyCancelled

This is clearer than returning generic values such as `False`, `None`, or `-1`.

## State Machines

State machines are useful when an entity follows a defined lifecycle.

An order may move through:

`CREATED → PAID → PACKED → SHIPPED → DELIVERED`

Cancellation may be allowed from selected states.

Explicit state transitions prevent invalid operations.

Payment processing can use a similar model:

`CREATED → AUTHORIZED → CAPTURED → REFUNDED`

The state machine makes business rules visible and enforceable.

## Data Ownership

Data ownership becomes particularly important in distributed architectures.

For an e-commerce system:

**Order Service owns:**

* Orders
* Order items
* Order state

**Inventory Service owns:**

* Stock
* Reservations

**Payment Service owns:**

* Payment attempts
* Payment state
* Provider references

A service should not directly modify another service's private database simply because it technically has access to it.

Direct database access between independent services creates hidden coupling.

Explicit APIs and events provide clearer boundaries.

## Database Per Service

Database-per-service is commonly associated with microservices.

Each service controls its persistence boundary.

This improves:

* Ownership
* Autonomy
* Schema independence
* Service isolation

The trade-off is that cross-service queries become more difficult.

Distributed systems often solve this through APIs, events, read models or data replication.

## CQRS

CQRS stands for Command Query Responsibility Segregation.

Commands modify state.

Queries read state.

The command and query models can be separate when their requirements differ significantly.

For example:

Commands:

* CreateOrder
* CancelOrder
* CapturePayment

Queries:

* CustomerOrderHistory
* SalesDashboard
* OrderTracking

CQRS does not automatically require two databases. It is primarily a separation of responsibilities.

## Read Models

A read model is a representation of data optimised for a particular query.

A customer order dashboard may require information from orders, payments, shipments and products.

A dedicated read model can combine this information so that the dashboard does not need to perform many distributed calls for every request.

The trade-off is that read models can become eventually consistent.

## Scalability and Capacity Estimation

System design should use approximate numbers when possible.

For example, if a system has 10 million users, 10% are active during peak periods and each active user generates five requests per minute:

10,000,000 × 0.10 × 5 = 5,000,000 requests per minute.

That is approximately 83,333 requests per second.

The calculation does not automatically determine the architecture, but it gives the architecture a workload to handle.

Capacity estimation can also be applied to:

* Storage
* Bandwidth
* Cache size
* Database operations
* Queue throughput

## Sharding

Sharding divides data across multiple partitions.

A system may distribute users according to a shard key such as user ID.

Possible approaches include:

* Range-based sharding
* Hash-based sharding
* Directory-based sharding

A poor shard key can create hotspots.

Sharding can improve scalability but increases operational and query complexity.

## Replication

Replication creates multiple copies of data.

It can improve:

* Availability
* Read capacity
* Recovery

But replication introduces issues such as:

* Replication lag
* Consistency
* Failover
* Conflict handling

A read replica may temporarily contain older data than the primary.

## Backpressure

Backpressure occurs when producers generate work faster than consumers can process it.

For example, if producers generate 10,000 messages per second while consumers process only 2,000, the queue grows.

A robust architecture must consider:

* Queue limits
* Consumer scaling
* Throttling
* Priority
* Dropping policies
* Retry behaviour

## Graceful Degradation

A system does not always need every feature to remain available during a failure.

For example, if a recommendation service fails, an e-commerce platform may still allow:

* Product browsing
* Cart operations
* Checkout

Recommendations can temporarily disappear.

This prevents an optional feature from becoming a dependency that can bring down the primary business workflow.

## Failure Domains

A failure domain is a group of resources likely to fail together.

Examples include:

* Process
* Machine
* Availability zone
* Region
* Database cluster

Running two processes on the same machine does not protect against machine failure.

High availability often requires redundancy across meaningful failure domains.

## Logical and Physical Architecture

Logical architecture describes what the system contains conceptually.

Physical architecture describes how those components are actually deployed.

Logical architecture may contain:

* Order Service
* Payment Service
* Inventory Service

Physical architecture may contain:

* Containers
* Virtual machines
* Kubernetes deployments
* Availability zones
* Networks
* Database clusters

A logical boundary does not automatically require an independent deployment boundary.

This distinction is important when designing modular monoliths and deciding when to split components into services.

## Architecture Diagrams

Different diagrams communicate different levels of design.

A context diagram shows the system and external actors.

A service or container diagram shows major application components.

A component diagram shows the internal structure of a major component.

A class diagram shows detailed object relationships.

A sequence diagram shows how components interact over time.

A useful diagram should communicate a meaningful relationship or decision rather than simply contain many boxes.

## Worked E-Commerce Design

The program develops an e-commerce platform from HLD to LLD.

At HLD level, the system contains major components such as:

* Client
* Load Balancer
* API Gateway
* Product Service
* Order Service
* User Service
* Payment Service
* Inventory Service
* Databases
* Message Broker
* Notification Service
* Analytics

At LLD level, the Order Service can contain:

* OrderController
* OrderApplicationService
* Order
* OrderItem
* PricingService
* OrderValidator
* OrderRepository
* PaymentGateway
* InventoryGateway

This illustrates the connection between the two levels.

HLD determines where responsibilities live.

LLD determines how those responsibilities are implemented inside each boundary.

## Checkout Design

A checkout workflow can be represented as:

1. Client sends an order request.
2. Order Service validates the request.
3. Inventory is reserved.
4. Payment is authorised.
5. Order state is updated.
6. An order event is published.
7. Notification processing happens asynchronously.

This workflow raises important architecture questions:

* What if inventory succeeds but payment fails?
* What if payment succeeds but the order update fails?
* What if the client retries the request?
* What if the event is delivered twice?
* What if notification processing is unavailable?

These questions expose the difference between a simple sequence of API calls and a reliable distributed system.

## Designing for Change

One of the major purposes of good design is controlling the cost of change.

If payment-provider-specific code is spread throughout the business logic, replacing the provider becomes difficult.

If the application uses:

`OrderService → PaymentGateway → PaymentAdapter`

the provider-specific implementation can be isolated.

The same principle can apply to:

* Databases
* Message brokers
* External APIs
* Storage systems
* Notification providers

Abstraction is most valuable when it protects an important boundary from change.

## Accidental Complexity

Accidental complexity is complexity introduced by design or implementation choices rather than by the actual problem.

Examples include:

* Unnecessary microservices
* Excessive abstractions
* Too many design patterns
* Unnecessary distributed infrastructure
* Redundant databases
* Overly complicated asynchronous workflows

Essential complexity comes from the problem itself.

Good design manages essential complexity while avoiding unnecessary accidental complexity.

## Premature Abstraction

An abstraction is useful when it protects a meaningful boundary or handles real variation.

Creating an abstraction before understanding the problem can make software harder to read.

The goal is not to maximise the number of interfaces.

The goal is to use abstractions where they provide clear architectural or design value.

## Over-Engineering

Over-engineering occurs when the complexity of the solution is significantly greater than the requirements justify.

A small internal application may not need:

* Multiple microservices
* Distributed tracing
* Service mesh
* Event sourcing
* Several databases
* Distributed caching

The appropriate architecture depends on the actual problem.

An architecture decision should be connected to a requirement, constraint, risk or expected change.

## HLD Design Process

A practical HLD process involves:

1. Understanding requirements.
2. Identifying non-functional requirements.
3. Estimating workload.
4. Identifying major use cases.
5. Defining system boundaries.
6. Identifying major components.
7. Defining communication.
8. Defining data ownership.
9. Selecting persistence.
10. Considering caching.
11. Considering asynchronous processing.
12. Considering failure modes.
13. Considering security.
14. Considering observability.
15. Estimating capacity.
16. Documenting trade-offs.

## LLD Design Process

A practical LLD process involves:

1. Identifying the use case.
2. Identifying domain objects.
3. Assigning responsibilities.
4. Defining invariants.
5. Defining interfaces.
6. Defining dependencies.
7. Choosing composition relationships.
8. Modelling state transitions.
9. Defining errors.
10. Considering concurrency.
11. Designing persistence interaction.
12. Ensuring testability.

LLD should be driven by behaviour and responsibility rather than by a target number of classes.

## Connecting HLD and LLD

A useful way to understand the relationship is:

**HLD**

`Order Service`

↓

**LLD**

* OrderController
* OrderApplicationService
* Order
* OrderItem
* PricingService
* OrderRepository
* PaymentGateway
* InventoryGateway

The HLD establishes the major boundary.

The LLD defines the internal structure within that boundary.

If the HLD says that the Order Service owns order state, but the LLD allows several unrelated components to modify that state directly, the two designs are inconsistent.

## Design Quality

A design can be evaluated across several dimensions.

### Correctness

Does the design satisfy the requirements?

### Clarity

Can engineers understand the structure and reasoning?

### Cohesion

Are responsibilities properly grouped?

### Coupling

Are dependencies controlled?

### Changeability

Can expected changes be implemented without unnecessary disruption?

### Testability

Can important behaviour be tested independently?

### Scalability

Can the system handle increasing workload?

### Reliability

Can failures be contained?

### Security

Are trust boundaries and sensitive operations protected?

### Operability

Can the system be monitored, diagnosed and maintained?

### Cost

Is the development and operational complexity justified?

## Important Distinctions

| Concept              | Meaning                                                |
| -------------------- | ------------------------------------------------------ |
| HLD                  | Major system structure                                 |
| LLD                  | Internal component structure                           |
| Module               | Logical unit of code organisation                      |
| Component            | Coherent functional unit with a contract               |
| Service              | Independent or remotely accessible business capability |
| Entity               | Identity-based domain object                           |
| Value Object         | Value-based domain object                              |
| Coupling             | Dependency between components                          |
| Cohesion             | Relatedness of responsibilities                        |
| Abstraction          | Important behaviour without implementation detail      |
| Encapsulation        | Protection of internal state and invariants            |
| Synchronous          | Caller waits for the result                            |
| Asynchronous         | Work can continue independently                        |
| Strong Consistency   | Strong guarantee around current state                  |
| Eventual Consistency | State converges over time                              |
| Vertical Scaling     | Increasing resources of a machine                      |
| Horizontal Scaling   | Adding more machines                                   |
| Replication          | Maintaining multiple copies of data                    |
| Sharding             | Partitioning data across multiple locations            |

## Core Design Principles Covered

The Python program develops the following principles in practical terms:

* Clear responsibility boundaries
* High cohesion
* Controlled coupling
* Encapsulation
* Abstraction
* Dependency inversion
* Explicit interfaces
* Composition over unnecessary inheritance
* Explicit domain rules
* Explicit state transitions
* Dependency injection
* Testability
* Data ownership
* Failure-aware design
* Idempotency
* Appropriate consistency
* Controlled scalability
* Security by design
* Observability
* Architecture trade-off analysis
* Proportional complexity

The important distinction throughout the material is that **LLD explains how a component works internally, while HLD explains how major components work together as a complete system**. Architecture decisions connect these two levels by defining boundaries, dependencies, data ownership, communication patterns, scalability characteristics, reliability mechanisms and operational behaviour.

