# Kafka Architecture: Messaging, Replication, Consumer Groups, and Fault Tolerance

## Technical Scope

This project models a Kafka-style distributed messaging system through five independent implementations:

| Implementation | Primary perspective |
|---|---|
| Python | In-memory Kafka cluster and workflow simulation |
| JavaScript | Event-driven broker and consumer-group model |
| C++17 | Repository-independent governance and merge-eligibility style engine for messaging availability |
| Java 17 | Enterprise domain model with policies, immutable records, services, and explicit state |
| PostgreSQL | Persistent relational representation of brokers, topics, partitions, replicas, messages, consumers, offsets, and health |

The implementations focus on four related but distinct mechanisms:

1. **Messaging** defines how records are produced, partitioned, stored, and consumed.
2. **Kafka architecture** defines brokers, topics, partitions, leaders, replicas, and high-watermark behavior.
3. **Replication** provides multiple copies of partition logs and determines whether writes can continue when brokers fail.
4. **Consumer groups** distribute partitions among consumers and maintain committed offsets so processing can resume after reassignment.

The relationship can be represented as:

Repository-like messaging domain
→ Brokers
→ Topics
→ Partitions
→ Leaders and Replicas
→ Messages
→ Consumer Groups
→ Partition Assignments
→ Committed Offsets
→ Failure Detection
→ Leader Election
→ Continued Consumption

## Messaging Model

A message contains a topic, partition, offset, key, value, timestamp, and the broker that acted as leader when the record was written.

The key determines the partition. Each implementation uses a deterministic key-to-partition calculation so messages for the same key are directed to the same partition within a topic.

A partition is an append-only sequence:

`partition-0: offset 0 → offset 1 → offset 2 → offset 3`

Offsets are scoped to a partition. Offset `5` in partition `0` is different from offset `5` in partition `1`.

The examples use order events because keyed ordering is meaningful. A customer key such as `customer-100` consistently selects one partition, allowing records associated with that key to preserve partition-local ordering.

## Kafka Architecture

A topic is divided into partitions to provide parallelism.

For example:

`orders`
→ `partition 0`
→ `partition 1`
→ `partition 2`

Each partition has replicas distributed across brokers:

`orders[0] → broker 1, broker 2, broker 3`

One replica is the current leader. Producers write through the leader. Replicas maintain copies of the partition log.

The model deliberately separates:

- topic configuration
- partition metadata
- replica placement
- leader state
- message storage
- consumer assignments
- committed offsets

This separation prevents partition identity from being confused with broker identity.

## Replication

Replication factor three means a partition has three configured replicas.

A simplified replica layout is:

`orders[0] → B1 leader, B2 replica, B3 replica`

`orders[1] → B2 leader, B3 replica, B1 replica`

`orders[2] → B3 leader, B1 replica, B2 replica`

The implementations use a minimum in-sync replica requirement of two.

Therefore:

`online replicas >= min.insync.replicas`

is required for an accepted write.

With three replicas:

| Online replicas | Minimum ISR | Write |
|---:|---:|---|
| 3 | 2 | Accepted |
| 2 | 2 | Accepted |
| 1 | 2 | Rejected |
| 0 | 2 | Rejected |

This demonstrates an important fault-tolerance trade-off. Replication protects data availability against individual broker failures, while `min.insync.replicas` prevents successful writes when the configured durability threshold cannot be maintained.

The simulation does not claim to reproduce every internal Kafka replication mechanism. It specifically models the architectural relationship among leaders, replicas, broker availability, and write eligibility.

## Leader Failure and Failover

When a leader broker becomes unavailable, the implementations search the partition's configured replicas for an online broker and promote an available replica.

The transition is:

`B1 leader`
→ `B1 offline`
→ `B2 eligible replica`
→ `B2 leader`

The high-watermark and replicated message log remain associated with the partition rather than the failed broker.

This is important because the partition is the logical storage unit. A broker is a physical participant in that storage.

The examples also demonstrate recovery:

`broker failure`
→ `leader election`
→ `write eligibility check`
→ `continued processing`
→ `broker recovery`

## Consumer Groups

A consumer group represents cooperating consumers that collectively process a topic.

For a topic with three partitions:

`orders[0]`
`orders[1]`
`orders[2]`

two active consumers can receive assignments such as:

`worker-1 → partition 0`

`worker-2 → partition 1, partition 2`

A partition is assigned to one active consumer within a group at a time in the simplified model.

If a consumer becomes inactive, the group is rebalanced:

`worker-1 → inactive`

`partition 0 → reassigned`

The consumer group therefore provides horizontal processing capacity without requiring every consumer to process every partition.

Different consumer groups can independently consume the same topic because each group maintains its own committed offsets.

## Offset Management

The implementations distinguish the current polling position from the committed position.

A consumer may read:

`offset 0`
`offset 1`
`offset 2`

and then commit:

`next offset = 3`

The committed value represents the next record that should be considered available for that consumer group after successful processing.

Offsets are stored per:

`group + topic + partition`

The PostgreSQL implementation enforces monotonicity so that an offset cannot accidentally move backward.

This models an important failure scenario. If processing succeeds but the offset is not committed, a later consumer may read the message again. If the offset is committed before processing succeeds, a failure can cause the message to be skipped. Correct processing therefore requires deliberate coordination between message handling and offset commits.

## Python Implementation

The Python program implements a complete in-memory cluster.

The main domain objects are:

- `Broker`
- `Partition`
- `Topic`
- `Message`
- `Consumer`
- `KafkaCluster`

`KafkaCluster` manages topic creation, deterministic partition selection, message publication, replication, leader election, consumer registration, group rebalancing, polling, offset commits, broker failures, and state export.

Python `dataclasses` provide explicit domain records. Enums represent broker and consumer states. Dictionaries provide indexed access to brokers, topics, consumers, and committed offsets.

The `publish()` operation:

1. selects a partition from the message key;
2. verifies the leader;
3. elects a new leader if necessary;
4. calculates online replicas;
5. checks the minimum ISR requirement;
6. creates the message with the next partition offset;
7. appends the record to every online replica;
8. advances the partition high watermark.

The consumer workflow separates `poll()` and `commit_offsets()` so the difference between fetching data and acknowledging progress remains explicit.

The demo also exports cluster state to `kafka_cluster_state.json`.

## JavaScript Implementation

The JavaScript implementation emphasizes Node.js event-driven behavior.

`KafkaCluster` extends `EventEmitter` and emits events for:

- topic creation
- message publication
- leader changes
- consumer joins
- group rebalancing
- broker state changes
- committed offsets

The consumer polling method is asynchronous and yields through the Node.js event loop before returning its batch.

JavaScript `Map` and `Set` structures are used for broker registries, topic metadata, consumer groups, subscriptions, and assignments.

The event-driven model makes operational state changes observable without embedding logging logic into every domain operation.

The implementation also uses `structuredClone()` for message values and cryptographic hashing for deterministic partition selection.

The resulting architecture is intentionally different from the Python implementation: Python emphasizes object-oriented simulation and state export, while JavaScript emphasizes event emission and asynchronous processing.

## C++17 Implementation

The C++17 program presents the messaging system as a strongly typed systems-oriented engine.

The central class is `KafkaGovernanceEngine`.

The domain uses:

- `struct` for compact records
- `enum class` for state values
- `std::map` for deterministic indexed storage
- `std::vector` for append-only logs and assignments
- `std::set` for consumer subscriptions
- custom exception classes for configuration, availability, and offset failures

The implementation explicitly models broker failure and leader election.

`minInSyncReplicas_` is treated as a write-admission policy. A publish operation is rejected when the available replica count falls below the configured threshold.

This makes the durability policy explicit rather than embedding it in message publication code.

The C++ implementation also demonstrates the systems-level trade-off between deterministic data structures and implementation complexity. `std::map` is used where predictable ordered traversal is useful, while vectors represent sequential partition logs.

## Java 17 Implementation

The Java implementation uses an enterprise-style domain structure.

Records represent immutable value objects:

- `Message`
- `PartitionKey`
- `Assignment`
- `BrokerSnapshot`

Classes represent mutable domain entities such as brokers, partitions, topics, consumers, and the cluster.

The `ReplicationPolicy` interface separates policy from infrastructure. `MinimumInSyncReplicaPolicy` implements the decision that determines whether a write can proceed.

This separation allows the cluster to ask:

`Is this write allowed under the current replication policy?`

without embedding policy logic into the storage implementation.

The consumer-group service performs explicit assignment and rebalancing. Java Streams are used for filtering and ordering eligible consumers and partitions.

Custom exceptions distinguish configuration failures, broker availability failures, and offset errors.

This structure is suitable for enterprise applications because domain behavior, policy evaluation, state transitions, and persistence-oriented concepts remain separate.

## PostgreSQL Data Model

The PostgreSQL implementation translates the messaging architecture into relational structures.

Core relationships are:

`brokers`
→ physical messaging nodes

`topics`
→ logical streams

`topic_partitions`
→ ordered partitions belonging to topics

`partition_replicas`
→ broker placement for each partition

`messages`
→ persisted message records

`consumer_groups`
→ independent consumption contexts

`consumers`
→ members of consumer groups

`consumer_subscriptions`
→ topics a consumer group member can process

`consumer_assignments`
→ current partition ownership

`committed_offsets`
→ group-specific progress

`message_processing`
→ processing state for individual messages

`status_checks`
→ operational partition checks

Foreign keys preserve these relationships at the database level.

## Database Integrity

Several important rules are enforced directly by PostgreSQL.

Partition identifiers must belong to configured topics.

Replica rows must reference existing partitions.

Message offsets must be non-negative.

A partition's high watermark is automatically advanced by a trigger after message insertion.

Committed offsets cannot move backward because a trigger checks the existing value before accepting an update.

The `publish_message()` function checks the current number of online replicas against the topic's `min_insync_replicas` requirement before inserting a message.

This means the database can reject an unsafe write rather than relying entirely on application code.

## PostgreSQL Transaction Model

The sample publication workflow uses transactions.

A successful transaction contains:

`BEGIN`
→ message publication
→ message publication
→ message publication
→ `COMMIT`

A failed transaction can be rolled back without exposing a partially completed operation.

The broker failure example changes broker state and leader assignment within a transaction so the metadata transition is atomic.

## Consumer Lag

Consumer lag is derived from the difference between the partition high watermark and the group's committed offset.

Conceptually:

`lag = max(high_watermark + 1 - committed_offset, 0)`

A high lag value indicates that the consumer group has not committed progress through the available partition records.

The PostgreSQL `consumer_lag_report` view exposes this relationship directly.

This is distinct from broker health. A healthy broker cluster can still have a slow consumer group.

## Fault Tolerance

The implementations cover several failure conditions.

### Single Broker Failure

With replication factor three and minimum ISR two:

`B1 fails`
→ replicas remain on B2 and B3
→ a replica can become leader
→ writes remain possible

### Multiple Broker Failure

If only one replica remains online:

`online replicas = 1`
`min ISR = 2`

the write is rejected.

This prevents the simulation from treating mere leader availability as equivalent to sufficient replication.

### Consumer Failure

When one consumer becomes inactive, its partitions are reassigned to active members of the same group.

The committed offsets remain associated with the group rather than the consumer instance.

This allows a replacement consumer to continue from the group's stored progress.

### Offset Regression

A commit that attempts to move from a later offset to an earlier offset is rejected.

This protects the logical monotonic progression of a consumer group's checkpoint.

## Failure Boundaries

The system distinguishes several kinds of failure:

| Failure | Primary mechanism |
|---|---|
| Unknown topic | Configuration validation |
| Invalid partition | Partition lookup validation |
| Empty message key | Producer validation |
| Failed broker | Leader election |
| Insufficient replicas | Write rejection |
| Inactive consumer | Consumption rejection |
| Consumer departure | Group rebalance |
| Offset regression | Commit validation |
| Missing database relationship | Foreign key |
| Invalid partition metadata | Trigger validation |

These failures are deliberately handled at the layer that owns the relevant invariant.

## Security Considerations

The implementations are local architectural models and do not attempt to implement network authentication or production Kafka authorization.

The relevant security boundaries are still represented conceptually.

Message keys and values are validated before storage.

The PostgreSQL schema uses foreign keys and constraints to prevent invalid relationships.

Broker and consumer state changes are explicit operations rather than arbitrary field mutations.

Production deployments would need authentication, authorization, encrypted transport, encrypted storage where required, secret management, audit logging, network controls, and carefully scoped administrative permissions.

The examples do not store credentials or connection secrets.

## Performance Considerations

Partitioning is the primary scaling mechanism.

Publishing and consuming can proceed independently across partitions.

The PostgreSQL message table has an index on:

`topic_id, partition_id, message_offset`

This supports ordered partition reads.

Consumer assignments and committed offsets also have targeted indexes for partition-oriented queries.

The in-memory implementations use dictionaries, maps, and sets to avoid repeated linear searches for common metadata operations.

The simplified simulations replicate a message to all online replicas synchronously. Real Kafka implementations use more sophisticated replication protocols, batching, network transfer, disk I/O, fetch cycles, and broker-level coordination.

The simulations therefore prioritize architectural clarity rather than reproducing Kafka's complete internal implementation.

## Architectural Distinctions

The four major concepts should not be treated as synonyms.

| Concept | Responsibility |
|---|---|
| Messaging | Records moving through topics and partitions |
| Kafka architecture | Brokers, topics, partitions, leaders, and replicas |
| Replication | Multiple copies of partition data and availability policy |
| Consumer groups | Parallel consumption and group-specific progress |

A producer does not directly define consumer-group membership.

A consumer group does not define replication.

Replication does not determine the business meaning of a message.

A partition is not the same thing as a broker.

A committed offset is not the same thing as a message offset.

These distinctions are essential when reasoning about distributed messaging systems.

## State Flow

The implemented workflow is:

`Producer`
→ `Topic`
→ `Partition Selection`
→ `Leader`
→ `Replica Append`
→ `High Watermark`
→ `Consumer Group`
→ `Partition Assignment`
→ `Poll`
→ `Processing`
→ `Offset Commit`

A failure can interrupt this path:

`Broker Failure`
→ `Leader Election`
→ `ISR Evaluation`
→ `Write Allowed or Rejected`

A consumer failure follows a different path:

`Consumer Failure`
→ `Group Membership Change`
→ `Rebalance`
→ `Partition Reassignment`
→ `Resume from Committed Offset`

## Practical Edge Cases

The implementations deliberately address:

- empty topic names
- duplicate topics
- invalid replication factors
- invalid partition counts
- unknown topics
- invalid partitions
- inactive consumers
- unknown consumers
- insufficient online replicas
- broker failure during leadership
- consumer reassignment
- offset regression
- empty message keys
- invalid message values
- missing relational references
- partition metadata outside configured bounds

These cases represent operational boundaries rather than decorative validation.

## File-Level Responsibilities

| File | Responsibility |
|---|---|
| Python source | Full in-memory Kafka-style workflow and state export |
| JavaScript source | Event-driven and asynchronous messaging model |
| C++17 source | Strongly typed broker, replication, and consumer engine |
| Java 17 source | Enterprise domain model with explicit policies |
| PostgreSQL source | Relational persistence and database-level integrity |

Each implementation models the same architectural subject while emphasizing different engineering mechanisms.

## Execution Model

### Python

Requires Python 3.10 or later.

Run the script directly. It creates the in-memory cluster, publishes orders, consumes messages, simulates broker failure, performs leader election, restores the broker, and writes cluster state to `kafka_cluster_state.json`.

### JavaScript

Requires a modern Node.js runtime with support for `structuredClone`, `crypto.randomUUID`, and ES classes.

Run the file with Node.js. The program demonstrates event emission, asynchronous polling, replication, consumer-group assignment, broker failure, and state persistence.

### C++17

Compile with a C++17-compatible compiler.

The program uses only the C++ standard library and runs a complete broker, replication, consumer-group, failure, and offset workflow.

### Java 17

Compile and run with Java 17 or later.

The implementation uses records, streams, immutable collection views, interfaces, custom exceptions, and explicit domain classes without third-party dependencies.

### PostgreSQL

Execute the SQL script in PostgreSQL.

The script creates the `kafka_lab` schema, defines the relational model, inserts operational data, creates triggers and functions, performs transactional operations, and executes reporting queries.

## Limitations

This project is an architectural learning model rather than a full Kafka broker implementation.

It does not implement Kafka's network protocol, controller quorum, log segment files, producer epochs, idempotent producers, transactional producers, rack awareness, ISR fetch protocol, exactly-once semantics, cooperative rebalancing, schema registry integration, ACL enforcement, or production-grade replication timing.

The simplified leader-election model selects the first available replica rather than implementing Kafka's complete controller and replica-state machinery.

The PostgreSQL model represents Kafka metadata and message state relationally. It is not a replacement for Kafka's distributed log storage engine.

These limits are intentional so that the core relationships among messaging, partitions, replication, consumer groups, offsets, and fault tolerance remain directly observable.
