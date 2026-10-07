# Database Replication: Primary-Replica, Synchronous and Asynchronous Replication

## Scope

This learning artifact models database replication as a distributed data-flow problem involving a writable primary, one or more replicas, ordered change records, replay positions, acknowledgement rules, replication lag, failure recovery, and promotion.

The three central replication behaviors are kept distinct:

- **Primary-replica replication** defines the topology and write authority. The primary accepts writes, produces an ordered stream of changes, and replicas consume that stream.
- **Asynchronous replication** allows the primary to acknowledge a write without waiting for a replica to replay the corresponding change. This usually reduces write latency but introduces a replication window in which a committed change may not yet exist on a replica.
- **Synchronous replication** makes one or more replica acknowledgements part of the commit condition. This can reduce the amount of committed data exposed to loss during primary failure, but availability and latency become dependent on the configured synchronous replicas.

The implementations also distinguish receiving a change from replaying it. A replica can have received a log record while its data state is still behind the primary.

## Replication terminology

### Primary

The primary is the authoritative writable node in the model. A write changes primary state and produces an ordered change record.

The Python `Primary`, JavaScript `Primary`, C++ `Primary`, and Java `Primary` classes all maintain a data structure representing primary state and a monotonically increasing log position.

A primary is not merely "the first database." It has a write-authority role. During failover, that authority must move safely.

### Replica

A replica consumes changes produced by the primary. It normally serves read workloads or provides redundancy rather than independently accepting ordinary writes.

Each implementation tracks a replica replay position. The SQL model stores this as `replayed_lsn` in `database_node`.

A replica being available does not prove that it is current.

### LSN and ordered change records

The implementations use an LSN-like integer to represent the position of a change in an ordered replication stream.

For example, a change may conceptually look like:

`LSN=27, transaction=18, SET customer:1001=ACTIVE`

The exact mechanism differs between database engines. PostgreSQL physical replication uses WAL positions, while other systems use different log or binlog mechanisms.

The important property in this model is ordering. A replica should not apply LSN 28 while LSN 27 is still missing.

### Received position versus replayed position

The model intentionally tracks both:

`received_lsn`

and

`replayed_lsn`

The difference is replication lag.

A replica can therefore be:

- reachable but behind,
- receiving changes faster than it can replay them,
- temporarily disconnected,
- caught up,
- or completely unavailable.

This distinction is important for monitoring and read-after-write decisions.

## Primary-replica workflow

A normal write path in the model is:

Primary write → ordered change record → delivery to replicas → replica replay → replica position advances

The exact commit semantics depend on the replication mode.

In asynchronous operation, the primary does not wait for replica replay.

In synchronous operation, configured replica acknowledgement becomes part of the acknowledgement condition.

The Python simulation exposes these differences through `ReplicationCluster.commit()`. The JavaScript implementation uses event-driven delivery and replay. The C++ program models the same process with explicit systems-oriented classes. The Java implementation adds an acknowledgement policy abstraction. The SQL script represents the workflow using `wal_change`, `replication_delivery`, and `database_node`.

## Asynchronous replication

Asynchronous replication separates the primary's write acknowledgement from replica replay.

A simplified timeline is:

`Client → Primary: write`

`Primary → WAL/change log: persist ordered change`

`Primary → Client: acknowledge`

`Primary → Replica: deliver change`

`Replica → local state: replay change`

This ordering means the client can receive a successful response before the replica has applied the change.

The advantage is lower write-path latency and less dependency on replica network round-trip time.

The trade-off is a replication window. If the primary fails after acknowledging a write but before the replica has durably received or replayed it, failover may expose a state that does not contain that recent write.

The Python implementation demonstrates this by committing changes with `auto_replay=False`, then explicitly advancing individual replicas.

The JavaScript implementation represents asynchronous delivery through `EventEmitter` events. The primary emits a write event, the change is delivered, and replay occurs independently.

The C++ case study shows a primary producing ordered records while replicas independently advance their replay positions.

The Java implementation uses `ReplicationMode.ASYNCHRONOUS` with an acknowledgement policy that does not impose a replica replay requirement.

The SQL implementation allows WAL-like records to exist before individual `replication_delivery` rows are replayed.

## Synchronous replication

Synchronous replication changes the acknowledgement rule.

A simplified model is:

`Client → Primary: write`

`Primary → change log: persist change`

`Primary → Replica: deliver change`

`Replica → replay and acknowledge`

`Primary → Client: acknowledge`

The exact meaning of "acknowledge" varies between database systems and configuration. A system may wait for a replica to receive a record, flush it durably, or apply it, depending on the replication mechanism and settings.

The implementations use replay as the acknowledgement point so the distinction is visible in a self-contained simulation.

The synchronous requirement is represented by `synchronous_replicas`.

For example, a requirement of `2` means two healthy replicas must satisfy the acknowledgement condition before the modeled commit is accepted.

This improves durability characteristics relative to an entirely asynchronous arrangement, but it creates a dependency:

`commit availability ← replica availability + network availability + replica replay capacity`

A slow or unavailable synchronous replica can therefore increase write latency or prevent acknowledgement.

## Quorum-style synchronous behavior

A synchronous requirement does not necessarily mean that every replica must acknowledge every write.

The Python and C++ implementations demonstrate a configuration in which two replicas are required while three replicas exist.

With three replicas:

`A = healthy`

`B = healthy`

`C = healthy`

and a requirement of two acknowledgements, the system can continue acknowledging writes if C fails, provided A and B satisfy the acknowledgement condition.

If another replica also becomes unavailable, the required acknowledgement count can no longer be reached.

This illustrates the availability trade-off created by synchronous replication.

## Python implementation

The Python program is an executable replication laboratory.

The `Change` dataclass represents an immutable ordered log record. It carries an LSN, transaction identifier, operation, key, value, and generation.

The `Replica` class maintains:

- replica state,
- replicated data,
- received position,
- replayed position,
- pending changes,
- applied LSNs.

The applied-LSN set provides an idempotency mechanism. If the same change is delivered twice, the replica does not apply it twice.

The `Primary` class maintains writable state and an ordered WAL-like list.

`ReplicationCluster.commit()` demonstrates the difference between asynchronous and synchronous acknowledgement.

The program also contains explicit scenarios for:

- asynchronous replay,
- synchronous acknowledgement,
- replica outage,
- lag recovery,
- duplicate delivery,
- consistency validation,
- quorum-style acknowledgement,
- failover and promotion.

The consistency check compares primary and replica state rather than assuming that process health means data health.

## JavaScript implementation

The JavaScript implementation uses an event-driven architecture.

`ReplicationCluster` extends Node.js `EventEmitter`. Important events include:

- `primaryWrite`
- `changeDelivered`
- `replay`
- `commitAcknowledged`
- `promotion`

This design is useful for understanding replication as a stream-processing problem.

The `Replica` class uses a `Map` for pending changes and a `Set` for applied LSNs. Replay always requests the next expected LSN, which exposes a gap if an earlier record has not arrived.

The JavaScript implementation also models asynchronous operational behavior through independent replica state and explicit replay calls.

The failover model introduces a generation number. A new generation represents a new primary authority. In production, a generation number alone is not sufficient to prevent split brain, but it illustrates why old-primary writes must be fenced.

## C++ case study

The C++ program treats replication as a systems-oriented data-flow engine.

The principal components are:

`Primary`

The writable database authority and WAL-like producer.

`Replica`

A stateful consumer that receives ordered changes and replays them.

`ReplicationCluster`

The orchestration layer that delivers records, evaluates acknowledgements, reports lag, and performs promotion.

`ChangeRecord`

A strongly typed representation of a replication log entry.

The C++ implementation uses `std::map` for deterministic key/value state, `std::vector` for the primary log, `std::set` for applied LSN tracking, and ordered pending records for replay.

The program demonstrates a realistic operational sequence:

A primary writes ledger records.

A replica receives those records.

The replica replays them in LSN order.

The primary becomes unavailable.

The replica is promoted only after the old primary has been fenced.

A new write is then accepted by the promoted primary.

The promotion scenario demonstrates the most important operational danger in failover: split brain.

If the old primary can continue accepting writes while the new primary is also accepting writes, the two authorities can produce divergent histories.

## Java implementation

The Java program models replication as an enterprise domain.

`Change` is an immutable Java record containing the log position, transaction identifier, operation, key, value, generation, and creation timestamp.

`Replica` represents a stateful database replica.

`Primary` represents the authoritative writer.

`ReplicationCluster` coordinates delivery, replay, health, recovery, and promotion.

The `AcknowledgementPolicy` interface separates synchronous policy from the mechanics of the replication cluster.

`SynchronousAcknowledgementPolicy` expresses a rule that a configured number of replicas must have replayed the relevant LSN.

This separation is useful because replication topology and acknowledgement policy are related but not identical concerns.

The Java implementation also uses immutable snapshots when returning replica data. This prevents callers from directly mutating internal replica state.

## SQL data model

The SQL script is PostgreSQL-compatible and represents replication control data relationally.

It does not pretend that ordinary application SQL can configure a PostgreSQL physical standby completely. Physical streaming replication depends on server-level configuration and database infrastructure.

Instead, the SQL model exposes the important state and rules using ordinary tables and functions.

### `database_cluster`

Stores:

- cluster identity,
- replication mode,
- synchronous replica requirement,
- generation.

The `valid_sync_requirement` check prevents a synchronous cluster from being configured with zero required synchronous replicas.

### `database_node`

Represents primary and replica nodes.

Important fields include:

`role`

`state`

`generation`

`received_lsn`

`replayed_lsn`

The partial unique index `one_primary_per_cluster` prevents multiple primary rows in the same cluster.

The `replay_cannot_exceed_received` constraint ensures that a replica cannot claim to have replayed a position it has not received.

### `wal_change`

Represents ordered primary change records.

The unique constraint on `(cluster_id, lsn)` ensures that a cluster cannot contain two different records with the same log position.

The operation and value constraint prevents a `set` record from having a missing value.

### `replication_delivery`

Connects a WAL change with a replica.

The unique `(change_id, replica_id)` constraint prevents the same delivery record from being inserted repeatedly.

This supports idempotent transport bookkeeping.

### `replication_event`

Provides an operational event trail for primary writes, replay, and acknowledgement events.

This is useful for diagnosing whether a replica is behind because it has not received a record or because it received the record but has not replayed it.

## Database-level replay enforcement

The SQL function `apply_wal_change()` checks:

- that the WAL record exists,
- that the replica exists,
- that the target is actually a replica,
- that the replica belongs to the same cluster,
- that the replica is up,
- that the next expected LSN is being replayed.

The LSN check is especially important:

`incoming_lsn = replayed_lsn + 1`

Without ordered replay, a replica could construct a state from changes whose dependencies have not yet been applied.

The function then changes the logical replicated state and advances the replica's replay position.

## Replication lag

The SQL view `replica_health` calculates:

`replay_lag = received_lsn - replayed_lsn`

The same concept appears in all four programs.

A production monitoring system should distinguish at least:

- node unavailable,
- node connected but not receiving,
- node receiving but not replaying,
- node replaying slowly,
- node caught up.

A simple "replica is alive" health check cannot provide these distinctions.

## Failure and recovery

Replica failure is fundamentally different from primary failure.

When a replica fails in asynchronous replication, the primary may continue accepting writes. The replica later resumes from its durable replication position and consumes missing changes.

The model demonstrates this by retaining the primary's ordered change stream and replaying the missing range after recovery.

Recovery should not normally mean blindly copying the entire database. A healthy replica with a valid log position can usually continue from the appropriate replication point.

If a replica's state or log history is no longer usable, a rebuild or reinitialization may be required.

## Primary failure and promotion

Primary failure is more sensitive because the primary owns write authority.

A safe promotion sequence conceptually requires:

`detect failure → fence old primary → select sufficiently current replica → promote replica → establish new primary generation → redirect writes`

The fencing step is essential.

Simply declaring a replica to be primary while the old primary can still accept writes creates split brain.

The Python, C++, JavaScript, and Java examples all refuse or model promotion while the old primary remains writable.

The generation field illustrates another important property: the new primary belongs to a new authority generation.

In real systems, this must be backed by an actual fencing or consensus mechanism. A counter stored only inside application memory cannot prevent a disconnected server from writing.

## Data consistency versus availability

Replication creates several distinct consistency questions.

A primary and replica can be temporarily different while asynchronous replication catches up.

A synchronous system can provide stronger commit durability characteristics, but synchronous acknowledgement does not automatically solve every consistency problem.

For example, a client may write to the primary and immediately read from a lagging asynchronous replica. The read may not yet contain the newly committed value.

Applications that require read-after-write behavior therefore need an appropriate read-routing or consistency strategy.

Possible approaches include:

- reading from the primary after a write,
- routing a session to an appropriately synchronized replica,
- waiting for a known replication position,
- using database-specific consistency guarantees.

The correct choice depends on the application's consistency requirements.

## Read scaling and replication topology

Primary-replica architecture can separate workloads.

The primary can handle writes while replicas serve read-heavy workloads such as:

- reporting,
- analytics,
- search-oriented queries,
- dashboards,
- read-only application traffic.

The architecture is not automatically linear in performance.

A replica can become a bottleneck if replay cannot keep up with the primary's change rate.

Network bandwidth, disk throughput, transaction volume, row/index modification cost, and replica query workload all affect replay capacity.

A replica under heavy analytical load may have sufficient CPU for queries but insufficient resources for timely replay.

## Synchronous versus asynchronous trade-offs

| Property | Asynchronous | Synchronous |
|---|---|---|
| Primary acknowledgement | Does not require replica replay | Requires configured replica acknowledgement |
| Write latency | Usually lower | Usually higher |
| Dependency on replica health | Lower | Higher |
| Potential replication window | Yes | Reduced according to acknowledgement semantics |
| Failure sensitivity | Primary can continue while replicas lag | Loss or slowdown of required replicas can affect writes |
| Operational complexity | Requires lag monitoring | Requires careful synchronous-node policy |
| Typical use | Read scaling, general redundancy, workloads tolerant of lag | Stronger durability requirements where added latency is acceptable |

These are architectural tendencies rather than universal guarantees. Actual behavior depends on the database engine and replication configuration.

## Edge cases

### Replica receives changes but does not replay them

This is represented by `received_lsn > replayed_lsn`.

The replica is not necessarily disconnected. It may simply be replaying slowly.

### Replica goes offline

The primary can continue in asynchronous mode while the replica accumulates a recovery gap.

A production system must retain enough log history for the replica to resume. If required log records have already been removed, the replica may require reinitialization.

### Synchronous replica failure

If the failed replica is required for acknowledgement, synchronous writes may stop or become unavailable.

This is not an implementation bug. It is a consequence of making replica acknowledgement part of the commit condition.

### Duplicate delivery

Network transports can retry messages.

The implementations therefore track applied LSNs and make replay idempotent.

A production database uses its own durable replication and transaction mechanisms rather than a simple in-memory set, but the invariant is important.

### Replay gap

If a replica has LSN 12 and receives LSN 14 without LSN 13, applying 14 immediately is unsafe for an ordered log model.

The implementations detect this situation rather than silently advancing the replica.

### Split brain

Two writable primaries can independently generate valid-looking writes that cannot be safely merged without a conflict-resolution strategy.

The safer architectural approach is to ensure that only one node has active write authority.

## Performance considerations

Asynchronous replication usually removes replica acknowledgement from the primary's critical write path, so primary latency is less sensitive to replica network round trips.

Synchronous replication adds network and replica processing latency to the acknowledgement path.

Replica replay throughput matters in both modes. If primary generation rate is higher than replica replay capacity, lag grows.

A useful operational approximation is:

`lag growth ≈ primary change rate - replica replay rate`

when the primary change rate exceeds replica replay capacity.

Large transactions can also create significant replay bursts. A replica may appear healthy between bursts while still experiencing substantial lag during high-volume transactions.

Indexes and secondary structures can make replay more expensive because replicated writes may require the same underlying maintenance work as primary writes.

## Monitoring considerations

Useful replication metrics include:

- current primary generation,
- primary log position,
- replica received position,
- replica replay position,
- byte or transaction lag,
- replay throughput,
- time since last replay,
- replica connection state,
- synchronous acknowledgement availability,
- failed replay attempts,
- replication slot or log-retention pressure where the database engine provides those mechanisms.

A replica with zero connection errors can still be unhealthy if its replay lag continues to increase.

## Security considerations

Replication channels carry database changes and can expose sensitive information.

Production replication should use authenticated replication identities and encrypted transport where supported.

Replication credentials should have only the privileges necessary for replication.

Administrative failover operations require stronger authorization than ordinary read access.

Fencing is also a security and integrity concern. An unauthorized or stale primary that continues accepting writes can corrupt the logical consistency of the cluster even if the database itself remains operational.

Replication logs and monitoring data may contain sensitive values, so operational observability should not automatically expose complete change payloads to every operator.

## Production distinction

The code in this artifact intentionally models replication behavior instead of implementing a real database storage engine.

A production database supplies mechanisms such as:

- durable transaction logging,
- crash recovery,
- WAL or binlog management,
- replication transport,
- transaction ordering,
- durable replay state,
- checkpointing,
- log retention,
- replication authentication,
- network security,
- replica initialization,
- failover tooling.

The Python, JavaScript, C++, and Java programs make those mechanisms observable as domain objects so that the acknowledgement, lag, ordering, and failure semantics can be examined directly.

The SQL implementation models the same state relationally and uses database constraints to enforce important invariants such as one primary per cluster and replay position not exceeding received position.

## Practical relationship between the mechanisms

Primary-replica architecture answers:

**Who writes, and where are redundant copies maintained?**

Asynchronous replication answers:

**Does the primary need to wait for a replica before acknowledging the write?**

Synchronous replication answers:

**Which replica acknowledgement conditions must be satisfied before the write is acknowledged?**

Replication lag answers:

**How far behind is a replica's replay state?**

Failover answers:

**How does write authority move when the primary becomes unavailable?**

Fencing answers:

**How do we prevent the old primary from continuing to write after authority has moved?**

These mechanisms solve different problems and should not be treated as interchangeable.

## Implementation map

| Implementation | Primary technical emphasis |
|---|---|
| Python | Executable replication simulation, lag, idempotent replay, synchronous acknowledgement, quorum behavior, consistency checks, and failover |
| JavaScript | Event-driven replication events, asynchronous delivery, replay processing, quorum behavior, and generation-aware promotion |
| C++ | Systems-oriented replication engine with typed change records, ordered replay, lag, acknowledgement rules, and failover fencing |
| Java | Enterprise domain model with immutable change records, explicit acknowledgement policy, validation, replay state, recovery, and promotion |
| SQL | Relational replication control model, WAL-like records, delivery state, replay enforcement, constraints, indexes, views, functions, and operational events |

## Key implementation invariants

The implementations consistently preserve several important invariants.

A replica cannot replay beyond what it has received.

A replica replays changes in ordered log position.

A duplicate change should not be applied as a new logical change.

A synchronous acknowledgement requires the configured acknowledgement condition.

A failed replica should not be counted as an available synchronous acknowledgement target.

A primary should not be promoted while the old primary remains writable.

A replica's process health is not equivalent to zero replication lag.

A new primary generation represents a change in write authority.

These invariants are more important than any particular programming-language representation because they express the underlying distributed-data behavior.
