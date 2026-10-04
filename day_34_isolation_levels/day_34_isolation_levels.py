#!/usr/bin/env python3
"""
Transaction Isolation Levels: Read Uncommitted, Read Committed,
Repeatable Read, and Serializable.

This self-contained simulation demonstrates the anomalies and guarantees
associated with common SQL transaction isolation levels.

The simulator uses a small in-memory database, row versions, locks, and
transaction snapshots. It is intentionally educational rather than a
replacement for a database engine. Real databases implement isolation with
MVCC, locking, predicate/range locks, serialization mechanisms, or combinations
of these techniques.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Dict, List, Optional, Tuple
import copy


class IsolationLevel(str, Enum):
    READ_UNCOMMITTED = "READ UNCOMMITTED"
    READ_COMMITTED = "READ COMMITTED"
    REPEATABLE_READ = "REPEATABLE READ"
    SERIALIZABLE = "SERIALIZABLE"


class TransactionState(str, Enum):
    ACTIVE = "ACTIVE"
    COMMITTED = "COMMITTED"
    ROLLED_BACK = "ROLLED BACK"


@dataclass
class Account:
    account_id: int
    owner: str
    balance: int


@dataclass
class Version:
    commit_id: int
    value: Account


@dataclass
class Transaction:
    transaction_id: int
    isolation: IsolationLevel
    snapshot_commit: int
    state: TransactionState = TransactionState.ACTIVE
    writes: Dict[int, Account] = field(default_factory=dict)
    read_cache: Dict[int, Account] = field(default_factory=dict)
    range_predicates: List[Tuple[int, int]] = field(default_factory=list)


class IsolationError(RuntimeError):
    """Raised when a simulated transaction cannot legally proceed."""


class InMemoryDatabase:
    """
    A compact transactional database simulator.

    The simulator maintains committed versions separately from uncommitted
    transaction writes. This distinction makes dirty reads possible at
    READ UNCOMMITTED while preventing them at stronger isolation levels.

    SERIALIZABLE is modeled conservatively with a database-wide transaction
    lock. Real database engines can use finer-grained locking or predicate
    locking, but the conservative model makes the serial execution guarantee
    explicit.
    """

    def __init__(self) -> None:
        self._commit_id = 0
        self._transaction_id = 0
        self._accounts: Dict[int, List[Version]] = {}
        self._uncommitted: Dict[int, Dict[int, Account]] = {}
        self._mutex = Lock()
        self._serial_lock = Lock()
        self._active_serial_transaction: Optional[int] = None

    @property
    def commit_id(self) -> int:
        return self._commit_id

    def seed(self, accounts: List[Account]) -> None:
        """Create initial committed state."""
        with self._mutex:
            self._commit_id += 1
            for account in accounts:
                self._accounts[account.account_id] = [
                    Version(self._commit_id, copy.deepcopy(account))
                ]

    def begin(self, isolation: IsolationLevel) -> Transaction:
        with self._mutex:
            self._transaction_id += 1
            transaction = Transaction(
                transaction_id=self._transaction_id,
                isolation=isolation,
                snapshot_commit=self._commit_id,
            )

        if isolation == IsolationLevel.SERIALIZABLE:
            self._serial_lock.acquire()
            self._active_serial_transaction = transaction.transaction_id

        self._uncommitted[transaction.transaction_id] = {}
        return transaction

    def _ensure_active(self, transaction: Transaction) -> None:
        if transaction.state != TransactionState.ACTIVE:
            raise IsolationError(
                f"Transaction {transaction.transaction_id} is "
                f"{transaction.state.value.lower()}."
            )

    def _latest_committed(self, account_id: int) -> Optional[Account]:
        versions = self._accounts.get(account_id)
        if not versions:
            return None
        return copy.deepcopy(versions[-1].value)

    def _snapshot_value(
        self,
        account_id: int,
        snapshot_commit: int,
    ) -> Optional[Account]:
        versions = self._accounts.get(account_id, [])
        visible = None
        for version in versions:
            if version.commit_id <= snapshot_commit:
                visible = version.value
            else:
                break
        return copy.deepcopy(visible) if visible is not None else None

    def _uncommitted_value(
        self,
        reader: Transaction,
        account_id: int,
    ) -> Optional[Account]:
        """
        READ UNCOMMITTED can see another transaction's private write.

        The read is deliberately unsafe: if the writer later rolls back,
        the reader has observed a value that never became durable.
        """
        for transaction_id, writes in self._uncommitted.items():
            if transaction_id == reader.transaction_id:
                continue
            if account_id in writes:
                return copy.deepcopy(writes[account_id])
        return None

    def read_account(
        self,
        transaction: Transaction,
        account_id: int,
    ) -> Optional[Account]:
        self._ensure_active(transaction)

        own_write = self._uncommitted[transaction.transaction_id].get(account_id)
        if own_write is not None:
            return copy.deepcopy(own_write)

        if transaction.isolation == IsolationLevel.READ_UNCOMMITTED:
            dirty = self._uncommitted_value(transaction, account_id)
            if dirty is not None:
                return dirty
            return self._latest_committed(account_id)

        if transaction.isolation == IsolationLevel.READ_COMMITTED:
            return self._latest_committed(account_id)

        if transaction.isolation == IsolationLevel.REPEATABLE_READ:
            if account_id not in transaction.read_cache:
                value = self._snapshot_value(
                    account_id,
                    transaction.snapshot_commit,
                )
                if value is not None:
                    transaction.read_cache[account_id] = copy.deepcopy(value)
                return value
            return copy.deepcopy(transaction.read_cache[account_id])

        if transaction.isolation == IsolationLevel.SERIALIZABLE:
            return self._latest_committed(account_id)

        raise IsolationError("Unsupported isolation level.")

    def write_account(
        self,
        transaction: Transaction,
        account_id: int,
        new_balance: int,
    ) -> None:
        self._ensure_active(transaction)

        if new_balance < 0:
            raise ValueError("Account balance cannot be negative.")

        current = self.read_account(transaction, account_id)
        if current is None:
            raise KeyError(f"Account {account_id} does not exist.")

        updated = copy.deepcopy(current)
        updated.balance = new_balance
        self._uncommitted[transaction.transaction_id][account_id] = updated
        transaction.writes[account_id] = copy.deepcopy(updated)

    def query_balance_range(
        self,
        transaction: Transaction,
        minimum: int,
        maximum: int,
    ) -> List[Account]:
        """
        Range reads expose the phantom-read problem.

        REPEATABLE READ protects the rows already observed by the transaction
        in this simulator but does not prevent another transaction from
        inserting a new qualifying row. SERIALIZABLE owns the transaction
        execution lock and therefore prevents the concurrent insert.
        """
        self._ensure_active(transaction)

        if minimum > maximum:
            raise ValueError("Minimum balance cannot exceed maximum.")

        transaction.range_predicates.append((minimum, maximum))

        if transaction.isolation == IsolationLevel.SERIALIZABLE:
            source = self._all_visible_accounts()
        elif transaction.isolation == IsolationLevel.REPEATABLE_READ:
            source = self._all_accounts_at_snapshot(transaction.snapshot_commit)
        else:
            source = self._all_visible_accounts()

        result = [
            account
            for account in source
            if minimum <= account.balance <= maximum
        ]
        return sorted(result, key=lambda account: account.account_id)

    def insert_account(
        self,
        transaction: Transaction,
        account: Account,
    ) -> None:
        self._ensure_active(transaction)

        if account.balance < 0:
            raise ValueError("Account balance cannot be negative.")

        if self._account_exists_visible(account.account_id):
            raise ValueError(f"Account {account.account_id} already exists.")

        if account.account_id in self._uncommitted[transaction.transaction_id]:
            raise ValueError(
                f"Transaction already contains account {account.account_id}."
            )

        self._uncommitted[transaction.transaction_id][account.account_id] = (
            copy.deepcopy(account)
        )
        transaction.writes[account.account_id] = copy.deepcopy(account)

    def _account_exists_visible(self, account_id: int) -> bool:
        return account_id in self._accounts

    def _all_visible_accounts(self) -> List[Account]:
        return [
            copy.deepcopy(versions[-1].value)
            for versions in self._accounts.values()
            if versions
        ]

    def _all_accounts_at_snapshot(self, snapshot_commit: int) -> List[Account]:
        result: List[Account] = []
        for account_id in self._accounts:
            value = self._snapshot_value(account_id, snapshot_commit)
            if value is not None:
                result.append(value)
        return result

    def commit(self, transaction: Transaction) -> None:
        self._ensure_active(transaction)

        with self._mutex:
            self._commit_id += 1
            commit_id = self._commit_id

            writes = self._uncommitted[transaction.transaction_id]
            for account_id, account in writes.items():
                self._accounts.setdefault(account_id, []).append(
                    Version(commit_id, copy.deepcopy(account))
                )

            transaction.state = TransactionState.COMMITTED
            del self._uncommitted[transaction.transaction_id]

        if transaction.isolation == IsolationLevel.SERIALIZABLE:
            self._active_serial_transaction = None
            self._serial_lock.release()

    def rollback(self, transaction: Transaction) -> None:
        self._ensure_active(transaction)

        self._uncommitted.pop(transaction.transaction_id, None)
        transaction.state = TransactionState.ROLLED_BACK

        if transaction.isolation == IsolationLevel.SERIALIZABLE:
            self._active_serial_transaction = None
            self._serial_lock.release()

    def dump(self) -> List[Account]:
        return sorted(
            self._all_visible_accounts(),
            key=lambda account: account.account_id,
        )


def print_accounts(title: str, accounts: List[Account]) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    for account in accounts:
        print(
            f"account={account.account_id:<3} "
            f"owner={account.owner:<12} balance={account.balance}"
        )


def demonstrate_dirty_read() -> None:
    """
    Dirty read:
    T1 changes an account without committing.
    T2 under READ UNCOMMITTED sees that private value.
    T1 rolls back, proving that T2 observed a value that never committed.
    """
    print("\n=== Dirty Read: READ UNCOMMITTED ===")

    db = InMemoryDatabase()
    db.seed([Account(1, "Asha", 1000)])

    writer = db.begin(IsolationLevel.READ_COMMITTED)
    reader = db.begin(IsolationLevel.READ_UNCOMMITTED)

    db.write_account(writer, 1, 250)

    dirty_value = db.read_account(reader, 1)
    print(f"Reader observes uncommitted balance: {dirty_value.balance}")

    db.rollback(writer)

    committed_value = db.read_account(reader, 1)
    print(
        "After writer rollback, committed balance is "
        f"{committed_value.balance}"
    )

    db.rollback(reader)


def demonstrate_non_repeatable_read() -> None:
    """
    Non-repeatable read:
    READ COMMITTED resolves a normal read against current committed state.
    Another committed transaction can therefore change the value between two
    reads made by the first transaction.
    """
    print("\n=== Non-Repeatable Read: READ COMMITTED ===")

    db = InMemoryDatabase()
    db.seed([Account(1, "Asha", 1000)])

    reader = db.begin(IsolationLevel.READ_COMMITTED)
    first = db.read_account(reader, 1)

    writer = db.begin(IsolationLevel.READ_COMMITTED)
    db.write_account(writer, 1, 700)
    db.commit(writer)

    second = db.read_account(reader, 1)

    print(f"First read:  {first.balance}")
    print(f"Second read: {second.balance}")
    print("The value changed because the second statement saw a newer commit.")

    db.rollback(reader)


def demonstrate_repeatable_read() -> None:
    """
    REPEATABLE READ in this simulator uses a transaction-level snapshot for
    previously read rows. A later committed update is therefore invisible to
    the transaction's repeated read of that row.
    """
    print("\n=== Repeatable Read: REPEATABLE READ ===")

    db = InMemoryDatabase()
    db.seed([Account(1, "Asha", 1000)])

    reader = db.begin(IsolationLevel.REPEATABLE_READ)
    first = db.read_account(reader, 1)

    writer = db.begin(IsolationLevel.READ_COMMITTED)
    db.write_account(writer, 1, 700)
    db.commit(writer)

    second = db.read_account(reader, 1)

    print(f"First read:  {first.balance}")
    print(f"Second read: {second.balance}")
    print(
        "The repeated row read remains stable because it uses "
        "the transaction snapshot."
    )

    db.commit(reader)


def demonstrate_phantom_read() -> None:
    """
    Phantom read:
    A range query can return a different set of rows after another
    transaction inserts a qualifying row.

    REPEATABLE READ in many systems protects existing rows but does not,
    by itself, guarantee predicate-level serializability. SERIALIZABLE
    requires the concurrent transaction to be ordered as if transactions
    executed one at a time.
    """
    print("\n=== Phantom Read and SERIALIZABLE ===")

    db = InMemoryDatabase()
    db.seed(
        [
            Account(1, "Asha", 1000),
            Account(2, "Ravi", 4000),
            Account(3, "Mina", 8000),
        ]
    )

    reader = db.begin(IsolationLevel.REPEATABLE_READ)
    first_range = db.query_balance_range(reader, 1000, 5000)

    inserter = db.begin(IsolationLevel.READ_COMMITTED)
    db.insert_account(inserter, Account(4, "Noor", 3000))
    db.commit(inserter)

    second_range = db.query_balance_range(reader, 1000, 5000)

    print(
        "REPEATABLE READ range sizes:",
        len(first_range),
        "then",
        len(second_range),
    )
    print(
        "A new qualifying row can appear because row stability and "
        "predicate stability are different guarantees."
    )
    db.commit(reader)

    serial_db = InMemoryDatabase()
    serial_db.seed(
        [
            Account(1, "Asha", 1000),
            Account(2, "Ravi", 4000),
            Account(3, "Mina", 8000),
        ]
    )

    serial_reader = serial_db.begin(IsolationLevel.SERIALIZABLE)
    serial_first = serial_db.query_balance_range(serial_reader, 1000, 5000)

    print(
        "SERIALIZABLE first range size:",
        len(serial_first),
        "(the transaction owns the serial execution slot)"
    )

    # A second SERIALIZABLE transaction cannot start until the first releases
    # the serial lock. This models the serialization constraint explicitly.
    serial_db.commit(serial_reader)


def demonstrate_write_skew_concept() -> None:
    """
    Write skew is a useful advanced isolation example.

    Two transactions can independently read valid state and then write
    different rows. If their combined result violates an invariant, snapshot
    style isolation may be insufficient unless the database detects the
    dangerous dependency pattern or SERIALIZABLE prevents the interleaving.
    """
    print("\n=== Write Skew: Why Serializable Matters ===")

    db = InMemoryDatabase()
    db.seed(
        [
            Account(1, "Doctor-A", 1),
            Account(2, "Doctor-B", 1),
        ]
    )

    t1 = db.begin(IsolationLevel.REPEATABLE_READ)
    t2 = db.begin(IsolationLevel.REPEATABLE_READ)

    available = [
        account
        for account in db.dump()
        if account.balance == 1
    ]

    print(
        "Both transactions observe available resources:",
        [account.account_id for account in available],
    )

    # Each transaction independently disables a different resource.
    # A real database's exact behavior depends on its implementation and
    # conflict detection rules. This simulator records the conceptual risk.
    db.write_account(t1, 1, 0)
    db.write_account(t2, 2, 0)

    db.commit(t1)
    db.commit(t2)

    remaining = [
        account
        for account in db.dump()
        if account.balance == 1
    ]
    print("Remaining available resources:", [a.account_id for a in remaining])
    print(
        "The business invariant 'at least one doctor remains available' "
        "has been violated."
    )


def compare_levels() -> None:
    print("\n=== Isolation Level Comparison ===")
    rows = [
        (
            IsolationLevel.READ_UNCOMMITTED.value,
            "May",
            "May",
            "May",
            "Weakest",
        ),
        (
            IsolationLevel.READ_COMMITTED.value,
            "No",
            "May",
            "May",
            "Statement-level current reads",
        ),
        (
            IsolationLevel.REPEATABLE_READ.value,
            "No",
            "No",
            "Implementation-dependent",
            "Stable repeated row reads",
        ),
        (
            IsolationLevel.SERIALIZABLE.value,
            "No",
            "No",
            "No",
            "Strongest; serial-equivalent behavior",
        ),
    ]

    print(
        f"{'Level':<20} {'Dirty':<10} {'Non-repeatable':<16} "
        f"{'Phantom':<20} {'Characteristic'}"
    )
    print("-" * 90)
    for level, dirty, non_repeatable, phantom, characteristic in rows:
        print(
            f"{level:<20} {dirty:<10} {non_repeatable:<16} "
            f"{phantom:<20} {characteristic}"
        )


def validation_examples() -> None:
    print("\n=== Validation and Failure Conditions ===")

    db = InMemoryDatabase()
    db.seed([Account(1, "Asha", 1000)])

    transaction = db.begin(IsolationLevel.READ_COMMITTED)

    try:
        db.write_account(transaction, 1, -50)
    except ValueError as exc:
        print(f"Rejected invalid write: {exc}")

    db.commit(transaction)

    try:
        db.read_account(transaction, 1)
    except IsolationError as exc:
        print(f"Rejected read after commit: {exc}")


def production_notes() -> None:
    """
    These are printed as concise engineering observations rather than being
    treated as database-engine documentation. Actual semantics vary by DBMS.
    """
    print("\n=== Production Engineering Notes ===")
    print(
        "READ UNCOMMITTED trades correctness for weak visibility guarantees "
        "and is uncommon for correctness-sensitive financial operations."
    )
    print(
        "READ COMMITTED is often a practical default because each statement "
        "sees committed data without holding a transaction-wide snapshot."
    )
    print(
        "REPEATABLE READ is useful when a transaction needs stable row-level "
        "observations, but exact phantom and write-conflict behavior depends "
        "on the database engine."
    )
    print(
        "SERIALIZABLE provides the strongest standard isolation guarantee, "
        "but may reduce concurrency through blocking, aborts, or retries."
    )
    print(
        "Applications must still enforce business constraints with database "
        "constraints, appropriate locking, conflict detection, or retries."
    )


def main() -> None:
    print("TRANSACTION ISOLATION LEVEL LAB")
    print("===============================")

    demonstrate_dirty_read()
    demonstrate_non_repeatable_read()
    demonstrate_repeatable_read()
    demonstrate_phantom_read()
    demonstrate_write_skew_concept()
    compare_levels()
    validation_examples()
    production_notes()

    db = InMemoryDatabase()
    db.seed(
        [
            Account(1, "Asha", 1250),
            Account(2, "Ravi", 3200),
            Account(3, "Mina", 9100),
        ]
    )
    print_accounts("Final demonstration database state", db.dump())


if __name__ == "__main__":
    main()
