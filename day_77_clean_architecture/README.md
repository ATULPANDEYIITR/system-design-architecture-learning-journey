# Clean Architecture: Dependency Inversion and Boundaries

## 1. Introduction

Clean Architecture is a software design approach that separates business rules from implementation details. Its primary objective is to keep the central business logic independent of databases, web frameworks, external services, user interfaces, and other infrastructure.

The architecture organizes software into boundaries. Each boundary defines which components may communicate and which abstractions must be used when crossing between architectural layers.

The central design principle is the Dependency Rule:

**Source-code dependencies must point inward, towards policies and business rules.**

Infrastructure can change without requiring changes to the central domain model, provided that the external implementations continue to satisfy the contracts defined by the application.

The implementations in this repository use an enterprise order-processing system to demonstrate these principles.

## 2. Core Concepts

### 2.1 Architectural independence

Architectural independence means that important business rules should not require a particular technical implementation.

For example, an order-processing application should not require PostgreSQL to calculate an order total. The calculation belongs to the domain model and should work independently of the database.

Similarly, payment processing should be expressed through an application-defined contract rather than a direct dependency on a particular payment provider.

Consider the following separation:

| Concern | Architectural responsibility |
|---|---|
| Order calculation | Domain |
| Order state transitions | Domain |
| Order placement workflow | Application |
| Repository contract | Application |
| HTTP request conversion | Interface adapter |
| PostgreSQL implementation | Infrastructure |
| External payment integration | Infrastructure |
| Dependency construction | Composition root |

This separation reduces coupling and makes individual components easier to test.

### 2.2 The four architectural layers

The implementations use four logical layers.

| Layer | Responsibility | Typical components |
|---|---|---|
| Domain | Business rules and enterprise concepts | Entities, value objects |
| Application | Coordinates business workflows | Use cases, input and output ports |
| Adapter | Translates between external representations and application contracts | Controllers, presenters, gateways |
| Infrastructure | Supplies concrete technical implementations | Databases, external services, file systems |

The four-layer model is an organizational choice. Clean Architecture does not require every application to use precisely four physical directories or modules.

The important requirement is that source-code dependencies preserve the intended direction.

### 2.3 Domain layer

The domain layer contains business concepts and rules.

The order-processing example includes:

- `Order`
- `OrderLine`
- `Money`
- `OrderStatus`

The `Order` entity maintains its own state and controls valid state transitions.

For example:

- A pending order can become paid.
- A pending order can become cancelled.
- A paid order cannot be cancelled through the ordinary cancellation operation.
- A cancelled order cannot be reopened through an ordinary state transition.

The domain model does not know whether orders are stored in PostgreSQL, JSON files, or memory.

The `Money` value object represents an amount and currency together. Its operations validate currency compatibility and prevent negative monetary values.

Money is represented using `Decimal`, `BigDecimal`, or integer minor units depending on the implementation.

Binary floating-point arithmetic is avoided for financial calculations because many decimal fractions cannot be represented exactly in binary floating-point formats.

### 2.4 Application layer

The application layer contains use cases.

A use case represents an operation that the system performs in response to an application request.

The principal use case is `PlaceOrder`.

Its workflow is:

1. Receive an order-placement command.
2. Validate the application input.
3. Construct an order.
4. Save the pending order through a repository port.
5. Request payment through a payment port.
6. Apply the successful payment transition.
7. Persist the updated order.
8. Publish an application event.

The use case coordinates operations without implementing the underlying database or payment integration.

This is an important distinction:

- Domain logic determines what operations are valid.
- Application logic determines when those operations occur.
- Infrastructure determines how external operations are performed.

### 2.5 Input ports and output ports

Ports define the contracts through which the application communicates with other components.

**Input ports**

Input ports describe operations that an external actor can request from the application.

Examples:

- `PlaceOrderInputPort`
- `PlaceOrderCommand`
- `PlaceOrder.execute()`

An HTTP controller can invoke an input port without needing to know the internal implementation of the use case.

**Output ports**

Output ports describe services required by the application.

Examples:

- `OrderRepository`
- `PaymentGateway`
- `EventPublisher`

The application defines these abstractions because it owns the business workflow that requires them.

Infrastructure implements the contracts.

| Port | Purpose | Concrete implementation |
|---|---|---|
| OrderRepository | Store and retrieve orders | In-memory or PostgreSQL repository |
| PaymentGateway | Process payment requests | External payment adapter |
| EventPublisher | Publish application events | Messaging adapter |

Ports are contracts, not infrastructure implementations.

## 3. Dependency Inversion Principle

### 3.1 Meaning

The Dependency Inversion Principle is one of the SOLID design principles.

It establishes two important rules:

1. High-level policies should not depend directly on low-level implementation details.
2. Both should depend on abstractions.

Abstractions should not be designed around the internal requirements of a particular infrastructure implementation.

Consider an application service that directly creates a PostgreSQL repository.

This creates the following dependency:

Application Service → PostgreSQL Repository

Changing the persistence technology can then affect the application service.

Dependency inversion introduces a repository abstraction:

Application Service → OrderRepository

PostgreSQL Repository → OrderRepository

The application and infrastructure now communicate through a stable contract.

The runtime object relationship can still involve a concrete PostgreSQL repository. What changes is the direction of the source-code dependency.

### 3.2 Dependency inversion versus dependency injection

These concepts are related but different.

| Aspect | Dependency inversion | Dependency injection |
|---|---|---|
| Nature | Design principle | Implementation technique |
| Purpose | Control dependency direction | Supply required collaborators |
| Main concern | Abstractions and boundaries | Object construction and wiring |
| Example | Application depends on a repository interface | Composition root supplies a repository instance |

Dependency inversion determines which abstraction owns the contract.

Dependency injection supplies an implementation of that contract.

Dependency injection alone does not guarantee Clean Architecture. An application can use dependency injection while remaining tightly coupled to infrastructure-specific abstractions.

### 3.3 Dependency direction

The intended dependency structure is:

Domain
    ↑
Application
    ↑
Interface Adapters
    ↑
Infrastructure

This diagram represents inward source-code dependencies. It does not mean that runtime execution must always move upward.

For example, an application service can call an infrastructure implementation through an output port. The infrastructure implementation depends on the application-owned contract, even though the runtime operation travels from the application to infrastructure.

## 4. Boundaries and Dependency Ownership

### 4.1 Boundary definition

A boundary separates components with different responsibilities and different reasons to change.

A well-defined boundary protects business rules from implementation details.

Examples include:

- Domain-to-application boundaries.
- Application-to-persistence boundaries.
- Application-to-payment boundaries.
- HTTP-to-application boundaries.
- Messaging-to-application boundaries.

Each boundary should expose an explicit contract.

### 4.2 Boundary crossing

Consider an HTTP request to place an order.

The controller receives an external request and converts it into an application command.

The application service executes the use case and communicates with its output ports.

The repository adapter converts the persistence request into a database operation.

The database returns stored information, which the adapter maps back into an application-compatible representation.

The application does not need to know about HTTP request objects, SQL statements, database connection pools, or payment-provider SDK classes.

### 4.3 The composition root

The composition root is the location where application dependencies are constructed and connected.

It is responsible for:

- Creating repository implementations.
- Creating payment adapters.
- Creating event publishers.
- Supplying these objects to application services.
- Managing configuration and application startup.

The Python implementation demonstrates constructor-based dependency injection.

The JavaScript implementation uses a `buildApplication()` function.

The Java implementation uses `ApplicationConfiguration`.

The composition root belongs near the application entry point and infrastructure configuration. It should not become a place where business rules are implemented.

## 5. Pulling the Architecture Together

The order-processing example has the following component relationships:

                 External Client
                       |
                       v
                 HTTP Controller
                       |
                       v
                Input Port
                       |
                       v
              PlaceOrder Use Case
                       |
             +---------+---------+
             |         |         |
             v         v         v
           Order   Repository  Payment
           Domain    Port       Port
                       |         |
                       v         v
                  Database    Payment
                   Adapter    Adapter
                       |         |
                       v         v
                  PostgreSQL  Provider

              Composition Root
                       |
                       v
              Dependency Injection


The diagram distinguishes two separate concerns:
- Source-code dependencies determine which modules know about other modules.
- Runtime collaboration determines which implementations execute an operation.
These relationships must not be confused.
6. Pull Requests and Architectural Boundaries
A Pull Request provides a workflow for proposing source-code changes.

In a Clean Architecture project, proposed changes can affect multiple boundaries.

For example, a developer might introduce a payment integration that directly imports a PostgreSQL repository into the domain package.

The proposed change may compile and pass ordinary unit tests while violating the intended dependency direction.

Architectural validation should therefore be part of the repository's development workflow.

A suitable review sequence includes:
1. Identify the changed components.
2. Identify newly introduced dependencies.
3. Verify that the application still depends on abstractions.
4. Verify that domain components do not depend on infrastructure.
5. Run automated architecture tests.
6. Review changes to public contracts.
7. Verify integration and application behavior.
The Pull Request is the change-proposal mechanism. Architectural validation is one of the quality controls applied to the proposed changes.
7. Code Review and Architecture Review
Code Review examines proposed source-code changes for correctness, maintainability, security, and consistency.

Architecture Review examines whether the changes preserve system-level design decisions.

These activities overlap but are not identical.
Review dimension	Primary concern
Functional correctness	Does the use case behave correctly?
Domain correctness	Are business rules enforced?
Dependency direction	Do source-code dependencies point inward?
Boundary integrity	Are component contracts respected?
Infrastructure isolation	Can infrastructure implementations change independently?
Testability	Can components be tested without unnecessary external dependencies?
Maintainability	Can responsibilities be understood and modified independently?

A review should identify whether a dependency is necessary, whether an abstraction is owned by the correct layer, and whether a concrete implementation has leaked across a boundary.
8. Approvals and Branch Protection
Approvals represent review decisions.

An approval indicates that an eligible reviewer accepts the proposed changes under the repository's review rules.

Approval does not independently prove that an architecture is valid.

For example, a Pull Request may have two approvals but still introduce a forbidden dependency.

Branch protection provides repository-level enforcement.

It can require:
- A minimum number of approvals.
- Successful automated tests.
- Successful architectural dependency checks.
- Resolution of review conversations.
- Restrictions on direct pushes.
- Restrictions on force pushes.
- Required merge methods.
An architecture-validation check can be integrated into continuous integration.

The distinction is:
Mechanism	Responsibility
Pull Request	Propose repository changes
Code Review	Evaluate proposed changes
Approval	Record reviewer decisions
Branch Protection	Enforce repository merge conditions
Architecture Test	Detect violations of architectural rules

A protected branch can prevent merging when the architecture-validation check fails.
9. Implementation Details
9.1 Python implementation
The Python script provides a runnable model of a Clean Architecture application.

Its main components are:
Component	Implementation
Domain entities	Order, OrderLine, Money
Domain states	OrderStatus
Application contracts	Protocol
Application services	PlaceOrder, CancelOrder
Persistence adapters	In-memory and JSON repositories
Payment adapter	SimulatedPaymentGateway
Event adapter	ConsoleEventPublisher
Dependency validator	ArchitectureValidator

Python's Protocol provides structural typing for the application ports.

A concrete repository does not need to inherit from a particular repository base class if it implements the required operations.

The architecture validator evaluates dependency relationships and detects circular dependencies through depth-first traversal.

The file adapter demonstrates persistence without requiring an external database package.

The demonstration includes successful payment, declined payment, invalid quantities, currency mismatches, and invalid state transitions.
9.2 JavaScript implementation
The JavaScript implementation provides an event-driven perspective.

Its principal features include:
- Classes for domain entities.
- Private fields for infrastructure state.
- Map for in-memory persistence.
- Set for idempotency tracking.
- Promises and asynchronous repository operations.
- EventEmitter for application events.
- Runtime contract validation.
- A policy engine for dependency evaluation.
JavaScript does not enforce interface implementation at compile time in the same way as Java.

The assertPort() function therefore validates the required operations when application dependencies are constructed.

The event publisher provides an example of event-driven communication.

The JSON repository demonstrates asynchronous file persistence and atomic replacement.

For production use, monetary calculations should use integer minor units or a decimal arithmetic implementation rather than relying on binary floating-point arithmetic.
9.3 C++17 implementation
The C++ implementation emphasizes explicit contracts, memory ownership, and domain modeling.

Its major components include:
- Money and OrderLine structures.
- Order domain entity.
- Abstract repository, payment, and event interfaces.
- Concrete in-memory adapters.
- PlaceOrderService.
- ArchitecturePolicy.
- DependencyGraph.
The interfaces use virtual functions and virtual destructors.

The application service receives dependencies through references. It does not own or construct the infrastructure implementations.

The dependency graph uses STL containers and depth-first traversal to identify circular dependencies.

Integer minor units represent monetary amounts, avoiding floating-point rounding errors.

Overflow checks protect monetary multiplication and addition.
9.4 Java 17 implementation
The Java implementation models an enterprise-oriented architecture.

It uses:
- Records for immutable value objects and commands.
- Interfaces for application ports.
- Classes for entities and application services.
- Collections for dependency management.
- Optional for repository lookup results.
- ConcurrentHashMap for thread-safe in-memory storage.
- Enum types for domain states and architectural layers.
- Explicit exception classes for failure classification.
The ApplicationConfiguration class acts as the composition root.

The application service receives repository, payment, and event-publishing abstractions through constructor injection.

The architecture policy evaluates dependency relationships independently of the order-processing workflow.

The cycle detector provides an additional architecture validation mechanism.
9.5 PostgreSQL implementation
The PostgreSQL script models architectural metadata and business transactions relationally.

Its principal tables include:
Table	Responsibility
architecture_projects	Architectural project identity
architecture_components	Components and their architectural layers
architecture_policies	Permitted dependency directions
component_dependencies	Source-code dependency relationships
application_ports	Application-facing contracts
adapter_implementations	Concrete port implementations
dependency_injections	Runtime dependency registrations
architecture_validation_runs	Validation execution history
architecture_violations	Detected architecture violations
orders	Order aggregates
order_items	Individual order lines
payments	Payment processing records
application_events	Transactional event records

The script uses foreign keys, unique constraints, check constraints, indexes, triggers, functions, procedures, views, and recursive queries.

The dependency-validation trigger rejects newly registered dependency relationships that violate the configured policy.

The validation procedure evaluates the existing dependency graph and stores its results.

The recursive dependency query identifies circular relationships.

The order-total trigger recalculates totals when order items change.

The payment procedure locks the relevant order row and processes its state transition.

The application event table demonstrates the database portion of the transactional outbox pattern.
10. Architectural Dependency Validation
Architecture validation is important because ordinary compilation does not establish that the dependency direction is correct.

A program can compile successfully while violating its intended architecture.

A dependency validator should examine:
- Module imports.
- Package references.
- Interface implementations.
- Runtime dependency registrations.
- Dependency cycles.
- Forbidden framework references.
- Infrastructure references inside domain components.
The supplied implementations demonstrate layer-level policy evaluation and graph-cycle detection.

The dependency rules are represented as a policy matrix.
Source layer	Domain	Application	Adapter	Infrastructure
Domain	Restricted	Forbidden	Forbidden	Forbidden
Application	Allowed	Allowed	Forbidden	Forbidden
Adapter	Allowed	Allowed	Restricted	Forbidden
Infrastructure	Allowed	Allowed	Allowed	Allowed

The matrix is an explicit project policy rather than a universal requirement of every Clean Architecture implementation.

For example, an application can legitimately contain application-level components that collaborate with other application-level components.

Similarly, adapter-to-adapter collaboration should be governed by explicit contracts rather than unrestricted imports.

A real architecture-validation system should distinguish:
1. Source-code dependency.
2. Interface implementation.
3. Runtime dependency injection.
4. Event-contract dependency.
These relationships have different architectural meanings.
11. Dependency Cycles
A circular dependency occurs when a component can reach itself through a sequence of dependency relationships.

Consider:
Domain
  |
  v
Application
  |
  v
Adapter
  |
  v
Domain


This arrangement introduces a cycle.

Circular dependencies make module initialization, independent testing, and component replacement more difficult.

The implementations use depth-first search with visited and active-node tracking.

The general complexity of graph traversal is:
- Time: O(V + E)
- Space: O(V)
Where:
- V represents the number of components.
- E represents the number of dependency relationships.
For large repositories, dependency graphs should be evaluated incrementally when possible.

A complete validation should also inspect transitive dependencies, because a forbidden relationship may exist several modules away from the original component.
12. State Management and Failure Handling
The order-processing example demonstrates explicit domain state transitions.
Current state	Operation	Result
PENDING	Successful payment	PAID
PENDING	Payment failure	CANCELLED
PENDING	Cancellation	CANCELLED
PAID	Ordinary cancellation	Rejected
CANCELLED	Direct reopening	Rejected

State transitions belong to the domain model.

The application service coordinates the workflow and persists the resulting state.

Infrastructure failures are translated into application-level failures where appropriate.

This separation prevents database-specific or provider-specific exceptions from becoming part of the domain contract.

A production distributed payment workflow requires additional controls:
- Idempotency keys.
- Payment reconciliation.
- Retry policies.
- Compensation operations.
- Transactional event publishing.
- Timeout handling.
- Observability and audit records.
A local database transaction cannot guarantee atomicity across an independent external payment provider.

For that reason, distributed workflows generally require explicit recovery mechanisms rather than assuming that a sequence of external calls behaves as one transaction.
13. Database Boundaries and the Transactional Outbox
The PostgreSQL implementation demonstrates a relational representation of application and domain responsibilities.

The database stores architectural metadata separately from order-processing data.

The architecture tables describe the software structure.

The business tables represent customer orders, items, payments, and events.

The transactional outbox pattern addresses the problem of publishing an event after a successful database transaction.

Without an outbox, an application could update an order successfully but fail before publishing the corresponding event.

The outbox records the event in the same database transaction as the business state change.

A separate dispatcher can publish unpublished events and record delivery progress.

Event consumers should be idempotent because message delivery may occur more than once.
14. Testing Strategy
Testing should be performed at multiple architectural levels.
Test category	What it verifies
Domain unit tests	Business rules and state transitions
Application unit tests	Use-case orchestration
Port contract tests	Expected adapter behavior
Adapter integration tests	Communication with databases and external services
Architecture tests	Dependency direction and boundary integrity
End-to-end tests	Complete application workflows
Failure tests	Recovery and exception behavior

Domain tests
Examples include:
- Negative monetary values are rejected.
- Currency mismatches are rejected.
- Zero quantities are rejected.
- Paid orders cannot be cancelled through the ordinary operation.
- Order totals are calculated correctly.
Application tests
Examples include:
- Successful payment produces a paid order.
- Failed payment produces a cancelled order.
- The repository receives the expected state.
- Events are published only after successful payment processing.
Architecture tests
Examples include:
- Domain modules do not import infrastructure packages.
- Application modules do not depend on concrete database implementations.
- Infrastructure adapters implement application-owned ports.
- Dependency graphs contain no forbidden cycles.
- Framework dependencies remain outside the domain.
Architecture tests should run automatically during the repository's continuous integration workflow.
15. Security Considerations
Clean Architecture improves the organization of security responsibilities, but architectural separation does not automatically make an application secure.

Important controls include:
- Validate external input before constructing domain objects.
- Apply authorization at the appropriate application boundary.
- Avoid exposing internal infrastructure exceptions to clients.
- Protect database credentials and payment-provider secrets.
- Use parameterized database operations.
- Apply least-privilege database permissions.
- Validate event payloads before processing.
- Avoid logging sensitive payment information.
- Use idempotency controls for payment requests.
- Restrict access to composition-root configuration.
The domain model should enforce business invariants even when requests originate from trusted internal components.

Security checks should not be bypassed merely because a request originates inside the application.
16. Performance Considerations
Architectural boundaries introduce some additional interfaces and translation operations. Their benefits should be balanced against actual application requirements.
Area	Consideration
Domain operations	Keep calculations independent of I/O
Repository access	Use appropriate indexes and bounded queries
Dependency injection	Construct long-lived dependencies once where appropriate
Event publishing	Use asynchronous delivery for external systems
Architecture validation	Cache or incrementally evaluate dependency metadata
Persistence	Avoid unnecessary repeated database writes
Serialization	Use bounded payloads and explicit contracts
Concurrency	Use optimistic or pessimistic locking according to workload

The architecture should not introduce unnecessary abstraction layers around every method.

An abstraction is useful when it protects a meaningful boundary, supports independent implementation, or provides a stable application contract.
17. Limitations and Design Trade-offs
The supplied implementations are executable architectural demonstrations rather than complete production commerce systems.

Their limitations include:
- In-memory repositories do not provide durable storage.
- JSON persistence does not provide multi-process transaction guarantees.
- Simulated payment gateways do not communicate with actual providers.
- The JavaScript monetary implementation is suitable only for controlled examples and should use exact decimal arithmetic in financial production systems.
- The architecture policy matrices represent configurable project rules.
- The database dependency model relies on registered component relationships.
- Runtime dependency injection is represented through metadata rather than a complete service container.
- Circular dependency detection does not replace source-code and build-system analysis.
- Distributed payment recovery requires stronger reconciliation and compensation workflows.
A production implementation should validate architecture against actual source-code imports and compiled dependency information, rather than relying exclusively on manually maintained metadata.
18. Practical Engineering Implications
The main benefit of Clean Architecture is not the number of layers or interfaces introduced into a project.

Its value comes from protecting business policies against unnecessary dependence on technical implementation choices.

A well-designed application can replace its database adapter, payment integration, HTTP framework, or event transport without rewriting its core business rules.

The most important design decisions are:
- Place business rules in the domain.
- Place workflow orchestration in application services.
- Let the application own its required ports.
- Implement those ports through external adapters.
- Construct concrete dependencies at the composition root.
- Validate architectural dependencies automatically.
- Treat database transactions and distributed operations as separate concerns.
- Preserve domain invariants independently of infrastructure behavior.
These principles establish a maintainable boundary between enterprise business policies and the technical systems that support them.
