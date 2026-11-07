# Service Communication: REST, gRPC, and Messaging

## 1. Technical Scope

Service communication defines how independently deployed software components exchange requests, responses, commands, and events.

This implementation examines three communication approaches:

| Characteristic | REST | gRPC | Messaging |
|---|---|---|---|
| Communication model | Request/response | Remote procedure call | Asynchronous message exchange |
| Typical transport | HTTP | HTTP/2 | Broker-dependent |
| Data representation | Usually JSON | Usually Protocol Buffers | JSON, binary, or other formats |
| Contract | Resource and HTTP contract | Service and method contract | Event and message schema |
| Coupling | Resource-oriented | Interface-oriented | Producer and consumer contracts |
| Response behavior | Usually immediate | Usually immediate | Independent of consumer execution |
| Delivery | HTTP request handling | RPC invocation | Broker-managed delivery |
| Typical application | Public and internal APIs | Low-latency service calls | Event-driven workflows |

The implementations use standard language features to model these mechanisms without requiring external networking libraries, generated Protocol Buffer classes, or message-broker installations.

The REST implementations demonstrate actual local HTTP communication in Python and JavaScript. The RPC implementations demonstrate typed invocation and status handling. Messaging implementations demonstrate broker behavior through in-memory queues.

The C++ and Java programs provide domain-oriented simulations.

The PostgreSQL implementation models communication contracts and persistent operational state.

## 2. REST: Resource-Oriented Communication

### 2.1 Architectural Model

REST stands for Representational State Transfer. It organizes communication around resources identified by URLs.

A product service can expose resources such as:

| Method | Endpoint | Purpose | Typical response |
|---|---|---|---|
| GET | `/products` | Retrieve products | 200 |
| GET | `/products/101` | Retrieve one product | 200 or 404 |
| POST | `/products` | Create a product | 201 |
| PUT | `/products/101` | Replace a product | 200 |
| PATCH | `/products/101` | Partially update a product | 200 |
| DELETE | `/products/101` | Delete a product | 204 |

HTTP methods communicate the intended operation.

Important distinctions:

- GET retrieves a representation.
- POST submits data for processing or resource creation.
- PUT replaces a resource representation.
- PATCH applies partial modifications.
- DELETE requests resource removal.

### 2.2 HTTP Request and Response

A REST request contains:

- HTTP method.
- Resource URL.
- Headers.
- Optional request body.
- Authentication credentials.
- Optional correlation and idempotency identifiers.

A response contains:

- HTTP status.
- Response headers.
- Optional response body.
- Error information where appropriate.

The Python and JavaScript implementations use JSON request and response bodies.

The Python implementation uses `http.server`, `urllib.request`, and `json`.

The JavaScript implementation uses Node.js `http`, `fetch`, and asynchronous request-body processing.

Both implementations include:

- Product retrieval.
- Product creation.
- Input validation.
- JSON parsing.
- Request-size restrictions.
- Appropriate HTTP status codes.
- Missing-resource handling.
- Request timeouts on the client side.

### 2.3 HTTP Status Codes

| Status | Meaning | Application |
|---|---|---|
| 200 | OK | Successful retrieval |
| 201 | Created | Successful creation |
| 204 | No Content | Successful operation without a response body |
| 400 | Bad Request | Invalid input |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Missing resource |
| 409 | Conflict | Conflicting resource state |
| 413 | Content Too Large | Request exceeds size limits |
| 415 | Unsupported Media Type | Unsupported content format |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Unexpected server failure |
| 502 | Bad Gateway | Invalid upstream response |
| 503 | Service Unavailable | Temporarily unavailable service |
| 504 | Gateway Timeout | Upstream request timed out |

An HTTP status communicates the outcome of the HTTP operation. It should not be confused with application-specific error details.

### 2.4 REST Idempotency

An operation is idempotent when repeating the same request produces the same intended state.

GET, PUT, and DELETE are defined as idempotent methods in HTTP semantics. POST is not inherently idempotent.

For example, repeatedly submitting an order-creation request can create multiple orders.

An idempotency key allows an application to identify repeated submissions.

A robust implementation should:

- Associate the key with the authenticated caller.
- Associate it with the operation.
- Persist the original outcome.
- Reject reuse with incompatible request data.
- Apply a defined retention period.

The PostgreSQL `rest_requests` table includes an idempotency key and a unique index to prevent duplicate registrations for the same endpoint and key.

### 2.5 REST Security and Performance

Production REST services should consider:

- TLS encryption.
- OAuth 2.0 or other appropriate authentication mechanisms.
- Authorization at resource and operation levels.
- Request validation.
- Maximum request-body size.
- Rate limiting.
- Timeouts.
- Pagination.
- Cache-control policies.
- Structured error responses.
- Correlation identifiers.
- API version compatibility.

The Python and JavaScript demonstrations bind their servers to the local loopback interface. They do not provide production authentication or TLS termination.

The communication policy models mandatory authentication and encryption as deployment requirements.

## 3. gRPC: Typed Remote Procedure Calls

### 3.1 Architectural Model

gRPC is a remote procedure call framework.

It allows one service to invoke a method exposed by another service through a defined service contract.

For example:

- Caller: Order Service.
- Destination: Product Service.
- Service: `ProductService`.
- Method: `GetProduct`.
- Request: `GetProductRequest`.
- Response: `GetProductResponse`.

Unlike REST, which emphasizes resources and HTTP methods, gRPC emphasizes service methods and typed messages.

### 3.2 Protocol Buffers

Protocol Buffers define structured message contracts.

A typical product contract contains:

| Field | Type | Purpose |
|---|---|---|
| product_id | int64 | Product identifier |
| name | string | Product name |
| price | double | Product price |

A gRPC interface can define:

- Service names.
- Method names.
- Request message types.
- Response message types.
- Streaming behavior.
- Field numbers.
- Contract versions.

Protocol Buffers use field numbers to identify serialized fields. Field numbers should remain stable because they affect wire compatibility.

The PostgreSQL implementation records service and method contracts through `grpc_services` and `grpc_methods`.

### 3.3 HTTP/2 and RPC Communication

gRPC normally uses HTTP/2.

Important characteristics include:

- Binary message framing.
- Multiplexed streams.
- Header compression.
- Bidirectional communication.
- Flow control.
- Streaming RPC support.

The main RPC patterns are:

| Pattern | Description |
|---|---|
| Unary | One request and one response |
| Server streaming | One request and multiple responses |
| Client streaming | Multiple requests and one response |
| Bidirectional streaming | Both sides exchange multiple messages |

The SQL contract tables include client-streaming and server-streaming flags.

### 3.4 RPC Status Codes

gRPC defines its own status model.

| Status | Meaning |
|---|---|
| OK | Successful invocation |
| INVALID_ARGUMENT | Invalid request |
| NOT_FOUND | Requested resource unavailable |
| ALREADY_EXISTS | Resource already exists |
| PERMISSION_DENIED | Operation not permitted |
| UNAUTHENTICATED | Authentication required |
| RESOURCE_EXHAUSTED | Resource limit exceeded |
| DEADLINE_EXCEEDED | Invocation exceeded its deadline |
| UNAVAILABLE | Service unavailable |
| INTERNAL | Internal processing failure |

RPC status codes describe the outcome of a remote method invocation.

They are distinct from HTTP response status codes, even though gRPC uses HTTP/2 as its transport.

### 3.5 Deadlines and Failure Handling

A deadline specifies the maximum time allowed for an RPC operation.

A caller should not wait indefinitely for a remote service.

The Java implementation uses `CompletableFuture` and `orTimeout()` to model deadline-aware invocation.

The Python implementation uses a timeout-aware RPC client simulation.

The C++ implementation separates the RPC request, service, response, and status types.

The implementations distinguish:

- Invalid requests.
- Missing resources.
- Internal errors.
- Unavailable services.
- Deadline failures.

A real gRPC deployment additionally requires generated stubs, a Protocol Buffers contract, an HTTP/2 transport, and appropriate channel configuration.

The RPC examples in these files are executable typed simulations, not wire-compatible gRPC servers.

### 3.6 When gRPC Is Appropriate

gRPC is useful when:

- Services have strongly defined interfaces.
- Internal service communication requires efficient serialization.
- Streaming is required.
- Multiple programming languages must share a contract.
- Explicit deadlines and status codes are important.
- Service-to-service communication needs generated client and server interfaces.

It introduces requirements around schema evolution, generated code, channel lifecycle, HTTP/2 configuration, and observability.

## 4. Messaging: Asynchronous Communication

### 4.1 Architectural Model

Messaging allows a producer to publish a message without requiring the consumer to process it immediately.

A message broker receives messages and makes them available to consumers.

The producer and consumer can operate independently.

Example:

1. Order Service creates an order.
2. Order Service publishes an `OrderCreated` event.
3. Inventory Service receives the event.
4. Inventory Service reserves stock.
5. Payment Service processes the payment request.
6. Order Service receives the resulting events.

This separates event production from event consumption.

### 4.2 Queue-Based Communication

A queue stores messages until consumers process them.

Important components include:

- Producer.
- Broker.
- Queue.
- Consumer.
- Message identifier.
- Delivery acknowledgement.
- Retry mechanism.
- Dead-letter queue.

A message can move through the following states:

`PENDING → PROCESSING → ACKNOWLEDGED`

A failure can result in:

`PROCESSING → RETRY → PROCESSING`

After the configured retry limit:

`RETRY → DEAD_LETTERED`

The implementations model these states through message status fields and queue structures.

### 4.3 Topics and Event Distribution

A topic represents a named stream or category of events.

For example:

| Topic | Event | Consumer |
|---|---|---|
| `product.events` | ProductCreated | Inventory Service |
| `order.events` | OrderCreated | Inventory Service |
| `inventory.events` | StockReserved | Order Service |
| `payment.events` | PaymentCompleted | Order Service |

A queue normally distributes work among competing consumers.

A publish-subscribe system allows multiple subscriptions to receive events independently.

The exact delivery and retention behavior depends on the broker.

### 4.4 Message Delivery Guarantees

Messaging systems commonly expose different delivery guarantees.

| Guarantee | Meaning | Consideration |
|---|---|---|
| At-most-once | Message may be lost, but is not redelivered | Suitable only when loss is acceptable |
| At-least-once | Message is redelivered until acknowledged according to broker rules | Consumer idempotency is important |
| Exactly-once processing effect | Repeated delivery does not produce repeated business effects | Requires coordinated state and transaction design |

Exactly-once delivery should not be assumed merely because a broker offers exactly-once features.

The application must also manage database transactions, consumer state, and external side effects.

### 4.5 Idempotent Consumers

An idempotent consumer safely handles repeated messages.

The implementations use a processed-event identifier set.

For example, if a stock-reservation event is delivered twice, the consumer should not reserve the same quantity twice.

A production implementation should persist processed identifiers and the business update in one transaction.

The JavaScript and Java versions use event identifiers and synchronized or single-process state management.

The Python and C++ implementations use sets to track processed events.

The PostgreSQL `consumer_inbox` table provides a persistent uniqueness constraint on:

`consumer_service_id, message_id`

This prevents duplicate registration for the same consumer and message.

### 4.6 Retry and Dead-Letter Handling

A failed message can be retried when the failure is temporary.

Typical transient failures include:

- Network interruptions.
- Temporary service unavailability.
- Database connection failures.
- Rate limiting.

Permanent failures include:

- Invalid event structures.
- Unsupported event versions.
- Invalid business identifiers.
- Unrecoverable authorization failures.

A retry strategy should use:

- A maximum attempt count.
- Exponential backoff.
- A retry delay.
- Error classification.
- Dead-letter storage.
- Monitoring and alerting.

Repeatedly retrying a permanent failure can waste resources and delay other messages.

The Python, JavaScript, C++, and Java implementations include bounded retry behavior and dead-letter handling.

The PostgreSQL `fail_message()` function performs the persistent retry-state transition.

### 4.7 Transactional Outbox

The transactional outbox pattern solves a common consistency problem.

Consider an order service that:

1. Saves an order in its database.
2. Publishes an `OrderCreated` event.

If the database transaction succeeds but event publication fails, downstream services never receive the event.

The opposite ordering can publish an event for an order that was never committed.

The outbox pattern stores business changes and events in the same database transaction.

A separate dispatcher publishes committed events.

The workflow is:

`Business Transaction → Outbox Record → Dispatcher → Broker → Consumer`

The Python and Java implementations simulate this pattern with synchronized application state.

The PostgreSQL implementation provides persistent outbox records and a dispatcher procedure using row-level locking and `SKIP LOCKED`.

For production deployment, the dispatcher must also handle the possibility that publishing succeeds but updating the publication state fails. This can produce duplicate publication, which is why consumer idempotency remains necessary.

## 5. Comparing the Three Approaches

The protocols solve different communication problems.

| Decision factor | REST | gRPC | Messaging |
|---|---|---|---|
| Immediate response | Yes | Yes | Not required |
| Resource-oriented API | Strong fit | Not its primary model | Not its primary model |
| Typed method contracts | Application-defined | Strong fit | Event schema |
| Asynchronous workflows | Possible | Possible | Strong fit |
| Streaming | Application-dependent | Native support | Broker-dependent |
| Consumer independence | Limited | Limited | Strong |
| Retry management | Client/application | Client/application | Broker and consumer |
| Event distribution | Requires additional design | Requires additional design | Native pattern |
| Request deadlines | HTTP client/server | RPC deadline | Message delivery policy |
| Typical external API | Strong fit | Less common | Usually indirect |

## 6. Cross-Service Workflow

The examples represent an order-processing architecture.

A typical workflow is:

1. The client submits an order through the REST interface.
2. Order Service validates the request.
3. Order Service invokes Product Service through an RPC interface when an immediate product lookup is required.
4. Order Service records the business transaction and an outbox event.
5. The dispatcher publishes the order event.
6. Inventory Service consumes the event.
7. Inventory Service records the event identifier and reservation outcome.
8. Payment Service processes the corresponding payment workflow.
9. Resulting events update the order state.

Plain-text architecture:

Client
  |
  | HTTP / JSON
  v
API Layer
  |
  v
Order Service
  |
  +---- gRPC ----> Product Service
  |
  +---- Database Transaction
  |          |
  |          v
  |      Outbox
  |          |
  |          v
  |       Message Broker
  |          |
  |          +----> Inventory Service
  |          |
  |          +----> Payment Service
  |          |
  |          +----> Notification Service

Each communication mechanism has a separate responsibility.

REST handles resource access, gRPC handles typed remote operations, and messaging coordinates asynchronous business events.

## 7. Implementation Architecture

### 7.1 Python

The Python implementation uses:

| Component | Responsibility |
|---|---|
| `ProductService` | Product domain operations |
| `RestHandler` | HTTP resource handling |
| `rest_client` | HTTP requests with timeout handling |
| `ProductRpcService` | Typed RPC simulation |
| `RpcClient` | RPC invocation and failure handling |
| `MessageBroker` | Queue management and delivery |
| `IdempotentConsumer` | Duplicate-event prevention |
| `TransactionalOutbox` | Event persistence simulation |
| `CommunicationPolicy` | Communication security validation |

Python uses dataclasses for message structures, enums for protocol and delivery states, dictionaries for product storage, deques for queues, and sets for deduplication.

The local HTTP server uses an ephemeral port and shuts down after the demonstration.

### 7.2 JavaScript

The JavaScript implementation emphasizes asynchronous programming and event-driven behavior.

| Component | Responsibility |
|---|---|
| `ProductRepository` | Map-based product storage |
| `createRestServer` | Node.js HTTP server |
| `ProductRpcService` | RPC contract implementation |
| `RpcClient` | Deadline-aware asynchronous invocation |
| `MessageBroker` | EventEmitter-based broker simulation |
| `InventoryConsumer` | Idempotent event processing |
| `Outbox` | Event recording and dispatch |
| `CommunicationPolicy` | Security policy evaluation |

The implementation uses:

- `Map` for resource storage.
- `Set` for deduplication.
- `Promise` and `async/await` for asynchronous operations.
- `EventEmitter` for broker events.
- `structuredClone()` for message payload isolation.
- `crypto.randomUUID()` for unique identifiers.

The message broker executes handlers asynchronously and applies bounded retries.

### 7.3 C++17

The C++ implementation emphasizes explicit domain types and state management.

| Component | Responsibility |
|---|---|
| `ProductRepository` | Product persistence simulation |
| `RestApi` | Resource operations and HTTP response modeling |
| `ProductRpcService` | Typed RPC interface |
| `RpcClient` | Client invocation |
| `MessageBroker` | Queue and delivery state |
| `InventoryConsumer` | Idempotent event handling |
| `OrderService` | Order lifecycle transitions |
| `CommunicationPolicy` | Security and transport constraints |

C++ uses:

- `unordered_map` for average constant-time lookups.
- `unordered_set` for event deduplication.
- `deque` for queue operations.
- `optional` for missing resources.
- `enum class` for strongly typed states.
- Exceptions for invalid operations.

The order workflow rejects invalid state transitions.

### 7.4 Java 17

The Java implementation emphasizes enterprise domain modeling and service abstractions.

| Component | Responsibility |
|---|---|
| `ProductStore` | Repository interface |
| `InMemoryProductStore` | Product storage implementation |
| `ProductRestController` | REST resource behavior |
| `ProductRpcImplementation` | Typed RPC service |
| `RpcClient` | Asynchronous RPC invocation |
| `MessageBroker` | Topic-based delivery |
| `InventoryConsumer` | Duplicate-event protection |
| `TransactionalOutbox` | Event recording and dispatch |
| `CommunicationPolicy` | Security validation |

Java uses:

- Records for immutable request and response models.
- Interfaces for service contracts.
- `Optional` for missing resources.
- `CompletableFuture` for asynchronous operations.
- `Concurrent`-oriented synchronization through synchronized methods.
- Collections for message and event state.
- Custom exceptions for domain failures.

The implementation separates service contracts from their concrete implementations.

### 7.5 PostgreSQL

The database implementation provides persistent communication metadata and operational state.

| Database object | Responsibility |
|---|---|
| `services` | Service registry |
| `rest_endpoints` | REST endpoint contracts |
| `rest_requests` | REST request history |
| `grpc_services` | RPC service definitions |
| `grpc_methods` | RPC method contracts |
| `grpc_invocations` | RPC execution history |
| `message_topics` | Event topic definitions |
| `message_subscriptions` | Consumer subscriptions |
| `outbox_events` | Transactional outbox |
| `messages` | Persistent message delivery |
| `consumer_inbox` | Consumer deduplication |
| `communication_audit` | Cross-protocol audit history |

The schema uses:

- Primary and foreign keys.
- Unique constraints.
- Check constraints.
- Partial indexes.
- JSONB payload storage.
- UUID correlation identifiers.
- Database procedures.
- Database functions.
- Views.
- Common table expressions.
- Transactions.
- `FOR UPDATE SKIP LOCKED` for concurrent dispatchers.

The schema distinguishes communication contracts from actual network transport.

## 8. Reliability and Failure Management

Distributed services cannot assume that every remote dependency is available.

Important failure categories include:

| Failure | REST handling | gRPC handling | Messaging handling |
|---|---|---|---|
| Invalid input | HTTP 400 | INVALID_ARGUMENT | Reject or dead-letter |
| Missing resource | HTTP 404 | NOT_FOUND | Domain-specific handling |
| Network failure | Client error handling | UNAVAILABLE | Broker retry |
| Timeout | HTTP client timeout | DEADLINE_EXCEEDED | Delivery and processing timeout |
| Duplicate operation | Idempotency key | Application-level deduplication | Consumer inbox |
| Temporary dependency failure | Bounded retry | Bounded retry | Delayed redelivery |
| Permanent processing failure | Error response | RPC status | Dead-letter queue |

Retries must be designed carefully.

An operation that transfers money or creates an order should not be repeated without appropriate idempotency protection.

Circuit breakers can prevent repeated calls to an unhealthy dependency.

Bulkheads can isolate resource consumption between independent services.

Backpressure can prevent producers from overwhelming consumers.

These controls should be applied according to the actual workload and failure characteristics.

## 9. Security and Governance

Communication security requires more than encryption.

Important controls include:

- TLS for REST and gRPC connections.
- Mutual TLS where service identity verification is required.
- Authentication of service identities.
- Authorization at endpoint, method, and event-subscription levels.
- Secure credential storage and rotation.
- Input validation.
- Request-size restrictions.
- Message-schema validation.
- Protection against replay and duplicate requests.
- Sensitive-data minimization.
- Audit logging.
- Rate limiting.
- Network segmentation.

Message payloads should not contain unnecessary credentials, authentication tokens, or sensitive personal information.

Correlation identifiers should support tracing without becoming authentication credentials.

Production deployments should avoid logging complete confidential request and response bodies.

## 10. Observability and Performance

Communication performance must be evaluated at the protocol and application levels.

Useful measurements include:

| Metric | Purpose |
|---|---|
| Request rate | Incoming workload |
| Request latency | Time required to process requests |
| p95 latency | High-percentile response time |
| p99 latency | Tail latency |
| Error rate | Communication failures |
| RPC deadline failures | Timed-out invocations |
| Queue depth | Pending message workload |
| Consumer lag | Delay in message processing |
| Retry rate | Frequency of failed deliveries |
| Dead-letter count | Unrecoverable messages |
| Outbox backlog | Events awaiting publication |
| Duplicate-event count | Repeated delivery detection |

Correlation identifiers connect operations across services.

Distributed tracing should preserve trace context across HTTP headers, RPC metadata, and message headers.

Performance considerations differ:

- REST benefits from connection reuse, pagination, caching, and appropriate payload sizes.
- gRPC benefits from HTTP/2 multiplexing, efficient serialization, channel reuse, and streaming where appropriate.
- Messaging benefits from batching, controlled concurrency, partitioning, bounded queues, and efficient acknowledgement handling.

The SQL performance views and indexes support operational reporting and failure investigation.

## 11. Edge Cases and Design Limitations

The implementations intentionally expose several issues that require stronger infrastructure in production.

| Area | Demonstration limitation | Production requirement |
|---|---|---|
| REST authentication | No authentication middleware | Identity verification and authorization |
| REST transport | Local HTTP server | TLS-enabled deployment |
| gRPC | Typed simulation | Generated stubs and HTTP/2 |
| Messaging persistence | In-memory queues | Durable broker |
| Message ordering | Basic queue ordering | Defined partition and ordering strategy |
| Idempotency | In-memory state in language examples | Persistent transactional deduplication |
| Outbox dispatch | Simplified publication tracking | Recovery from publication uncertainty |
| Retries | Basic bounded retry | Classified errors and backoff policies |
| RPC deadlines | Client-side simulation | Propagated transport deadlines |
| Concurrent processing | Limited simulation | Durable leases and concurrency controls |
| Schema evolution | Basic contract metadata | Version compatibility and migration policies |

The in-memory message implementations do not provide durable delivery guarantees.

The PostgreSQL schema models durable records, but the database alone is not a message broker. A production dispatcher and broker integration must implement the actual transport and delivery protocol.

## 12. Execution Requirements

| Deliverable | Runtime | External dependencies |
|---|---|---|
| Python | Python 3.10+ | None |
| JavaScript | Node.js 18+ | None |
| C++17 | C++17 compiler | None |
| Java | Java 17 | None |
| PostgreSQL | PostgreSQL 15+ | PostgreSQL server |

The PostgreSQL script uses `gen_random_uuid()` for UUID generation.

Each program includes an executable demonstration of its communication model.

The examples are designed to distinguish resource-oriented requests, typed remote method invocation, and asynchronous event delivery while showing how validation, reliability, state management, and security requirements affect service-to-service communication.
