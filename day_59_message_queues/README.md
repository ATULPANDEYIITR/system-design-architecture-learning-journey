# Message Queues: Producers, Consumers, and Brokers

## Scope

This project models a message-queue system in which producers publish messages to broker-managed queues and consumers receive, process, acknowledge, retry, or reject those messages.

The four primary roles are deliberately separated:

| Component | Responsibility |
|---|---|
| Producer | Creates and publishes messages |
| Broker | Stores, routes, delivers, and tracks messages |
| Queue | Provides ordered buffering and delivery state |
| Consumer | Receives messages and reports processing results |

The central workflow is:

Producer → Broker → Queue → Consumer → Acknowledge / Retry / Reject → Broker

A message queue is not simply a list of records. Reliable delivery requires state management, ownership of in-flight messages, acknowledgement semantics, retry handling, dead-letter handling, consumer limits, validation, and operational visibility.

## Core Concepts

### Producer

A producer is the component that creates messages.

A message normally contains:

- a unique identifier
- payload
- producer identity
- creation timestamp
- routing or business headers
- delivery-attempt information
- lifecycle state

The producer does not directly execute the consumer's business logic. It submits work to the broker.

The implementations use producer identities such as `checkout-service` and publish business events such as order creation and payment processing.

### Broker

The broker is responsible for coordinating message delivery.

The in-memory implementations maintain:

- queue definitions
- message records
- consumer registrations
- in-flight ownership
- acknowledgement state
- retry state
- dead-letter state

The PostgreSQL implementation persists these concerns relationally.

A broker provides an isolation boundary between message production and message consumption. A producer can publish work without requiring the consumer to be immediately available.

### Queue

A queue buffers messages until a consumer is ready.

The model distinguishes:

- `ready`: available for delivery
- `in_flight`: delivered but not yet settled
- `acked`: successfully processed
- `dead_lettered`: permanently removed from normal processing

This distinction prevents a message that has already been acknowledged from being accidentally processed as a new message.

### Consumer

A consumer is a worker that receives messages from a queue.

Consumers have a `prefetch` limit. Prefetch controls how many messages a consumer may own simultaneously.

A small prefetch value limits outstanding work and can reduce memory pressure. A larger value can improve throughput when processing has meaningful latency, but it can also increase the amount of work held by a slow consumer.

## Message Lifecycle

A typical message progresses through the following states:

    READY
      |
      v
    IN_FLIGHT
      |
      +------> ACKED
      |
      +------> READY
      |          |
      |          +---- retry
      |
      +------> DEAD_LETTERED
                 |
                 +---- operational investigation

`READY` means the broker may deliver the message.

`IN_FLIGHT` means a consumer owns the current delivery and has not yet completed it.

`ACKED` is a terminal successful state.

`DEAD_LETTERED` is a terminal failure state in these implementations. The message remains available for inspection without remaining in the normal processing queue.

## Acknowledgement and Retry

Acknowledgement is explicit.

A consumer acknowledges a message only after the relevant processing operation succeeds. This prevents the broker from treating an unfinished operation as successful.

A failed delivery can be retried:

1. Consumer receives the message.
2. Consumer processing fails.
3. Broker checks the attempt count.
4. The message returns to `READY` if retry attempts remain.
5. The consumer receives it again.
6. The message is dead-lettered after the configured attempt limit.

This approach prevents infinite retry loops.

The Python, JavaScript, C++17, Java 17, and PostgreSQL implementations all represent maximum attempts explicitly.

## Dead-Letter Handling

Dead-lettering is different from ordinary retry.

Retry means the system still believes the message may succeed later.

Dead-lettering means the message has reached a policy boundary or was explicitly rejected and should leave the normal processing path.

The examples dead-letter a message after three failed attempts.

Dead-letter records are operationally useful because they preserve failure information without allowing a poisoned message to consume worker capacity indefinitely.

## Idempotency

Message delivery systems can deliver a message more than once.

A consumer should therefore avoid assuming that one delivery corresponds to exactly one execution.

The Python and JavaScript implementations maintain processed business identifiers. If an already-completed order is delivered again, the handler recognizes the duplicate and acknowledges it without repeating the business operation.

Idempotency is especially important when the consumer performs an external side effect such as:

- charging a payment
- creating an order
- issuing a shipment
- sending a notification
- updating inventory

A message identifier alone may not always be sufficient. A business identifier such as `order_id` or `payment_id` can be used as an idempotency key when the business operation requires it.

## Python Implementation

The Python implementation is an executable in-memory broker simulation.

### Domain Model

The main types are:

- `Message`
- `Queue`
- `Consumer`
- `Broker`
- `MessageState`

`Message` is a dataclass containing identity, payload, headers, producer information, attempt count, and lifecycle state.

`Queue` uses a `deque` for ready messages and another `deque` for dead-lettered messages.

`Consumer` records its queue, handler, prefetch limit, and current in-flight message identifiers.

### Broker Operations

The `Broker` provides:

- queue declaration
- message publication
- consumer registration
- message delivery
- acknowledgement
- rejection
- retry
- dead-lettering
- polling
- queue statistics

The `poll_consumer` method connects delivery with application processing. A handler returning `True` acknowledges a message. A `False` result causes retry or dead-letter processing.

Exceptions raised by handlers are treated as failed deliveries rather than silently marking the message as successful.

### Python-Specific Design

Python dictionaries provide constant-average lookup for queues, messages, and consumers.

Sets provide efficient tracking of in-flight messages and processed business identifiers.

The implementation uses standard-library facilities only.

The example also uses assertions to verify final state:

- two messages are acknowledged
- one repeatedly failing message is dead-lettered
- no ready messages remain

## JavaScript Implementation

The JavaScript implementation models the broker as an event-driven Node.js component.

### Event-Driven Behavior

The `MessageBroker` extends `EventEmitter`.

Important events include:

- `queue.declared`
- `consumer.registered`
- `message.published`
- `message.delivered`
- `message.acknowledged`
- `message.requeued`
- `message.deadLettered`
- `consumer.error`

This separates core broker state transitions from operational observation.

A monitoring component could subscribe to these events without modifying the delivery logic.

### Asynchronous Consumers

Consumer handlers return promises.

The broker therefore supports asynchronous work such as network calls or database operations without requiring a third-party messaging package.

The `drain` method awaits the consumer handler before settling the message.

An exception during processing results in retry handling.

### JavaScript Data Structures

`Map` is used for queues, messages, and consumers.

`Set` tracks in-flight messages and processed business identifiers.

Objects hold message metadata and headers.

This creates a natural event-driven model while retaining explicit message ownership.

## C++17 Implementation

The C++ implementation treats the broker as a compact systems-engineering component.

### Architecture

The main structures are:

- `Message`
- `QueueDefinition`
- `Consumer`
- `Broker`

The `Broker` owns the system state.

Queues use `std::queue` for ready messages.

Consumers use `std::unordered_set` for in-flight ownership.

Messages and consumers are stored in `std::unordered_map`, providing efficient average-case lookup.

### Explicit Delivery Results

The C++ model defines:

- `Acknowledge`
- `Retry`
- `Reject`

as a separate `DeliveryResult` enum.

This makes settlement behavior explicit instead of encoding decisions as arbitrary boolean values.

The broker applies the result according to queue policy.

A retry is converted into a dead-letter transition when the maximum attempt count has been reached.

### Error Handling

Invalid queues, consumers, message ownership, payloads, and prefetch values produce exceptions.

Consumer handler exceptions are caught at the broker boundary and converted into retry behavior.

This prevents one failed handler execution from terminating the entire broker process.

## Java 17 Implementation

The Java implementation represents an enterprise-oriented message-processing service with explicit domain types.

### Records and Immutable Messages

`Message`, `QueuePolicy`, and `Consumer` are Java records.

Messages are immutable. State changes create a new message instance through methods such as `withDeliveryAttempt` and `withState`.

This prevents accidental mutation of message state from unrelated code.

### Service-Oriented Broker

`MessageBroker` provides the domain operations:

- declare queue
- publish message
- register consumer
- deliver message
- settle message
- process messages
- report queue state

The service explicitly separates delivery from settlement.

This is important because receiving a message is not equivalent to successfully processing it.

### Policy Modeling

`QueuePolicy` contains:

- queue name
- durability
- maximum attempts

`ReviewResult` represents consumer outcomes.

The broker uses these domain types to enforce state transitions instead of relying on unstructured strings.

### Streams

Java Streams are used for operational reporting and filtering messages by lifecycle state.

This provides a concise way to calculate acknowledged and in-flight counts without changing the underlying state model.

## PostgreSQL Implementation

The PostgreSQL implementation models the broker as a persistent relational system.

The schema is contained in the `messaging` namespace.

### Relational Model

The main relationships are:

    Broker
      |
      +-- Producer
      |
      +-- Queue
             |
             +-- Consumer
             |
             +-- Message
                    |
                    +-- Delivery
                           |
                           +-- Review Event

A dead-letter record references both the message and its originating queue.

### Broker and Producer

`broker` identifies the logical messaging infrastructure.

`producer` associates producers with a broker.

The unique constraint on `(broker_id, producer_name)` prevents duplicate producer identities within one broker.

### Queue

The `queue` table contains:

- durability
- maximum retry attempts
- queue identity
- broker ownership

The check constraint prevents invalid retry policies.

### Message

The `message` table contains:

- UUID message identifier
- queue
- producer
- JSONB payload
- optional message key
- state
- attempts
- timestamps

The payload is stored as `JSONB`, allowing structured event data while retaining PostgreSQL's indexing and querying capabilities.

### Delivery

A separate `delivery` table records individual delivery attempts.

This is important because one logical message can have multiple delivery attempts.

The unique constraint on `(message_id, delivery_attempt)` prevents duplicate attempt numbers for the same message.

Delivery history allows operational analysis of retries and consumer behavior.

### Dead Letters

`dead_letter` preserves messages that leave the normal queue-processing path.

The unique constraint on `message_id` prevents the same message from generating multiple dead-letter records.

## Concurrent Delivery

The PostgreSQL delivery function uses `FOR UPDATE SKIP LOCKED`.

The important behavior is:

1. Locate a ready message.
2. Lock the selected row.
3. Skip rows already locked by another worker.
4. Change the message to `in_flight`.
5. Increment its attempt count.
6. Create a delivery record.

This supports multiple workers competing for work without forcing every worker to wait on the same locked row.

This pattern is useful for database-backed worker queues where concurrent consumers need safe work claiming.

## Transactional Integrity

Message settlement is performed inside transaction boundaries.

A settlement operation changes both:

- the message state
- the delivery state

The dead-letter transition also creates a corresponding dead-letter record.

Keeping these operations transactional prevents a state in which the message says it is dead-lettered while the dead-letter record was never persisted.

## Database Constraints

The database enforces important invariants directly.

Examples include:

- queue names cannot be empty
- retry limits must be positive
- consumer prefetch values must be positive
- payloads must be JSON objects
- delivery attempts must be positive
- acknowledged messages require an acknowledgement timestamp
- producer names are unique within a broker
- queue names are unique within a broker
- consumer names are unique within a queue

Application validation remains useful, but database constraints protect the data even when another application writes to the same database.

## Indexing

The main operational index is:

`message(queue_id, state, created_at)`

It supports finding ready messages for a particular queue while retaining chronological ordering.

The partial delivery index on unsettled deliveries focuses on active work rather than historical deliveries.

The dead-letter index supports queue-specific operational inspection.

Indexes should be selected according to real query patterns. Excessive indexing increases write cost and storage requirements.

## Failure Modes

### Consumer Failure

A consumer can fail after receiving a message.

The message remains `in_flight` until the system explicitly settles it or a recovery mechanism handles the abandoned delivery.

Production systems generally require visibility timeouts, leases, consumer heartbeats, or broker-managed redelivery for this case.

### Repeated Processing Failure

A permanently failing message can otherwise create an endless retry loop.

The maximum-attempt policy converts repeated failures into a dead-letter state.

### Duplicate Delivery

A consumer may receive the same logical event more than once.

Business operations should therefore be designed for idempotency where duplicate side effects are possible.

### Slow Consumer

A consumer with insufficient processing capacity can accumulate work.

Prefetch limits reduce the amount of uncompleted work assigned to one consumer.

Operational monitoring should track queue depth, delivery latency, retry counts, and dead-letter volume.

### Producer Failure

A producer can publish successfully but fail before recording the result locally.

A production producer may therefore require a transactional outbox or another durable publication strategy when database changes and message publication must remain consistent.

## Reliability Considerations

A queue implementation can provide different delivery guarantees.

| Model | Meaning |
|---|---|
| At-most-once | A message is not intentionally redelivered, but loss can occur |
| At-least-once | Failed or uncertain deliveries may be repeated |
| Exactly-once effect | Requires application-level or infrastructure-level coordination to prevent duplicate side effects |

The implementations focus on at-least-once-style processing with explicit acknowledgement, retries, and dead-letter handling.

Exactly-once business effects should not be inferred merely from a queue's acknowledgement mechanism.

## Security Considerations

A production broker should enforce authentication and authorization around:

- publishing
- consuming
- queue creation
- queue administration
- dead-letter inspection
- configuration changes

Message payloads should be validated before processing.

Sensitive information should not be placed in headers or payloads unless required and appropriately protected.

Consumers should treat message content as untrusted input. Validation must occur before invoking business operations.

A broker should also restrict which producers can publish to particular queues and which consumers can consume from them.

## Performance Characteristics

For the in-memory implementations, queue insertion and removal are designed around efficient queue operations.

Hash-based maps provide average constant-time lookup for message, queue, and consumer identifiers.

The database implementation adds indexing and row-locking costs in exchange for persistence and transactional coordination.

The main scalability factors are:

- queue depth
- message size
- consumer concurrency
- prefetch size
- processing latency
- retry frequency
- dead-letter volume
- persistence cost

Increasing consumer count can improve throughput until another bottleneck becomes dominant.

Increasing prefetch can improve utilization but can also increase memory usage and the amount of work held by a slow worker.

## Relationship Between the Implementations

| File | Primary Perspective | Main Mechanism |
|---|---|---|
| Python | Simulation and domain behavior | Dataclasses, deque, sets, handlers |
| JavaScript | Event-driven processing | EventEmitter, promises, Maps, Sets |
| C++17 | Systems-oriented broker engine | STL containers, enums, explicit settlement |
| Java 17 | Enterprise domain model | Records, services, policies, streams |
| PostgreSQL | Persistent queue workflow | Relational state, functions, transactions, locking |

The implementations are intentionally related without being mechanical translations.

Python emphasizes readable state simulation.

JavaScript emphasizes asynchronous event handling.

C++17 emphasizes explicit systems-level ownership and control.

Java 17 emphasizes domain modeling and immutable state transitions.

PostgreSQL emphasizes persistence, relational integrity, concurrent work claiming, and transactional settlement.

## Practical Workflow

A realistic order-processing workflow represented by the artifacts is:

    Checkout Service
          |
          | publish order.created
          v
       Broker
          |
          v
       orders queue
          |
          +----------------+
          |                |
          v                v
    Worker 1          Worker 2
          |
          v
    Business Processing
          |
       +--+--+
       |     |
      ACK   RETRY
              |
              v
        Attempt Limit
              |
              v
        Dead-Letter Queue

The important boundaries remain explicit:

- publication creates proposed work
- queue state records available work
- delivery transfers temporary ownership
- consumer processing performs business work
- acknowledgement records successful completion
- retry returns recoverable failures to normal processing
- dead-lettering isolates unrecoverable messages
- broker policy controls delivery behavior
- persistence protects state across process boundaries

## Limitations

These implementations are educational broker models rather than replacements for production messaging infrastructure.

The in-memory implementations do not provide process-crash recovery.

The PostgreSQL implementation demonstrates durable relational queue mechanics but does not implement a complete distributed broker protocol.

Production deployments may require:

- connection management
- authentication and authorization
- encryption in transit
- visibility timeouts
- consumer heartbeats
- message expiration
- delayed delivery
- back-pressure
- partitioning
- replication
- monitoring
- alerting
- retention policies
- operational replay controls

The examples intentionally keep those concerns outside the core workflow so that producer behavior, broker responsibilities, consumer processing, acknowledgement, retry, and persistence remain distinguishable.
