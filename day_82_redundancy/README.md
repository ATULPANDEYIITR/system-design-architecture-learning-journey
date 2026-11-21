# Redundancy: Active-Active and Active-Passive Architectures

## 1. Redundancy in Distributed Systems

Redundancy is the provision of additional infrastructure components so that a service can continue operating when an individual component fails.

A redundant architecture distributes service responsibilities across multiple nodes, regions, availability zones, or data centres. Its purpose is to reduce dependence on a single infrastructure component.

A node can represent:

- An application server.
- A database server.
- A storage system.
- A network service.
- A complete deployment environment.
- An independently operated infrastructure region.

Redundancy is not equivalent to backup. A backup preserves information for restoration, whereas redundancy provides additional operational capacity or an alternative execution path during failure.

Two important redundancy architectures are:

1. Active-active.
2. Active-passive.

Both provide alternatives to single-node operation, but they differ in request distribution, resource utilization, replication requirements, failure handling, and operational complexity.

## 2. Fundamental Architectural Concepts

### 2.1 Node

A node is an independently operating component participating in a distributed service.

Each node has:

| Attribute | Meaning |
|---|---|
| Node identifier | Unique identity |
| Region | Physical or logical deployment location |
| Role | Active, passive, failed, or recovering |
| Health | Healthy, degraded, or down |
| Capacity | Maximum supported workload |
| Current load | Currently consumed capacity |
| Applied sequence | Latest replicated operation applied |
| Replication lag | Outstanding replication delay |
| Fencing epoch | Current authorization generation |

A node's role and health are separate properties.

For example, a node can be assigned the active role but become unavailable because its health is down. A recovered node may be healthy while temporarily remaining in the recovering role.

### 2.2 Redundancy and Availability

Availability describes whether a service can successfully respond to requests.

For a simplified series system containing independent components, availability is:

\[
A_{system}=\prod_{i=1}^{n} A_i
\]

A system that requires every component to operate becomes less available as additional mandatory dependencies are introduced.

For two independent parallel components where either component can provide the service:

\[
A_{parallel}=1-(1-A_1)(1-A_2)
\]

For identical components:

\[
A_{parallel}=1-(1-A)^2
\]

These equations assume independent failures and correctly functioning failover mechanisms.

Real distributed systems can experience correlated failures, common network dependencies, shared storage failures, software defects, and configuration errors. Their actual availability may therefore be lower than a simple mathematical estimate.

### 2.3 Fault Tolerance

Fault tolerance is the ability to continue providing an acceptable level of service when components fail.

A redundant system may tolerate:

- Application process failure.
- Server hardware failure.
- Operating system failure.
- Network interface failure.
- Availability-zone failure.
- Regional infrastructure failure.

The failure scenarios supported by an architecture depend on the actual placement of nodes and the independence of their infrastructure dependencies.

### 2.4 Failover and Failback

**Failover** transfers service responsibility from a failed or unavailable component to an alternative component.

**Failback** is the controlled return to the preferred operational arrangement after the original component has recovered.

Failback is not necessarily automatic. A recovered node may first synchronize its data, undergo validation, and rejoin as a standby rather than immediately reclaiming the primary role.

## 3. Active-Active Architecture

### 3.1 Definition

An active-active architecture operates multiple nodes simultaneously. Each participating active node can accept requests and contribute to service delivery.

A load balancer, distributed router, service mesh, or application-level routing mechanism directs requests to available nodes.

Example:

    Client Requests
          |
       Load Balancer
          |
      +---+---+
      |   |   |
      v   v   v
     A1  A2  A3
      |   |   |
      +---+---+
          |
     Replication Layer
          |
     Shared Logical Dataset

All three nodes provide active service.

### 3.2 Request Distribution

Requests can be distributed through several strategies:

| Strategy | Mechanism |
|---|---|
| Round robin | Requests rotate between nodes |
| Weighted round robin | Nodes receive traffic according to assigned weights |
| Least connections | Requests go to the node with fewer active connections |
| Least response time | Routing considers observed response times |
| Consistent hashing | Requests are assigned using stable key-based partitions |
| Geographic routing | Requests are directed according to client location |

The Python implementation uses a least-loaded selection mechanism.

The C++ implementation also considers normalized capacity utilization and replication lag.

The JavaScript implementation adds event-driven cluster notifications.

### 3.3 Resource Utilization

Multiple nodes contribute to normal service delivery.

For example, three nodes with a capacity of 100 workload units each provide a nominal aggregate capacity of:

\[
C_{total}=100+100+100=300
\]

This assumes the workload can be distributed effectively and that shared dependencies do not become bottlenecks.

If one node fails, the remaining nodes provide 200 nominal workload units.

A production system must reserve enough capacity to absorb the workload transferred from failed nodes.

### 3.4 Failure Handling

When an active node fails:

1. Health monitoring identifies the failure.
2. Traffic routing excludes the failed node.
3. Remaining active nodes continue serving requests.
4. Capacity and availability requirements are evaluated.
5. The failed node is recovered.
6. Replication synchronization takes place.
7. The recovered node rejoins the active pool.

The active-active architecture does not necessarily require promotion of a passive node because the remaining nodes are already serving requests.

### 3.5 Data Consistency

Active-active deployments introduce important data-management challenges.

Multiple nodes may receive writes concurrently. If they independently modify the same record, conflicting updates can occur.

Common consistency mechanisms include:

- Synchronous replication.
- Asynchronous replication.
- Distributed transactions.
- Optimistic concurrency control.
- Version numbers.
- Conflict-free replicated data types.
- Application-level conflict resolution.
- Consensus-based coordination.

The implementations use a simplified centralized logical data model to demonstrate request processing and replication state.

They do not implement a production distributed database or a consensus protocol.

### 3.6 Advantages

- Multiple nodes contribute to normal workload.
- No idle standby is required.
- Workload can be distributed geographically.
- Failure of one node does not necessarily interrupt service.
- Additional capacity can be introduced by adding nodes.
- Rolling maintenance can be performed with suitable traffic management.

### 3.7 Limitations

- Concurrent writes introduce consistency challenges.
- Replication conflicts require resolution.
- Load balancing requires reliable health information.
- More active nodes increase operational complexity.
- Network partitions can create divergent states.
- Shared dependencies can eliminate the expected availability benefit.
- Session management requires appropriate distribution or persistence mechanisms.

## 4. Active-Passive Architecture

### 4.1 Definition

An active-passive architecture operates one primary active node while one or more passive nodes remain available for failover.

The active node processes normal requests. Passive nodes receive replicated state and wait for promotion.

Example:

    Client Requests
          |
       Load Balancer
          |
          v
       Primary
          |
     Replication
          |
      +---+---+
      |       |
      v       v
    Standby  Standby
       1        2

Only the primary accepts normal application writes.

### 4.2 Primary Node

The primary node:

- Accepts normal service requests.
- Processes application operations.
- Maintains the authoritative write sequence.
- Sends changes to standby nodes.
- Participates in health monitoring.
- Provides operational information for failover decisions.

### 4.3 Passive Standby

A standby node:

- Remains available for promotion.
- Receives replicated data.
- Maintains its applied sequence.
- Reports replication lag.
- Is monitored for health and capacity.
- Becomes active after an approved failover operation.

A standby can be hot, warm, or cold.

| Type | Characteristics |
|---|---|
| Hot standby | Continuously running and receiving updates |
| Warm standby | Running but may require additional activation |
| Cold standby | Requires substantial startup or restoration before service |

The implementations model hot standby behavior.

### 4.4 Failover Lifecycle

A typical active-passive failover follows this sequence:

    Primary Operating
          |
     Failure Detection
          |
     Primary Fenced
          |
     Standby Eligibility
          |
     Data Consistency Check
          |
     Standby Promotion
          |
     Routing Update
          |
     Service Restoration

Important stages include:

**Failure detection:** A monitoring system identifies that the primary is no longer operating correctly.

**Fencing:** The former primary loses authorization to perform writes.

**Standby selection:** The system selects a healthy standby satisfying replication and capacity policies.

**Promotion:** The selected standby becomes active.

**Routing update:** Requests are redirected to the promoted node.

**Recovery:** The original primary is restored and synchronized before rejoining the cluster.

### 4.5 Advantages

- Clear ownership of the active write role.
- Simpler write coordination compared with unrestricted multi-primary operation.
- Reduced concurrent-write conflict risk.
- Suitable for primary-database architectures.
- Standby capacity can provide disaster-recovery capability.
- Failover policy can enforce replication consistency requirements.

### 4.6 Limitations

- Passive resources may remain underutilized.
- Failover can introduce interruption.
- Replication lag can cause data loss during asynchronous promotion.
- Standby promotion requires coordination.
- Recovery and failback require careful sequencing.
- A shared storage or network failure can affect both primary and standby nodes.

## 5. Active-Active and Active-Passive Comparison

| Dimension | Active-Active | Active-Passive |
|---|---|---|
| Normal active nodes | Multiple | One |
| Request handling | Distributed | Primary-based |
| Resource utilization | Multiple nodes serve traffic | Standby resources may be idle |
| Write coordination | Potentially complex | Centralized primary |
| Failover | Traffic redistribution or capacity adjustment | Standby promotion |
| Concurrent writes | Requires conflict management | Usually reduced |
| Replication | Often bidirectional or multi-node | Usually primary-to-standby |
| Recovery | Rejoin active pool | Rejoin as standby |
| Complexity | Higher distributed coordination | Higher promotion and fencing requirements |
| Typical use | Distributed application services | Primary database and standby systems |

The two architectures are not mutually exclusive across an entire enterprise.

An application may use active-active web servers while its database uses active-passive replication.

## 6. Replication Mechanisms

Replication maintains corresponding data across multiple nodes.

### 6.1 Synchronous Replication

Synchronous replication requires the configured replication acknowledgements before a write is considered committed.

Simplified sequence:

    Application
        |
        v
     Primary
        |
        +------> Replica 1
        |
        +------> Replica 2
        |
        v
    Required Acknowledgements
        |
        v
     Commit

Advantages:

- Stronger durability guarantees.
- Lower risk of losing acknowledged writes during failover.
- More predictable standby consistency.

Limitations:

- Higher write latency.
- Dependence on replica availability.
- Network delays affect transaction completion.
- Strict replication requirements can reduce write availability.

The implementations use a simplified all-healthy-replica acknowledgement policy.

Production systems may use configurable acknowledgement quorums.

### 6.2 Asynchronous Replication

Asynchronous replication acknowledges the primary write without waiting for every replica to apply the update.

Simplified sequence:

    Application
        |
        v
     Primary
        |
        +------> Acknowledge Write
        |
        +------> Replication Queue
                      |
                      v
                   Replica

Advantages:

- Lower write latency.
- Greater tolerance of temporarily unavailable replicas.
- Reduced dependency on immediate replica response.

Limitations:

- Replication lag.
- Potential loss of acknowledged writes during failover.
- Temporary data inconsistency.
- More complex recovery and reconciliation.

### 6.3 Replication Lag

Replication lag is the difference between the latest committed primary operation and the latest operation applied by a replica.

In a sequence-based model:

\[
Lag=S_{primary}-S_{replica}
\]

Where:

- \(S_{primary}\) represents the latest committed sequence.
- \(S_{replica}\) represents the latest applied sequence.

A replica with a large lag may not be suitable for promotion.

The examples enforce a maximum replication lag before asynchronous promotion.

### 6.4 Replication Log

The implementations maintain a write log containing:

- Sequence number.
- Record key.
- Record value.
- Source node.
- Timestamp.
- Commit state.

A replica can compare its applied sequence with the log and apply missing records.

The sequence number provides ordering within the simulated cluster.

A production distributed database may require additional mechanisms for transaction ordering, duplicate delivery, idempotency, conflict detection, and log retention.

## 7. Failure Detection and Recovery

### 7.1 Health Monitoring

Health monitoring evaluates whether nodes can perform their assigned responsibilities.

Typical monitoring signals include:

- Heartbeat responses.
- Application health endpoints.
- Database connectivity.
- CPU and memory utilization.
- Storage availability.
- Network connectivity.
- Replication delay.
- Request failure rate.
- Response latency.

A single missed heartbeat does not always prove a node has failed.

Network congestion, packet loss, and temporary scheduling delays can produce false failure suspicions.

### 7.2 Failure Detection States

The implementations use the following conceptual states:

| State | Meaning |
|---|---|
| Healthy | Node is operating normally |
| Degraded | Node operates with restricted capabilities |
| Down | Node is unavailable |
| Recovering | Node is being restored and synchronized |

These states are distinct from node roles.

### 7.3 Failover Eligibility

An active-passive standby must satisfy relevant eligibility rules.

Typical requirements include:

1. Standby health must be healthy.
2. Replication lag must remain within policy.
3. Synchronous replication must satisfy its consistency requirement.
4. Node capacity must be sufficient.
5. The standby must belong to the correct cluster.
6. The previous primary must be fenced.
7. Only one node may own the active write authority.

The C++ and Java implementations enforce these conditions through their governance services.

The Python implementation demonstrates automatic standby selection.

The JavaScript implementation combines selection with fencing-token validation.

### 7.4 Recovery

Recovery does not simply change a failed node's health to healthy.

The node must:

- Re-establish communication.
- Validate its local state.
- Retrieve missing records.
- Apply pending changes.
- Reconcile replication sequence numbers.
- Confirm operational readiness.
- Rejoin the cluster with an appropriate role.

In active-passive systems, the recovered former primary normally rejoins as passive.

This prevents two independent primaries from accepting writes simultaneously.

## 8. Split-Brain and Fencing

### 8.1 Split-Brain

Split-brain occurs when two or more nodes independently believe they are authorized to act as the primary.

Example:

    Network Partition
          |
      +---+---+
      |       |
      v       v
    Node A  Node B
    Primary Primary

Both nodes may accept writes.

The result can include:

- Conflicting records.
- Divergent transaction histories.
- Lost updates.
- Duplicate processing.
- Inconsistent application state.

### 8.2 Fencing Tokens

A fencing token is a monotonically increasing authorization value associated with a node's ownership of a resource.

Example:

| Primary | Fencing epoch |
|---|---:|
| Node A | 10 |
| Node B after promotion | 11 |

When Node B becomes primary, its epoch is newer.

A storage or transaction layer can reject operations carrying the old epoch.

The JavaScript, C++, and Java implementations model fencing authority.

The Python implementation demonstrates role transitions but does not provide a full fencing mechanism.

The SQL model maintains a cluster fencing epoch and records it during failover.

### 8.3 Important Production Requirement

Updating a node's role in an application database is not sufficient fencing by itself.

A real deployment must ensure that stale primaries cannot continue modifying authoritative storage.

Fencing may require:

- Storage-level fencing.
- Lease expiration.
- Consensus-backed ownership.
- Distributed lock coordination.
- Network isolation.
- Database primary-term validation.

## 9. Quorum and Consensus Considerations

Quorum is a minimum number of participating members required for a distributed decision.

For a cluster of \(N\) voting members, a majority quorum is:

\[
Q=\left\lfloor\frac{N}{2}\right\rfloor+1
\]

For example:

| Members | Majority quorum |
|---:|---:|
| 3 | 2 |
| 5 | 3 |
| 7 | 4 |

A majority quorum helps prevent conflicting ownership decisions when implemented within an appropriate consensus protocol.

Quorum is not identical to synchronous replication.

Synchronous replication determines when writes are acknowledged according to replication rules. Consensus determines how distributed participants agree on authoritative decisions or ordered state.

The supplied implementations do not implement Raft, Paxos, or a complete quorum protocol.

Their fencing and replication models are educational simulations.

## 10. Recovery Objectives

Two important operational measurements are RTO and RPO.

### 10.1 Recovery Time Objective

RTO is the maximum acceptable duration for restoring a service following disruption.

It can include:

- Failure detection time.
- Promotion time.
- Routing update time.
- Application initialization time.
- Validation time.

A simplified expression is:

\[
RTO=T_d+T_p+T_r+T_v
\]

Where:

- \(T_d\) is detection time.
- \(T_p\) is promotion time.
- \(T_r\) is routing restoration time.
- \(T_v\) is validation time.

### 10.2 Recovery Point Objective

RPO specifies the maximum acceptable amount of data loss measured in time.

Synchronous replication can provide a lower potential data-loss window under appropriate acknowledgement and failure assumptions.

Asynchronous replication may lose updates that were acknowledged by the primary but had not reached the promoted standby.

Replication sequence lag helps identify this risk, although sequence differences alone do not directly express elapsed-time RPO.

### 10.3 Capacity Planning

A redundant cluster must retain sufficient capacity after failures.

For \(N\) equally capable active nodes with capacity \(C\), the nominal capacity after one node fails is:

\[
C_{remaining}=(N-1)C
\]

This capacity must support the transferred workload.

For active-passive systems, standby capacity must be sufficient to handle the workload after promotion.

Capacity planning must also consider peak load, regional constraints, storage throughput, network bandwidth, and downstream dependencies.

## 11. Python Implementation

The Python file implements a repository-style service simulator using object-oriented domain modeling.

### 11.1 Domain Classes

| Class | Responsibility |
|---|---|
| `Node` | Stores node health, role, capacity, and replication state |
| `Repository` | Coordinates cluster operations |
| `ReplicatedWrite` | Represents a sequenced data modification |
| `Request` | Represents a client operation |
| `FailoverEvent` | Records failover outcomes |
| `RedundancyConfiguration` | Defines architecture and operational policy |

Enums distinguish architecture, node health, replication mode, role, and failover state.

### 11.2 Request Processing

The `process_request()` method supports reads and writes.

The node-selection mechanism chooses the least-loaded available active node.

The `finally` block ensures that temporary load accounting is released even when an operation fails.

### 11.3 Write Processing

The implementation supports:

- Synchronous replication.
- Asynchronous replication.
- Write sequencing.
- Replication-lag tracking.
- Replica synchronization.
- Invalid operation rejection.
- Capacity validation.

### 11.4 Failover

The active-active workflow evaluates whether the remaining active nodes satisfy the minimum node requirement.

The active-passive workflow selects a healthy standby according to replication sequence, capacity, and lag constraints.

### 11.5 Recovery

The `recover_node()` method synchronizes a recovered node before restoring its role.

The active-passive implementation returns the recovered node to passive operation.

### 11.6 Execution

Run the script with Python 3.10 or later.

The implementation uses only the Python standard library.

It prints active-active and active-passive operational reports and demonstrates expected failure conditions.

## 12. JavaScript Implementation

The JavaScript file uses Node.js event-driven capabilities to model a redundant cluster.

### 12.1 Event-Driven Architecture

`RedundantCluster` extends `EventEmitter`.

It emits events for:

- Successful writes.
- Node failures.
- Completed failovers.
- Failed failovers.
- Replica synchronization.
- Node recovery.
- Availability loss.

This separates cluster state transitions from operational monitoring.

### 12.2 Asynchronous Operations

The implementation exposes asynchronous read, write, failover, synchronization, and recovery methods.

A serialized promise queue prevents concurrent operations in the simulator from independently modifying shared cluster state.

This is a local execution mechanism, not a distributed locking protocol.

### 12.3 Fencing Authority

`FencingAuthority` maintains:

- Current owner.
- Monotonically increasing epoch.
- Ownership validation.

A promoted standby receives a newer fencing token.

A stale primary cannot pass the local fencing check after ownership changes.

### 12.4 Replication Log

`ReplicationLog` stores ordered write records.

A recovered node uses its applied sequence to identify pending records.

### 12.5 Operational Metrics

The cluster tracks:

- Requests.
- Failures.
- Failover attempts.
- Rejected writes.

The reporting mechanism exposes the cluster state without directly exposing mutable internal collections.

### 12.6 Execution

Run using Node.js 18 or later.

No external npm dependencies are required.

The file uses `node:crypto` and `node:events`.

## 13. C++17 Implementation

The C++ program provides a governance-oriented redundancy engine using strongly typed domain structures and STL containers.

### 13.1 Domain Modeling

The implementation uses:

- Enumerations for architecture, health, and role.
- Structures for nodes and write records.
- Maps for node inventory and application data.
- Vectors for replication history.
- Optional values for read results.
- Exceptions for operational validation.

### 13.2 Node Selection

The engine selects a node according to normalized load:

\[
U_i=\frac{Load_i}{Capacity_i}
\]

The node with the lowest utilization is preferred.

Replication lag and node identity provide additional deterministic selection criteria.

### 13.3 Replication

Synchronous replication validates available replicas before applying changes.

Asynchronous replication records outstanding lag for replicas.

The write log supports recovery through sequence-based synchronization.

### 13.4 Failover Governance

The `failNode()` method evaluates the failed node and determines the correct architectural response.

For active-active, it evaluates remaining service capacity.

For active-passive, it:

1. Identifies healthy passive nodes.
2. Evaluates replication lag.
3. Checks sequence consistency for synchronous replication.
4. Selects the most current eligible standby.
5. Obtains a new fencing epoch.
6. Promotes the standby.

### 13.5 Error Handling

The implementation rejects:

- Empty record keys.
- Missing active nodes.
- Insufficient active-active capacity.
- Invalid replication conditions.
- Stale primary fencing tokens.
- Unknown nodes.
- Recovery of unknown nodes.

The program uses C++17 standard-library features without external dependencies.

### 13.6 Execution

Compile with a C++17-compatible compiler.

The implementation is suitable for demonstrating domain-level governance decisions, not production distributed transaction processing.

## 14. Java 17 Implementation

The Java implementation models an enterprise-oriented cluster governance service.

### 14.1 Immutable Configuration

`ClusterPolicy` is a Java record.

It defines architecture, replication mode, required active nodes, maximum lag, automatic failover, and degraded-write behavior.

Its compact constructor validates configuration before the service is initialized.

### 14.2 Enterprise Domain Types

| Type | Responsibility |
|---|---|
| `ClusterPolicy` | Immutable operational configuration |
| `Node` | Cluster member state |
| `WriteRecord` | Immutable operation history |
| `OperationResult` | Structured operation outcome |
| `FailoverRecord` | Failover audit history |
| `FencingService` | Ownership and epoch validation |
| `GovernanceService` | Cluster-level orchestration |

### 14.3 Governance Service

`GovernanceService` coordinates the cluster lifecycle.

It handles:

- Initial configuration validation.
- Node-role initialization.
- Read and write operations.
- Replication.
- Failover eligibility.
- Primary promotion.
- Fencing.
- Recovery.
- Operational reporting.

### 14.4 State Management

The service distinguishes cluster state from node state.

Cluster states include:

- Normal.
- Degraded.
- Failover in progress.
- Failover completed.
- Unavailable.

A cluster can therefore report a degraded or unavailable condition without incorrectly changing every node's health.

### 14.5 Synchronization and Concurrency

The public state-changing service methods are synchronized.

This provides serialized access within a single Java process.

It does not coordinate multiple Java processes or machines.

A production implementation would require distributed coordination, durable transactional storage, and external ownership enforcement.

### 14.6 Execution

Compile using Java 17:

`javac RedundancyEnterprise.java`

Run:

`java RedundancyEnterprise`

No third-party dependencies are required.

## 15. PostgreSQL Implementation

The SQL file provides a relational model for cluster configuration, node inventory, replication history, failover processing, and operational reporting.

### 15.1 Database Schema

The `redundancy` schema separates redundancy-related objects from unrelated database structures.

PostgreSQL ENUM types constrain architectural and operational values.

### 15.2 Relational Structure

The main relationships are:

    clusters
       |
       +---- cluster_nodes
       |
       +---- replication_log
       |
       +---- cluster_data
       |
       +---- failover_events
       |
       +---- operation_audit

| Table | Purpose |
|---|---|
| `clusters` | Architecture and governance configuration |
| `cluster_nodes` | Node roles, health, capacity, and replication state |
| `replication_log` | Ordered write history |
| `cluster_data` | Latest committed logical application records |
| `failover_events` | Promotion and failure history |
| `operation_audit` | Operational request history |

### 15.3 Integrity Constraints

The schema includes:

- Primary keys.
- Foreign keys.
- Unique node identifiers within clusters.
- Positive capacity requirements.
- Valid load limits.
- Nonnegative replication lag.
- Nonnegative fencing epochs.
- Positive sequence numbers.
- ENUM-based state validation.

The node-role trigger prevents an active-active node from being assigned a passive role and prevents failed nodes from having a non-down health state.

### 15.4 Transactional Write Function

`write_cluster_data()` performs a controlled write workflow.

It:

1. Validates input.
2. Locks the cluster configuration row.
3. Locks the selected node.
4. Checks active role and node health.
5. Validates capacity.
6. Checks synchronous replica availability.
7. Allocates a sequence number.
8. Inserts the replication log entry.
9. Updates replication state.
10. Updates committed application data.
11. Marks the log entry committed.
12. Records an audit event.

The function executes within the caller's PostgreSQL transaction.

A failure causes the transaction to roll back.

### 15.5 Replica Synchronization

`synchronize_replica()` identifies committed log records newer than the replica's applied sequence.

It applies the latest value for each affected key and updates the replica's sequence and lag.

The implementation demonstrates logical synchronization. It does not implement physical PostgreSQL streaming replication.

### 15.6 Failover Function

`process_failover()` performs failover eligibility evaluation and promotion.

For active-active systems, it evaluates the remaining active node count.

For active-passive systems, it checks:

- Automatic failover policy.
- Passive role.
- Healthy node status.
- Maximum replication lag.
- Synchronous sequence consistency.

It then promotes the selected standby and increments the cluster fencing epoch.

The function locks the cluster row to serialize failover decisions for that cluster.

### 15.7 Reporting Views

The SQL implementation provides:

| View | Purpose |
|---|---|
| `node_inventory` | Current node state |
| `cluster_availability` | Active-node availability requirements |
| `failover_eligibility` | Standby promotion eligibility |
| `cluster_performance_report` | Cluster capacity and operational statistics |

Additional queries use aggregation, CTEs, filters, and joins to examine cluster utilization and operational history.

### 15.8 Transaction Rollback

The final transaction demonstration inserts a temporary operation and rolls it back.

This demonstrates that database operations can be grouped into an atomic transaction.

### 15.9 Execution

Execute the SQL script using PostgreSQL 14 or later.

The script creates its own schema and database objects.

It requires a database role with permission to create schemas, types, tables, functions, and triggers.

## 16. Performance and Scalability Considerations

### 16.1 Load Distribution

A well-designed active-active cluster must distribute traffic according to actual node capability.

Equal traffic distribution is not always optimal.

A node with lower capacity or higher latency may need a smaller routing weight.

### 16.2 Replication Throughput

Replication throughput depends on:

- Write volume.
- Record size.
- Network bandwidth.
- Replica processing speed.
- Storage throughput.
- Transaction ordering.
- Replication protocol overhead.

A replica that processes updates more slowly than the primary will accumulate replication lag.

### 16.3 Failover Selection

The implementations use sorting to choose eligible nodes.

For \(N\) nodes, sorting requires approximately:

\[
O(N\log N)
\]

A production implementation can maintain priority queues or indexed eligibility structures when cluster sizes and failover frequency justify the added complexity.

### 16.4 Database Indexing

The PostgreSQL schema indexes:

- Cluster, role, and health.
- Replication lag.
- Cluster sequence history.
- Application record keys.
- Failover timestamps.
- Audit timestamps.

Indexes accelerate relevant lookups but increase write overhead and storage requirements.

### 16.5 Replication Log Retention

An unbounded replication log increases storage consumption.

Production systems require:

- Log retention policies.
- Checkpoint management.
- Snapshot creation.
- Replica progress tracking.
- Safe log truncation.
- Recovery validation.

Deleting log records before all required replicas have synchronized can make recovery impossible.

## 17. Security and Operational Governance

Redundancy is also a security concern because multiple nodes introduce additional operational identities and communication paths.

Important controls include:

- Mutual TLS for node communication.
- Authentication between cluster members.
- Authorization for promotion operations.
- Least-privilege database accounts.
- Encryption at rest.
- Protected replication channels.
- Fencing and ownership validation.
- Immutable failover audit records.
- Restricted administrative access.
- Monitoring of unexpected role changes.
- Separation of operational and application permissions.

Failover endpoints should not be exposed as unrestricted public operations.

Administrative promotion must require authorization and should produce an auditable event.

Health checks must avoid exposing sensitive application information.

## 18. Limitations of the Implementations

The five source files provide complementary models of redundancy, but they do not constitute production-grade distributed infrastructure.

| Area | Demonstrated behavior | Production requirement |
|---|---|---|
| Node health | Simulated health states | Independent health monitoring |
| Load balancing | In-memory node selection | Distributed traffic management |
| Replication | Logical sequence-based records | Durable replication protocol |
| Synchronous writes | Simplified replica acknowledgement | Transactional replication guarantees |
| Asynchronous writes | Simulated replication lag | Durable asynchronous transport |
| Failover | Local state transitions | Distributed failure coordination |
| Fencing | Local ownership epochs | Storage-enforced fencing |
| Quorum | Not fully implemented | Consensus-backed coordination |
| Split-brain | Partially addressed | Independent ownership enforcement |
| Recovery | In-memory synchronization | Durable recovery and reconciliation |
| Persistence | In-memory application models | Persistent distributed storage |
| Observability | Logs and reports | Metrics, traces, alerts, and dashboards |

The PostgreSQL implementation provides persistent relational state but does not automatically coordinate external application processes or configure PostgreSQL physical replication.

The Python, JavaScript, C++, and Java implementations maintain simulated state within their respective processes.

## 19. Practical Architectural Selection

The architecture should be selected according to workload requirements rather than treating one model as universally superior.

| Requirement | Suitable consideration |
|---|---|
| High request throughput | Active-active |
| Distributed geographic access | Active-active |
| Multiple nodes serving traffic | Active-active |
| Centralized write ownership | Active-passive |
| Simpler primary-based database operation | Active-passive |
| Reduced concurrent-write conflicts | Active-passive |
| Lower standby utilization cost | Active-active |
| Controlled database promotion | Active-passive |
| Strong regional disaster recovery | Either, with appropriate placement and replication |
| Strict consistency | Either, with suitable replication and coordination |

An enterprise may combine both models.

For example:

    Internet Users
          |
    Global Traffic Manager
          |
      Active-Active
      Application Tier
          |
      Database Router
          |
      Active-Passive
      Database Cluster
          |
      Standby Database

The application tier distributes normal workload across multiple active nodes.

The database tier maintains one active write primary and one or more synchronized standbys.

This combination separates application scalability from database write ownership.

## 20. Technical Terminology

| Term | Definition |
|---|---|
| Redundancy | Additional components providing alternative operational capacity |
| High availability | Design objective of maintaining service availability |
| Fault tolerance | Ability to continue operation despite component failures |
| Active node | Node currently accepting normal service requests |
| Passive node | Standby node waiting for activation |
| Primary | Authoritative active node in a primary-based architecture |
| Standby | Node prepared to replace the primary |
| Failover | Transfer of service responsibility |
| Failback | Controlled return to a preferred operational arrangement |
| Replication | Propagation of data changes between nodes |
| Synchronous replication | Replication acknowledgements required before commit |
| Asynchronous replication | Replication proceeds without waiting for every replica |
| Replication lag | Difference between committed and applied replication progress |
| Split-brain | Multiple nodes independently operating as primary |
| Fencing | Mechanism preventing stale ownership from modifying authoritative resources |
| Fencing token | Monotonically increasing ownership authorization value |
| Quorum | Minimum participation required for a distributed decision |
| RTO | Recovery Time Objective |
| RPO | Recovery Point Objective |
| Hot standby | Continuously running standby receiving updates |
| Capacity planning | Assessment of resources needed under normal and failure conditions |
| Health check | Evaluation of operational readiness |
| Recovery | Restoration and synchronization of a failed node |

## 21. Key Architectural Distinctions

The central distinction is the way service responsibility is assigned.

**Active-active** uses multiple active nodes to process normal traffic and distribute workload.

**Active-passive** assigns normal processing to a primary while standby nodes prepare for failover.

Replication determines how data changes reach other nodes.

Failover determines how service responsibility changes when a node becomes unavailable.

Fencing prevents an obsolete primary from continuing to modify authoritative data.

Recovery restores a failed node to an eligible operational state.

These mechanisms work together, but none of them independently guarantees high availability. Reliable redundancy requires coordinated data consistency, capacity planning, health monitoring, failure detection, traffic management, security, and recovery procedures.
