# Kafka Fundamentals: Topics, Partitions, Offsets, and Brokers

## Scope

This project models the core storage and coordination concepts of Apache Kafka through five independent implementations:

| File | Technical perspective | Primary focus |
|---|---|---|
| Python | Object-oriented cluster simulation | Topics, partitions, offsets, consumer groups, failover |
| JavaScript | Event-driven Node.js model | Asynchronous production, events, assignments, offsets |
| C++17 | Systems-oriented implementation | Broker governance, partition logs, replication, failover |
| Java 17 | Enterprise domain model | Explicit services, records, policies, state transitions |
| PostgreSQL | Relational representation | Cluster metadata, records, assignments, offsets, health |

The implementations use the same domain concepts while making different engineering choices. The central relationship is:

Repository-style operational thinking is useful for understanding the workflow, but Kafka's actual domain is distributed event streaming:

`Broker Cluster → Topic → Partitions → Records → Offsets → Consumer Groups → Committed Offsets`

The four primary concepts must remain distinct:

- A **topic** is a named logical stream.
- A **partition** is an ordered append-only log inside a topic.
- An **offset** identifies a record position within a partition.
- A **broker** is a Kafka server that stores and serves partitions.

## Kafka Domain Model

A topic is divided into one or more partitions.

```text
orders
│
├── partition 0
│   ├── offset 0
│   ├── offset 1
│   └── offset 2
│
├── partition 1
│   ├── offset 0
│   ├── offset 1
│   └── offset 2
│
└── partition 2
    ├── offset 0
    └── offset 1
```

Partitions are distributed across brokers.

```text
                  Kafka Cluster
                      │
        ┌──────────────┼──────────────┐
        │              │              │
    Broker 1        Broker 2       Broker 3
        │              │              │
     P0 leader       P1 leader      P2 leader
        │              │              │
     P1 replica      P2 replica     P0 replica
```

A record's offset is local to its partition. There is no single offset sequence covering every partition of a topic.

For example:

| Partition | Offset | Key | Value |
|---|---|---|---|
| 0 | 0 | order-1001 | CREATED |
| 0 | 1 | order-1004 | SHIPPED |
| 1 | 0 | order-1002 | PAID |
| 1 | 1 | order-1005 | DELIVERED |

The ordering guarantee applies within an individual partition.

## Topics

A topic provides the logical name used by producers and consumers.

Examples used in the implementations include:

- `orders`
- `payments`
- `audit-events`

A topic configuration normally determines:

- partition count
- replication factor
- retention behavior
- operational state

The Python, JavaScript, C++17, and Java implementations create topics in memory. The PostgreSQL implementation stores topic metadata in `topics`.

A topic should not be confused with a partition. A topic is the logical stream, while partitions provide the physical parallelism and ordering boundaries.

## Partitions

A partition is an ordered log.

Each record receives an offset when it is appended.

```text
Partition 0

offset 0 ── CREATED
offset 1 ── PAID
offset 2 ── PACKED
offset 3 ── SHIPPED
```

The next available offset is represented by the number immediately after the highest stored offset.

If offsets are `0`, `1`, and `2`, the next offset is `3`.

The implementations reject invalid offsets rather than silently accepting them. This matters because consumers use offsets to determine their position in a partition.

Partition selection can use a record key. The Python and JavaScript implementations hash the key, while the Java implementation exposes the strategy through the `PartitionStrategy` interface.

A stable key-based partitioning strategy helps route records with the same key to the same partition, subject to the partition-count configuration.

## Offsets

An offset is a position in one partition.

Consider:

```text
orders-0:
offset 0
offset 1
offset 2

orders-1:
offset 0
offset 1

orders-2:
offset 0
```

`orders-0@2` and `orders-1@2` are not interchangeable. The first identifies a position in partition 0, while the second would identify a position in partition 1.

The implementations distinguish:

- available `nextOffset`
- record offset
- consumer committed offset
- invalid offset

A consumer normally commits the next offset it intends to read rather than the offset of the last successfully processed record.

For example:

```text
Processed record: offset 7
Committed position: 8
```

This makes restart behavior explicit.

## Brokers

A broker is a server responsible for storing and serving partitions.

The implementations represent brokers with:

- broker ID
- hostname
- online/offline state

The cluster models partition leadership. Each partition has a leader broker and a replica list.

Example:

```text
Partition 0
Leader: Broker 1
Replicas: Broker 1, Broker 2
```

The leader is the broker through which normal partition operations are coordinated in the simplified models.

The programs validate leader availability before accepting production or reading records.

## Replication

Replication places copies of a partition on multiple brokers.

For a replication factor of two:

```text
orders-0
   │
   ├── Broker 1
   └── Broker 2
```

Replication improves fault tolerance but does not automatically mean that every replica is equally current or eligible to become leader.

The PostgreSQL implementation explicitly stores replica membership and `in_sync` state in `partition_replicas`.

The C++ and Java models keep replica membership with each partition and select an online replica during simplified leader failover.

A production Kafka deployment also has concepts such as in-sync replicas, acknowledgements, leader election, and controller-driven metadata management. These implementations model the core relationships without pretending to reproduce the full Kafka broker protocol.

## Producers

A producer sends records to a topic.

The basic workflow is:

```text
Producer
   │
   ├── topic
   ├── key
   └── value
        │
        ▼
    partition selection
        │
        ▼
    partition leader
        │
        ▼
    append record
        │
        ▼
    assign offset
```

The implementations validate:

- topic existence
- key presence
- value type
- partition existence
- leader availability
- offset validity where relevant

The Python implementation returns the selected partition and offset.

The JavaScript implementation returns an asynchronous production result and emits `recordProduced` or `recordRejected` events.

The C++ implementation exposes production through a typed cluster service.

The Java implementation uses `KafkaService.publish()` and a dedicated `PartitionStrategy`.

## Partition Selection

When a producer does not explicitly select a partition, a key can determine the partition.

Conceptually:

```text
partition = hash(key) mod partition_count
```

The exact partitioning behavior of a production Kafka client depends on the configured partitioner and client version. The learning implementations use deterministic hash-based selection to make the relationship visible.

Keys are important because they can preserve ordering for records mapped to the same partition.

For example:

```text
customer-42 → partition 1
customer-42 → partition 1
customer-42 → partition 1
```

This provides ordering within that partition for that key.

A partition-count change can affect partition mapping, so key-based routing should not be treated as a universal global-ordering mechanism.

## Consumers

Consumers read records from partitions.

A consumer does not simply ask for "the next record in the topic." It reads from assigned partitions and uses offsets to determine its position.

The simplified workflow is:

```text
Consumer
   │
   ▼
Consumer Group
   │
   ▼
Partition Assignment
   │
   ▼
Committed Offset
   │
   ▼
Fetch Records
   │
   ▼
Process
   │
   ▼
Commit Next Offset
```

The Python, JavaScript, C++, and Java implementations model this workflow explicitly.

## Consumer Groups

A consumer group allows multiple consumers to divide partitions among themselves.

Example:

```text
Topic: orders
Partitions: P0 P1 P2 P3

Group: order-workers

worker-a → P0, P2
worker-b → P1, P3
```

Within a consumer group, a partition is assigned to one consumer at a time in the simplified model.

Adding or removing consumers can cause reassignment.

If there are more consumers than partitions, some consumers may receive no partition:

```text
Partitions: P0 P1
Consumers:  C0 C1 C2

C0 → P0
C1 → P1
C2 → none
```

This is a fundamental scalability boundary.

## Rebalancing

Rebalancing changes partition ownership among consumers.

The implementations use simple round-robin assignment.

The process is represented as:

```text
Before:

worker-a → P0 P1
worker-b → P2

After adding worker-c:

worker-a → P0
worker-b → P1
worker-c → P2
```

The real Kafka consumer-group protocol contains additional coordination and failure-detection behavior. The project isolates the core assignment concept rather than implementing the complete protocol.

The Java implementation gives consumers explicit `ACTIVE` and `REBALANCING` states. This makes the state transition visible as a domain operation.

## Offset Commit Behavior

A committed offset represents the consumer group's durable position.

Suppose a consumer has:

```text
offset 10 → processed
offset 11 → processed
offset 12 → currently processing
```

The committed offset may remain `12`.

If processing succeeds, the consumer can commit `13`.

```text
Committed position: 13
Next record to read: 13
```

The PostgreSQL `committed_offsets` table stores this relationship per consumer group, topic, and partition.

This is deliberately separate from the record itself. The same record can be consumed by different groups with independent positions.

## Multiple Consumer Groups

Consumer groups have independent offsets.

```text
Topic: orders

Group A:
P0 → offset 50

Group B:
P0 → offset 17
```

Both groups can consume the same partition independently.

The PostgreSQL model represents this with the composite key:

`group_id + topic_id + partition_id`

This prevents one application's progress from overwriting another application's progress.

## Broker Failure

A broker can become unavailable.

The simplified failover workflow is:

```text
Broker 1 OFFLINE
       │
       ▼
Find affected leaders
       │
       ▼
Find available replica
       │
       ▼
Elect available replica
       │
       ▼
Continue partition service
```

The Python, JavaScript, C++17, and Java programs demonstrate this behavior.

The PostgreSQL implementation represents failure by changing broker state and then querying partition health.

The example is intentionally simplified. Production Kafka leader election depends on Kafka's controller and metadata mechanisms, replica state, election policy, and cluster configuration.

## Leader and Replica Distinction

A replica is a copy associated with a partition.

The leader is the broker currently responsible for the partition's active leadership role.

Example:

```text
Partition P0

Leader
   └── Broker 1

Replica
   └── Broker 2
```

After a failure:

```text
Broker 1
   └── OFFLINE

Broker 2
   └── becomes leader
```

Replication therefore describes storage relationships, while leadership describes the currently active broker role.

## Python Implementation

The Python implementation uses dataclasses and explicit domain classes:

- `Record`
- `Partition`
- `Topic`
- `Broker`
- `Consumer`
- `ConsumerGroup`
- `KafkaCluster`

`KafkaCluster` coordinates the major operations.

The implementation supports:

- broker registration
- topic creation
- partition creation
- key-based partition selection
- record production
- consumer-group creation
- consumer registration
- round-robin rebalancing
- polling
- offset commits
- broker failure
- leader reassignment
- broker recovery
- retention
- validation failures

Exceptions distinguish validation problems, unavailable brokers, and invalid offsets.

The retention implementation demonstrates that records can be removed according to age. This also illustrates why offsets in a real system should be interpreted together with the available log range.

The script uses only the Python standard library.

## JavaScript Implementation

The JavaScript implementation uses Node.js standard-library functionality and an event-driven architecture.

Important structures include:

- `Map` for brokers, topics, groups, and partitions
- `Set` for consumer assignments
- `EventEmitter` for cluster events
- `Promise` for asynchronous production and polling
- `crypto` for deterministic hash-based partition selection

The cluster emits events for accepted records, rejected records, and broker failures.

This creates a different perspective from the Python implementation. Instead of concentrating on a synchronous object model, the JavaScript version makes operational events observable.

The asynchronous methods also establish a natural boundary for later integration with network or storage operations.

No external npm package is required.

## C++17 Implementation

The C++ implementation treats the cluster as a systems-oriented service.

Important types include:

- `Broker`
- `Record`
- `Partition`
- `Topic`
- `Consumer`
- `ConsumerGroup`
- `MergeEligibilityEngine`

The name `MergeEligibilityEngine` represents a governance-style decision service. Its actual responsibility is Kafka cluster and partition eligibility, not source-code merging.

The implementation uses:

- `std::map` for ordered cluster metadata
- `std::vector` for ordered partition logs
- `std::set` for consumer assignments
- `std::optional` for optional partition selection
- `std::hash` for key-based routing
- custom exception classes
- explicit broker states

The partition log stores records in vector order, making sequential offset access straightforward.

For a partition containing `n` records, obtaining the next offset is constant time. Appending to the vector is amortized constant time. Reading a contiguous range is proportional to the number of returned records.

## Java 17 Implementation

The Java implementation uses explicit enterprise domain types and service boundaries.

Records are used for immutable value-oriented objects such as:

- `Broker`
- `Message`
- `PartitionId`
- `ConsumerAssignment`

The `PartitionStrategy` interface separates partition-selection policy from the Kafka service.

The service layer contains responsibilities for:

- broker registration
- topic creation
- publishing
- consumer groups
- consumer registration
- rebalancing
- polling
- committing offsets
- broker failure
- broker recovery

Consumer state is explicitly represented with `ConsumerState`.

This makes operational transitions visible:

```text
ACTIVE
  │
  ▼
REBALANCING
  │
  ▼
ACTIVE
```

The implementation also uses immutable collections at service boundaries where appropriate, reducing accidental modification of returned domain state.

## PostgreSQL Implementation

The PostgreSQL implementation represents the Kafka model as relational data.

Core tables include:

| Table | Purpose |
|---|---|
| `brokers` | Broker identity, hostname, and state |
| `topics` | Topic configuration |
| `topic_partitions` | Partition identity, leader, and next offset |
| `partition_replicas` | Replica placement and synchronization state |
| `records` | Partition records and offsets |
| `consumer_groups` | Consumer-group identity |
| `consumers` | Consumer membership and state |
| `consumer_assignments` | Partition ownership inside groups |
| `committed_offsets` | Consumer progress |
| `status_checks` | Partition health observations |
| `cluster_policies` | Cluster eligibility requirements |

Composite keys preserve the natural Kafka identity of a partition:

`topic_id + partition_id`

Records use:

`topic_id + partition_id + record_offset`

This correctly models the fact that offsets are unique only within a partition.

## Database-Level Offset Validation

The `validate_record_offset()` trigger checks that a newly inserted record uses the current `next_offset`.

The transaction locks the partition row before updating it.

The sequence is:

```text
Read partition next_offset
        │
        ▼
Validate submitted record_offset
        │
        ▼
Insert record
        │
        ▼
Increment next_offset
```

This prevents arbitrary gaps from being inserted through the database interface.

The trigger does not reproduce Kafka's distributed storage protocol. It provides a relational integrity model for the same logical invariant.

## Consumer Lag

Consumer lag measures the distance between the available partition position and the consumer group's committed position.

The project calculates:

`lag = max(next_offset - committed_offset, 0)`

Example:

```text
Partition next offset: 100
Consumer committed offset: 83

Lag = 17
```

The `consumer_lag` view exposes this value per group, topic, and partition.

Lag is a useful operational signal because it identifies partitions where consumers are not keeping pace with production.

## Health Evaluation

The PostgreSQL function `evaluate_topic_health()` evaluates partition eligibility using:

- leader state
- replica count
- in-sync replica count
- minimum replication policy
- leader availability requirement
- in-sync replica requirement

The decision model is:

```text
Leader online?
      │
      ├── No → Not eligible
      │
      ▼
Enough replicas?
      │
      ├── No → Not eligible
      │
      ▼
Enough in-sync replicas?
      │
      ├── No → Not eligible
      │
      ▼
Eligible
```

This is a governance decision over the modeled cluster state.

## Failure Conditions

The implementations deliberately cover operational failures rather than only successful paths.

Important failures include:

| Failure | Handling |
|---|---|
| Unknown topic | Validation exception |
| Unknown partition | Validation exception |
| Empty message key | Validation exception |
| Invalid offset | Offset exception |
| Offline leader | Broker availability failure |
| Empty consumer group | Rebalance failure |
| Invalid commit position | Commit validation failure |
| Missing broker | Broker configuration failure |
| Invalid replication factor | Topic configuration failure |

These failures are part of the domain model rather than incidental error messages.

## Ordering Guarantees

Kafka provides ordering within a partition, not across all partitions of a topic.

For example:

```text
Partition 0:
A → B → C

Partition 1:
X → Y → Z
```

The ordering relationship between `A` and `X` is not established by the partition logs.

This distinction is critical when designing applications that require ordered events.

A key can be used to place related records into the same partition:

```text
account-42
    │
    ├── DEPOSIT
    ├── BALANCE_UPDATE
    └── WITHDRAWAL
```

If all three events map to the same partition, their partition-local order can be preserved.

## Parallelism

Partitions provide the basic unit of consumer parallelism.

With four partitions:

```text
P0 ── consumer A
P1 ── consumer B
P2 ── consumer C
P3 ── consumer D
```

A fifth consumer cannot independently process a fifth partition because only four partitions exist.

This creates an important design relationship:

`partition count → maximum parallel partition ownership within one consumer group`

Increasing partition count can increase parallelism, but it also affects partition management, storage distribution, ordering boundaries, and key-to-partition mapping.

## Retention

Kafka topics commonly use retention policies to determine how long records remain available.

The Python implementation includes a time-based retention simulation.

Retention should not be confused with consumer acknowledgement.

A consumer committing an offset does not itself mean that the corresponding record is immediately deleted.

Storage retention and consumer progress are separate concepts:

```text
Record lifetime
      │
      ├── controlled by retention policy
      │
Consumer position
      │
      └── controlled by committed offset
```

This distinction is essential when diagnosing replay and data-availability behavior.

## Security Considerations

A production Kafka deployment requires controls beyond this learning model.

Important controls include:

- authenticated broker and client connections
- TLS encryption
- authorization through Kafka ACLs or equivalent policy controls
- controlled broker administration
- restricted topic creation
- protected consumer-group access
- secure credential handling
- audit logging
- network segmentation
- controlled replication configuration

The implementations do not claim to implement Kafka authentication or authorization protocols.

Their security-oriented validation focuses on preventing invalid state transitions and malformed operations inside the simulated domain.

## Performance Considerations

Partitioned logs are effective because sequential append and sequential consumption can be implemented efficiently.

The in-memory implementations use arrays or vectors for partition records. Sequential append is amortized constant time, while fetching `k` records is proportional to `k`.

Cluster metadata uses maps for lookup.

Consumer assignment is intentionally simple and uses round-robin distribution. Real Kafka group coordination is more sophisticated because it must handle distributed membership, heartbeats, rebalancing, metadata, and failure detection.

The PostgreSQL design adds indexes only for recurring access patterns:

- records by topic and partition
- assignments by consumer
- replicas by broker and synchronization state
- status checks by partition and state

The relational database is suitable for representing metadata and analytical views, but it is not presented as a replacement for Kafka's distributed log storage.

## Data Integrity

The PostgreSQL schema enforces important relationships with:

- primary keys
- foreign keys
- unique constraints
- check constraints
- triggers
- transactions

For example, a record cannot reference a nonexistent partition.

A committed offset cannot exceed the currently available partition position through the database trigger.

A partition leader must reference a broker that is online when the leader assignment is inserted or changed.

These constraints move part of the domain validation into the database layer.

## Conceptual Distinctions

The project keeps the following concepts separate:

| Concept | Meaning |
|---|---|
| Topic | Logical named stream |
| Partition | Ordered log belonging to a topic |
| Offset | Position inside one partition |
| Broker | Kafka server responsible for partitions |
| Replica | Copy of a partition on another broker |
| Leader | Broker currently serving the partition leadership role |
| Producer | Client publishing records |
| Consumer | Client reading records |
| Consumer Group | Set of consumers sharing partition work |
| Assignment | Mapping between a group consumer and partition |
| Committed Offset | Durable consumer position for a group and partition |
| Lag | Distance between available data and committed consumer position |

Confusing these concepts leads to incorrect system designs.

A topic does not have one universal ordering sequence.

An offset is not globally unique.

A broker is not synonymous with a partition.

A replica is not necessarily the current leader.

A consumer's position is not stored inside the record itself.

## End-to-End Workflow

The implementations represent the following complete workflow:

```text
Broker Registration
       │
       ▼
Topic Creation
       │
       ▼
Partition Creation
       │
       ▼
Replica Placement
       │
       ▼
Producer Sends Record
       │
       ▼
Partition Selection
       │
       ▼
Leader Appends Record
       │
       ▼
Offset Assigned
       │
       ▼
Consumer Group Assignment
       │
       ▼
Consumer Fetches Records
       │
       ▼
Application Processes Record
       │
       ▼
Consumer Commits Next Offset
       │
       ▼
Broker Failure
       │
       ▼
Replica Becomes Candidate
       │
       ▼
Leader Reassignment
       │
       ▼
Production and Consumption Resume
```

This workflow connects the five implementations without collapsing their individual technical perspectives.

## Practical Limitations

The project is a learning-oriented Kafka domain model rather than a Kafka protocol implementation.

It does not implement:

- Kafka's binary network protocol
- Kafka controller internals
- ZooKeeper-based historical architecture
- KRaft controller quorum internals
- real network replication
- ISR protocol behavior
- producer idempotence protocol
- transactions across Kafka partitions
- exactly-once processing semantics
- real consumer heartbeats
- group coordinator networking
- schema registry integration
- compression codecs
- TLS negotiation
- SASL authentication
- Kafka ACL enforcement
- disk-backed segment files

The simplified models preserve the important conceptual relationships while keeping the implementations executable and inspectable.

## Technical Relationship Across the Five Implementations

The same domain is deliberately expressed differently.

Python emphasizes direct simulation and validation.

JavaScript emphasizes event-driven behavior and asynchronous operations.

C++17 emphasizes explicit data structures, typed failure handling, and systems-level control.

Java 17 emphasizes enterprise domain modeling, service boundaries, interfaces, records, immutable values, and explicit state.

PostgreSQL emphasizes durable relational state, referential integrity, transactional updates, indexes, views, triggers, and analytical queries.

The common domain remains:

`topics → partitions → records → offsets → brokers → consumer groups`

The differences in implementation make the same Kafka concepts visible from application, event-driven, systems, enterprise, and database perspectives.
