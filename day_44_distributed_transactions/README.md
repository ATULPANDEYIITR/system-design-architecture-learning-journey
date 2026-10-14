# Distributed Transactions: Two-Phase Commit and Distributed Coordination

## Technical scope

A distributed transaction coordinates a single logical operation across multiple independent participants. Each participant owns local state and can independently validate, reserve, and apply changes. The coordinator determines whether the operation is committed or aborted globally.

The central difficulty is that a network request, a local database transaction, and a global business operation have different failure boundaries. A participant may successfully prepare a change while the coordinator is unavailable. A coordinator may record a commit decision and fail before every participant receives it. A timeout can indicate a lost response rather than a failed operation.

This project models those conditions through five complementary implementations:

- **Python** implements a transaction coordinator, participant reservations, a journal abstraction, recovery, and executable failure scenarios.
- **JavaScript** models asynchronous participant messaging, request deadlines, retry behavior, and incomplete decision delivery.
- **C++** presents a repository-style governance engine adapted to financial settlement, with explicit states, a decision journal, validation, and recovery.
- **Java** implements an enterprise settlement service using domain types, collections, validation, exception handling, and explicit transaction state transitions.
- **PostgreSQL** models coordinators, participants, ledger entries, decisions, events, and a transactional outbox using relational constraints and queries.

The implementations share protocol principles but are independent educational simulations. Their in-memory journals are not equivalent to a replicated production log, and their local state changes do not provide genuine atomicity across independent databases.

## Transaction boundaries and failure models

A local ACID transaction provides atomicity, consistency, isolation, and durability within a single transactional resource. A distributed transaction must coordinate multiple such resources without assuming that a successful local commit means every other participant has committed.

Consider a marketplace payment of 125 monetary units. The customer ledger must decrease by 125, the merchant ledger must increase by 120, and the platform fee account must increase by 5.

The desired invariant is:

\[
\Delta B_{\text{customer}}+
\Delta B_{\text{merchant}}+
\Delta B_{\text{platform}}=0
\]

A partial application would violate the business operation even if every individual account update were valid.

The coordinator must distinguish several situations:

| Situation | What it means | Correct protocol response |
|---|---|---|
| Participant votes NO | The participant cannot safely perform the requested operation | Record a global abort decision |
| Participant does not respond | The coordinator cannot determine the participant's current status from the timeout alone | Apply a defined failure policy and recover from the recorded decision |
| Participant prepares successfully | The participant has promised it can commit if instructed | Retain its reservation and recovery information |
| Coordinator records COMMIT | The global outcome is commit, even if delivery is incomplete | Retry commit delivery until participants reconcile |
| Coordinator has no durable decision | The global outcome may be unknown | Recover from authoritative logs or use the protocol's prescribed termination procedure |
| Commit message is duplicated | A transport retry repeats an earlier request | Return the existing result without applying the change twice |

A timeout is a failure detector signal, not proof that a remote operation never happened.

## Two-phase commit

Two-phase commit, or 2PC, separates transaction processing into a prepare phase and a decision phase. Its purpose is to coordinate a common outcome, not to make the network reliable.

### Prepare phase

The coordinator identifies the participants and sends each one a prepare request. Each participant validates the requested operation and establishes the local conditions needed to commit.

For a database participant, preparation generally involves:

- Validating constraints and business rules.
- Acquiring or retaining the necessary locks or reservations.
- Recording enough recovery information to finish after a process restart.
- Persisting its prepared state before sending a YES vote.

A YES vote is a promise to follow the global decision, not a statement that the local change has already become committed and visible.

A NO vote prevents the coordinator from deciding to commit. The coordinator may also fail to obtain every vote because a participant is unreachable. In either case, it must not infer unanimous approval.

### Decision phase

When every required participant votes YES, the coordinator records a global COMMIT decision. Only after the decision is durable should it send commit commands.

If any participant votes NO, or the protocol cannot proceed with the required votes, the coordinator records ABORT and instructs participants to release their prepared resources.

The essential ordering is:

`BEGIN → PREPARING → PREPARED votes → durable global decision → participant completion`

A production implementation must preserve this ordering across crashes, not merely within an in-memory function.

### Coordinator and participant state

The implementations use distinct state types because participant state and global transaction state describe different things.

| Coordinator state | Meaning |
|---|---|
| `NEW` | The operation has been registered but preparation has not started |
| `PREPARING` | Votes are being collected |
| `COMMIT_DECIDED` | The durable global decision is commit |
| `ABORT_DECIDED` | The durable global decision is abort |
| `COMMITTED` | Required participant work has completed successfully |
| `ABORTED` | Abort processing has completed |
| `IN_DOUBT` | Decision delivery or recovery is incomplete, or no authoritative decision is available |

| Participant state | Meaning |
|---|---|
| `ACTIVE` | No prepared operation is held for the transaction |
| `PREPARED` | The participant retains the operation and can honor the coordinator's decision |
| `COMMITTED` | The local change has been applied |
| `ABORTED` | The participant has abandoned the prepared change |

`IN_DOUBT` does not mean that a transaction should be guessed into a committed or aborted state. It means the available evidence is insufficient to claim full completion.

## Distributed coordination and recovery

Coordination requires more than sending requests in the correct order. The system must establish an authoritative decision, associate requests with stable transaction identities, and reconcile participants after interruptions.

### Durable decision records

The coordinator journal records events such as `BEGIN`, `PREPARING`, `GLOBAL_COMMIT`, `GLOBAL_ABORT`, and `TRANSACTION_COMPLETE`.

The most important record is the global decision. If the coordinator crashes after recording COMMIT but before delivering the command to a participant, recovery must resend COMMIT. Choosing ABORT during recovery would contradict the authoritative decision.

Likewise, if the global decision is ABORT and one participant was unavailable during abort delivery, the coordinator must retry the abort when the participant becomes reachable.

The sample journals are educational. They do not provide replicated storage, consensus, atomic log writes, corruption recovery, or power-loss durability. A real service must establish these properties explicitly.

### Idempotent command handling

Networks commonly deliver retries after a timeout. The sender cannot always determine whether the first request was processed.

An idempotent participant handler makes a repeated command safe:

- A repeated COMMIT after successful commit does not apply the ledger delta again.
- A repeated ABORT after successful abort does not release resources twice in a harmful way.
- A retry for an existing transaction must not silently substitute a different operation.

Transaction IDs identify distributed operations. Idempotency keys identify logical requests and allow repeated submissions to be recognized. A production system should persist both identities and associate them with the expected payload or payload hash.

Idempotency does not eliminate the need for transaction isolation. Two different transactions may still attempt to modify the same account concurrently.

### Recovery procedure

A recovery worker should identify incomplete transactions, read the authoritative coordinator decision, contact participants, retry safe operations, and update the completion state only after reconciliation.

Recovery should also record each attempt, the participant involved, the decision being delivered, the observed failure, and the eventual outcome. Backoff, retry limits, alert thresholds, and operator escalation should be based on service requirements.

A participant that remains prepared while the coordinator is unreachable may need to retain locks and reservations. This is a major availability cost of traditional 2PC.

## Python implementation

The Python program uses `Participant`, `Coordinator`, `TransactionRecord`, `Vote`, and `DurableJournal` to separate protocol responsibilities.

`Participant.prepare()` checks the projected balance, creates a reservation, and records `PREPARED`. The balance itself remains unchanged until `commit()` applies the reserved delta. `abort()` releases a reservation without applying it.

`Coordinator._execute()` collects votes and persists the global decision before issuing participant commands. A negative vote causes an abort. An unavailable participant can leave decision delivery incomplete, which the coordinator represents as `IN_DOUBT`.

`Coordinator.recover()` reads the recorded global decision and retries the corresponding participant action. The executable scenarios cover successful transfers, insufficient funds, participant outages, repeated commit commands, and event inspection.

The optional journal path supports append-only JSON Lines records. The implementation flushes the file but does not call `fsync`, and it does not reconstruct complete transaction records after a process restart. Its recovery demonstration operates on the current in-memory transaction registry.

Run with `python distributed_transactions.py`. The standard library is sufficient.

## JavaScript implementation

The JavaScript program focuses on asynchronous communication boundaries. Its `EventJournal`, `Participant`, and `Coordinator` classes model votes, prepared reservations, decisions, and retries.

`sendWithDeadline()` places a deadline around a participant operation. `callParticipant()` retries failures identified as participant unavailability. The implementation illustrates an important limitation: `Promise.race()` does not cancel the losing operation. A remote request may still complete after the caller has timed out.

Consequently, deadlines must not be treated as proof that the participant did nothing. Production transports need cancellation where supported, idempotent handlers, bounded retries, and fencing against obsolete coordinator instances.

The participant uses `Map` collections for transaction state, reservations, and operation identifiers. `structuredClone()` isolates journal details from subsequent object mutation. Integer amounts use JavaScript safe integers; actual monetary systems should select a representation with explicit currency precision and overflow behavior.

The recovery scenario makes a participant unavailable, observes incomplete decision delivery, restores connectivity, and reapplies the authoritative abort decision. Run with Node.js 18 or later using `node distributed-transactions.js`.

## C++ case study

The C++ program models a marketplace settlement engine. The transaction debits a buyer account, credits a seller account, and credits a platform fee account.

`GovernanceEngine` owns the coordinator's transaction registry and journal. `Participant` owns the local balance and prepared reservation. `Transaction` tracks votes and the global decision, while `Journal` exposes the recorded outcome for recovery.

The program uses `std::map` to associate participants and transaction IDs with their state. `std::optional<Decision>` distinguishes a recorded decision from the absence of a decision. Checked integer arithmetic prevents signed overflow when evaluating account changes.

The settlement case validates conservation of the total balance. The insufficient-funds case verifies that the source account remains unchanged after abort. The recovery case simulates an unavailable participant and retries delivery of the recorded decision.

The example is intentionally single-threaded and in-memory. It does not implement network transport, concurrent account locking, durable logs, or consensus. The state machine and checked arithmetic are useful foundations for understanding the protocol, but they are not substitutes for production database guarantees.

Compile with a C++17 compiler, for example `g++ -std=c++17 -Wall -Wextra -pedantic distributed_transactions.cpp -o distributed_transactions`.

## Java enterprise model

The Java implementation separates domain state from orchestration. `ParticipantState`, `TransactionState`, and `Decision` are enums, which restrict protocol values to defined alternatives. `Vote`, `JournalEvent`, and transaction metadata are represented with records and dedicated domain classes.

`TransactionService` validates participant registration, initiates the prepare phase, records the decision, delivers participant commands, and coordinates recovery. `Participant` owns the balance, operation ID, reservation, and state transition rules.

`Math.addExact()` exposes numeric overflow instead of silently wrapping a monetary value. Synchronization around participant state protects local state transitions in this example, but does not provide distributed locking or a globally consistent view of the transaction.

The immutable participant list prevents accidental modification of the participants selected for a transaction. The unmodifiable vote view protects transaction metadata from external mutation.

Run with Java 17 or later using `javac DistributedTransactions.java` followed by `java DistributedTransactions`.

## PostgreSQL relational model

The SQL script separates transaction coordination data from account state and event history.

### Core relations

| Table | Responsibility |
|---|---|
| `repositories` | Defines the coordination domain |
| `participants` | Records participating services and availability |
| `accounts` | Holds account balances and local versions |
| `distributed_transactions` | Stores transaction identity, state, and global decision |
| `transaction_participants` | Tracks participant votes and local completion states |
| `transaction_entries` | Records the intended account deltas |
| `transaction_events` | Maintains an ordered operational history |
| `transaction_outbox` | Stores decision messages that require delivery or retry |

Foreign keys preserve referential integrity. Unique constraints prevent duplicate participant registration, duplicate transaction-account entries, and duplicate outbox messages for the same transaction and participant. Check constraints reject negative account balances, invalid counters, and inconsistent decision timestamps.

Indexes support coordinator state scans, participant recovery queries, event-history retrieval, and pending outbox processing.

### Decision and outbox transaction

The script records the global decision and inserts corresponding outbox rows in a local SQL transaction. This establishes a durable relationship between the recorded decision and the messages that must be delivered.

A dispatcher can claim pending outbox entries, send the decision to the participant, and record delivery status. Failed delivery remains visible for retry.

An outbox is not itself a distributed commit protocol. It prevents the coordinator from losing the relationship between its local decision and pending delivery work. Remote handlers must still be idempotent, and the coordinator must reconcile remote outcomes.

The demonstration applies account changes in a local PostgreSQL transaction, updates participant states, and marks entries as applied. In a real multi-database system, those statements would execute within each participant's own transaction rather than one shared database transaction.

### SQL dialect and execution

The script uses PostgreSQL enums, `JSONB`, filtered aggregates, common table expressions, partial indexes, identity columns, and `TIMESTAMPTZ`. It uses `gen_random_uuid()` for transaction identifiers.

Run the script in a dedicated PostgreSQL learning database. It drops and recreates the `distributed_tx_demo` schema, so existing data in that schema will be removed.

The schema illustrates coordinator records and simulated participant behavior. It does not invoke PostgreSQL's native prepared-transaction commands. Native two-phase transaction support requires a separately managed protocol and operational configuration.

## Two-phase commit versus alternatives

Two-phase commit is appropriate when all required participants can participate in a coordinated atomic outcome and the application accepts the associated availability and resource-retention costs.

Its principal limitation is blocking. If a participant has voted YES and the coordinator becomes unreachable before the decision is known, the participant cannot safely infer whether to commit or abort. It may need to retain prepared resources while awaiting recovery.

Other coordination strategies solve different problems:

- **Saga orchestration** decomposes a long-running business operation into local transactions and compensating actions. Compensation is a new business operation, not a rollback of an already committed database transaction.
- **Transactional outbox** reliably associates local state changes with messages to be delivered. It supports asynchronous coordination but does not independently guarantee global atomicity.
- **Consensus protocols** such as Raft coordinate replicated state among nodes. Consensus can support a durable coordinator, but consensus alone does not make arbitrary transactions across independent databases atomic.
- **Eventual consistency** allows participants to converge through asynchronous updates. It can improve availability where temporary disagreement is acceptable.
- **Three-phase commit** introduces an additional phase intended to reduce blocking under particular timing and failure assumptions. It does not remove the need to state assumptions about network partitions and failure detection.

These mechanisms are not interchangeable. A system may use consensus to maintain coordinator state, an outbox to deliver messages, and 2PC to coordinate database participants.

## Failure modes and production considerations

### Coordinator crash

The coordinator must reconstruct its state from durable records. If it has recorded COMMIT, recovery resends COMMIT. If it has recorded ABORT, recovery resends ABORT. A missing decision requires the prescribed protocol recovery procedure rather than an arbitrary guess.

### Participant crash after YES

A participant must recover the prepared transaction and preserve the ability to follow the global decision. If it loses its reservation or forgets the prepared state, the coordinator may no longer be able to complete the operation safely.

### Lost response after successful commit

The coordinator may retry COMMIT because it did not receive the original acknowledgement. The participant must detect that the operation has already committed and return the existing outcome.

### Conflicting coordinator instances

An old coordinator process must not issue a stale decision after leadership changes. Production designs can use epochs, fencing tokens, leases with appropriate assumptions, and a consensus-backed decision log. Merely storing a coordinator name is insufficient.

### Concurrent operations

The examples do not serialize transactions that modify the same account. Production participants require database locking, optimistic concurrency checks, serializable isolation where appropriate, or equivalent mechanisms. Idempotency prevents duplicate application of one operation; it does not prevent conflicting operations from racing.

### Observability

Operational monitoring should track the age of prepared transactions, time from begin to decision, time from decision to completion, vote failures, participant unavailability, retry counts, and pending outbox depth.

An old prepared transaction can indicate a coordinator outage, a partition, a blocked participant, or an incomplete recovery process. It should be investigated using transaction IDs and authoritative journal records rather than resolved by guessing.

### Security

Transaction identifiers and operation IDs are correlation data, not authorization credentials. Participant endpoints must authenticate the coordinator, validate that commands target the correct transaction, and reject unauthorized decisions. Logs should avoid storing credentials or sensitive payloads.

### Atomicity boundaries

The examples demonstrate the decision protocol, but their in-memory reservations are not database locks and their journals are not fully durable transaction logs. The PostgreSQL example offers local transactional enforcement, not cross-database atomicity. A production design must specify precisely which resources participate in the protocol and what durability, isolation, recovery, and availability guarantees each participant provides.
