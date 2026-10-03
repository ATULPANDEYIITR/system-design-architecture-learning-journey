# Transactions: ACID Properties and Transactional Guarantees

## Topic Scope

A transaction is a logical unit of work whose constituent operations must be coordinated according to defined correctness guarantees. In a financial system, a transfer is not merely a subtraction followed by an addition. It is a business operation in which the debit, credit, transfer record, and accounting entries have to form a coherent state transition.

The central ACID properties are:

- **Atomicity**: the transaction's changes are treated as one unit. A failed transaction does not leave only part of its intended work committed.
- **Consistency**: a successful transaction moves the database from one valid state to another valid state while preserving database constraints and application invariants.
- **Isolation**: concurrent transactions are prevented from observing or producing invalid intermediate states according to the isolation guarantees provided by the database.
- **Durability**: once a transaction has successfully committed, the database's durability mechanism is responsible for preserving that committed state across subsequent recovery events.

These properties are related but are not interchangeable. Atomicity is primarily concerned with all-or-nothing completion. Consistency concerns valid state transitions. Isolation concerns concurrent visibility and interaction. Durability concerns preservation of committed state.

The three implementations approach the same subject from different technical perspectives:

- The Python implementation uses a real SQLite database and demonstrates actual transaction statements, constraints, savepoints, concurrent connections, rollback, commit, and persistence.
- The JavaScript implementation builds an event-driven transaction model using private transaction snapshots, staged mutations, optimistic concurrency, idempotency keys, and lifecycle events.
- The C++ implementation models a payment transaction coordinator with explicit transaction states, staged account mutations, version-based concurrency control, a double-entry ledger, idempotency, validation, and audit events.

## Transaction Boundaries

A transaction boundary defines which operations belong to the same atomic unit.

Consider a transfer from account `A100` to `B200`. A correct transaction may contain:

- validation of the source and destination accounts
- validation of the amount and currency
- debit of the source account
- credit of the destination account
- creation of the transfer record
- creation of the corresponding ledger entries

If only the debit is committed and the application fails before the credit, the database contains a state that does not represent the intended business operation.

The transaction boundary therefore has to follow the business operation rather than arbitrary individual statements.

The Python function `transfer()` demonstrates this boundary with an explicit `BEGIN`, multiple SQL statements, and a single `COMMIT`. Any exception causes `ROLLBACK`.

The C++ `Transaction::transfer()` method stages all dependent mutations, while `Transaction::commit()` publishes them only after validation succeeds. This makes the boundary explicit in the application architecture.

## Atomicity

Atomicity means that a transaction is indivisible from the perspective of the committed database state.

A useful mental model is:

`initial state -> transaction work -> committed state`

or:

`initial state -> failed transaction -> initial state`

There should not be a durable state representing only a subset of the transaction.

### Python implementation

The Python implementation uses SQLite's actual transaction mechanism. The transfer operation performs:

- source-account lookup
- destination-account lookup
- conditional debit
- destination credit
- transfer insertion
- ledger insertion
- commit

A deliberately injected exception occurs before the final ledger operation. The exception triggers `ROLLBACK`. The demonstration then verifies that both account balances are exactly what they were before the transaction.

This is stronger than simply catching an exception in application code. The rollback is performed by the database transaction mechanism, which discards the transaction's uncommitted changes.

### JavaScript implementation

The JavaScript implementation uses staged state. A `Transaction` owns a snapshot and a set of pending mutations. Changes remain outside the shared `LedgerStore` until `commit()` succeeds.

If the callback throws before commit, `rollback()` clears the staged account changes, pending transfers, and pending ledger entries.

This models the conceptual boundary that a database engine implements internally.

### C++ implementation

The C++ case study follows the same architectural idea using `staged_accounts_`, `pending_transfers_`, and `pending_ledger_`.

`Transaction::commit()` first validates the complete staged state. Only after validation and concurrency checks succeed are changes applied to `Store`.

This separates mutation preparation from publication.

## Consistency

Consistency means that transactions must preserve defined rules and invariants. ACID consistency is not simply a promise that "the database will be correct" without specification. The relevant constraints must be represented by database constraints, transaction logic, or both.

The financial case study uses several concrete invariants:

- account balances cannot be negative
- account currencies must be supported
- source and destination accounts must exist
- source and destination must differ
- a transfer amount must be positive
- a transfer must not mix currencies without conversion logic
- every committed transfer must have a matching debit
- every committed transfer must have a matching credit
- debit and credit amounts must match
- total balances in a currency remain conserved by an internal transfer

The Python schema uses `CHECK`, `PRIMARY KEY`, and `FOREIGN KEY` constraints. These constraints make some invalid states impossible at the database layer.

The application also performs business validation before committing a transaction. This distinction matters because not every business invariant can be represented conveniently as a simple database constraint.

## Database Constraints and Application Invariants

Database constraints are useful because they provide a final correctness boundary close to the stored data.

The Python `accounts` table contains:

`CHECK (balance_cents >= 0)`

This prevents a transaction from storing a negative balance through ordinary SQL operations.

The `transfers` table uses a primary key for `transfer_id`. The uniqueness rule is important for idempotency because the same logical transfer should not be inserted twice under the same identifier.

Foreign keys ensure that a transfer references existing accounts.

Application-level invariants complement these constraints. The ledger requirement that every transfer has one debit and one credit is explicitly verified by `verify_ledger_integrity()`.

A robust design normally uses both layers where practical:

`application validation -> transaction processing -> database constraints -> commit`

Application validation provides meaningful business errors. Database constraints provide a final integrity barrier against invalid state.

## Isolation

Isolation addresses what happens when multiple transactions execute concurrently.

Without appropriate isolation, one transaction could observe another transaction's intermediate changes, overwrite a concurrent change, or make decisions based on stale data.

The exact behavior depends on the database engine and selected isolation level. Common isolation concepts include:

- **Read uncommitted**: permits the weakest visibility guarantees and may permit dirty reads depending on the engine.
- **Read committed**: a statement normally sees committed data available under the database's rules at statement execution.
- **Repeatable read**: repeated reads of previously observed rows receive stronger stability guarantees.
- **Serializable**: concurrent execution is constrained so that the result corresponds to some serial ordering of transactions.
- **Snapshot-based isolation**: a transaction can read from a consistent snapshot while concurrent work proceeds.

Isolation levels are database-specific in their exact implementation and terminology. A label should not be treated as proof of identical behavior across database systems.

### Python isolation demonstration

The Python program opens two SQLite connections. One connection performs an uncommitted update while the second connection reads the account.

The second connection does not observe the first connection's uncommitted balance change under the demonstrated configuration.

The example then commits the first transaction and verifies the new balance.

The example is intentionally tied to SQLite rather than presented as universal behavior for every database engine.

### JavaScript snapshot model

The JavaScript implementation gives each transaction a private snapshot when `begin()` is called.

If transaction A changes an account but has not committed, transaction B continues reading its own snapshot.

This is an educational model of snapshot-oriented isolation. It is not a replacement for the concurrency implementation of a production database engine.

## Optimistic Concurrency Control

Isolation alone does not mean that an application can safely perform a read-modify-write sequence without considering concurrent updates.

The JavaScript and C++ implementations therefore use account versions.

Suppose both transactions read:

`A100.version = 0`

Transaction A commits an update and changes the version to `1`.

Transaction B still holds version `0`. When B tries to commit, it detects:

`current version != original version`

and rejects the transaction as a serialization conflict.

The transaction can then be retried from a fresh snapshot.

This approach is called optimistic concurrency control because conflicting transactions are allowed to proceed until commit-time validation detects an incompatible concurrent change.

It is especially useful when conflicts are relatively uncommon and holding database locks for a long period would be undesirable.

## Durability

Durability concerns committed state after the transaction has successfully committed.

A database may use mechanisms such as:

- write-ahead logging
- transaction logs
- journal files
- flushed data pages
- recovery protocols
- replication

The exact durability guarantee depends on the database engine, configuration, storage system, and failure model.

The Python implementation demonstrates durability more concretely because SQLite writes to a temporary database file. After a successful commit, the connection is closed and a new connection opens the same database. The committed balances remain available.

The JavaScript implementation intentionally distinguishes committed application state from actual durable storage. Its in-memory `LedgerStore` does not provide operating-system-backed durability. The code comments identify this boundary rather than pretending that an in-memory object provides database durability.

The C++ `Store` likewise represents a storage boundary rather than implementing a filesystem or database recovery engine. Its case study focuses on transaction coordination and correctness rules.

## Commit and Rollback

`COMMIT` publishes the transaction's changes according to the database engine's transaction mechanism.

`ROLLBACK` discards changes that belong to the active transaction.

The distinction is particularly important when an operation contains several dependent statements.

For example:

`debit -> credit -> transfer record -> ledger entries`

should not become:

`debit committed -> application failure -> credit missing`

The Python implementation directly demonstrates this with SQLite.

The JavaScript implementation represents the same concept by keeping changes in transaction-local structures until commit.

The C++ implementation applies staged state only after consistency and concurrency validation.

## Savepoints

A savepoint provides a rollback point inside a larger transaction.

The Python implementation creates a savepoint for an optional operation:

`SAVEPOINT optional_step`

The operation is then undone with:

`ROLLBACK TO SAVEPOINT optional_step`

The surrounding transaction remains active, allowing other work to continue before the final commit.

This is useful when a business operation contains an optional sub-operation that may fail without invalidating the entire transaction.

A savepoint is not equivalent to an independent transaction. The outer transaction still determines whether the overall unit commits.

## Idempotency and Transactional Guarantees

Idempotency is not itself one of the four ACID letters, but it is an important companion to transactional design, especially in distributed systems.

Consider a payment request:

`POST /payments`

The server commits the transaction, but the network connection fails before the client receives the response.

The client may retry the request.

If the retry performs the same financial mutation again, the customer could be charged twice.

An idempotency key gives repeated attempts a stable identity.

The implementations use identifiers such as:

`TRANSFER-IDEMPOTENT`

and request keys such as:

`payment-request-7f31`

The key should be stored atomically with the operation or associated with a durable record so that a crash cannot produce an ambiguous state between "operation committed" and "idempotency record missing."

The important relationship is:

`ACID transaction + idempotency strategy`

rather than treating idempotency as a substitute for transactions.

## Retryable and Non-Retryable Failures

Transactions frequently encounter failures that have different meanings.

A serialization conflict or temporary database lock can be retryable.

An invalid amount, missing account, currency mismatch, or insufficient funds is normally a business failure and should not be retried unchanged.

The Python retry demonstration explicitly accepts only `sqlite3.OperationalError` as the retryable class for its simulated transient failure.

The JavaScript model attaches a `retryable` property to `TransactionError`.

The C++ `TransactionError` similarly carries a Boolean retryability attribute.

This distinction prevents a dangerous pattern in which every exception causes repeated execution.

Retries also need bounded attempts and appropriate delay strategies. A retry must begin a fresh transaction rather than attempting to continue a transaction that has already been rolled back or invalidated.

## Double-Entry Ledger Invariant

The case study uses a simple accounting model.

For a transfer of `100.00 INR`:

`DEBIT A100 100.00`

and:

`CREDIT B200 100.00`

The two entries must balance.

This gives a concrete consistency invariant:

`sum(debits for transfer) = sum(credits for transfer) = transfer amount`

The Python implementation verifies this through SQL aggregation.

The JavaScript implementation checks the staged ledger entries before commit.

The C++ implementation checks the pending ledger entries in `Transaction::validateConsistency()`.

The ledger invariant is deliberately separate from the transaction mechanism. ACID provides transaction guarantees; the application defines what constitutes a valid financial state.

## Transaction Lifecycle

The implementations represent a transaction lifecycle using states:

`CREATED -> ACTIVE -> COMMITTED`

or:

`CREATED -> ACTIVE -> ROLLED_BACK`

A committed transaction cannot subsequently be rolled back through the application transaction object.

This state model prevents invalid operations such as:

- committing a transaction twice
- rolling back after commit
- modifying a transaction after rollback
- reading transaction-local state before the transaction begins

The JavaScript implementation exposes these states through `TransactionState`.

The C++ implementation uses `TransactionState` as an enum class.

The Python implementation delegates the transaction state machine to SQLite's transaction mechanism using explicit `BEGIN`, `COMMIT`, and `ROLLBACK`.

## Python Implementation

The Python program uses SQLite because it provides a real transactional database without requiring an external server.

The database schema contains:

- `accounts` for balances and currency
- `transfers` for business-level transfer identities
- `ledger` for debit and credit entries

The implementation demonstrates actual database operations rather than merely printing an imagined transaction sequence.

Important implementation details include:

- `PRAGMA foreign_keys = ON` enables foreign-key enforcement for every SQLite connection.
- Monetary values are represented as integer cents in database storage, avoiding binary floating-point representation for persisted money.
- Conditional balance updates use `balance_cents >= ?` so the debit succeeds only when sufficient funds exist.
- A unique transfer identifier prevents duplicate insertion.
- Database constraints provide a final integrity boundary.
- Savepoints demonstrate partial rollback inside a larger transaction.
- Two connections demonstrate transaction visibility and SQLite write behavior.
- Reopening the database demonstrates persistence of committed data.
- The retry helper retries only explicitly classified transient database errors.
- Ledger verification provides an application-level reconciliation check.

The Python script is therefore both an executable transaction demonstration and a compact example of how application rules can be layered over a relational database.

## JavaScript Implementation

The JavaScript program uses Node.js built-in modules and takes an event-driven approach.

`LedgerStore` represents shared committed state.

`Transaction` represents an isolated unit of work. It receives a snapshot at `begin()`, stages changes locally, validates them, checks versions, and then publishes them during `commit()`.

`TransactionService` provides a higher-level execution boundary and emits transaction lifecycle events.

`IdempotencyRegistry` models the request-level mechanism needed to prevent a network retry from repeating a committed operation.

The event system produces events such as:

`transaction.begin`

`transaction.mutation`

`transaction.commit`

`transaction.rollback`

This reflects an important operational distinction: transaction correctness and transaction observability are different concerns. A transaction engine can be correct while still being difficult to operate if there is no audit trail or lifecycle telemetry.

The JavaScript implementation also demonstrates optimistic concurrency. Account versions detect whether another transaction changed data that the current transaction relied upon.

The in-memory model does not claim to reproduce every isolation behavior of a production database. Its purpose is to make transaction state, snapshots, staged writes, conflict detection, and event-driven behavior explicit.

## C++ Payment Transaction Case Study

The C++ implementation models a payment service using explicit transaction objects.

The architecture consists of:

`Store`

Holds committed accounts, transfers, ledger entries, and audit events.

`Transaction`

Owns transaction-local staged account changes, original versions, pending transfers, and pending ledger entries.

`PaymentService`

Provides the higher-level operation that creates a transaction, executes the transfer, commits it, or rolls it back after failure.

`IdempotencyRegistry`

Associates a request key with a committed result so that repeated requests can reuse the existing outcome.

### Data structures

The account model contains:

- account identifier
- owner
- currency
- balance in integer cents
- version number

Transfers contain:

- transfer identifier
- source account
- destination account
- amount

Ledger entries contain:

- transfer identifier
- account identifier
- debit or credit direction
- amount

The use of integer cents avoids floating-point rounding problems in the core accounting calculations.

### Commit algorithm

The C++ transaction commit process is conceptually:

`validate staged state`

`check original account versions`

`verify transfer identifiers`

`apply staged accounts`

`increment versions`

`insert transfers`

`insert ledger entries`

`mark transaction committed`

The important design decision is that validation occurs before publication.

A production database would normally provide the atomic publication mechanism itself. The case study models the same logical architecture in memory to make the boundaries visible in source code.

### Failure handling

If validation fails, the transaction is rolled back.

If a concurrency conflict is detected, the transaction is marked as failed and can be recreated from fresh state.

If a business rule fails, such as insufficient funds, the operation is rejected without changing committed balances.

The C++ code also distinguishes retryable failures from non-retryable validation errors.

## ACID Versus Related Guarantees

ACID should not be treated as a collection of unrelated features.

| Concern | Main question | Demonstrated mechanism |
|---|---|---|
| Atomicity | Did all dependent changes commit together? | Explicit rollback and staged commit |
| Consistency | Did the state remain valid? | Constraints, balance checks, ledger invariants |
| Isolation | How do concurrent transactions interact? | SQLite visibility and version checks |
| Durability | Does committed state survive reopening/recovery? | SQLite file persistence |
| Idempotency | Can a retried request repeat the effect? | Unique transfer IDs and request keys |
| Concurrency control | What happens when another transaction changes the same data? | Optimistic version validation |
| Auditability | Can transaction lifecycle be reconstructed? | Audit and event records |

Idempotency, auditability, and concurrency-control techniques complement ACID but should not be confused with individual ACID properties.

## Common Transaction Failure Modes

### Partial business operations

A debit is committed without its corresponding credit because the application treats each statement as an independent operation.

The solution is to define a transaction boundary that includes all dependent changes.

### Long-running transactions

A transaction remains open while the application waits for an external service.

This can increase lock duration, resource consumption, contention, and conflict probability.

A common design is to avoid holding database transactions open across slow network operations unless the architecture explicitly requires that behavior.

### Retrying non-idempotent work

A transient error causes a request to be executed again, but the first attempt may already have committed.

Without an idempotency mechanism, the retry can produce a duplicate effect.

### Treating rollback as universal recovery

Rollback can undo the database transaction, but it cannot automatically undo external side effects that occurred outside the transaction.

For example, an email, external API request, message delivery, or physical action may not be reversible merely because the database transaction rolls back.

Distributed workflows therefore need explicit coordination patterns when external side effects are involved.

### Assuming ACID solves every business invariant

A database transaction cannot infer a business rule that has never been encoded.

For example, "a customer may not exceed a daily transfer limit" requires an explicit rule and appropriate transaction logic.

### Assuming one isolation level behaves identically everywhere

Database engines implement isolation using different locking, versioning, snapshot, and logging mechanisms.

Isolation-level names provide useful concepts, but production behavior must be evaluated for the actual database engine and configuration.

## Performance Considerations

Transactions have overhead.

A larger transaction may reduce the number of commits but can also hold locks or snapshots for longer.

Very short transactions generally reduce contention, but excessively fragmented transactions may destroy atomicity when several operations are logically one unit.

Useful performance considerations include:

- keep transaction boundaries aligned with business atomicity
- avoid unnecessary queries while a transaction is open
- avoid waiting on remote services inside a database transaction
- index columns used for transactional lookups
- use conditional updates when the correctness condition belongs in the same database operation
- monitor lock waits and serialization conflicts
- keep retry counts bounded
- avoid retry storms by introducing appropriate backoff
- measure commit latency separately from application processing latency

Performance optimizations must not remove a required correctness guarantee merely to reduce transaction duration.

## Security Considerations

Transaction correctness is part of application security when transactions modify financial, authorization, inventory, or other sensitive state.

Relevant controls include:

- use parameterized SQL instead of string concatenation
- validate authorization before performing sensitive mutations
- do not trust client-provided account ownership information
- protect idempotency keys from predictable collisions where they carry security significance
- record sufficient audit information to investigate sensitive state changes
- restrict database permissions according to least privilege
- avoid exposing database error details directly to untrusted clients
- use database constraints as a defense against invalid state, not as the only authorization mechanism

The Python implementation uses parameterized SQL for transaction values, which avoids treating user-controlled values as executable SQL syntax.

## Debugging and Operational Verification

Transaction failures can be difficult to diagnose because the visible database state may show only the final committed result.

Useful diagnostic information includes:

- transaction identifier
- transfer or business-operation identifier
- request or idempotency key
- transaction start and completion timestamps
- retry count
- failure classification
- affected account or record identifiers
- concurrency-conflict information
- commit or rollback outcome

The JavaScript implementation demonstrates event-driven lifecycle observation.

The C++ implementation stores audit events containing transaction identifiers and event types.

The Python implementation performs post-operation ledger verification.

These mechanisms serve different purposes. Audit records explain what happened, reconciliation checks whether state remains coherent, and transaction logs support database recovery.

## Production Considerations

A production transactional system normally delegates the fundamental ACID implementation to a mature database engine rather than implementing durability or isolation in application memory.

The application layer should define:

- transaction boundaries
- business invariants
- validation rules
- retry policy
- idempotency semantics
- authorization requirements
- reconciliation rules
- audit requirements

The database layer should enforce appropriate:

- constraints
- transactional atomicity
- isolation semantics
- durability configuration
- indexing
- locking or versioning behavior
- recovery mechanisms

The boundary between application and database is important. Application code determines what the transaction means. The database engine provides the mechanisms needed to safely store and coordinate the transaction.

## Key Relationships

The complete model can be viewed as:

`Business operation`

`-> transaction boundary`

`-> validation`

`-> transactional reads and writes`

`-> consistency checks`

`-> concurrency/isolation checks`

`-> COMMIT or ROLLBACK`

`-> durable committed state`

For distributed requests, an additional layer is required:

`client request`

`-> idempotency identity`

`-> transaction`

`-> committed result`

`-> retry returns the same logical result`

This separation prevents several common conceptual mistakes. Atomicity does not automatically provide idempotency. Consistency does not define business rules automatically. Isolation does not guarantee that an application-level read-modify-write operation is safe without considering concurrency. Durability does not mean that an external API call can be rolled back.

The four properties describe complementary guarantees around a transaction, while the surrounding application architecture determines how those guarantees are used to implement a correct business operation.
