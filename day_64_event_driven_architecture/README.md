# Event-Driven Architecture

## Scope

This project models an event-driven order-processing system across five implementations:

| File | Engineering perspective |
|---|---|
| Python | In-memory event bus, domain events, subscriptions, idempotent delivery, dead-letter handling |
| JavaScript | Asynchronous Node.js event broker using `EventEmitter`, Promises, Maps, Sets, and immutable event data |
| C++17 | Explicit repository-style domain modeling using STL containers, event subscriptions, failure isolation, and delivery tracking |
| Java 17 | Enterprise-oriented event model using records, interfaces, immutable payloads, service classes, and explicit domain validation |
| PostgreSQL | Persistent event, producer, consumer, subscription, delivery, and aggregate state model with functions and triggers |

The common scenario is an order service that publishes domain events without directly depending on the internal implementation of downstream consumers.

## Event-Driven Architecture

Event-driven architecture organizes distributed behavior around events representing facts that have occurred.

An event is a message such as `order.created`. It normally contains:

- a unique event identifier
- an event type
- an aggregate identifier
- event payload
- producer identity
- occurrence timestamp
- version information where ordering matters

The important architectural distinction is that an event represents a fact rather than a direct command to a specific implementation.

The basic relationship is:

`Order Service → Event → Event Broker → Multiple Consumers`

The producer publishes a fact. Consumers independently decide how to react to that fact.

## Events

The implementations use four domain event types:

| Event | Meaning |
|---|---|
| `order.created` | An order has been successfully created |
| `payment.authorized` | Payment authorization has completed |
| `order.confirmed` | The order has reached the confirmed state |
| `order.cancelled` | The order has been cancelled |

An event contains identity and context so that consumers can process it independently.

For example, an `order.created` event contains the order identifier, customer identifier, and amount.

The event does not contain implementation instructions for the notification service or payment service. This prevents the producer from becoming coupled to consumer internals.

## Producers

A producer creates and publishes events.

In the implementations, `OrderService` acts as the producer for `order.created`.

Its responsibility is:

1. Validate the order request.
2. Create the order state.
3. Construct the domain event.
4. Publish the event.

The producer does not need to know whether the event is consumed by:

- a payment service
- a notification service
- an analytics service
- an audit service

This is the primary decoupling mechanism.

## Consumers

A consumer subscribes to one or more event types and performs an independent operation.

The examples use several consumers.

### Payment Consumer

The payment consumer reacts to `order.created`.

Its responsibilities include:

- validating the payment amount
- authorizing payment
- maintaining idempotent authorization state

It does not modify the order producer's implementation.

### Notification Consumer

The notification consumer reacts to `order.created` and `order.confirmed`.

It converts events into notification records.

This consumer can be added or removed without changing the order service.

### Analytics Consumer

The analytics consumer subscribes to multiple event types.

It maintains event counts independently of transactional order processing.

This demonstrates that one event can support several independent business capabilities.

### Audit Consumer

The audit consumer records event identifiers.

Its introduction demonstrates the extensibility of an event-driven design.

The producer does not need new conditional logic when a new consumer is introduced.

## Decoupling

The main architectural benefit demonstrated by the implementations is temporal and structural decoupling.

A direct synchronous design could look like:

`Order Service → Payment Service → Notification Service → Analytics Service`

This creates direct dependencies between service implementations.

The event-driven model is:

`                    ┌→ Payment Consumer`
`Order Service → Event ├→ Notification Consumer`
`                    ├→ Analytics Consumer`
`                    └→ Audit Consumer`

The producer publishes one event while independent consumers react to it.

The producer therefore depends on the event contract rather than on consumer implementation details.

## Event Broker

The Python, JavaScript, C++, and Java implementations contain an in-memory event broker.

Its responsibilities are:

- accepting published events
- maintaining pending events
- finding subscribers
- dispatching events
- isolating consumer failures
- recording successful deliveries
- preventing duplicate delivery effects

The in-memory broker is intentionally smaller than a production messaging platform. Its purpose is to make the architecture and state transitions explicit.

A production broker would normally provide durable storage, delivery guarantees, partitioning, consumer groups, retry mechanisms, and operational monitoring.

## Event Delivery

Publishing and consuming are separate operations.

The producer places an event into the broker.

The broker later dispatches it to subscribed consumers.

This separation means that event publication does not require the producer to execute all downstream operations immediately.

The delivery flow is:

`Publish`
`   ↓`
`Queue`
`   ↓`
`Consumer Selection`
`   ↓`
`Consumer Processing`
`   ↓`
`Processed / Failed`
`   ↓`
`Retry or Dead Letter`

This separation is central to asynchronous event processing.

## Idempotency

Duplicate event delivery is a normal concern in distributed systems.

A consumer may receive the same event more than once because of:

- retries
- network failures
- consumer crashes
- broker redelivery
- acknowledgement failures

The source implementations track delivery identities using combinations such as:

`event_id + consumer_name`

This allows a consumer to recognize an already completed delivery.

Payment processing is especially important because duplicate processing could cause duplicate financial side effects.

Idempotency keys should be persisted in production rather than held only in process memory.

## Failure Handling

Consumer failure should not automatically invalidate unrelated consumers.

For example:

`order.created`
`   ├── payment-service → success`
`   ├── notification-service → success`
`   └── audit-service → failure`

The event itself remains valid even though one delivery failed.

The implementations record failed deliveries and demonstrate dead-letter behavior.

Production systems generally add:

- bounded retries
- exponential backoff
- retry classification
- dead-letter queues
- alerting
- operational dashboards
- manual replay procedures

Transient failures and permanent validation failures should be treated differently.

## Dead-Letter Handling

A dead-letter mechanism isolates events that cannot currently be processed successfully.

Typical causes include:

- malformed payloads
- unavailable downstream services
- exhausted retry attempts
- incompatible event versions
- permanent business validation failures

Dead-letter records should retain enough context to diagnose the failure.

Useful fields include:

- event identifier
- event type
- consumer
- attempt count
- failure reason
- first attempt timestamp
- last attempt timestamp

The PostgreSQL implementation models this information through `event_deliveries`.

## PostgreSQL Data Model

The SQL implementation separates event infrastructure into several relational entities.

| Table | Purpose |
|---|---|
| `repositories` | Represents the application domain owner |
| `event_types` | Defines recognized event names |
| `producers` | Identifies event-producing services |
| `consumers` | Identifies event-consuming services |
| `orders` | Stores transactional aggregate state |
| `events` | Stores published domain events |
| `subscriptions` | Defines which consumers receive which event types |
| `event_deliveries` | Tracks per-consumer processing state |

The core relationship is:

`Producer → Event → Subscription → Consumer → Delivery`

An event may therefore have many delivery records.

## Database Integrity

The PostgreSQL implementation uses:

- primary keys
- foreign keys
- unique constraints
- check constraints
- enumerated delivery states
- JSONB payload validation
- indexes
- triggers

For example, event versions are constrained by:

`UNIQUE (aggregate_id, version)`

This prevents two events from claiming the same version for one aggregate.

The payload trigger also ensures that an event payload is a JSON object.

## Transactional Processing

A database transaction groups related state changes.

The example demonstrates an order state transition followed by event publication.

Conceptually:

`BEGIN`
`  update order state`
`  publish domain event`
`COMMIT`

This protects local consistency.

In a production architecture, a simple database transaction is not sufficient when a separate external broker is involved. The transactional outbox pattern is commonly used to persist the business change and event record in the same database transaction before a relay publishes the event externally.

## Transactional Outbox Relationship

A durable architecture can use:

`Business Transaction`
`       ↓`
`Order State + Outbox Event`
`       ↓`
`Commit`
`       ↓`
`Event Relay`
`       ↓`
`Message Broker`
`       ↓`
`Consumers`

The outbox prevents the failure scenario in which the database commits successfully but the application crashes before publishing the corresponding event.

The PostgreSQL `events` table can serve as the durable event record in such a design, although a production implementation would normally distinguish the outbox state from the externally consumed event state.

## Event Ordering

Events for one aggregate can require ordering.

For an order:

`order.created → payment.authorized → order.confirmed`

If `order.confirmed` is processed before `order.created`, a consumer may observe an invalid business state.

Possible strategies include:

- aggregate version numbers
- broker partitions keyed by aggregate ID
- consumer-side sequence validation
- optimistic concurrency control

The PostgreSQL model uses `aggregate_id` and `version` to represent event sequencing.

Global ordering is generally expensive and unnecessary. Per-aggregate ordering is usually a more appropriate requirement.

## Delivery Semantics

Event systems can provide different delivery guarantees.

| Guarantee | Meaning |
|---|---|
| At-most-once | An event is delivered zero or one time |
| At-least-once | An event can be delivered multiple times but should not be lost after successful publication |
| Exactly-once effect | Duplicate deliveries may occur internally, but application state behaves as though processing occurred once |

The examples favor idempotent consumer behavior because at-least-once delivery is common in practical distributed systems.

Exactly-once processing across multiple independent systems is substantially harder than exactly-once local database transactions.

## Validation

The source implementations reject invalid input such as:

- empty customer identifiers
- empty producer names
- empty consumer names
- non-positive order amounts
- invalid event types
- missing payment amounts
- malformed payloads

Validation occurs before invalid state is propagated.

This is important because event-driven systems can amplify errors. A malformed event can otherwise reach many independent consumers.

## Security

Event payloads should contain only information required by consumers.

Sensitive information should not be published merely because it is available to the producer.

Important controls include:

- authentication of event publishers
- authorization of consumers
- encryption in transit
- encryption at rest
- secret management outside event payloads
- payload minimization
- audit logging
- schema validation
- access control on event topics
- retention policies

Event brokers can become highly valuable sources of operational and business information, so access should be treated as a security boundary.

## Schema Evolution

Event contracts change over time.

A producer may add a field while existing consumers still expect the earlier structure.

Backward-compatible changes are preferable.

Typical practices include:

- adding optional fields
- retaining existing field meaning
- explicit event versions
- consumer tolerance for unknown fields
- schema validation
- controlled deprecation

The PostgreSQL model includes an event `version` associated with an aggregate sequence. This is different from a full event-schema versioning strategy, which should be treated as a separate concern.

## Performance

The in-memory implementations use maps, sets, queues, and subscription indexes.

Typical operations are approximately:

- event enqueue: O(1)
- consumer lookup: O(1) average with hash-based structures
- delivery tracking: O(1) average with sets
- processing: O(E + D), where `E` is the number of events and `D` is the number of consumer deliveries

The C++ implementation uses STL containers for explicit control over storage and lookup behavior.

The JavaScript implementation uses `Map` and `Set` for efficient subscription and idempotency tracking.

The Java implementation uses typed collections and an `EnumMap` for event-type indexing.

The PostgreSQL implementation adds indexes on event type, status, aggregate identifiers, delivery status, and JSONB payloads.

## Asynchronous JavaScript Model

The JavaScript implementation uses Node.js `EventEmitter` together with asynchronous handlers.

The broker separates event publication from consumer execution.

Promises allow consumers to represent asynchronous work such as:

- network requests
- database operations
- remote service calls
- notification delivery

`Promise.all` allows independent consumers to execute concurrently.

A production implementation would also need bounded concurrency so that a large event burst does not exhaust memory, sockets, or downstream capacity.

## Enterprise Java Model

The Java implementation uses records for immutable domain values.

`DomainEvent` provides:

- event identity
- type
- aggregate identity
- immutable payload
- producer identity
- timestamp

The `EventHandler` interface separates the broker from consumer implementations.

Service classes model business responsibilities independently.

This structure makes it possible to replace the in-memory broker with a durable messaging implementation without changing the fundamental domain concepts.

## C++ Domain Model

The C++ implementation emphasizes explicit ownership and domain modeling.

The program uses:

- `enum class` for event types
- structs for domain values
- STL containers for state
- `std::function` for consumer handlers
- `std::set` for idempotency
- exceptions for invalid states

The implementation keeps the event lifecycle visible rather than hiding it behind a framework.

## Python Domain Model

The Python implementation uses:

- `dataclass` for event and order state
- `Enum` for event types
- dictionaries for aggregate state
- `deque` for pending events
- sets for idempotency
- callable handlers for subscriptions
- exceptions for invalid input

The Python version also demonstrates event serialization through JSON-compatible structures.

## Failure Scenarios

Important failure cases represented in the implementations include:

| Failure | Handling |
|---|---|
| Empty customer ID | Validation error |
| Non-positive amount | Validation error |
| Unknown event type | Rejected |
| Missing payment amount | Consumer failure |
| Downstream service unavailable | Failed delivery / dead letter |
| Duplicate delivery | Idempotency check |
| Inactive producer | PostgreSQL validation |
| Unknown consumer | PostgreSQL exception |
| Missing subscription delivery | PostgreSQL integrity check |

These states demonstrate that event-driven architecture is not simply a publish-subscribe API. Reliable systems require explicit state, validation, failure handling, and operational controls.

## Practical Workflow

A typical order workflow is:

`Customer Request`
`      ↓`
`Order Service`
`      ↓`
`Persist Order`
`      ↓`
`Publish order.created`
`      ↓`
`+-----------------------------+`
`|                             |`
`↓                             ↓`
`Payment Service        Notification Service`
`↓                             ↓`
`Authorization             Notification`
`|`
`↓`
`Payment Result`
`      ↓`
`Workflow Service`
`      ↓`
`order.confirmed`
`      ↓`
`Analytics / Notifications / Audit`

Each consumer can evolve independently as long as it continues to respect the event contract.

## Event-Driven Architecture vs Direct Calls

| Characteristic | Direct service call | Event-driven interaction |
|---|---|---|
| Coupling | Producer knows consumer interface | Producer knows event contract |
| Timing | Usually synchronous | Often asynchronous |
| Fan-out | Explicit calls | Multiple subscriptions |
| Failure propagation | Often immediate | Can be isolated |
| Retry | Usually caller-controlled | Consumer or broker controlled |
| Replay | Usually difficult | Possible with durable events |
| Ordering | Call sequence | Must be designed |
| Duplicate processing | Usually less visible | Must be expected |
| Operational complexity | Lower initially | Higher at distributed scale |

Event-driven architecture does not eliminate coupling. It changes the coupling from direct implementation dependencies toward event contracts, schemas, operational guarantees, and business semantics.

## Limitations of the Demonstrations

The Python, JavaScript, C++, and Java brokers are in-memory demonstrations.

They do not provide:

- durable broker storage
- distributed consumer groups
- cross-process delivery
- broker replication
- persistent replay
- network authentication
- distributed tracing
- production-grade retry scheduling

The PostgreSQL implementation provides persistent relational state but is not itself a complete distributed message broker.

A production architecture requires explicit decisions about broker durability, ordering, delivery semantics, schema governance, security, observability, and disaster recovery.

## Architectural Design Decisions

The implementations deliberately separate:

1. Event creation from event consumption.
2. Producers from consumer implementations.
3. Event publication from delivery.
4. Delivery tracking from aggregate state.
5. Validation from downstream processing.
6. Consumer failure from unrelated consumer execution.
7. Local database transactions from external broker delivery.
8. Event identity from aggregate identity.

These distinctions are necessary for understanding why event-driven architecture can scale across independently evolving services.

## Key Terminology

| Term | Meaning |
|---|---|
| Event | Immutable representation of a fact that occurred |
| Producer | Component that publishes an event |
| Consumer | Component that reacts to an event |
| Broker | Infrastructure that transports and manages events |
| Subscription | Relationship between a consumer and event type |
| Aggregate | Business entity whose state is represented by related events |
| Event ID | Unique identity of one event |
| Aggregate ID | Identity of the business entity associated with an event |
| Idempotency | Ability to process duplicate delivery without repeated side effects |
| Dead Letter | Failed message retained for investigation or later recovery |
| Event Version | Ordering or compatibility information associated with an event |
| Consumer Lag | Delay between event availability and consumer processing |
| Outbox | Durable record used to bridge local database transactions and external publication |

## Source File Relationship

The five implementations describe the same architectural principles from different engineering perspectives.

The Python implementation emphasizes clear simulation and domain behavior.

The JavaScript implementation emphasizes asynchronous event handling and Node.js event-driven execution.

The C++ implementation emphasizes explicit domain modeling, STL-based state management, and failure isolation.

The Java implementation emphasizes typed enterprise domain structures, immutable records, interfaces, and service boundaries.

The PostgreSQL implementation emphasizes persistent event infrastructure, relational integrity, delivery tracking, transaction handling, and queryable operational state.

The shared architecture is:

`Domain State`
`     ↓`
`Producer`
`     ↓`
`Event`
`     ↓`
`Broker / Persistent Event Store`
`     ↓`
`Subscription`
`     ↓`
`Consumer`
`     ↓`
`Consumer State`
`     ↓`
`Monitoring / Retry / Dead Letter`

This structure demonstrates the central relationship among events, producers, consumers, and decoupling while making reliability, validation, security, state management, and operational behavior explicit.
