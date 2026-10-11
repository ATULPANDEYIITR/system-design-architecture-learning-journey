# Distributed Systems Fundamentals

## Scope

Distributed systems coordinate computation and state across multiple independent processes or machines that communicate over a network. The central difficulty is that the participants do not share reliable memory, do not necessarily share a perfectly synchronized clock, and can fail independently.

This learning artifact models those conditions through executable implementations in Python, JavaScript, C++, Java, and PostgreSQL.

The implementations deliberately approach the subject from different technical perspectives:

| Implementation | Primary perspective |
|---|---|
| Python | Progressive simulation of distributed mechanisms |
| JavaScript | Asynchronous and event-driven distributed behavior |
| C++ | Replicated payment-processing case study |
| Java | Enterprise-oriented distributed order service |
| SQL | Durable relational model for distributed state and coordination |

The examples cover message passing, logical time, replication, quorum decisions, failure detection, leader election, retries, idempotency, partition behavior, consistent hashing, tracing, and eventual consistency.

## What Makes a System Distributed

A distributed system contains independently executing components that cooperate through communication rather than through a single shared process.

A useful model is:

`Client → Service A → Service B → Service C`

Each service can have its own process state, memory, clock, failures, and execution timing.

The network introduces uncertainty. A message can arrive late, arrive twice, arrive out of order, or never arrive. A process can crash after receiving a request but before responding. A machine can be reachable from one part of a cluster but unreachable from another.

These conditions distinguish distributed-system engineering from ordinary single-process programming.

The Python `Node` and JavaScript `DistributedNode` classes model independent participants. The C++ payment replicas and Java order replicas model replicated service state. The SQL schema persists the same concepts as relational entities.

## Message Passing

Communication between distributed components is normally expressed through messages or requests.

The Python implementation represents a message with sender, receiver, type, payload, and message identifier. A node advances its logical clock before sending. The receiving node incorporates the sender's clock when processing the message.

The JavaScript implementation uses a `MessageBus` with asynchronous delivery. This makes the network boundary explicit and demonstrates a behavior that is fundamental to distributed systems: the sender cannot assume that the receiver processes the message immediately.

The JavaScript implementation also allows communication paths to be blocked. This models a network failure without requiring real network infrastructure.

A distributed request therefore has two separate concerns:

- The application operation itself must be correct.
- The communication mechanism must tolerate uncertainty around delivery.

## Partial Failure

A single-process application often fails as a whole when its process terminates. A distributed system can experience partial failure.

For example:

`node-a = online`

`node-b = online`

`node-c = offline`

The remaining nodes may still be capable of serving requests.

The Python quorum store demonstrates this by allowing one replica to become unavailable while continuing to operate with the remaining majority. When enough replicas become unavailable, the operation fails because the configured quorum cannot be reached.

The Java and C++ implementations use explicit node state to distinguish `ONLINE` and `OFFLINE`.

The SQL model stores node state as `ONLINE`, `OFFLINE`, or `SUSPECTED`. This distinction matters because a failure detector normally observes symptoms rather than directly observing whether a remote process has crashed.

## Logical Time

Physical clocks are not sufficient for determining the causal ordering of distributed events.

Suppose service A sends a request to service B. A local clock on each machine may report different physical times. A logical clock can instead represent the ordering relationship created by communication.

The Python implementation uses a Lamport clock.

A local event increments the clock:

`C = C + 1`

When a node receives a message carrying remote timestamp `R`, it updates its clock using:

`C = max(C, R) + 1`

This establishes an ordering compatible with message causality.

The Java and C++ implementations apply the same principle through explicit `LogicalClock` objects.

Logical time should not be confused with real-world time. A Lamport timestamp is useful for ordering events but does not tell an operator that an event occurred at a particular physical instant.

## Vector Clocks

A Lamport clock cannot distinguish every form of concurrency.

The Python implementation therefore includes vector clocks. A vector clock stores one logical counter for each participating node.

For two nodes A and B, a vector can look like:

`{A: 3, B: 1}`

and another can be:

`{A: 2, B: 4}`

Neither vector is less than or equal to the other across every component, so the events are concurrent.

This distinction becomes important in replicated systems where independent nodes can modify state during a communication failure.

Vector clocks provide more causal information than a single Lamport counter, but they also require more metadata. The metadata grows with the number of tracked participants unless a system uses techniques to control its size.

## Replication

Replication stores multiple copies of information across independent nodes.

The C++ case study stores payment records in multiple replicas. The Java implementation stores orders in multiple `OrderReplica` objects. The Python implementation provides a generic replicated key-value store.

Replication can improve availability because the failure of one copy does not necessarily make the data unavailable.

Replication also creates new problems:

- Copies can become temporarily inconsistent.
- Updates must be propagated.
- A failed node may recover with stale state.
- Conflicting updates require a defined resolution strategy.
- The system must determine when enough replicas have acknowledged an operation.

Replication therefore does not mean that every copy is automatically consistent at every instant.

## Quorums

A quorum defines the minimum number of replica responses required for an operation.

For three replicas, a majority quorum is two.

The Python, C++, JavaScript, and Java implementations use this pattern. The SQL implementation stores the replication factor, read quorum, and write quorum in `quorum_policies`.

For a system with replication factor `N`, read quorum `R`, and write quorum `W`, a common design considers whether:

`R + W > N`

This overlap can make it possible for a successful read quorum and successful write quorum to share at least one replica.

The exact consistency guarantees depend on the complete protocol, failure model, conflict handling, and read/write semantics. Quorum arithmetic alone is not a complete consistency model.

## Leader Election

Some distributed architectures require a coordinator or leader.

The Python and JavaScript implementations use a simplified highest-live-node election. The C++ and Java systems also select a leader from currently available nodes.

The purpose of the example is to demonstrate the state transition:

`leader failure → election → new leader`

Leader election is not the same as consensus. A simple election algorithm does not automatically prevent an old leader from continuing to act after losing authority.

Production consensus protocols introduce terms, epochs, voting rules, durable state, quorum requirements, and mechanisms that prevent stale leaders from safely committing conflicting decisions.

The Java `LeaderService` keeps leadership as an explicit domain state rather than hiding it inside arbitrary conditionals.

## Failure Detection

A distributed system cannot directly observe a remote process's internal state.

The usual approach is to use evidence such as heartbeats.

A node periodically reports:

`I am alive at time T`

If no heartbeat is observed within a configured timeout, another component may mark the node as suspected.

The Python `FailureDetector`, JavaScript `HeartbeatMonitor`, Java `FailureDetector`, and PostgreSQL `heartbeat_events` table model this mechanism.

The important limitation is that a timeout does not prove that the node crashed.

The same symptom can occur because of:

- network congestion
- packet loss
- overloaded processes
- long garbage-collection pauses
- scheduling delays
- network partitions

This is why distributed failure detectors are generally better described as suspicion mechanisms.

## Retries

A network timeout creates an ambiguity:

`Did the operation fail, or did the response fail to arrive?`

A client may retry because it cannot distinguish these cases.

The JavaScript implementation includes exponential backoff. The delay increases after repeated failures, reducing the risk that a large collection of clients will immediately retry together and overload a recovering service.

A simplified sequence is:

`attempt → failure → short delay → retry → longer delay → retry`

Retries must be combined with operation semantics. Retrying a read is often different from retrying a payment, order creation, or inventory reservation.

## Idempotency

An idempotent operation produces the same intended effect when the same request is delivered multiple times.

The Python `PaymentService`, JavaScript `IdempotentCommandProcessor`, C++ `IdempotencyRegistry`, and Java `IdempotencyService` all use request identifiers to recognize duplicate requests.

The SQL implementation makes `idempotency_key` unique.

A typical workflow is:

`request arrives`

`check idempotency key`

`existing result → return existing result`

`new key → perform operation → record result`

This protects against duplicate application effects caused by client retries.

The key must be generated and managed carefully. A random identifier that changes on every retry does not provide idempotency because the server sees every retry as a new operation.

## Network Partitions

A partition occurs when groups of nodes cannot communicate even though the individual processes may still be running.

The Python `PartitionedCluster` separates nodes into communication groups.

For example:

`A ↔ B`

`C ↔ D`

while:

`A ↛ C`

and:

`B ↛ D`

A partition creates a central distributed-systems problem: different parts of the system may believe they are able to continue operating.

A system must therefore define what happens when communication is lost. Some designs prefer availability and allow divergent state. Others reject operations that cannot obtain sufficient coordination.

The appropriate decision depends on the application's consistency requirements.

## Eventual Consistency

Eventual consistency permits replicas to temporarily disagree while requiring them to converge when updates propagate and no new conflicting updates continue.

The Python example uses a last-write-wins register as a simple conflict-resolution mechanism.

The important design point is that the conflict rule is part of the data model.

Possible domain-specific strategies include:

- last-write-wins
- version-based resolution
- merge functions
- application-specific reconciliation
- conflict records requiring human or service-level resolution

Last-write-wins is convenient but can discard an update that is semantically important. A timestamp-based rule also depends on how timestamps are defined and compared.

## Consistent Hashing

Distributed caches and partitioned key-value systems need a method for mapping keys to nodes.

The Python and JavaScript implementations use a simplified consistent-hashing ring.

Without consistent hashing, adding one node to a simple modulo-based scheme can remap a large proportion of keys.

Consistent hashing places nodes and keys into the same logical token space. Adding a node primarily affects keys in the new node's ownership range.

Virtual nodes improve distribution by assigning multiple positions to each physical node.

The Python implementation exposes `add_node`, `remove_node`, and `owner`. The JavaScript implementation provides equivalent behavior through `HashRing`, while using a JavaScript-specific implementation based on SHA-256 strings.

## Distributed Tracing

A request can cross multiple services:

`gateway → order-service → inventory-service → payment-service`

A single application log is not enough to understand the complete request path.

The Python and JavaScript implementations represent trace spans with:

- trace identifier
- span identifier
- parent span
- service
- operation
- duration

The parent-child relationship reconstructs the request tree.

Tracing helps identify whether latency originates at the gateway, an internal service, a database call, or another remote dependency.

Tracing is also valuable when a request partially succeeds. The trace can reveal which operation completed before a later failure occurred.

## Python Implementation

The Python program is a broad executable simulation of distributed-system fundamentals.

Its `Node` and `Message` classes demonstrate message passing and logical-clock updates.

`LamportNode` demonstrates logical ordering without relying on synchronized physical clocks. `VectorClock` extends the model to identify concurrent events.

`FailureDetector` represents heartbeat-based failure suspicion, while `BullyElection` demonstrates a simplified leader-election mechanism.

`QuorumStore` combines replication with majority read and write requirements. It explicitly rejects writes when too few replicas are available.

`PaymentService` demonstrates idempotent retry handling. A repeated request identifier returns the existing result rather than applying the charge twice.

`ConsistentHashRing` demonstrates partitioning of keys across distributed nodes. `Tracer` models parent-child request spans. `PartitionedCluster` represents communication loss between node groups.

The `DistributedOrderService` combines several mechanisms into one small service model, including leader failure, replication, quorum checks, and idempotent order creation.

The program also validates distributed configuration parameters so that impossible quorum settings are rejected before use.

## JavaScript Implementation

The JavaScript implementation emphasizes asynchronous and event-driven behavior.

`MessageBus` provides an explicit communication boundary. The `send` method uses asynchronous delivery, which is a natural fit for Node.js.

`DistributedNode` updates a logical clock during message exchange.

The `retry` function demonstrates asynchronous exponential backoff. It does not assume that every failure should be retried and accepts a retry-policy predicate.

`IdempotentCommandProcessor` shows how asynchronous service calls still require deterministic duplicate-request handling.

`QuorumReplicatedStore` provides replicated state and quorum checks. Its availability controls make it possible to simulate individual replica failures.

`ElectionCluster` demonstrates a simplified leader transition, while `HeartbeatMonitor` models timeout-based suspicion.

The JavaScript `HashRing` uses SHA-256 from Node's built-in `crypto` module. `TraceCollector` models distributed spans without introducing an external tracing dependency.

The JavaScript design therefore focuses on the relationship between distributed behavior and asynchronous execution rather than simply translating the Python classes.

## C++ Case Study

The C++ program models a replicated payment-processing platform.

`DistributedNode` contains a Lamport clock and records local and received events. This gives the payment platform a mechanism for representing causal ordering.

`Replica` owns a node and a collection of payment records. Each payment contains a version and writer identity.

`QuorumReplicatedPaymentStore` distributes a payment across currently online replicas. A write is accepted only when the number of acknowledgements reaches a majority.

The case study intentionally demonstrates a partial failure. One replica is taken offline, and the system continues because two of three replicas can satisfy the majority. A second replica is then disabled, making the majority unavailable.

`LeaderElection` provides a coordinator and selects the highest-priority live node. When the leader fails, another node is elected.

`FailureDetector` stores heartbeat timestamps and reports suspicion after the configured timeout.

`IdempotencyRegistry` prevents the same payment request from being applied repeatedly.

The C++ implementation uses strong typing through `enum class`, `optional`, encapsulation, and exception-based failure reporting. These choices make invalid states and unavailable operations explicit.

The case study does not claim that a simple majority election is a production consensus algorithm. Real systems require stronger protection against stale leaders, split-brain behavior, concurrent elections, and durable coordination state.

## Java Implementation

The Java implementation models an enterprise order service using explicit domain types.

`NodeState` represents node availability, while `OrderStatus` models order lifecycle state.

The `Order` record makes the core order data immutable. Its compact constructor validates identifiers, amounts, and versions before an object can exist.

`LogicalClock` handles local and received event ordering.

`OrderReplica` separates replicated storage from the service coordinator. It uses version comparison when deciding whether incoming replicated state supersedes existing state.

`QuorumPolicy` represents replication and quorum requirements as a domain object. Its methods explicitly answer whether a set of responses is sufficient for a read or write.

`FailureDetector` uses `Instant` and `Duration`, which keeps physical heartbeat timing separate from logical event ordering.

`LeaderService` represents cluster leadership as a distinct domain concern. It does not mix leader state with order persistence.

`IdempotencyService` provides duplicate-request recognition.

`DistributedOrderService` combines these abstractions. It validates requests, obtains a leader, creates a versioned order, replicates it, checks the write quorum, and records successful request identifiers.

The example then fails the leader, elects another node, continues with one unavailable replica, and finally demonstrates quorum failure when too many replicas are unavailable.

## SQL Data Model

The PostgreSQL implementation treats distributed-system state as durable relational data.

`cluster_nodes` stores membership, region, priority, health state, and heartbeat information.

`leader_elections` records elected nodes and election terms. This provides durable history rather than keeping leader state only in application memory.

`operations` stores client requests and logical versions. Its unique `request_id` and `idempotency_key` constraints prevent duplicate operation records.

`orders` stores the authoritative business object and references both the writer node and originating operation.

`order_replicas` represents copies of an order on individual nodes. Its unique `(order_id, node_id)` constraint prevents duplicate replica rows for the same order and node.

`quorum_policies` stores replication factors and read/write quorum thresholds. Database constraints ensure that quorum values remain within the configured replication factor.

`idempotency_records` provides a durable duplicate-request lookup.

`distributed_events` stores logical clocks and optional parent events. This allows an event sequence to be inspected independently of physical timestamps.

`heartbeat_events` preserves failure-detection evidence.

The SQL script also defines views for leader state, replication health, and quorum eligibility. These views turn low-level relational state into operational queries without duplicating the source data.

## Database Integrity

The SQL implementation deliberately places important invariants inside the database.

Positive amounts are enforced with `CHECK` constraints.

Order statuses are restricted to known values.

Foreign keys prevent references to nonexistent nodes, operations, or orders.

Unique constraints protect request identifiers and idempotency keys.

Replica uniqueness prevents the same order from being registered twice on the same node.

These constraints are valuable in distributed applications because application-level validation alone can race when multiple service instances execute concurrently.

Database constraints do not replace distributed coordination, but they provide a strong local integrity boundary.

## Transaction Boundaries

The SQL script uses a transaction around initial operation registration, order creation, idempotency recording, and replica registration.

The transaction provides atomicity within the PostgreSQL database.

This distinction matters: a database transaction does not automatically create an atomic distributed transaction across independent databases.

If three physical databases are involved, a local PostgreSQL transaction cannot by itself guarantee that all three databases commit together.

The application must therefore define a replication protocol, retry behavior, recovery process, or consensus mechanism appropriate to the system's requirements.

## Quorum Failure

With three replicas and a write quorum of two:

`3 online → write possible`

`2 online → write possible`

`1 online → write rejected`

The SQL `quorum_eligibility` view exposes this state from database records.

The Python, C++, and Java implementations enforce equivalent conditions in application memory.

The important point is that quorum availability is a system property at a particular moment. A node becoming reachable after an operation does not retroactively make an unavailable quorum available at the time the operation was attempted.

## Stale Replicas

A replica can be online but stale.

This is different from a failed replica.

An online replica may respond to a read while holding an older version. The SQL `order_replication_health` view counts current replicas separately from total replicas.

The same distinction appears in the application implementations through version numbers.

A production system needs a defined repair mechanism. When a stale node returns, it may need to obtain missing state from another replica before it is considered fully current.

## Retry and Duplicate Execution

A timeout after a successful server-side operation is one of the most important distributed failure scenarios.

Consider:

`client → server`

`server commits operation`

`server → response`

If the response is lost, the client cannot know whether the operation committed.

A retry can therefore execute the same logical request again.

The implementations use idempotency keys to distinguish:

`new operation`

from:

`retry of an existing operation`

This is especially important for operations such as payments, order creation, reservations, and resource provisioning.

Idempotency should be designed as part of the API contract rather than added only after retry-related incidents occur.

## Consistency Versus Availability

Distributed systems often require explicit decisions about what should happen when communication fails.

If an application continues serving writes from isolated partitions, different replicas may accept conflicting updates.

If an application refuses operations without sufficient coordination, availability decreases during partitions.

Neither choice is universally correct.

A payment ledger, inventory reservation system, collaborative editor, cache, and analytics pipeline can have very different consistency requirements.

The correct architecture follows from the semantics of the data and the consequences of conflicting state.

## Performance Considerations

Distributed communication introduces latency because a request may depend on remote nodes.

A quorum write can require several network round trips. Larger replication factors increase storage and propagation work.

Consistent hashing reduces the amount of data that needs to move when nodes join or leave a partitioned key space.

Logical clocks add metadata but help establish event ordering.

Tracing adds observability overhead but makes distributed latency diagnosable.

Retries can increase load during an outage. Exponential backoff reduces synchronized retry pressure but does not eliminate overload by itself.

The most useful performance measurements are normally based on actual system behavior: request latency, error rate, replication lag, quorum failures, retry volume, queue depth, and resource utilization.

## Security Considerations

Distributed communication should not be assumed to be trustworthy merely because nodes belong to the same internal network.

Production deployments should authenticate service identities and protect traffic in transit.

Authorization should determine which services may perform particular operations.

Idempotency keys and request identifiers should not expose confidential business information.

Operational logs and distributed traces can contain customer identifiers or transaction details, so observability data requires appropriate access controls and retention policies.

Leader and membership changes are security-sensitive because an unauthorized participant must not be able to impersonate a legitimate coordinator.

## Common Failure Modes

### Duplicate requests

A client retries after a timeout and unintentionally performs the operation twice. Idempotency records prevent this when the same logical request identifier is reused.

### Stale reads

A client reads from a replica that has not received the latest update. Version-aware replication and appropriate read policies are required when stale data is unacceptable.

### False failure suspicion

A slow network or overloaded node misses its heartbeat deadline. The system suspects failure even though the process is still running.

### Split brain

Different node groups believe they can act as coordinator after losing communication. Stronger election and consensus mechanisms are required to prevent conflicting authority.

### Retry storms

Many clients retry at the same time after a service disruption. Exponential backoff and bounded retry policies reduce synchronized pressure.

### Replica divergence

A node falls behind while offline. Recovery requires state synchronization before it can safely be treated as current.

### Hidden partial failure

A service successfully completes an internal operation but fails before returning the response. The client sees failure while the server has already changed state.

## Debugging Distributed Behavior

Debugging requires more than examining one process.

A useful diagnostic model connects:

`request ID → service trace → node events → logical ordering → replica state → failure evidence`

The implementations provide different parts of this model.

Request identifiers make retries traceable.

Logical clocks provide event-ordering information.

Distributed traces show service relationships.

Replica versions expose stale state.

Heartbeat records show when failure was suspected.

Quorum calculations explain why an operation was accepted or rejected.

Without these relationships, distributed failures can appear nondeterministic even when the underlying sequence of events is understandable.

## Architectural Relationship

The major mechanisms demonstrated by the six deliverables form a connected system:

`Client request`
→ `idempotency`
→ `leader/coordinator`
→ `replicated write`
→ `quorum`
→ `logical event`
→ `replica state`
→ `response`

Failure can occur at almost every boundary.

A client can retry.

A coordinator can fail.

A replica can become unavailable.

A network path can partition.

A heartbeat can be delayed.

A response can be lost after the state change.

Distributed-systems design is therefore less about eliminating failure and more about defining what the system does when failure occurs.

## Practical Boundary of the Examples

The programs intentionally use in-memory simulations or a single PostgreSQL database. They demonstrate distributed-system mechanisms without pretending to implement a production consensus protocol, service mesh, broker, or multi-database transaction coordinator.

A real distributed platform would need durable coordination, authenticated service communication, carefully defined consistency semantics, persistent recovery procedures, observability, capacity planning, deployment topology, and rigorous testing under failures.

The core mechanisms in these implementations provide the conceptual foundation for understanding those larger systems.
