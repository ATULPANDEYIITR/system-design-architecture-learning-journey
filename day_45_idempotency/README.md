# Idempotency: Safe Retries, Duplicate Requests, and Idempotent APIs

## Scope

Idempotency is a mechanism for making repeated attempts to perform the same logical operation produce the same externally observable result rather than creating an additional business side effect.

It is particularly important for APIs that perform operations such as creating an order, charging a payment instrument, reserving inventory, provisioning a subscription, submitting a shipment, or creating another durable resource. A client can send a request successfully while failing to receive the response. From the client's perspective, the outcome is then unknown. Retrying without an idempotency mechanism can create the same business object twice.

The central distinction in this implementation set is between a **request attempt** and a **logical operation**. Two HTTP requests can be different transport attempts while representing one logical operation. An idempotency key gives the server a durable identifier for that logical operation.

The six artifacts use different technical perspectives:

- Python builds a progressively richer executable payment example, including request fingerprints, replay, conflicts, concurrent attempts, expiration, and a SQLite-backed store.
- JavaScript models asynchronous order creation and shows how event-loop concurrency interacts with idempotency state.
- C++ treats idempotency as a concurrent reservation-governance problem and emphasizes locking, state ownership, and side-effect recovery.
- Java models an enterprise subscription-provisioning domain with explicit records, states, repository behavior, validation, and service boundaries.
- PostgreSQL represents idempotency as durable relational state protected by constraints, transactions, indexes, and queries.
- This README connects those implementations to the underlying API design decisions.

## Core Concept

A request such as:

`POST /payments`

may create a durable payment. If the client sends the request, the server creates the payment, but the network connection fails before the response reaches the client, the client cannot safely conclude that the operation failed.

A retry without idempotency may execute the business operation again:

`request A -> payment created -> response lost`

followed by:

`request B -> payment created again -> response received`

The intended model is instead:

`request A -> logical operation O -> payment created -> response lost`

followed by:

`request B + same idempotency key -> lookup O -> original response replayed`

The key is not simply a duplicate HTTP request detector. It identifies the intended logical operation across multiple transport attempts.

## Idempotency Key

An idempotency key is normally supplied by the client in a request header such as `Idempotency-Key`.

The value should be sufficiently unique for the scope of the operation. A random UUID is a common choice.

The server stores the key with information such as:

| Field | Purpose |
| --- | --- |
| `idempotency_key` | Identifies the logical operation |
| `request_fingerprint` | Binds the key to the original request parameters |
| `state` | Distinguishes processing from completed execution |
| `response_status` | Allows the original HTTP status to be replayed |
| `response_body` | Allows the original response to be replayed |
| `created_at` | Establishes the start of the retention period |
| `expires_at` | Defines when the record can be removed |
| `completed_at` | Records durable completion |

The request fingerprint is important because a key should not silently change meaning.

For example, if a client first submits:

`customer = C42, amount = 2500`

and later sends the same key with:

`customer = C42, amount = 9900`

the server should not interpret the second request as another legitimate use of the key. It should report a conflict.

## Logical Request Identity

An idempotency key and a request fingerprint solve different problems.

The key answers:

> Which logical operation is this?

The fingerprint answers:

> Does this retry still represent the same operation?

The Python implementation calculates a SHA-256 fingerprint over canonical JSON. Canonicalization matters because object field ordering should not accidentally make equivalent request representations appear different.

For example, these two objects contain the same logical data:

`{"customer_id": "customer-1", "amount_cents": 1200}`

and

`{"amount_cents": 1200, "customer_id": "customer-1"}`

The Python canonicalization sorts dictionary keys before hashing, so both produce the same fingerprint.

A fingerprint should normally cover the business parameters whose modification would change the meaning of the operation. It should not blindly include volatile transport metadata such as a timestamp generated independently for every retry.

## Safe Retry

A retry is safe when the server can determine that the request belongs to a previously known logical operation and return the stored outcome without performing the business side effect again.

The basic state transition is:

`PROCESSING -> COMPLETED`

The first request claims the key and becomes the owner of execution.

A later request with the same key and matching fingerprint sees `COMPLETED`. It receives the stored response.

The retry does not call the payment, order, reservation, or provisioning operation again.

This is the central safety property demonstrated by all five executable implementations, although each uses a different business domain.

## Why the Response Must Be Stored

It is not sufficient to remember only that an idempotency key was used.

Suppose the original request returned:

`201 Created`

with a resource identifier such as:

`payment_id = pay_abc123`

A retry needs enough information to produce a semantically equivalent response.

The Python, JavaScript, Java, and SQL examples therefore associate the completed idempotency record with the original response.

This is particularly important for APIs that return generated identifiers. A retry should normally receive the same identifier rather than a newly generated identifier.

## Processing and Completed States

The implementations distinguish at least two states:

`PROCESSING`

means that one request has claimed the logical operation but has not yet recorded its completed response.

`COMPLETED`

means that the server has a durable outcome that can be replayed.

The distinction prevents two independent requests from simultaneously deciding that they are the first execution.

The Java repository explicitly represents `RequestState.PROCESSING` and `RequestState.COMPLETED`. The C++ governance engine uses `OperationState`. The SQL table enforces the same distinction with a database `CHECK` constraint.

A production implementation may require more states depending on business semantics. For example, an operation could distinguish a durable failure from successful completion. The important requirement is that the state model accurately represents what is safe to retry.

## Duplicate Requests Are Not Always Identical

There are several different duplicate-request situations.

A repeated request with the same key and the same fingerprint is normally a legitimate retry.

A repeated key with a different fingerprint is a key conflict.

A request arriving while another request is still processing is an in-progress duplicate.

A request arriving after the idempotency record has expired may be treated as a new operation, depending on the API contract.

These cases should not be collapsed into a single generic "duplicate" response because their operational meanings differ.

## The Dangerous Failure Window

The hardest case is a failure after the business side effect but before the client receives the response.

Consider:

`client -> API -> database`

The API creates the order successfully.

Then:

`API -> client`

fails because the connection is interrupted.

The client knows only that it did not receive a successful response.

If the server deleted the idempotency record after the timeout, the retry could create another order.

The Python timeout demonstration deliberately creates the payment, records its completed idempotency result, and then raises a simulated timeout. The subsequent retry recovers the stored result.

The Java implementation uses the same concept for subscription provisioning.

The key design rule is:

**Do not remove an idempotency record merely because response delivery failed when the business side effect may already have committed.**

## Atomicity and Durable State

Idempotency is not a replacement for transactions.

The strongest implementation normally needs the business mutation and the idempotency state transition to be coordinated.

Conceptually:

`BEGIN TRANSACTION`

`claim idempotency key`

`perform business mutation`

`store response`

`COMMIT`

If the database transaction commits both the business row and the completed idempotency record, another request can observe a consistent result.

If they are stored independently, a crash can create an intermediate state.

For example:

`business mutation committed`

followed by:

`idempotency completion not committed`

can make a later retry uncertain.

The PostgreSQL implementation demonstrates the transactional model directly. It locks the idempotency record with `FOR UPDATE`, performs the order insertion, updates the stored response, and commits the transaction.

The exact production strategy depends on the storage architecture, transaction boundaries, and business operation.

## Python Implementation

The Python program uses a payment domain because duplicate monetary side effects provide a clear reason for safe retries.

`InMemoryIdempotencyStore` demonstrates the fundamental state machine. Its lock protects the local dictionary while the key is claimed, completed, or removed.

`PaymentLedger` deliberately remains a separate component. This separation demonstrates that idempotency state and business state have different responsibilities.

`IdempotentPaymentApi.post_payment()` first validates the request, computes a fingerprint, claims the key, and only then invokes the payment ledger.

When a completed record is encountered, the stored response is replayed with an `idempotent_replay` marker. The marker is an educational diagnostic field; a real API should define its response contract deliberately rather than arbitrarily adding fields to an established response schema.

The Python program also demonstrates a SQLite implementation. This is significant because an in-memory dictionary disappears when the process terminates and cannot coordinate independent application instances.

The SQLite store provides durable records and a uniqueness constraint on the idempotency key. PostgreSQL, MySQL, or another production database would normally be selected according to the application's architecture.

The concurrency demonstration shows that multiple threads can contend for the same key. Only one thread should acquire ownership in the local implementation; other attempts observe that the logical operation is already processing.

## JavaScript Implementation

The JavaScript artifact uses an asynchronous order service.

Its `OrderService.createOrder()` waits asynchronously before creating an order. This represents the type of asynchronous business operation common in Node.js services.

The `MemoryIdempotencyStore.claim()` method completes the local ownership decision synchronously before asynchronous work begins. This is important because a JavaScript application can interleave asynchronous continuations even though ordinary JavaScript execution is single-threaded within one event loop.

The JavaScript example uses `Promise.all()` to create concurrent duplicate attempts. This makes the concurrency model different from the C++ thread example.

The JavaScript implementation also demonstrates canonical fingerprint generation without requiring an npm dependency. Object keys are sorted before the hash is calculated.

The distinction between `before_side_effect` and `after_side_effect` failures is central. A failure before the business operation occurs can allow the processing record to be removed safely when the service knows no side effect occurred. A failure after the business operation requires retaining the completed result.

For a real multi-instance Node.js service, the in-memory `Map` would not be sufficient. Separate processes would need a shared durable store such as a transactional database or another appropriately designed coordination mechanism.

## C++ Case Study

The C++ program models an event reservation service.

A reservation is a useful idempotency scenario because repeated execution can consume additional capacity. If a client requests five seats, a duplicate execution could consume ten seats.

`ReservationService` protects the event capacity with a mutex. Its state is independent from `GovernanceEngine`, which represents the idempotency layer.

`GovernanceEngine::begin()` performs the logical ownership decision:

- An unknown key becomes `PROCESSING`.
- A known key with a different fingerprint raises `IdempotencyConflict`.
- A known key still in `PROCESSING` raises `OperationInProgress`.
- A completed key returns the stored result for replay.

The separation is architecturally important. The idempotency engine does not need to understand how seats are reserved. It only needs a stable representation of the logical request and a stored outcome.

The concurrency example creates multiple C++ threads using one idempotency key. Mutexes protect the shared maps and reservation counters.

The timeout scenario is especially important. The reservation is committed before the simulated network timeout is raised. Because the idempotency record is already complete, the retry returns the same reservation identifier.

This illustrates why a catch block must not indiscriminately erase idempotency state.

## Java Enterprise Model

The Java implementation models subscription provisioning.

The `ProvisioningRequest` record provides immutable request data and constructor validation.

`ProvisioningResult` represents the business outcome separately from the request.

`IdempotencyRecord` models the lifecycle of the server-side idempotency state.

`IdempotencyRepository` provides the persistence boundary. Its synchronized claim operation prevents two local service threads from simultaneously creating a new record for the same key.

`ProvisioningService` coordinates validation, idempotency ownership, business execution, response storage, and replay.

The `Claim` sealed interface distinguishes execution ownership from replay explicitly. This is preferable to using an unstructured flag because the type communicates the possible outcomes of the repository operation.

The example uses Java 17 records and sealed interfaces because they make the domain state explicit rather than merely demonstrating Java syntax.

The enterprise scenario also makes a practical architectural distinction: the idempotency repository should normally be durable and shared when several application instances handle the same API.

## PostgreSQL Data Model

The SQL implementation represents the idempotency domain directly.

The `customers` table contains the business actor.

The `orders` table contains the durable business side effect.

The `idempotency_requests` table contains the logical request identity and replay information.

The `api_status_checks` table represents operational checks associated with a request. It demonstrates how application-level validation data can be related to the idempotency lifecycle without confusing a status check with the idempotency key itself.

The primary key on `idempotency_requests.idempotency_key` provides database-level uniqueness.

The `request_fingerprint` column binds the key to the original business parameters.

The `state` constraint permits only `PROCESSING` and `COMPLETED`.

The multi-condition `CHECK` constraint prevents an internally inconsistent completed record from existing without response information.

The expiration index supports cleanup and operational queries.

## Database-Level Enforcement

Application code can reject invalid requests, but important invariants should also be protected by the database when practical.

For example, the database prevents:

- two idempotency records with the same key
- non-positive order amounts
- orders referencing nonexistent customers
- unsupported order states
- completed idempotency records without stored response data
- invalid status-check states

This matters because an API may eventually have multiple application services, background workers, administrative tools, or migration processes interacting with the same data.

Database constraints create a final integrity boundary.

## Transactional Workflow

The SQL transaction demonstrates a coordinated sequence:

`lock idempotency record`

`create business record`

`store response`

`commit`

A competing transaction cannot simply perform another business operation for the same key while the first transaction owns the relevant database state.

The exact transaction design must account for isolation levels, deadlocks, lock duration, database failover, and the behavior of the underlying business operation.

For an operation that crosses database boundaries, a single SQL transaction may not be enough. Payment gateways, external APIs, message brokers, and other services introduce additional failure boundaries.

## Idempotency and Exactly-Once Semantics

Idempotency should not be described as universal exactly-once execution.

A server can provide an idempotent API contract while external systems still observe multiple attempts.

For example:

`API -> external payment gateway`

may succeed, followed by an API crash before the local idempotency record is completed.

Recovering safely may require the downstream payment provider to support its own idempotency mechanism, transaction identifier, reconciliation process, or durable operation lookup.

The strongest design composes idempotency across the boundaries where duplicate side effects matter.

## Retry Policy

Idempotency and retry policy solve related but different problems.

A retry policy decides **when** a client should attempt the request again.

Idempotency determines **what the server does when that repeated logical operation arrives**.

A client may retry after:

- a connection timeout
- a temporary DNS or transport failure
- a transient gateway error
- an explicitly documented server failure

A client should not automatically retry every HTTP response. Some failures indicate invalid parameters or authorization problems that will not become valid merely through repetition.

The API contract should explicitly state which failures are retryable.

## Response Replay

A replay should preserve the semantics of the original operation.

If the first request returned a resource identifier, the retry should normally return that same identifier.

If the first request returned a business error that is part of the stored idempotent outcome, the retry policy should be defined explicitly. Some systems store successful and unsuccessful terminal outcomes; others retain only successful mutations. The correct choice depends on the API contract and business semantics.

The key requirement is consistency. A retry must not accidentally execute a different business path simply because it is a later transport attempt.

## Idempotency-Key Scope

The uniqueness scope of an idempotency key must be deliberate.

Possible scopes include:

- one API endpoint
- one authenticated customer
- one tenant
- one resource type
- an entire service

A key should not accidentally collide between unrelated operations.

The server can incorporate an operation type or endpoint into the persistence key, or store those values as separate columns.

For example, the logical identity might be represented as:

`tenant_id + operation_type + idempotency_key`

This is safer than assuming a client-generated string is globally unique across every operation in a distributed platform.

## Retention and Expiration

Idempotency records cannot necessarily be retained forever.

The retention period must cover the expected retry window.

If records expire too early, a delayed retry may become a new logical operation and duplicate the business side effect.

If records are retained for an unnecessarily long time, storage costs and lookup overhead increase.

The Python and SQL implementations demonstrate expiration and cleanup.

A production API should document the retention behavior because clients need to understand how long a retry remains associated with the original operation.

## Common Failure Modes

### Deleting the key after every exception

This is unsafe when the exception occurs after the business mutation.

A server must distinguish:

`failure before side effect`

from:

`failure after side effect`

The second case requires recovery of the original outcome rather than unrestricted re-execution.

### Using only an in-memory map

An in-memory map works only within the process that owns it.

With two API instances:

`request 1 -> instance A`

`retry -> instance B`

instance B may not know that instance A already executed the operation.

A shared durable store is normally required for horizontally scaled APIs.

### Allowing a key to change request parameters

Without a fingerprint, a client can accidentally reuse a key for a different operation.

This creates ambiguous semantics and can produce surprising business results.

A production API should define whether conflicting reuse returns `409 Conflict`, another documented error, or a domain-specific response.

### Treating all concurrent duplicates as successful replays

A second request arriving while the first is still processing does not necessarily have a completed response to replay.

The service needs a policy. It may return an in-progress response, wait for completion, or use a coordination mechanism that allows the second request to observe the eventual result.

The examples use an explicit processing state and return a conflict-style outcome for an active duplicate.

### Generating the key on the server for every request

If a client loses a response and sends a retry, the server cannot identify the retry as the same logical operation if every request receives a new key automatically.

For mutation APIs, the client normally supplies a stable key across retry attempts.

## Validation Rules

An idempotency key should be validated for presence and acceptable size.

The business request must also be validated independently.

An idempotency key does not make an invalid request valid.

For example, the Python payment API still rejects a non-positive amount. The Java subscription model validates the customer, plan, and seat count. The C++ reservation service validates the customer, event, and capacity request.

The key identifies the operation. It does not replace business validation.

## Security Considerations

Idempotency records may contain sensitive information.

A stored response should therefore follow the same data-protection requirements as other API state.

Sensitive request bodies should not be unnecessarily copied into idempotency storage.

Logs should avoid printing authentication tokens, payment credentials, secrets, or complete sensitive payloads merely for debugging idempotency behavior.

An attacker who obtains another customer's idempotency key should not automatically gain access to the associated response. Authorization still applies to replay behavior.

The server should validate that the authenticated principal is authorized to use the logical operation represented by the key.

A key should not be treated as an authentication credential.

## Observability

Useful operational fields include:

`idempotency_key`

`request_fingerprint`

`operation_state`

`created_at`

`completed_at`

`replay_count`

`request_id`

`trace_id`

The idempotency key and tracing identifier serve different purposes. The idempotency key represents logical operation identity, while a tracing identifier normally represents one request or distributed execution trace.

A useful monitoring signal is an unusual increase in replayed requests. It can indicate network instability, client retry storms, or a downstream service that is responding too slowly.

A high conflict rate can indicate buggy clients that reuse keys incorrectly.

A large population of long-running `PROCESSING` records can indicate stuck workers, database failures, or unhandled execution paths.

## Performance Considerations

Idempotency adds a lookup and usually a write to the request path.

The key lookup must therefore be indexed efficiently.

The PostgreSQL primary key on `idempotency_key` provides an efficient uniqueness and lookup structure. The expiration index supports cleanup.

The application should avoid storing unnecessarily large response bodies when the API can reconstruct a stable response safely. When reconstruction could produce a different result, storing the original response is safer.

Hot keys should be rare because the same key represents one logical operation. High traffic using the same key can indicate client retry storms or an incorrectly reused identifier.

## Distributed Systems Boundary

The most important production limitation is the boundary between local application state and external durable systems.

A robust architecture may involve:

`client`

`-> API gateway`

`-> application service`

`-> transactional database`

`-> external provider`

Each boundary can fail independently.

A local idempotency record cannot automatically guarantee that an external provider performed an operation exactly once.

The application may therefore need a stable downstream operation identifier, provider-side idempotency key, durable outbox, reconciliation job, or explicit state machine.

Idempotency is strongest when every important side-effecting boundary has a defined duplicate-handling strategy.

## Relationship Between the Implementations

The implementations intentionally do not use the same domain.

The Python program focuses on payment processing and compares an in-memory implementation with a durable SQLite implementation.

The JavaScript program focuses on asynchronous order creation and demonstrates how Promise-based concurrency interacts with a local idempotency store.

The C++ program focuses on event reservation and emphasizes thread synchronization and resource capacity.

The Java program focuses on enterprise subscription provisioning and uses explicit domain types, records, a repository boundary, sealed result types, and state modeling.

The PostgreSQL script focuses on persistence and integrity. Its primary contribution is showing which idempotency guarantees can be represented directly through keys, constraints, transactions, indexes, and durable response storage.

The common mechanism is logical-operation identity, but each implementation demonstrates a different engineering boundary rather than reproducing the same tutorial in another syntax.

## Practical Contract

A mutation API that uses idempotency should define at least these behaviors explicitly:

| Situation | Expected behavior |
| --- | --- |
| New key | Execute the logical operation |
| Existing key with matching request | Replay the stored result |
| Existing key with different request | Reject as a key conflict |
| Existing key still processing | Follow the documented in-progress policy |
| Response lost after successful side effect | Retry must recover the original result |
| Key expired | Apply the documented post-retention behavior |
| Unauthorized retry | Apply normal authorization rules |
| Invalid request | Reject without treating the key as a successful operation |

These rules are more important than the presence of a particular storage technology. The storage implementation must preserve the API contract across retries, failures, and process restarts.

## Production Design Boundary

A production implementation should decide where idempotency state is durable, how it participates in the business transaction, how long it is retained, how concurrent requests are coordinated, how conflicting key reuse is reported, and how external side effects are reconciled.

The central invariant is straightforward:

**One idempotency key with one request meaning must map to one logical outcome within the documented retention period.**

That invariant is what turns an unreliable sequence of transport attempts into a reliable API-level operation.
