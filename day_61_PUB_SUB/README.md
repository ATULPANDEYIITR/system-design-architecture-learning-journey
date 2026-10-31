# Pub/Sub: Topics, Subscribers, and Event Broadcasting

## Scope

This project models a publish/subscribe system in which producers publish events to named topics and independent subscribers receive events associated with those topics.

The four central domain objects are deliberately separated:

| Concept | Responsibility |
|---|---|
| Topic | Named routing channel for related events |
| Publisher | Produces an event without directly selecting consumers |
| Subscriber | Registers a handler for a topic |
| Broker | Maintains subscriptions and broadcasts events |

The core relationship is:

`Publisher → Topic → Broker → Subscribers → Event Handlers`

A topic is a routing boundary, not a subscriber. A subscriber may consume multiple topics, and one topic may have many subscribers.

## Pub/Sub Mechanics

A publication creates an event containing a topic, payload, identifier, and creation timestamp. The broker resolves the current subscriber set for that topic and attempts delivery independently for each subscriber.

This differs from direct point-to-point invocation. The publisher does not need to know which services consume the event.

A typical flow is:

`publish(topic, payload)`
→ validate topic and payload
→ create event
→ locate subscribers
→ deliver event
→ record delivery outcome
→ update subscriber failure state

The implementations use in-memory delivery for executable demonstrations. A production deployment would normally place durable events or delivery tasks in a broker or persistent queue.

## Topics

Topics provide logical event namespaces.

Examples used by the implementations include:

| Topic | Event purpose |
|---|---|
| `orders.created` | New order notification |
| `payments.completed` | Completed payment notification |
| `security.alert` | Security incident broadcasting |
| `inventory.updated` | Inventory state notification |

Topic validation prevents empty names, whitespace-containing names, and excessively long names.

A topic should represent a meaningful event category rather than an individual consumer. This preserves loose coupling between publishers and subscribers.

## Subscribers

A subscriber consists of an identifier and an event handler.

A subscription normally contains:

- Topic association
- Subscriber identity
- Handler or endpoint
- Failure policy
- Active or suspended state

The implementations reject duplicate subscriptions for the same subscriber and topic.

Subscriber isolation is important. If one handler fails, the broker continues attempting delivery to other subscribers. This prevents one unhealthy consumer from suppressing unrelated consumers.

Repeated failures can suspend a subscriber. The Python, C++, JavaScript, and Java implementations all model this behavior, although their execution mechanisms differ.

## Event Broadcasting

Broadcasting means that a single published event can be delivered to every eligible subscriber of its topic.

For example:

`orders.created`
→ `audit-service`
→ `analytics-service`
→ `notification-service`

The publisher performs one publication operation. The broker performs the fan-out.

The event payload is treated as data rather than executable content. The Python implementation copies dictionary payloads, JavaScript clones structured objects, Java records defensively copy attribute maps, and PostgreSQL stores structured payloads in `JSONB`.

## Python Implementation

The Python implementation is an in-memory broker centered on `PubSubBroker`, `Subscriber`, and immutable `Event` data.

### Main mechanisms

- `dataclass` represents event and delivery records.
- `Enum` represents delivery states.
- `defaultdict` organizes subscribers by topic.
- `deque` provides bounded event history.
- `RLock` protects broker state.
- Callable handlers represent subscriber behavior.
- Exceptions are isolated at the subscriber boundary.
- Repeated failures deactivate a subscriber.
- Retained events can be replayed to a subscribed consumer.

The broker copies the subscriber list before executing callbacks. This avoids holding the broker lock while application code runs.

The example models audit, analytics, and risk consumers for transaction events. A failing risk consumer does not prevent audit and analytics delivery.

### Failure handling

A handler failure increments its failure count. Once the configured threshold is reached, the subscriber becomes inactive.

This is intentionally different from silently discarding an error. The delivery result records `delivered`, `failed`, or `skipped`.

### Performance

Topic lookup is approximately `O(1)` for dictionary access. Delivery is `O(S)` for `S` subscribers on the selected topic. Retained-history replay is `O(H)` for `H` retained events.

The bounded history prevents unlimited in-memory growth.

## JavaScript Implementation

The JavaScript implementation uses an event-driven Node.js design.

### Main mechanisms

- `Map` stores topics and subscribers.
- `Set`-like uniqueness is represented through subscriber IDs in a `Map`.
- `Promise` supports asynchronous handlers.
- `Promise.all` coordinates concurrent worker execution.
- `EventEmitter` emits broker lifecycle events.
- `structuredClone` protects the stored event payload from direct mutation.
- A bounded history array provides replay support.
- Failure thresholds suspend unhealthy consumers.

The broker also limits concurrent deliveries through a worker count. This prevents a very large subscriber set from creating an unrestricted number of simultaneous asynchronous operations.

### Event-driven behavior

The broker emits internal events such as:

`subscribed`

`unsubscribed`

`published`

These events are separate from topic delivery. They represent broker observability rather than application-level topic messages.

### Failure isolation

`Promise` rejection from one subscriber is converted into a delivery result. Other subscribers continue independently.

This is particularly important for asynchronous systems because a slow or failed downstream service should not automatically cancel all fan-out operations.

## C++17 Implementation

The C++ program models a security-alert broadcasting system.

The domain contains:

- `Event`
- `Subscriber`
- `DeliveryResult`
- `Broker`
- Delivery and subscriber-state enums

The broker uses `unordered_map` for topic lookup and `map` for deterministic subscriber ordering.

A security alert is broadcast to:

- SOC dashboard
- Incident database
- Notification gateway

The notification gateway has a failure threshold. Repeated notification failures move the subscriber to a suspended state.

### Architectural decision

Callbacks execute outside any global broker synchronization mechanism. This avoids making the broker depend on the execution time of arbitrary subscriber code.

The implementation is intentionally synchronous at the callback boundary. A production implementation could place events into worker queues for asynchronous processing.

### Complexity

Topic lookup is approximately `O(1)` average using `unordered_map`.

Delivery is `O(S log S)` in the selected topic because subscribers are stored in an ordered `map`.

Retained-history filtering is `O(H)`.

## Java 17 Implementation

The Java implementation models enterprise payment-event distribution.

The domain is explicitly separated into:

- `Event`
- `SubscriberPolicy`
- `Subscription`
- `EventHandler`
- `PubSubBroker`
- `DeliveryResult`
- State enums

Java records are used for immutable event-oriented data. The `Event` record defensively copies its attribute map, preventing callers from changing the stored event through an external mutable reference.

### Service behavior

A payment completion is sent to:

- Ledger service
- Fraud service
- Notification service

The fraud service applies a domain-specific failure condition for high-value payments. Its failure policy allows two failures before suspension.

The broker copies subscription state under synchronization and performs handler execution through an executor outside the synchronized state-management section.

### Enterprise-oriented design

The separation between `SubscriberPolicy`, `Subscription`, and `PubSubBroker` keeps policy configuration distinct from routing.

This allows the failure threshold to be changed without changing event routing logic.

The executor also provides a controlled concurrency boundary. An enterprise implementation could replace it with a durable message queue and independently scalable consumer workers.

## PostgreSQL Data Model

The PostgreSQL implementation treats Pub/Sub as a durable relational workflow.

The principal tables are:

| Table | Purpose |
|---|---|
| `topic` | Defines event channels |
| `subscriber` | Defines consumers and failure state |
| `subscription` | Maps subscribers to topics |
| `event` | Stores published events |
| `delivery` | Records delivery obligations and outcomes |
| `status_check` | Stores event validation results |

The relationship is:

`topic`
→ `subscription`
→ `subscriber`

and:

`topic`
→ `event`
→ `delivery`
→ `subscription`

This separates the event itself from its delivery to individual consumers.

## PostgreSQL Constraints

The schema uses database-level validation for important invariants.

Examples include:

- Topic names cannot be empty.
- Topic names cannot contain whitespace.
- Subscriber failure limits must be positive.
- Event payloads must be JSON objects.
- Subscription pairs are unique.
- Delivery attempts must be positive.
- Failed deliveries must contain an error message.

The database therefore rejects invalid states even if an application layer contains a defect.

## PostgreSQL Functions and Triggers

`ensure_active_topic()` prevents new events from being inserted for inactive topics.

`validate_delivery_state()` maintains consistency between delivery state, error messages, and delivery timestamps.

`record_delivery_failure()` increments a subscriber's failure count and suspends the subscriber when the configured threshold is reached.

`reset_delivery_failures()` restores an eligible subscriber to an active state and clears its failure counter.

`publish_event()` validates the target topic and payload, creates a durable event identifier, and establishes delivery records.

The database records the durable routing obligation. Actual network delivery should be handled by a worker process rather than by a SQL trigger.

## Transactional Integrity

The sample publication workflow uses a transaction:

`BEGIN`
→ create event
→ establish related records
→ validate transaction
→ `COMMIT`

If an operation fails before commit, PostgreSQL can roll back the complete transaction.

This matters because an event should not appear partially created with inconsistent routing records.

## Event History and Replay

The Python, JavaScript, C++, and Java implementations retain bounded in-memory history.

The PostgreSQL implementation persists events in the `event` table.

Persistent event history supports auditing, operational investigation, and replay-oriented workflows. A production replay mechanism should also define idempotency behavior because delivering an event twice may produce duplicate side effects.

A common protection is an event identifier combined with a consumer-specific processing record.

## Delivery Semantics

The implementations demonstrate a consumer-oriented delivery model rather than claiming exactly-once network delivery.

A useful distinction is:

| Property | Meaning |
|---|---|
| At-most-once | Event may be lost, but is not intentionally retried |
| At-least-once | Failed delivery can be retried, so duplicates are possible |
| Exactly-once effect | Consumer processing is designed so repeated delivery has one logical effect |

The examples record event identifiers and delivery outcomes, which provides a foundation for idempotent processing.

Exactly-once effects cannot be inferred merely from storing an event in memory or a database.

## Failure Modes

Important Pub/Sub failure cases include:

### Invalid topic

The broker rejects an empty, malformed, or whitespace-containing topic.

### Duplicate subscription

The same subscriber cannot be registered twice for the same topic.

### Consumer failure

A subscriber handler can fail without cancelling unrelated deliveries.

### Repeated consumer failure

The subscriber can be suspended after a configurable number of failures.

### No subscribers

The event can still exist without active consumers. This is useful when event persistence and later replay are supported.

### Slow consumer

A synchronous implementation can block publication. The JavaScript and Java implementations address this through asynchronous execution and bounded worker concurrency.

### Duplicate processing

A retrying consumer may process the same event more than once. Event identifiers should therefore participate in consumer-side idempotency.

## Security Considerations

A real Pub/Sub platform should enforce controls beyond the in-memory demonstrations.

Important controls include:

- Authenticate publishers.
- Authenticate subscribers.
- Authorize access to individual topics.
- Restrict sensitive event payloads.
- Validate payload schemas.
- Encrypt event traffic in transit.
- Encrypt persistent event data where required.
- Avoid placing secrets in event payloads.
- Limit payload size.
- Rate-limit abusive publishers.
- Record security-relevant publication and subscription activity.
- Prevent one tenant from subscribing to another tenant's topics.

Topic names are routing identifiers, not authorization boundaries. Authorization must be enforced separately.

## Operational Considerations

A production broker must address concerns not fully represented by the self-contained programs:

- Durable message storage
- Consumer offsets
- Retry queues
- Dead-letter queues
- Back-pressure
- Consumer concurrency
- Ordering guarantees
- Partitioning
- Schema evolution
- Observability
- Authentication and authorization
- Retention policies
- Disaster recovery

Ordering should be specified explicitly. Global ordering is expensive and can reduce scalability. Many systems instead guarantee ordering only within a topic partition or entity key.

## Performance Model

For a topic with `S` subscribers, direct fan-out requires approximately `O(S)` delivery operations per event.

For retained history containing `H` events, replay is approximately `O(H)` when scanning a topic's retained history.

The PostgreSQL indexes focus on common access paths:

- Events by topic and publication time
- Deliveries by event
- Failed deliveries by subscription
- Subscriptions by subscriber

Indexes should correspond to actual query patterns because each additional index increases write and storage cost.

## Conceptual Architecture

`Producer`
  
`│`
  
`▼`
  
`Topic`
  
`│`
  
`▼`
  
`Pub/Sub Broker`
  
`├── Subscriber A`
  
`├── Subscriber B`
  
`├── Subscriber C`
  
`└── Subscriber N`

For a durable architecture:

`Producer`
→ `Topic`
→ `Durable Event Store / Broker`
→ `Consumer Queue`
→ `Subscriber`
→ `Processing Record`

The central design principle is separation of publication from consumption. Publishers produce events to topics; subscribers decide what they consume; the broker manages routing; delivery state records what happened during processing.
