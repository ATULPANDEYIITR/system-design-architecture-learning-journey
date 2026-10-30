# Queue Patterns: Point-to-Point and Competing Consumers

## 1. Scope

This project implements two related message-queue patterns:

- **Point-to-point messaging:** A producer places a message in a queue. The queue transfers that message to one consumer for processing.
- **Competing consumers:** Multiple independent workers retrieve messages from the same queue. Each available message is assigned to one worker at a time.

The patterns address different aspects of asynchronous processing. Point-to-point messaging defines the delivery relationship between a message and its consumer. Competing consumers define how several workers share the work arriving in that queue.

The implementations cover publication, message storage, delivery attempts, acknowledgement, rejection, retries, visibility timeouts, dead-letter handling, concurrent consumers, capacity restrictions, and idempotent processing.

The examples use an in-memory queue model. They demonstrate queue semantics and concurrency controls without claiming to provide the replication, persistence, distributed coordination, or fault tolerance of a production message broker.

## 2. Core Message-Queue Model

A queue separates the system that produces work from the systems that process it.

A producer publishes a message without needing to know which consumer will eventually process it. Consumers retrieve messages when they have capacity.

A typical message contains:

| Field | Purpose |
|---|---|
| Message identifier | Uniquely identifies one logical message |
| Payload | Contains the business data |
| Queue identifier | Identifies the destination queue |
| State | Records the current processing state |
| Attempt count | Tracks the number of deliveries |
| Consumer identifier | Identifies the current worker |
| Receipt | Identifies a particular delivery attempt |
| Lease deadline | Determines when an unacknowledged delivery expires |
| Error information | Records the most recent processing failure |

The distinction between a message identifier and a delivery receipt is important. A message identifier remains stable across retries. A receipt changes for each delivery attempt.

A worker must use the receipt belonging to its current delivery. An acknowledgement associated with an earlier attempt must not settle a newer delivery.

### 2.1 Message lifecycle

The implementations use four principal message states.

| State | Meaning |
|---|---|
| `READY` | The message is available for delivery |
| `IN_FLIGHT` | A consumer has received the message and holds an active lease |
| `ACKNOWLEDGED` | Processing was confirmed successfully |
| `DEAD_LETTERED` | The message exhausted its delivery policy or was rejected without requeueing |

The normal state transitions are:

`READY → IN_FLIGHT → ACKNOWLEDGED`

A failed delivery can follow this path:

`READY → IN_FLIGHT → READY → IN_FLIGHT`

When the retry policy is exhausted:

`READY → IN_FLIGHT → DEAD_LETTERED`

An acknowledged message is terminal in this model. A dead-lettered message is also terminal in its source queue. A separate dead-letter queue can hold a copy for investigation or controlled replay.

### 2.2 Delivery versus processing

Receiving a message does not mean that business processing succeeded.

A delivery indicates that a consumer obtained responsibility for attempting the work. The consumer must subsequently acknowledge or reject that delivery.

This distinction allows a queue to recover from a consumer that terminates unexpectedly. Without an acknowledgement mechanism, the queue cannot distinguish successful processing from a message that was merely retrieved.

## 3. Point-to-Point Messaging

Point-to-point messaging is a queue-based communication pattern in which each logical message is assigned to one consumer for a delivery attempt.

A producer can publish an order, payment instruction, shipment request, or report-generation task. The producer does not have to invoke the processing service directly.

A conceptual workflow is:

`Producer → Queue → Consumer → Business Operation → Acknowledgement`

The queue provides an intermediary between production and processing.

### 3.1 Publication

A producer creates a message and publishes it to a named queue.

The message should have a stable identifier and a validated payload. A production system should also define maximum payload size, serialization rules, retention policy, and duplicate-publication behavior.

The Python implementation validates JSON-compatible payloads and uses message identifiers to prevent duplicate identifiers in the same queue.

The JavaScript implementation validates serialization, payload size, and identifier uniqueness before inserting a message into its internal collection.

The C++ implementation rejects empty identifiers and payloads. It also enforces a bounded outstanding-message count.

The Java implementation represents each stored message as a domain object with an explicitly managed lifecycle.

The PostgreSQL implementation stores messages as `JSONB` records associated with a queue definition.

### 3.2 Retrieval and delivery

When a consumer requests a message, the queue selects one available message and changes its state to `IN_FLIGHT`.

The queue records:

- The consumer receiving the delivery.
- The delivery attempt number.
- A unique receipt.
- The lease expiration time.

A successful claim removes the message from the ready state. Other consumers must not receive the same active delivery.

### 3.3 Acknowledgement

An acknowledgement confirms that the current delivery was successfully processed.

The queue changes the message state to `ACKNOWLEDGED` and removes its active delivery ownership.

Acknowledgement should occur only after the business operation has reached its required durable completion point.

For example, a payment consumer should not acknowledge a payment instruction before the corresponding business transaction has been committed.

An acknowledgement sent before durable processing can cause permanent work loss. An acknowledgement sent after processing can result in duplicate execution if the consumer fails between the business commit and acknowledgement.

This is why acknowledgement and idempotency must be designed together.

### 3.4 Negative acknowledgement

A negative acknowledgement communicates that the consumer could not successfully process a delivery.

The implementation supports two outcomes:

| Decision | Result |
|---|---|
| Requeue | Return the message to `READY` when retry attempts remain |
| Do not requeue | Move the message to the dead-letter state |

The error reason is retained for operational investigation.

A transient network failure may justify requeueing. A permanently invalid business payload may justify immediate dead-letter routing.

Repeatedly retrying a message that cannot succeed wastes processing capacity and delays other work.

### 3.5 Visibility timeout

A visibility timeout is a temporary delivery lease.

After a consumer receives a message, the queue prevents other consumers from receiving it while the lease is active. The consumer is expected to acknowledge or reject the delivery before the deadline.

When the deadline expires without settlement, the queue recovers the message.

`IN_FLIGHT → READY`

The message can then be delivered to another worker.

Visibility timeouts protect against abandoned deliveries, but they do not guarantee that a message is processed only once. A worker may still be executing when the lease expires. Another worker can then receive the same logical message.

The timeout should therefore be designed around expected processing duration. Long-running tasks may require lease renewal or periodic visibility extension, which is not implemented in these examples.

## 4. Competing Consumers

Competing consumers use multiple workers to retrieve work from one shared queue.

Each worker requests the next available message. The queue assigns the message to one worker, subject to its delivery and locking rules.

A conceptual arrangement is:

`                    ┌─ Consumer A`
`Producer → Queue ───┼─ Consumer B`
`                    └─ Consumer C`

The diagram represents shared queue access. It does not represent message broadcasting.

If three workers are connected to the same point-to-point queue, one logical message is not intentionally copied to all three workers. Each delivery attempt is assigned to one consumer.

### 4.1 Work distribution

The queue distributes work according to message availability and consumer polling behavior.

A worker that finishes quickly can request another message sooner. A slower worker may process fewer messages.

The implementations use a shared ready collection and synchronized state transitions. A message is removed from the ready collection before its delivery is returned.

In the C++ implementation, a mutex protects queue state and condition variables coordinate waiting workers.

In Java, a `ReentrantLock` and `Condition` protect queue state and coordinate retrieval.

In PostgreSQL, `SELECT ... FOR UPDATE SKIP LOCKED` enables concurrent claim transactions to select different ready rows without waiting for another consumer's row lock.

These mechanisms prevent two consumers from claiming the same active message in the demonstrated in-memory or transactional model.

### 4.2 Throughput and concurrency

Adding workers can improve throughput when sufficient independent messages are available.

The useful number of consumers depends on more than the number of worker processes. It also depends on:

- Message arrival rate.
- Average processing time.
- Downstream service capacity.
- Database connection limits.
- Consumer concurrency.
- Queue polling and scheduling overhead.
- Retry frequency.
- Message ordering requirements.

Increasing worker count does not necessarily increase end-to-end throughput. If all workers compete for a limited database connection pool or invoke the same rate-limited API, additional consumers can increase contention without increasing completed work.

### 4.3 Work distribution is not strict fairness

A shared queue does not guarantee that every consumer receives the same number of messages.

Fast consumers may receive more work because they return to the queue more frequently. A worker that repeatedly requests messages may also receive a larger share of a burst.

The objective is generally effective work completion rather than equal assignment counts.

Where fair allocation is a strict requirement, a separate scheduling or partitioning policy is necessary.

### 4.4 Ordering

The examples use a ready queue and an enqueue-time ordering rule for initial publication.

Competing consumers can finish messages in a different order from the order in which messages were published.

For example:

- Consumer A receives message 1.
- Consumer B receives message 2.
- Consumer B completes message 2 first.
- Consumer A completes message 1 later.

The queue has maintained distinct delivery assignments, but processing completion order has changed.

Strict global ordering is difficult to combine with parallel processing. Applications requiring order should define whether ordering applies to publication, delivery, business completion, or a particular key.

A common design is to partition work by an entity key and preserve order within each partition. The implementations here do not provide partition-level ordering guarantees.

## 5. Acknowledgement, At-Least-Once Delivery, and Idempotency

### 5.1 At-least-once delivery

The queue model supports redelivery when a delivery remains unsettled beyond its visibility timeout.

This is an at-least-once delivery approach: a message can be delivered again when the queue cannot establish that the earlier attempt was settled.

At-least-once delivery is useful for recovering abandoned work, but consumers must tolerate duplicate delivery.

It should not be interpreted as exactly-once business execution.

### 5.2 The duplicate-processing problem

Consider the following sequence:

1. A consumer receives a payment message.
2. The consumer commits a payment update.
3. The consumer terminates before acknowledging the message.
4. The delivery lease expires.
5. Another consumer receives the same message.
6. The payment operation is attempted again.

The queue correctly recovered the unsettled delivery. The business operation may nevertheless have been executed twice.

This problem cannot be solved solely by assigning a different consumer to each delivery attempt.

### 5.3 Idempotent processing

An idempotent operation produces the same final business outcome when the same logical request is processed more than once.

The examples include an idempotency registry keyed by the stable message identifier.

The registry prevents the demonstration from applying a completed operation again.

For production systems, the business change and idempotency record should normally be committed within one durable database transaction.

A suitable relational design is:

- A table containing processed message identifiers.
- A unique constraint on the logical message identifier.
- A transaction that checks or inserts the identifier.
- The corresponding business update.
- A commit that makes both changes durable.

An in-memory set is suitable for demonstrating duplicate detection, but it is not durable across process restarts and does not coordinate independent application instances.

### 5.4 Receipt validation

A receipt identifies one delivery attempt.

Suppose message `M` is delivered first to Consumer A and later redelivered to Consumer B. The first receipt must not authorize Consumer A to acknowledge Consumer B's delivery.

The implementations generate a new receipt for each attempt and verify the receipt and consumer ownership before settlement.

This prevents a stale worker from settling a newer delivery.

## 6. Retry Policies and Dead-Letter Handling

### 6.1 Retry attempts

The maximum delivery-attempt count limits the number of times a message can be processed.

The count includes the initial delivery.

For a maximum attempt count of three, the sequence is:

| Attempt | Result |
|---:|---|
| 1 | Processing fails; message is requeued |
| 2 | Processing fails; message is requeued |
| 3 | Processing fails; message is dead-lettered |

A retry policy should distinguish temporary failures from permanent failures.

Examples of temporary failures include transient network errors, temporary downstream unavailability, or recoverable database contention.

Examples of permanent failures include invalid message structure, unsupported business states, and missing mandatory data.

A production implementation may include exponential backoff, randomized delay, error classification, and per-message retry policies. The supplied implementations use immediate requeueing to keep the state transitions explicit.

### 6.2 Dead-letter queue

A dead-letter queue stores messages that cannot continue through the normal processing path.

The dead-letter queue provides an operational boundary between normal traffic and messages requiring investigation.

Typical reasons include:

- Repeated processing failures.
- Exhausted delivery attempts.
- Invalid business data.
- Unsupported message versions.
- Explicit rejection without requeueing.

The PostgreSQL implementation retains the original message in the source queue with a `DEAD_LETTERED` state and creates a separate message in the configured dead-letter queue.

The Python, JavaScript, C++17, and Java 17 examples maintain dead-letter records within their in-memory queue models.

Dead-letter records should retain enough information for diagnosis: the original identifier, payload, attempt count, and failure reason.

A replay operation should be controlled. Replaying a message without correcting its original failure may create an endless failure cycle.

## 7. Queue Capacity and Backpressure

An unbounded queue can accumulate work faster than consumers can process it.

This creates increasing memory consumption, longer waiting times, and potential service instability.

The implementations enforce an outstanding-message capacity.

Outstanding work includes messages in `READY` and `IN_FLIGHT` states. Acknowledged and dead-lettered messages no longer consume this active capacity in the in-memory models.

When capacity is reached, publication is rejected rather than silently discarding a message.

A production publisher should respond to capacity failure through an explicit policy, such as:

- Retry with bounded delay.
- Return an error to the upstream service.
- Apply rate limiting.
- Temporarily stop accepting new work.
- Persist work in a separate durable staging system.

Capacity should be derived from expected message size, processing throughput, acceptable queue age, available storage, and downstream limits.

## 8. Python Implementation

The Python script models the queue lifecycle using standard-library types.

### 8.1 Domain representation

`MessageState` provides the valid lifecycle states.

`Message` stores mutable internal state, including attempts, active consumer, receipt, and lease deadline.

`Delivery` is a frozen dataclass representing a particular delivery attempt. Consumers receive a copy of the payload rather than direct access to the internal message object.

`QueueStatistics` provides a typed snapshot of queue state.

### 8.2 Queue operations

`PointToPointQueue` provides:

| Method | Function |
|---|---|
| `publish()` | Validates and inserts a message |
| `receive()` | Assigns one ready message to one consumer |
| `acknowledge()` | Settles a successful delivery |
| `reject()` | Requeues or dead-letters a failed delivery |
| `_expire_leases()` | Recovers deliveries past their visibility deadline |
| `statistics()` | Counts messages by state |
| `dead_letters()` | Returns dead-letter information |
| `close()` | Rejects new publication while retaining existing state |

A reentrant lock protects updates to the message dictionary, ready deque, and dead-letter collection.

The lock ensures that concurrent operations cannot independently claim or settle the same message state.

### 8.3 Validation and testing

The payload validator checks JSON serializability and applies a size limit.

The fake clock makes visibility-timeout behavior deterministic. Tests can advance time directly rather than waiting for real timeout intervals.

The assertion section checks capacity enforcement, redelivery, receipt validation, and dead-letter transitions.

### 8.4 Engineering limitation

The Python implementation is an in-memory simulation. Its lock provides thread safety within one process, not distributed coordination across multiple machines.

A production implementation would need durable storage, transactional publication and settlement, worker coordination, monitoring, and recovery after process failure.

## 9. JavaScript Implementation

The JavaScript implementation uses an event-driven queue model with asynchronous competing consumers.

### 9.1 Event-driven architecture

`PointToPointQueue` extends Node.js `EventEmitter`.

It emits events for:

| Event | Meaning |
|---|---|
| `published` | A message entered the queue |
| `delivered` | A consumer received a delivery |
| `acknowledged` | A delivery was successfully settled |
| `requeued` | A failed or expired delivery returned to the ready state |
| `dead-lettered` | The retry policy was exhausted or the delivery was rejected |
| `closed` | The queue stopped accepting publications |

These events provide a mechanism for connecting queue activity to logging, metrics, and operational monitoring.

### 9.2 Asynchronous consumers

`CompetingConsumer` represents one worker.

Its `run()` method repeatedly retrieves messages, invokes an asynchronous handler, and settles each delivery.

Independent consumer instances run through `Promise.all()`.

This allows the demonstration to execute multiple handlers concurrently without introducing an external npm dependency.

### 9.3 Payload handling

The queue serializes and parses payloads before storing them.

This restricts input to JSON-compatible data and prevents consumers from modifying the queue's internal object through shared references.

The `structuredClone()` operation also separates the returned payload from the internal message record.

### 9.4 Error handling

The worker catches processing errors and sends a negative acknowledgement.

The queue then decides whether the message should return to the ready collection or enter the dead-letter collection.

The example deliberately introduces a poison payment event to exercise this behavior.

### 9.5 Engineering limitation

The JavaScript implementation uses synchronous in-memory state transitions inside a single Node.js process. Its event loop makes each transition atomic with respect to other JavaScript callbacks when the transition contains no `await`.

This does not provide distributed locks or cross-process durability. A multi-instance deployment needs a shared broker or transactional storage service.

## 10. C++17 Implementation

The C++ program demonstrates a thread-safe bounded queue using standard-library concurrency primitives.

### 10.1 Data model

`MessageState` defines the message lifecycle.

`Delivery` carries the message identifier, payload, consumer identifier, receipt, and attempt count.

`QueueMetrics` contains counts of the principal message states.

`WorkQueue` owns the message map, ready deque, synchronization primitives, and capacity policy.

### 10.2 Concurrency controls

The implementation uses:

| Mechanism | Responsibility |
|---|---|
| `std::mutex` | Protects shared queue state |
| `std::condition_variable` | Coordinates waiting consumers |
| `std::unique_lock` | Allows controlled lock release while waiting |
| `std::deque` | Stores ready message identifiers |
| `std::unordered_map` | Stores message records |
| `std::thread` | Runs competing consumers |
| `std::optional` | Represents the absence of an available delivery |

The consumer threads call `receive()` against the same queue.

A successful retrieval changes the message to `InFlight` while the queue lock is held. Other consumers therefore cannot retrieve the same ready record during that state transition.

### 10.3 Bounded capacity

The queue tracks outstanding work and refuses publications when its configured capacity is reached.

Acknowledged and dead-lettered messages release outstanding capacity.

This avoids treating the internal message history as permanently active work.

### 10.4 Shutdown behavior

`close()` prevents new publications and wakes waiting consumers.

Workers continue to process existing work. They exit when the queue has been closed and outstanding work has reached zero.

The demonstration also exercises visibility-timeout recovery with a short lease and verifies that an obsolete receipt cannot acknowledge a newer delivery.

### 10.5 Engineering limitation

The C++ implementation is thread-safe within one process. It does not persist queue state across process termination.

A production system would also need a durable message store, cross-process consumer coordination, operational telemetry, and a defined shutdown policy for unfinished work.

## 11. Java 17 Implementation

The Java implementation uses explicit domain types and an enterprise-oriented service structure.

### 11.1 Domain types

The implementation uses Java records for immutable policy and data-transfer structures:

- `QueuePolicy`
- `Delivery`
- `DeadLetter`
- `QueueMetrics`

`MessageRecord` represents the mutable internal state of a stored message.

`MessageState` and `Settlement` separate message lifecycle status from the result of a consumer's settlement operation.

### 11.2 Queue service

`QueueService` centralizes message publication, delivery assignment, acknowledgement, rejection, lease recovery, and reporting.

The service uses a `ReentrantLock` to protect mutable queue state and a `Condition` to coordinate waiting consumers.

The message map preserves insertion order for the demonstration. The ready deque provides efficient removal from the front and insertion at the back.

### 11.3 Consumer abstraction

`MessageHandler` defines the processing contract.

`ConsumerWorker` implements the worker lifecycle without embedding a specific business operation in the queue service.

This separation allows different business handlers to use the same queue behavior.

The demonstration starts three workers through an `ExecutorService`.

### 11.4 Policy validation

`QueuePolicy` validates:

- Positive queue capacity.
- A positive maximum delivery-attempt count.
- A positive visibility timeout.

The queue service separately validates message identifiers, payload presence, duplicate identifiers, and active capacity.

### 11.5 Failure states

The worker handles exceptions from business processing by rejecting the active delivery.

A retryable failure moves the message back to `READY`. An exhausted failure moves it to `DEAD_LETTERED`.

The service also recovers an unsettled delivery when its lease expires.

The current example uses an in-memory concurrent idempotency registry. A production application should replace this with a durable, transactionally coordinated store.

## 12. PostgreSQL Data Model

The PostgreSQL script represents the queue as a relational system with explicit constraints and transactional operations.

### 12.1 Entity relationships

The main relationships are:

`Queue Definition`
`    └── Queue Messages`
`          ├── Delivery Attempts`
`          └── Dead-Letter Copies`

A delivery record references one message. A message may have multiple historical delivery attempts, but only one active delivery is permitted at a time.

### 12.2 Queue definition

`queue_definition` contains queue-level configuration.

| Column | Function |
|---|---|
| `queue_id` | Primary key |
| `queue_name` | Unique queue name |
| `max_delivery_attempts` | Maximum permitted delivery count |
| `visibility_timeout` | Active delivery lease duration |
| `max_outstanding` | Outstanding-message capacity |
| `dead_letter_queue_id` | Optional destination for dead-letter messages |

The queue can be configured independently of the messages it stores.

### 12.3 Message records

`queue_message` stores the payload and current message state.

`JSONB` supports structured message data while allowing PostgreSQL validation and query operations.

The table also stores the attempt count, enqueue time, availability time, optional deduplication key, failure reason, and original message reference for dead-letter copies.

A partial unique index ensures that a non-null deduplication key is unique within one queue.

### 12.4 Delivery history

`queue_delivery` represents individual delivery attempts rather than the logical message itself.

Each delivery has a unique UUID, consumer name, delivery timestamp, lease deadline, settlement timestamp, and outcome.

The partial unique index `uq_one_active_delivery_per_message` prevents multiple active delivery records for the same message.

Historical delivery records remain available after acknowledgement, requeueing, expiration, or dead-lettering.

### 12.5 Enqueue transaction

`enqueue_message()` performs the following operations:

1. Validates the JSON object.
2. Locks the queue definition row.
3. Checks for an existing deduplication key.
4. Counts outstanding messages.
5. Enforces queue capacity.
6. Inserts the message.

Locking the queue configuration row serializes capacity checks made by concurrent publishers for the same queue.

The function returns the existing identifier when a matching deduplication key is already present.

### 12.6 Competing-consumer claims

`claim_message()` uses a row-level locking query with `FOR UPDATE SKIP LOCKED`.

The behavior is important for concurrent consumers:

- A consumer selects one ready message.
- The row is locked inside the transaction.
- Other consumers skip that locked row.
- The selected message changes to `IN_FLIGHT`.
- A delivery record is created with a lease deadline.

The operation should be executed as a transaction. The default function execution already occurs within the calling SQL statement's transaction, and the caller should commit the claim before processing the message.

The claim function returns the message identifier, delivery identifier, payload, attempt count, and lease deadline.

### 12.7 Acknowledgement

`acknowledge_delivery()` verifies:

- The delivery exists.
- The supplied consumer owns it.
- The delivery remains active.
- The message is still in flight.
- The lease has not expired.

It then marks the delivery acknowledged and changes the message state.

The function rejects attempts to acknowledge an expired or previously settled delivery.

### 12.8 Negative acknowledgement

`nack_delivery()` implements retry and dead-letter behavior.

When requeueing is requested and attempts remain, the message returns to `READY`.

When requeueing is not requested or the retry limit has been reached, the original message enters `DEAD_LETTERED`.

If the source queue has a configured dead-letter destination, a copy is inserted into that queue. The `source_message_id` reference preserves the relationship between the original record and the copy.

### 12.9 Lease recovery

`recover_expired_deliveries()` identifies active deliveries whose lease has expired.

It locks candidate delivery records using `FOR UPDATE SKIP LOCKED` and delegates their settlement to `nack_delivery()`.

Messages with remaining attempts return to the ready state. Messages that have exhausted their attempts are dead-lettered.

A production deployment should run this recovery operation regularly, using a controlled scheduler or a dedicated maintenance worker.

### 12.10 Constraints, indexes, and reporting

The database applies constraints to message status, attempt count, queue capacity configuration, payload type, delivery outcome, and settlement timestamps.

The message-state trigger rejects invalid lifecycle transitions.

The principal indexes support:

- Retrieving ready messages by queue.
- Finding active deliveries whose leases have expired.
- Restricting duplicate active deliveries.
- Looking up delivery history by consumer.
- Enforcing per-queue deduplication keys.

The `queue_metrics` view reports ready, in-flight, acknowledged, and dead-lettered counts for each queue.

The reporting queries examine message states, delivery history, repeated attempts, dead-letter records, and queue age.

## 13. Comparison of the Five Implementations

| Implementation | Main mechanism | Concurrency model | Main engineering focus |
|---|---|---|---|
| Python | Dataclasses, dictionaries, deque, locks | Thread-safe in-process operations | Queue lifecycle simulation and deterministic testing |
| JavaScript | Classes, Maps, Sets, Promises, EventEmitter | Event-loop concurrency with asynchronous handlers | Event-driven competing consumers |
| C++17 | STL containers, mutex, condition variables, threads | Native concurrent worker threads | Bounded thread-safe queue |
| Java 17 | Records, enums, service classes, executor, locks | Managed worker pool | Explicit domain model and policy enforcement |
| PostgreSQL | Relational tables, functions, indexes, transactions | Transactional row-level locking | Persistent queue state and concurrent claims |

The implementations are deliberately not identical translations. Each emphasizes a different engineering aspect of message processing.

## 14. Performance Considerations

### 14.1 Retrieval complexity

The in-memory implementations use a ready deque for efficient removal from the front.

A typical retrieval from the ready collection is approximately constant time, excluding lease recovery and state lookup costs.

The current lease-recovery routines scan stored messages. Their cost is linear in the number of retained message records.

A production implementation would usually maintain an expiry-oriented structure or a separate indexed lease collection instead of repeatedly scanning all historical messages.

### 14.2 Contention

A single lock protects the in-memory queue state.

This is suitable for a learning model because it keeps message transitions consistent and easy to inspect.

Under heavy load, a single global lock can limit throughput. A production queue may use partitioned storage, multiple queue segments, or a broker designed to distribute state-management work.

### 14.3 Database retrieval

The PostgreSQL ready-message index supports queue-specific retrieval ordered by enqueue time and sequence identifier.

`SKIP LOCKED` allows independent claim transactions to progress without waiting for rows locked by other consumers.

The partial indexes reduce the indexed set to messages or delivery records relevant to a particular operational state.

Actual performance depends on table size, message-state distribution, transaction duration, index maintenance, and query plans.

### 14.4 Processing bottlenecks

Queue throughput is constrained by the slowest relevant part of the workflow.

Possible bottlenecks include:

- Database transaction duration.
- External API rate limits.
- CPU-intensive message processing.
- Large payload serialization.
- Queue lock contention.
- Retry storms.
- Unbalanced worker workloads.

Performance measurement should distinguish publication rate, delivery rate, processing rate, successful acknowledgement rate, retry rate, and dead-letter rate.

## 15. Security and Reliability Considerations

Queue messages may contain business-sensitive information. Message handling must follow the security requirements of the application.

Important controls include:

- Authenticate producers and consumers.
- Authorize publication and consumption by queue.
- Validate payload structure and size before processing.
- Avoid logging credentials, tokens, or unnecessary personal data.
- Encrypt message transport and persistent storage where required.
- Restrict administrative operations such as replay and purge.
- Protect receipt and acknowledgement operations from unauthorized access.
- Retain audit information for message settlement and dead-letter decisions.
- Apply retention and deletion policies to stored payloads.
- Use idempotency controls for operations with external side effects.

A receipt is a delivery capability. It should not be treated as a publicly exposed message identifier. Production systems should use unguessable receipts, authenticated connections, and server-side ownership checks.

The sample implementations generate unique receipts and verify the receipt against the active delivery, but they do not implement authentication, encryption, durable storage, or distributed authorization.

## 16. Failure Scenarios

| Failure | Queue behavior | Required application consideration |
|---|---|---|
| Consumer terminates before acknowledgement | Lease expires and message is redelivered | Make processing idempotent |
| Consumer processes a message but loses acknowledgement | Message may be delivered again | Commit business state and deduplication state transactionally |
| Downstream service is temporarily unavailable | Consumer can reject and requeue | Use bounded retries and suitable backoff |
| Message cannot pass validation | Message can be dead-lettered | Preserve diagnostic information |
| Queue reaches capacity | Publication is rejected | Apply upstream backpressure |
| Consumer uses an obsolete receipt | Settlement is rejected | Do not reuse receipts across attempts |
| Worker takes longer than its visibility timeout | Another worker may receive the message | Size or extend the visibility lease |
| Several consumers compete for one queue | Each claim receives an exclusive active assignment | Protect claim operations atomically |
| All consumers stop | Ready messages remain stored | Monitor queue age and worker availability |
| Dead-letter message is replayed without correction | The same failure may recur | Require controlled replay procedures |

## 17. Practical Design Boundaries

The point-to-point model is appropriate when each message represents one unit of work that should be processed by one consumer in a delivery attempt.

Competing consumers are appropriate when that work can be distributed across independent workers and parallel processing is beneficial.

Neither pattern, by itself, provides broadcast delivery to every subscriber. That is a different messaging requirement and would normally use a publish-subscribe model.

The implementations also do not claim to provide:

- Distributed replication.
- Broker clustering.
- Cross-region failover.
- Exactly-once business execution.
- Transactional coordination with arbitrary external services.
- Guaranteed global completion ordering.
- Dynamic consumer membership.
- Production authentication and authorization.
- Durable payload retention in the in-memory languages.

These boundaries matter because correct queue state transitions are necessary but not sufficient for a production messaging platform.

## 18. Execution Requirements

| File | Runtime or database | Execution |
|---|---|---|
| Python | Python 3.10 or later | Run the script directly with Python |
| JavaScript | Node.js 18 or later | Run the file with Node.js |
| C++17 | C++17-compatible compiler | Compile with thread support and execute |
| Java 17 | JDK 17 or later | Compile and run `QueuePatternsDemo` |
| PostgreSQL | PostgreSQL 13 or later | Execute the SQL script in a database session |

The Python, JavaScript, C++17, and Java 17 implementations use standard-library functionality and do not require third-party packages.

The PostgreSQL script drops and recreates the dedicated `queue_lab` schema. Existing objects under that schema will be removed when the script runs.
