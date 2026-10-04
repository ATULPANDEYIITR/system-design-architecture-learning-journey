# Transaction Isolation Levels

## Scope

This repository studies the four standard SQL transaction isolation levels:

- `READ UNCOMMITTED`
- `READ COMMITTED`
- `REPEATABLE READ`
- `SERIALIZABLE`

The implementations focus on the relationship between transaction visibility, concurrency, consistency, and anomalies. The central distinction is not simply that one level is "stronger" than another. Each level defines which effects from concurrent transactions a transaction is allowed to observe.

The examples use account records and business invariants because transactional correctness is particularly important when multiple operations must be evaluated against a consistent database state.

The repository contains three deliberately different implementations:

- Python provides a versioned in-memory transaction simulator with explicit transaction state, private writes, snapshots, row reads, range queries, validation, and anomaly demonstrations.
- JavaScript models transaction visibility while using asynchronous event scheduling to show how interleaved application operations can expose isolation behavior.
- C++ presents a transaction engine as a coherent case study, including version history, private write sets, snapshot reads, serial ownership, predicate queries, validation, and business-invariant failure.

## Transaction Isolation

A transaction is a logical unit of database work. It can read existing data, create or modify data, and eventually commit or roll back.

When transactions execute concurrently, the database must determine which effects are visible to each transaction. Isolation controls that visibility.

Consider two transactions operating on the same account:

`T1: read balance -> update balance -> commit`

`T2: read balance -> perform calculation -> commit`

If `T2` reads while `T1` has changed the account but has not committed, `T2` may observe data that later disappears. If `T1` commits between two reads by `T2`, the two reads may return different values. If `T2` executes a range query and another transaction inserts a new row that matches the range, the result set can change.

These are different concurrency effects and require different guarantees.

## Isolation Levels at a Glance

| Isolation level | Dirty reads | Non-repeatable reads | Phantom reads | Main characteristic |
|---|---|---|---|---|
| `READ UNCOMMITTED` | Possible | Possible | Possible | Allows the weakest visibility guarantees |
| `READ COMMITTED` | Prevented | Possible | Possible | Each normal read sees committed data at read time |
| `REPEATABLE READ` | Prevented | Prevented | Implementation-dependent | Repeated observations of previously read rows remain stable |
| `SERIALIZABLE` | Prevented | Prevented | Prevented | Transactions behave as if executed in a serial order |

The table describes the standard conceptual guarantees. Exact behavior varies between database engines because implementations can use locking, MVCC, snapshot isolation, serialization validation, predicate locking, or combinations of these techniques.

## READ UNCOMMITTED

`READ UNCOMMITTED` permits a transaction to observe data written by another transaction before that transaction commits.

The important property is that the reader is allowed to observe private transaction state.

Suppose account `1` has a committed balance of `1000`.

A writer changes the private value to `250`:

`T1: balance 1000 -> 250`

Before `T1` commits, another transaction reads the account:

`T2: reads 250`

If `T1` subsequently rolls back, the durable database returns to `1000`.

The value `250` was therefore never a committed database state, yet `T2` observed it. This is a dirty read.

The Python implementation makes this mechanism explicit through `_uncommitted` transaction write sets. The `READ UNCOMMITTED` branch checks those private writes before consulting committed versions.

The JavaScript implementation applies the same conceptual distinction using a `Map` for transaction-private writes. Its asynchronous scheduler makes the sequence visible as application events: write, dirty read, rollback, and subsequent committed read.

The C++ case study models private writes separately from version history. The `dirtyValue` function searches other active transaction write sets before the reader consults committed history.

### Why dirty reads are dangerous

A dirty value can influence decisions that become externally visible even though the underlying database operation is later rolled back.

Examples include:

- calculating a financial position from a value that will disappear;
- deciding that inventory is available when another transaction eventually rolls back;
- displaying a temporary state as if it were durable;
- triggering downstream processing from an uncommitted value.

`READ UNCOMMITTED` therefore provides very weak correctness guarantees.

## READ COMMITTED

`READ COMMITTED` prevents dirty reads. A transaction can see only committed data.

It does not necessarily provide a transaction-wide stable snapshot.

Suppose the initial balance is `1000`.

`T2` reads the balance and gets `1000`.

Another transaction changes the balance to `700` and commits.

`T2` reads the balance again and gets `700`.

Both reads were valid committed reads, but the value changed between statements.

This is a non-repeatable read.

The Python implementation models `READ COMMITTED` by resolving each read against the latest committed version rather than caching a transaction-wide row snapshot.

The JavaScript implementation uses the same visibility rule and demonstrates the effect by performing a second read after another transaction commits an update.

The C++ implementation explicitly documents this behavior in its `ReadCommitted` branch. Each read uses `latestCommitted`, so a later statement can observe a newer commit.

### Why READ COMMITTED is useful

`READ COMMITTED` is often a practical balance between consistency and concurrency.

It avoids the particularly dangerous behavior of consuming uncommitted data while allowing transactions to observe current committed information.

The trade-off is that a multi-statement transaction cannot assume that an earlier read will still be true when it performs a later read.

For example:

`SELECT balance`

followed later by:

`SELECT balance`

does not necessarily produce the same value under `READ COMMITTED`.

Applications that require the two observations to remain stable need stronger semantics or a different concurrency-control design.

## REPEATABLE READ

`REPEATABLE READ` strengthens transaction-level consistency for previously observed rows.

The key distinction from `READ COMMITTED` is that a transaction can retain the version it originally observed rather than automatically switching to the newest committed version after another transaction commits.

The Python implementation stores the first visible value of a row in `Transaction.read_cache`. Subsequent reads of that row use the cached observation.

The JavaScript implementation applies the same mechanism through the `readCache` map inside each `Transaction`.

The C++ implementation stores cached observations in `Transaction::readCache` and obtains the original visible version using the transaction's `snapshotVersion`.

This makes the following sequence stable:

`T1 reads 1000`

`T2 changes 1000 to 700 and commits`

`T1 reads the same row again`

Under the model used by the implementations, `T1` continues to observe `1000`.

### Row stability versus predicate stability

A crucial technical distinction is that repeatable observation of an existing row does not automatically mean that every query result is permanently fixed.

A range query such as:

`balance BETWEEN 1000 AND 5000`

is a predicate over a set of rows.

If another transaction inserts a new account with a balance of `3000`, the new account satisfies the predicate even though it did not exist in the original result.

This is the phantom-read problem.

The exact phantom behavior of `REPEATABLE READ` is database-engine dependent. Some systems provide stronger snapshot semantics, while others use locking schemes with different behavior. `REPEATABLE READ` should therefore not be treated as a universal synonym for `SERIALIZABLE`.

## SERIALIZABLE

`SERIALIZABLE` is the strongest isolation level in the standard hierarchy.

Its defining property is serial-equivalent behavior: the final effect of concurrent transactions must be consistent with some serial ordering of those transactions.

A serial execution might be:

`T1 -> T2`

or:

`T2 -> T1`

but not an uncontrolled interleaving whose result cannot be explained by a valid serial order.

A database can implement this guarantee in different ways. Possible mechanisms include:

- strict two-phase locking;
- key-range or predicate locks;
- serializable snapshot isolation;
- conflict detection and transaction aborts;
- timestamp ordering;
- optimistic validation followed by retry.

The implementations in this repository deliberately use a simpler model.

Python represents `SERIALIZABLE` with a database-level serial lock.

JavaScript represents the concept through a serial execution token and demonstrates asynchronous transaction admission around that conceptual critical section.

C++ represents the rule using `serialOwner_`. Only one `SERIALIZABLE` transaction can own the execution token at a time.

These are teaching models rather than claims about the internal implementation of a particular DBMS.

### Concurrency trade-off

Stronger isolation can reduce concurrency.

Depending on the database engine, serialization can cause:

- blocking;
- lock contention;
- deadlocks;
- serialization failures;
- transaction aborts;
- retries;
- increased latency.

A production application therefore needs to treat serialization failures as possible control-flow events rather than assuming every transaction will always commit on its first attempt.

## Concurrency Anomalies

### Dirty read

A transaction reads a value written by another transaction before that value commits.

Example:

`T1 writes 250`

`T2 reads 250`

`T1 rolls back`

`250` was never durable.

This is possible under `READ UNCOMMITTED` and prevented by the stronger isolation levels.

### Non-repeatable read

A transaction reads an existing row, another transaction changes and commits that row, and the first transaction reads it again and obtains a different value.

Example:

`T1 reads 1000`

`T2 commits 700`

`T1 reads 700`

`READ COMMITTED` can permit this. `REPEATABLE READ` and `SERIALIZABLE` prevent the effect under their corresponding guarantees.

### Phantom read

A transaction executes a predicate query twice and observes a changed set of qualifying rows because another transaction inserted, removed, or changed rows that satisfy the predicate.

Example:

`T1 queries balances from 1000 through 5000`

`T2 inserts account 4 with balance 3000 and commits`

`T1 repeats the range query`

The second result can contain a row that was not present in the first result.

Predicate-level protection is one of the reasons `SERIALIZABLE` requires stronger concurrency control than simple protection of already-read rows.

### Write skew

Write skew is an important advanced case because the conflicting condition may be distributed across multiple rows.

Suppose two doctors are available and the business rule requires at least one doctor to remain available.

`T1` sees both doctors and disables doctor A.

`T2` independently sees both doctors and disables doctor B.

If both changes commit, no doctor remains available.

Neither transaction necessarily changed the same row as the other transaction. The problem is the relationship between their reads and writes.

The C++ case study demonstrates this business-invariant failure using account balances as availability flags.

This example shows why stable individual row reads do not automatically guarantee that a multi-row business rule is safe under concurrent execution.

## Version Visibility Model

The Python, JavaScript, and C++ implementations separate committed history from transaction-local writes.

Conceptually, a row can have history resembling:

`commit 1 -> balance 1000`

`commit 2 -> balance 700`

`commit 3 -> balance 900`

A snapshot at commit version `1` sees `1000`.

A snapshot at commit version `2` sees `700`.

A current committed read sees the newest committed version.

This is a simplified model of version visibility. Real MVCC systems can maintain row versions with transaction identifiers, visibility metadata, undo information, timestamps, or other structures.

The purpose of the model is to make the visibility decision explicit rather than hiding it behind SQL syntax.

## Transaction Lifecycle in the Implementations

A transaction begins with an isolation level and a snapshot point.

During its active state it can:

- read committed or transaction-visible data;
- create private writes;
- execute predicate queries;
- validate input;
- commit its private writes;
- or discard its private writes through rollback.

A commit advances the simulated database version and transfers transaction-local writes into committed history.

A rollback discards private writes.

The implementations reject operations on completed transactions because allowing an application to continue using a committed transaction object would obscure the transaction boundary being demonstrated.

## Python Implementation

The Python program is a versioned in-memory transaction laboratory.

Its central structures are:

- `Account`, representing domain data;
- `Version`, representing committed historical versions;
- `Transaction`, representing isolation level, snapshot state, private writes, cached reads, and predicates;
- `InMemoryDatabase`, implementing visibility and transaction lifecycle.

`read_account()` is the central isolation mechanism. Its behavior changes according to the transaction's isolation level.

For `READ UNCOMMITTED`, it can inspect another transaction's private write set.

For `READ COMMITTED`, it reads the newest committed version.

For `REPEATABLE READ`, it establishes and reuses a row observation from the transaction snapshot.

For `SERIALIZABLE`, the simulator requires ownership of a serial execution lock.

The program also demonstrates range predicates, rollback, invalid balances, operations on inactive transactions, write skew, and the practical trade-offs between isolation levels.

The output is intended to expose the mechanism rather than merely print a theoretical table.

Run with:

`python isolation_levels.py`

## JavaScript Implementation

The JavaScript program provides a complementary event-driven representation.

`TransactionDatabase` manages committed versions, private writes, transaction snapshots, and read caches.

The `StepScheduler` is specifically useful for demonstrating JavaScript's asynchronous execution model. It executes named events with delays, making a dirty-read sequence visible as application-level events.

The scheduler does not claim to be a database lock manager. JavaScript's event loop is not a substitute for database transaction isolation. Its role here is to show how application operations can be interleaved while the database still has to decide which state each transaction may observe.

The program also uses:

- classes for transaction and account state;
- `Map` for transaction-local write sets;
- `Promise` and asynchronous functions for event sequencing;
- explicit validation errors;
- a serial execution concept for `SERIALIZABLE`;
- console tables for isolation comparison.

Run with:

`node isolation_levels.js`

## C++ Case Study

The C++ implementation models a financial-account transaction engine.

The scenario uses account balances because concurrent updates have a direct consistency consequence.

Its architecture separates:

`history_`

from:

`privateWrites_`

The first stores committed row versions. The second stores writes belonging to active transactions.

`Transaction` stores the isolation level, snapshot version, cached repeatable-read observations, pending writes, and predicates.

`GovernanceDatabase::read()` implements the visibility rules.

`GovernanceDatabase::write()` modifies transaction-local state without making it durable.

`commit()` creates a new committed version.

`rollback()` removes the private state.

`rangeQuery()` demonstrates why predicate queries have semantics distinct from single-row reads.

The `serialOwner_` field models exclusive serial execution for the `SERIALIZABLE` case study.

The write-skew demonstration introduces a business invariant: at least one doctor must remain available. Two `REPEATABLE READ` transactions can independently make decisions that are valid from their own observations while producing an invalid combined state.

This makes the C++ program more than an isolated anomaly demonstration. It models how isolation requirements interact with application-level business rules.

Compile using a C++17 compiler:

`g++ -std=c++17 -O2 -Wall -Wextra -pedantic isolation_levels.cpp -o isolation_levels`

Run with:

`./isolation_levels`

On Windows with a suitable C++17 toolchain, the resulting executable can be launched as:

`isolation_levels.exe`

## Why the Four Levels Are Not Interchangeable

`READ UNCOMMITTED` is primarily distinguished by its willingness to expose uncommitted state.

`READ COMMITTED` removes that dirty visibility but still permits a transaction to see different committed versions across statements.

`REPEATABLE READ` strengthens transaction-level stability for observations already made, while exact predicate behavior depends on the database implementation.

`SERIALIZABLE` moves the guarantee to serial-equivalent transactional behavior. The database must prevent or detect concurrent effects that would produce a result inconsistent with some serial ordering.

These are different guarantees rather than four names for the same concept.

## Snapshot and Current-Read Semantics

The implementations intentionally distinguish a snapshot read from a current committed read.

A snapshot read answers a question similar to:

"What value was visible to this transaction's snapshot?"

A current read answers:

"What is the newest committed value visible now?"

That distinction explains why `READ COMMITTED` and `REPEATABLE READ` can behave differently even when no transaction is reading uncommitted data.

The exact SQL behavior of a real DBMS can also depend on whether a statement is an ordinary consistent read, a locking read, or another specialized operation.

## Range Queries and Predicate Protection

A row lookup identifies a particular record.

A predicate query identifies a set of records satisfying a condition.

For example:

`account_id = 42`

identifies a particular row, while:

`balance BETWEEN 1000 AND 5000`

defines a set.

Protecting existing rows does not necessarily prevent another transaction from creating a new row that satisfies the predicate.

A serializable implementation must therefore control the logical range, detect dangerous conflicts, or otherwise ensure that the final outcome is equivalent to a valid serial ordering.

This is why phantom behavior is an important distinction when comparing `REPEATABLE READ` and `SERIALIZABLE`.

## Performance Considerations

Isolation affects concurrency because stronger guarantees require additional coordination.

`READ UNCOMMITTED` has minimal visibility coordination but can expose invalid intermediate state.

`READ COMMITTED` generally allows more concurrency because transactions do not need to preserve every previously observed committed value for the entire transaction.

`REPEATABLE READ` can require version retention or stronger locking so that previously observed rows remain consistent.

`SERIALIZABLE` can introduce the greatest coordination cost because conflicting transactions may have to wait, abort, or retry.

The cost is not simply CPU time. It can appear as:

- lock waits;
- increased transaction latency;
- reduced throughput;
- deadlocks;
- serialization failures;
- memory or storage overhead for version retention;
- application retries.

The appropriate level is therefore a correctness decision constrained by the workload, not a universal setting where the strongest option is always preferable.

## Common Mistakes

### Treating READ COMMITTED as a transaction-wide snapshot

`READ COMMITTED` prevents dirty reads but does not guarantee that repeated statements see the same committed version.

### Treating REPEATABLE READ as identical to SERIALIZABLE

The guarantees and implementation details differ. In particular, predicate and write-conflict behavior can be stronger under `SERIALIZABLE`.

### Assuming a successful individual update proves an invariant is safe

A transaction can make a locally valid decision while another transaction makes a different locally valid decision. Their combined commits can violate a multi-row business rule.

### Ignoring database-engine differences

SQL isolation levels have standard conceptual definitions, but implementation mechanisms and edge behavior differ across PostgreSQL, MySQL/InnoDB, SQL Server, Oracle, and other systems.

### Assuming isolation replaces constraints

Isolation controls concurrency visibility and transactional behavior. Database constraints remain important for enforcing properties such as uniqueness, valid ranges, and referential integrity.

### Assuming SERIALIZABLE means "nothing can fail"

Serializable transactions can still be aborted because the database detects a serialization conflict. Production code may need retry logic around retryable transaction failures.

## Validation and Failure Handling

The implementations reject invalid account balances.

They also reject:

- unsupported isolation levels;
- invalid transaction states;
- duplicate account identifiers;
- invalid numeric ranges;
- negative balances;
- operations against missing accounts;
- operations after commit or rollback.

These checks are intentionally part of the transaction model because isolation logic operates inside a larger state machine. Correct visibility alone does not make invalid transaction operations safe.

## Security and Integrity Considerations

Isolation is directly relevant to data integrity.

For financial systems, inventory systems, booking systems, and authorization-related data, consuming inconsistent transaction state can result in incorrect decisions.

Applications should avoid assuming that a read is sufficient to reserve or claim a resource. A safe design must account for the entire read-modify-write sequence and the business invariant involved.

Sensitive operations should also rely on database-enforced constraints and appropriate transaction semantics rather than trusting application-level checks performed outside the transaction.

Isolation does not itself provide authentication, authorization, encryption, or auditing. It is one component of transactional integrity.

## Debugging Transaction Anomalies

Transaction bugs are often difficult to reproduce because they depend on operation ordering.

A useful debugging record includes:

- transaction identifier;
- isolation level;
- operation type;
- row or predicate involved;
- transaction snapshot or visibility point;
- commit and rollback events;
- blocking or conflict information;
- retry decisions.

The Python and C++ implementations expose transaction IDs, snapshots, private writes, and committed versions so the visibility decision can be followed directly.

The JavaScript implementation exposes event ordering, which is useful when diagnosing application-level asynchronous interleavings.

## Production Design Considerations

A production system should select an isolation level according to the invariant that must remain correct.

A transaction that only needs committed point-in-time reads may fit `READ COMMITTED`.

A transaction that needs stable observations across multiple statements may require stronger semantics.

A transaction that coordinates a predicate-based resource allocation or a multi-row invariant may require `SERIALIZABLE`, explicit locking, carefully designed constraints, or another concurrency-control strategy.

When stronger isolation can cause retries, application code should make transactions retry-safe. Operations should avoid unintended external side effects before successful commit, or use an appropriate outbox or transactional integration pattern when external systems are involved.

Long-running transactions should also be avoided when practical because they can increase lock contention or delay cleanup of old row versions in MVCC systems.

## Practical Interpretation

The progression can be understood as increasing control over concurrent visibility:

`READ UNCOMMITTED`

allows uncommitted observations.

`READ COMMITTED`

requires committed observations but permits changes between statements.

`REPEATABLE READ`

stabilizes transaction observations of rows already visible to the transaction.

`SERIALIZABLE`

requires the complete transactional result to be equivalent to some serial execution.

The important engineering question is therefore not "Which isolation level is best?" but "Which concurrent outcomes are acceptable for this transaction and this business invariant?"

## Limitations of the Simulators

These programs model isolation concepts rather than implementing production database engines.

The Python simulator uses explicit version objects and a coarse serial lock.

The JavaScript simulator uses asynchronous scheduling and in-memory maps instead of a database storage engine.

The C++ simulator uses a serial ownership token rather than implementing a complete lock manager, MVCC subsystem, deadlock detector, or serialization validator.

Real database systems have substantially more complicated behavior involving transaction IDs, locks, latches, visibility rules, indexes, WAL or equivalent durability mechanisms, crash recovery, vacuum or garbage collection, deadlock detection, connection-level state, and query execution.

The examples therefore provide a mechanism-level model suitable for understanding isolation rather than a specification of the internals of any particular database product.
