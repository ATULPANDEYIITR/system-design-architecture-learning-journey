# Consistency Models in Distributed Systems

## Scope

Strong consistency, eventual consistency, and causal consistency describe different guarantees about the values that clients can observe when data is distributed across replicas.

A consistency model specifies which observations a system permits when writes, reads, and message delivery occur concurrently. It does not, by itself, specify replication topology, durability, failure recovery, or performance. Those properties depend on the protocols and storage mechanisms used to implement the model.

The implementations in this repository use a regional incident-management service as their principal example. An incident can be created in one region, assigned to an operations team, and replicated to other regions. The distinction between these events demonstrates why ordering guarantees matter.

## Terminology

**Replica:** An independently accessible copy of some application state. Replicas may temporarily contain different values while updates propagate.

**Operation:** A logical state change, such as creating an incident, changing its severity, or assigning an incident to a team. An operation identifier allows a receiver to recognize repeated delivery.

**Replication lag:** The delay between an operation being accepted at its origin and its visibility at another replica.

**Causal dependency:** An earlier operation that must be observed before a dependent operation becomes visible under causal consistency.

**Convergence:** Agreement between replicas after they have received and processed the same relevant operations. Convergence does not imply that every intermediate read is fresh or that every concurrent write has been preserved.

**Vector clock:** A collection of counters associated with replica identities. Vector clocks help establish whether one operation's recorded history includes another operation's history.

**Tombstone:** A replicated deletion marker. It preserves evidence that an entity was deleted, preventing a replica that later receives an older value from automatically treating the deleted entity as new.

## Strong consistency

Strong consistency is commonly implemented using linearizability, a guarantee under which operations appear to take effect atomically in an order consistent with real-time completion constraints.

If a client receives successful confirmation for a write and subsequently performs a read, that read must not return a value older than the acknowledged write. Concurrent operations must also be ordered according to the system's linearizability rules.

For example, when a monitoring service records that a safety sensor is operational, an authoritative read must not report an older acknowledged status. Systems that coordinate resource allocation, enforce financial invariants, or maintain unique assignments may need similarly strong guarantees.

### Coordination and availability

A distributed implementation typically requires a leader, a consensus protocol, synchronous replication, or another protocol that establishes a safe committed order. If the system cannot establish the required order during a network partition, it may reject or delay reads and writes.

Strong consistency is not synonymous with a single database transaction, nor does it automatically guarantee durability. A system must separately specify when a write is durable, which failures it tolerates, and which acknowledgments permit the client to treat an operation as committed.

The Python, JavaScript, C++, and Java examples use a single authoritative leader and synchronous application of successful writes to available replicas. These are deliberately simplified simulations. They do not implement a production consensus algorithm, replicated log, leader election, or crash-safe commit protocol.

## Eventual consistency

Eventual consistency permits a replica to return older data while updates are propagating. Its central convergence condition is that replicas receiving the same relevant updates will eventually agree, provided communication and processing recover and the system's conflict-resolution rules terminate.

An update can be accepted locally without waiting for every remote region. This can improve write availability and reduce latency, particularly when clients interact with nearby replicas.

A telemetry dashboard is a useful example. A sensor reading may appear immediately in its origin region while a dashboard in another region temporarily displays the previous reading. The lag can be acceptable for monitoring and historical analysis, but it may be inappropriate for safety interlocks or decisions that require an authoritative current value.

### Concurrent writes and conflict resolution

Two disconnected replicas can update the same entity before either observes the other's operation. These writes are concurrent, not necessarily sequential.

A system needs an explicit policy for resolving such conflicts. The examples use a deterministic last-writer-wins-style rule based on logical timestamps and stable tie-breakers. This makes the final selected value deterministic for a given operation set.

The policy has an important limitation: selecting one concurrent value can discard the other. Deterministic convergence is not the same as preserving every update.

Production alternatives include:

- A multi-value register that retains concurrent values until an application or user resolves them.
- A domain-specific merge function that combines compatible changes.
- A conflict-free replicated data type whose operations and merge rules are designed for safe convergence.
- A single-writer rule for entities whose concurrent modification cannot be reconciled safely.

The appropriate choice depends on whether the data represents replaceable preferences, additive measurements, collaborative edits, or business-critical state.

### Recovery and anti-entropy

Asynchronous replication requires more than sending each operation once. Messages may be delayed, duplicated, or lost. Replicas may be unavailable for long periods.

The examples maintain an operation registry and use an anti-entropy pass to deliver missing operations to available replicas. A production system would need durable replication logs, snapshot handling, retry policies, replica membership management, deletion-marker retention, and monitoring for excessive lag.

An operation registry in memory is not durable storage. A real implementation must preserve enough history to repair replicas after process restarts without accidentally reintroducing deleted data.

## Causal consistency

Causal consistency preserves the order of causally related operations while permitting concurrent operations to be observed in different orders.

Suppose an operator creates incident `INC-804`, then assigns it to the network operations team after seeing the incident. The assignment depends on the incident's creation. A replica should not expose the assignment before it has observed the creation operation.

Causal consistency does not require every replica to observe all concurrent operations in the same order. If two operators independently update unrelated records, those operations may be delivered in different orders as long as causal dependencies remain intact.

### Happens-before relationship

The causal relationship between operations is often described by the happens-before relation.

An operation happens before another when the second operation was produced after observing the first, or when a chain of such relationships connects them. Independent operations with no causal ordering may be concurrent.

The implementation records causal dependencies explicitly. A receiver checks whether its local causal context includes the required dependency context before applying a dependent operation.

### Vector clocks

A vector clock associates a counter with each replica. A counter represents the number of events from that replica included in the recorded history.

Consider these contexts:

| Context | Vector clock |
|---|---|
| Incident created in region A | `{A: 1}` |
| Assignment created after observing the incident | `{A: 2}` |
| Independent event created in region B | `{B: 1}` |

The context `{A: 2}` includes the earlier event represented by `{A: 1}`. The contexts `{A: 1}` and `{B: 1}` are concurrent because neither dominates the other componentwise.

When a client carries a causal context between requests, a server can delay a read, route it to a sufficiently advanced replica, or reject the read temporarily. The JavaScript, Python, C++, and Java examples model rejection when a replica has not observed the required context.

Vector clocks are useful but not free. Their metadata can grow with the number of independent replica identities. Systems with dynamic membership need strategies for retired replicas, compacted history, and identity reuse. A version vector also does not replace application-level conflict resolution for concurrent updates to the same entity.

## Relationship between the three models

| Property | Strong consistency | Eventual consistency | Causal consistency |
|---|---|---|---|
| Stale reads | Prevented according to the selected strong guarantee | Permitted during propagation | Permitted unless they violate the requested causal context |
| Write coordination | Usually requires coordination for committed ordering | Local acceptance may proceed without remote coordination | Dependency tracking is required; independent operations can proceed concurrently |
| Ordering of dependent operations | Included in the global ordering guarantee | Not guaranteed without extra mechanisms | Preserved |
| Concurrent writes | Ordered by the protocol or resolved by application rules | Require a convergence and conflict policy | Concurrent operations remain unordered unless the application imposes an order |
| Partition behavior | May block operations requiring unavailable coordination | May permit local operations | May permit independent operations while delaying dependent ones |
| Typical use | Authoritative transactions and shared invariants | Caches, telemetry, replicated read models | Collaborative workflows and causally dependent updates |

The exact guarantees depend on the implementation. For example, a system described as strong might provide linearizable writes but weaker reads unless its contract explicitly requires linearizable reads as well.

## Python implementation

The Python program provides a deterministic distributed key-value store simulator built from standard-library data structures.

`DistributedStore` owns a collection of replicas, an operation registry, and a queue of propagation messages. Each `Replica` records its materialized values, applied operation identifiers, and causal context.

`VersionVector` implements componentwise comparison, merging, and incrementing. The `strictly_dominates` and `concurrent_with` operations distinguish causal ordering from concurrent history.

The strong-consistency scenario routes operations through the configured leader and rejects access when the required service is unavailable. The eventual-consistency scenario demonstrates a local write before remote propagation, followed by convergence. The causal scenario deliberately delivers a dependent operation before its prerequisite and verifies that the operation is deferred.

The edge-case demonstration checks idempotent retries, conflicting reuse of operation identifiers, empty-key validation, and tombstone propagation.

The simulator is designed for reasoning about guarantees, not for production deployment. In particular, its in-memory leader does not implement consensus, and its deterministic conflict resolver is not appropriate for every application.

## JavaScript implementation

The JavaScript implementation uses `Map`, `Set`, immutable operation objects, and asynchronous replication processing.

The `ConsistencyCluster` class separates operation creation, replica application, read behavior, conflict resolution, and message delivery. This separation makes the consequences of delayed delivery visible without depending on a real network.

The asynchronous `flush` method periodically yields to the Node.js event loop with `setImmediate`. This illustrates how a simulator can process a bounded replication workload without monopolizing the event loop for its entire duration.

The example also tests client-carried causal context. A client that has observed an assignment can require a later read to observe at least that context. A lagging replica rejects the request rather than returning an observation that violates the requested guarantee.

Operation identifiers provide idempotency for repeated submissions with identical content. Reusing an identifier with different content raises an error. Production APIs should bind identifiers to authenticated callers, request scopes, and durable records, and should define how long idempotency keys remain valid.

## C++ case study

The C++ program models a regional infrastructure-monitoring platform. Three data centers replicate sensor status, dashboard configuration, and incident-related information.

`GovernanceDataCenter` owns the replica map, operation registry, sequence metadata, and replication queue. `VectorClock` is represented as an ordered map from replica identity to counter. The componentwise comparison functions establish causal relationships and identify concurrent histories.

The strong-consistency scenario checks that a successful operation is visible through the authoritative state and that an unavailable leader causes reads to fail safely. The eventual-consistency scenario demonstrates local visibility, delayed propagation, and conflict resolution. The causal scenario delivers an assignment before the corresponding incident creation and confirms that the assignment remains unavailable until its dependency is satisfied.

The implementation uses `std::optional` to distinguish a missing or deleted value from a present value, and `std::set` to make operation delivery idempotent. Exceptions represent availability failures, missing causal dependencies, and conflicting operation identifiers.

The anti-entropy routine revisits registered operations to repair available replicas. The implementation is a technical case study rather than a distributed consensus implementation: there is no durable log, election protocol, transport layer, or crash recovery. Those mechanisms are necessary before the model could be used as a production service.

## Java enterprise implementation

The Java program models an incident-management service with explicit domain types.

`VersionVector` is an immutable record. Its constructor validates counters and copies the supplied map, preventing a caller from modifying causal metadata after an operation has been created. `Operation` is another record that represents a state change and its dependency context.

`Replica` encapsulates availability, applied operation identifiers, materialized records, and observed causal context. `ConsistencyService` coordinates operations according to the configured model.

The service separates validation, operation creation, application, conflict resolution, read evaluation, and anti-entropy. `AvailabilityException`, `MissingDependencyException`, and `OperationConflictException` communicate distinct failure conditions rather than returning ambiguous values.

The incident scenario creates an incident and then assigns it to a team. The assignment contains the creation operation's causal context. Attempting to deliver the assignment first does not make the assignment visible at a replica that has not observed the incident.

The Java model uses ordinary in-memory collections. An enterprise implementation would need to integrate durable persistence, distributed transaction or consensus protocols where required, authentication, authorization, metrics, tracing, and controlled retry behavior.

## SQL data model

The PostgreSQL script models repositories as logical distributed deployments. Each repository has a consistency mode, a set of replicas, an operation history, and an optional materialized entity state.

`consistency_operations` records operation identity, origin replica, entity key, payload, vector clock, causal dependencies, and processing status. The unique constraint on `(origin_replica_id, operation_sequence)` prevents a replica from recording the same sequence position twice.

`replica_operation_receipts` records whether a replica received and applied an operation. This is important because central knowledge of an operation does not prove that every remote replica has processed it.

`entity_versions` stores each replica's materialized state. `causal_dependencies` records explicit dependency edges. The schema's foreign keys prevent receipts and dependencies from referring to nonexistent records.

### Constraints and indexes

The database checks that vector-clock fields are JSON objects and that tombstones do not contain visible entity payloads. Foreign keys enforce the relationship between operations, replicas, and repositories.

The pending-operation index supports workers that search for unprocessed updates. The entity-key index supports history queries, while the GIN index on vector-clock JSON supports appropriate containment-style lookups.

The `vector_dominates_or_equals` function compares required counters with observed counters, treating missing counters as zero. `vector_merge` computes the componentwise maximum of two clocks.

These functions validate causal metadata, but they do not establish that the metadata truthfully describes real execution. The application must construct dependency information correctly and authenticate the operations that supply it.

### Transactions and distributed limitations

The script demonstrates a transactional receipt update and separates an operation's existence from its application at a particular replica.

A PostgreSQL transaction protects the changes made within its own database transaction. It does not make independent databases in different regions strongly consistent merely because they use the same schema.

A production replication worker should claim pending work safely, apply an operation idempotently, update materialized state and receipts in one local transaction, and record failures for retry. Strong consistency across separate database instances requires an appropriate distributed protocol. Causal consistency requires reliable dependency tracking and enforcement before dependent state is exposed.

The script ends with a rollback so that its schema and sample records can be used as an isolated demonstration without retaining the setup in the caller's transaction.

## Operational and correctness considerations

### Read-your-writes

Read-your-writes is a session guarantee: after a client successfully writes a value, its subsequent reads should observe that write. Eventual consistency does not automatically provide this guarantee when the next read is routed to a lagging replica.

A client can be routed to the original replica or carry a version token that the read service checks. Causal consistency can incorporate this requirement when the client's context includes its own preceding write.

### Monotonic reads

Monotonic reads prevent a client from moving backward in the version history it has already observed. Routing a client between replicas without tracking context can violate this guarantee under eventual consistency.

A service can preserve monotonic reads by maintaining session context, routing to a sufficiently advanced replica, or waiting until the selected replica reaches the required version.

### Idempotency and duplicate delivery

At-least-once delivery commonly produces duplicate messages. Receivers should record operation identifiers and make applying the same operation more than once harmless.

The examples use sets of applied identifiers. Production implementations must make deduplication durable and atomic with the corresponding state change. An in-memory set cannot protect against duplicate processing after a process restart.

### Deletions and stale replicas

Deleting an entity by removing it immediately from every local data structure is unsafe when replicas can later deliver old values. A tombstone records the deletion as an operation that can be replicated and compared with older versions.

Tombstone retention requires care. Removing a tombstone before all relevant replicas have passed the deletion can allow deleted state to reappear. Production systems need a retention policy based on replication progress, replica membership, and recovery guarantees.

### Performance and metadata costs

Strong consistency can increase latency because operations wait for coordination and the required commit acknowledgments. Availability during partitions depends on the protocol and the quorum or leadership rules.

Eventual consistency can reduce write latency but creates operational work for lag monitoring, conflict resolution, and repair. Its practical cost includes stale reads and the possibility of lost updates under poorly chosen conflict policies.

Causal consistency requires metadata and dependency checks. Vector clocks may become expensive when replica membership is large or dynamic. Compact causal metadata, stable replica identities, bounded histories, or specialized replication protocols may be needed at scale.

### Testing guarantees

Tests should verify observable guarantees rather than merely checking that every replica eventually contains the same value.

Strong-consistency tests should examine acknowledged writes, concurrent operations, and behavior when the authoritative service cannot commit safely. Eventual-consistency tests should introduce delayed delivery, duplicates, partitions, concurrent writes, and recovery. Causal-consistency tests should reorder messages and confirm that dependent operations remain invisible until their prerequisites have been observed.

A convergence test alone cannot prove strong or causal consistency. A system can converge eventually while exposing stale reads or temporarily violating a required causal order.
