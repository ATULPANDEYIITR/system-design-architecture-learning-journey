#!/usr/bin/env python3
"""
Transactions: ACID Properties and Transactional Guarantees

A self-contained executable study of database transaction behavior using
Python's standard library. The implementation uses SQLite so that the
examples demonstrate real transaction semantics rather than pseudocode.

Covered mechanisms:
- Atomicity
- Consistency
- Isolation
- Durability
- COMMIT and ROLLBACK
- Savepoints
- Constraint failures
- Concurrent access and isolation observations
- Lost-update prevention with conditional updates
- Idempotent transaction design
- Transaction retries
- Transaction boundaries
- Durable audit records
- Failure injection
- Verification after commit
- Production-oriented transaction design
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Callable, Iterable


CENT = Decimal("0.01")


def money(value: Decimal | str | float | int) -> Decimal:
    """Normalize monetary values to exactly two decimal places."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def connect(database: str, timeout: float = 5.0) -> sqlite3.Connection:
    """
    Create a SQLite connection with foreign-key enforcement enabled.

    Foreign keys are connection-local in SQLite, so every connection must
    explicitly enable them.
    """
    connection = sqlite3.connect(
        database,
        timeout=timeout,
        isolation_level=None,
        check_same_thread=False,
    )
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def begin(connection: sqlite3.Connection) -> None:
    """Start an explicit transaction."""
    connection.execute("BEGIN")


def commit(connection: sqlite3.Connection) -> None:
    """Make all changes in the current transaction durable."""
    connection.execute("COMMIT")


def rollback(connection: sqlite3.Connection) -> None:
    """Discard all changes made since the transaction began."""
    connection.execute("ROLLBACK")


def create_schema(connection: sqlite3.Connection) -> None:
    """
    Create a small banking ledger.

    The database itself enforces important consistency rules:
    - balances cannot be negative
    - account currency is restricted
    - ledger entries reference real accounts
    - transfer identifiers are unique
    """
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            currency TEXT NOT NULL CHECK (currency IN ('INR', 'USD')),
            balance_cents INTEGER NOT NULL CHECK (balance_cents >= 0)
        );

        CREATE TABLE IF NOT EXISTS transfers (
            transfer_id TEXT PRIMARY KEY,
            source_account TEXT NOT NULL,
            destination_account TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_account) REFERENCES accounts(account_id),
            FOREIGN KEY (destination_account) REFERENCES accounts(account_id),
            CHECK (source_account <> destination_account)
        );

        CREATE TABLE IF NOT EXISTS ledger (
            entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transfer_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('DEBIT', 'CREDIT')),
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transfer_id) REFERENCES transfers(transfer_id),
            FOREIGN KEY (account_id) REFERENCES accounts(account_id)
        );

        CREATE INDEX IF NOT EXISTS idx_ledger_transfer
            ON ledger(transfer_id);

        CREATE INDEX IF NOT EXISTS idx_ledger_account
            ON ledger(account_id);
        """
    )


def seed_accounts(connection: sqlite3.Connection) -> None:
    """Create reproducible accounts for the demonstrations."""
    begin(connection)
    try:
        connection.execute("DELETE FROM ledger")
        connection.execute("DELETE FROM transfers")
        connection.execute("DELETE FROM accounts")

        connection.executemany(
            """
            INSERT INTO accounts(account_id, owner, currency, balance_cents)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("A100", "Anika", "INR", 100_000),
                ("B200", "Rohan", "INR", 50_000),
                ("C300", "Meera", "INR", 75_000),
            ],
        )
        commit(connection)
    except Exception:
        rollback(connection)
        raise


def get_balance(connection: sqlite3.Connection, account_id: str) -> Decimal:
    row = connection.execute(
        "SELECT balance_cents FROM accounts WHERE account_id = ?",
        (account_id,),
    ).fetchone()

    if row is None:
        raise ValueError(f"Unknown account: {account_id}")

    return money(Decimal(row[0]) / Decimal(100))


def print_accounts(connection: sqlite3.Connection, title: str) -> None:
    print(f"\n--- {title} ---")
    rows = connection.execute(
        """
        SELECT account_id, owner, currency, balance_cents
        FROM accounts
        ORDER BY account_id
        """
    ).fetchall()

    for account_id, owner, currency, balance_cents in rows:
        print(
            f"{account_id}: {owner:8s} "
            f"{money(Decimal(balance_cents) / Decimal(100))} {currency}"
        )


def transfer(
    connection: sqlite3.Connection,
    transfer_id: str,
    source: str,
    destination: str,
    amount: Decimal,
    *,
    inject_failure: bool = False,
) -> None:
    """
    Perform a transfer as one atomic unit.

    The debit, credit, transfer record, and ledger entries either all commit
    or all disappear. The conditional debit prevents an account from going
    below zero.
    """
    amount = money(amount)

    if amount <= 0:
        raise ValueError("Transfer amount must be positive")

    if source == destination:
        raise ValueError("Source and destination must differ")

    amount_cents = int(amount * 100)

    begin(connection)
    try:
        source_row = connection.execute(
            """
            SELECT currency, balance_cents
            FROM accounts
            WHERE account_id = ?
            """,
            (source,),
        ).fetchone()

        destination_row = connection.execute(
            """
            SELECT currency
            FROM accounts
            WHERE account_id = ?
            """,
            (destination,),
        ).fetchone()

        if source_row is None or destination_row is None:
            raise ValueError("Both accounts must exist")

        source_currency, source_balance = source_row
        destination_currency = destination_row[0]

        if source_currency != destination_currency:
            raise ValueError("Cross-currency transfer requires conversion logic")

        cursor = connection.execute(
            """
            UPDATE accounts
            SET balance_cents = balance_cents - ?
            WHERE account_id = ?
              AND balance_cents >= ?
            """,
            (amount_cents, source, amount_cents),
        )

        if cursor.rowcount != 1:
            raise ValueError("Insufficient funds")

        connection.execute(
            """
            UPDATE accounts
            SET balance_cents = balance_cents + ?
            WHERE account_id = ?
            """,
            (amount_cents, destination),
        )

        connection.execute(
            """
            INSERT INTO transfers(
                transfer_id, source_account, destination_account, amount_cents
            )
            VALUES (?, ?, ?, ?)
            """,
            (transfer_id, source, destination, amount_cents),
        )

        connection.execute(
            """
            INSERT INTO ledger(
                transfer_id, account_id, direction, amount_cents
            )
            VALUES (?, ?, 'DEBIT', ?)
            """,
            (transfer_id, source, amount_cents),
        )

        if inject_failure:
            raise RuntimeError(
                "Injected application failure before the transaction committed"
            )

        connection.execute(
            """
            INSERT INTO ledger(
                transfer_id, account_id, direction, amount_cents
            )
            VALUES (?, ?, 'CREDIT', ?)
            """,
            (transfer_id, destination, amount_cents),
        )

        commit(connection)

    except Exception:
        rollback(connection)
        raise


def demonstrate_atomicity(connection: sqlite3.Connection) -> None:
    print("\n=== Atomicity ===")
    seed_accounts(connection)

    before_source = get_balance(connection, "A100")
    before_destination = get_balance(connection, "B200")

    try:
        transfer(
            connection,
            "TX-ATOMIC-FAIL",
            "A100",
            "B200",
            money("100.00"),
            inject_failure=True,
        )
    except RuntimeError as exc:
        print(f"Expected failure: {exc}")

    after_source = get_balance(connection, "A100")
    after_destination = get_balance(connection, "B200")

    assert after_source == before_source
    assert after_destination == before_destination

    print("Rollback restored both account balances.")
    print_accounts(connection, "Atomicity after rollback")


def demonstrate_commit(connection: sqlite3.Connection) -> None:
    print("\n=== COMMIT ===")
    seed_accounts(connection)

    transfer(
        connection,
        "TX-COMMIT-001",
        "A100",
        "B200",
        money("250.00"),
    )

    assert get_balance(connection, "A100") == money("750.00")
    assert get_balance(connection, "B200") == money("750.00")

    transfer_row = connection.execute(
        """
        SELECT source_account, destination_account, amount_cents
        FROM transfers
        WHERE transfer_id = ?
        """,
        ("TX-COMMIT-001",),
    ).fetchone()

    assert transfer_row == ("A100", "B200", 25_000)

    print_accounts(connection, "After successful COMMIT")


def demonstrate_consistency(connection: sqlite3.Connection) -> None:
    print("\n=== Consistency ===")
    seed_accounts(connection)

    total_before = connection.execute(
        "SELECT SUM(balance_cents) FROM accounts"
    ).fetchone()[0]

    transfer(
        connection,
        "TX-CONSISTENCY-001",
        "A100",
        "C300",
        money("125.00"),
    )

    total_after = connection.execute(
        "SELECT SUM(balance_cents) FROM accounts"
    ).fetchone()[0]

    assert total_before == total_after

    negative_accounts = connection.execute(
        """
        SELECT account_id
        FROM accounts
        WHERE balance_cents < 0
        """
    ).fetchall()

    assert not negative_accounts

    print(
        "The transaction preserved the system invariant that total account "
        "balance remains constant."
    )
    print(
        f"Total before: {money(Decimal(total_before) / 100)} INR"
    )
    print(
        f"Total after:  {money(Decimal(total_after) / 100)} INR"
    )


def demonstrate_constraint_rollback(connection: sqlite3.Connection) -> None:
    print("\n=== Constraint Failure and Consistency ===")
    seed_accounts(connection)

    begin(connection)
    try:
        connection.execute(
            """
            UPDATE accounts
            SET balance_cents = -1
            WHERE account_id = 'A100'
            """
        )
        commit(connection)
    except sqlite3.IntegrityError as exc:
        print(f"Database rejected invalid state: {exc}")
        rollback(connection)

    assert get_balance(connection, "A100") == money("1000.00")
    print("The CHECK constraint prevented a negative account balance.")


def demonstrate_savepoints(connection: sqlite3.Connection) -> None:
    print("\n=== Savepoints ===")
    seed_accounts(connection)

    begin(connection)
    try:
        connection.execute(
            """
            UPDATE accounts
            SET balance_cents = balance_cents - 1000
            WHERE account_id = 'A100'
            """
        )

        connection.execute("SAVEPOINT optional_step")

        connection.execute(
            """
            UPDATE accounts
            SET balance_cents = balance_cents - 5000
            WHERE account_id = 'B200'
              AND balance_cents >= 5000
            """
        )

        connection.execute("ROLLBACK TO SAVEPOINT optional_step")
        connection.execute("RELEASE SAVEPOINT optional_step")

        connection.execute(
            """
            UPDATE accounts
            SET balance_cents = balance_cents + 1000
            WHERE account_id = 'C300'
            """
        )

        commit(connection)

    except Exception:
        rollback(connection)
        raise

    assert get_balance(connection, "A100") == money("990.00")
    assert get_balance(connection, "B200") == money("500.00")
    assert get_balance(connection, "C300") == money("760.00")

    print(
        "The optional B200 change was rolled back while the surrounding "
        "transaction committed."
    )


def demonstrate_isolation(connection: sqlite3.Connection) -> None:
    print("\n=== Isolation ===")
    seed_accounts(connection)

    second = connect(connection.execute("PRAGMA database_list").fetchone()[2])

    begin(connection)
    try:
        connection.execute(
            """
            UPDATE accounts
            SET balance_cents = balance_cents + 1000
            WHERE account_id = 'A100'
            """
        )

        # A second SQLite connection cannot normally observe an uncommitted
        # change from the first transaction. This demonstrates why a database
        # must control visibility between concurrent transactions.
        visible_to_second = get_balance(second, "A100")

        assert visible_to_second == money("1000.00")

        commit(connection)
    finally:
        second.close()

    assert get_balance(connection, "A100") == money("1010.00")
    print(
        "The second connection observed the committed state, not the "
        "uncommitted write."
    )


def demonstrate_idempotency(connection: sqlite3.Connection) -> None:
    print("\n=== Idempotent Transaction Design ===")
    seed_accounts(connection)

    transfer(
        connection,
        "TX-IDEMPOTENT-001",
        "A100",
        "B200",
        money("50.00"),
    )

    try:
        transfer(
            connection,
            "TX-IDEMPOTENT-001",
            "A100",
            "B200",
            money("50.00"),
        )
    except sqlite3.IntegrityError as exc:
        print(f"Duplicate transfer rejected: {exc}")

    assert get_balance(connection, "A100") == money("950.00")
    assert get_balance(connection, "B200") == money("550.00")

    transfer_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM transfers
        WHERE transfer_id = ?
        """,
        ("TX-IDEMPOTENT-001",),
    ).fetchone()[0]

    assert transfer_count == 1
    print(
        "The unique transfer identifier prevents a retry from creating "
        "a second transfer."
    )


def demonstrate_conditional_update(connection: sqlite3.Connection) -> None:
    print("\n=== Conditional Update and Lost-Update Defense ===")
    seed_accounts(connection)

    begin(connection)
    try:
        cursor = connection.execute(
            """
            UPDATE accounts
            SET balance_cents = balance_cents - ?
            WHERE account_id = ?
              AND balance_cents >= ?
            """,
            (90_000, "A100", 90_000),
        )

        if cursor.rowcount != 1:
            raise ValueError("Conditional debit failed")

        commit(connection)
    except Exception:
        rollback(connection)
        raise

    assert get_balance(connection, "A100") == money("100.00")
    print(
        "A balance-sensitive UPDATE performs the eligibility check and "
        "mutation as one database operation."
    )

    begin(connection)
    try:
        cursor = connection.execute(
            """
            UPDATE accounts
            SET balance_cents = balance_cents - ?
            WHERE account_id = ?
              AND balance_cents >= ?
            """,
            (90_000, "A100", 90_000),
        )

        if cursor.rowcount != 1:
            raise ValueError("Second debit correctly rejected")

        commit(connection)
    except ValueError as exc:
        print(f"Expected rejection: {exc}")
        rollback(connection)

    assert get_balance(connection, "A100") == money("100.00")


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    delay_seconds: float = 0.05


def run_with_retry(
    operation: Callable[[], None],
    policy: RetryPolicy,
    retryable_errors: tuple[type[BaseException], ...],
) -> None:
    """
    Retry only errors that the caller has explicitly classified as retryable.

    Retrying every exception is dangerous because validation failures,
    duplicate operations, and business-rule violations are not transient.
    """
    last_error: BaseException | None = None

    for attempt in range(1, policy.max_attempts + 1):
        try:
            operation()
            return
        except retryable_errors as exc:
            last_error = exc
            if attempt == policy.max_attempts:
                break
            time.sleep(policy.delay_seconds * attempt)

    assert last_error is not None
    raise last_error


def demonstrate_retry_strategy(connection: sqlite3.Connection) -> None:
    print("\n=== Retry Strategy ===")
    seed_accounts(connection)

    attempts = {"count": 0}

    def operation() -> None:
        attempts["count"] += 1

        if attempts["count"] < 3:
            raise sqlite3.OperationalError("simulated transient database error")

        transfer(
            connection,
            "TX-RETRY-001",
            "A100",
            "B200",
            money("30.00"),
        )

    run_with_retry(
        operation,
        RetryPolicy(max_attempts=3, delay_seconds=0.01),
        (sqlite3.OperationalError,),
    )

    assert attempts["count"] == 3
    assert get_balance(connection, "A100") == money("970.00")
    assert get_balance(connection, "B200") == money("530.00")

    print("The operation succeeded after retrying transient failures.")


def demonstrate_durability(connection: sqlite3.Connection, database: str) -> None:
    print("\n=== Durability ===")
    seed_accounts(connection)

    transfer(
        connection,
        "TX-DURABLE-001",
        "A100",
        "C300",
        money("80.00"),
    )

    connection.close()

    reopened = connect(database)
    try:
        assert get_balance(reopened, "A100") == money("920.00")
        assert get_balance(reopened, "C300") == money("830.00")

        print(
            "After closing and reopening the database, committed balances "
            "remain present."
        )
    finally:
        reopened.close()


def demonstrate_transaction_boundary_error(connection: sqlite3.Connection) -> None:
    print("\n=== Transaction Boundary Failure ===")
    seed_accounts(connection)

    begin(connection)
    try:
        connection.execute(
            """
            UPDATE accounts
            SET balance_cents = balance_cents - 2000
            WHERE account_id = 'A100'
            """
        )

        # A transaction should include every dependent write. Committing here
        # would expose an incomplete business operation to other transactions.
        raise RuntimeError("failure before the dependent credit")

    except RuntimeError:
        rollback(connection)

    assert get_balance(connection, "A100") == money("1000.00")
    assert get_balance(connection, "B200") == money("500.00")

    print(
        "The debit was not committed independently from the missing credit."
    )


def verify_ledger_integrity(connection: sqlite3.Connection) -> None:
    """
    Verify that every transfer has exactly one matching debit and credit.

    This is an application-level invariant layered on top of database
    constraints. It is useful for reconciliation and operational auditing.
    """
    rows = connection.execute(
        """
        SELECT
            t.transfer_id,
            t.amount_cents,
            SUM(CASE WHEN l.direction = 'DEBIT' THEN 1 ELSE 0 END) AS debits,
            SUM(CASE WHEN l.direction = 'CREDIT' THEN 1 ELSE 0 END) AS credits,
            SUM(
                CASE
                    WHEN l.direction = 'DEBIT' THEN l.amount_cents
                    ELSE 0
                END
            ) AS debit_total,
            SUM(
                CASE
                    WHEN l.direction = 'CREDIT' THEN l.amount_cents
                    ELSE 0
                END
            ) AS credit_total
        FROM transfers t
        LEFT JOIN ledger l ON l.transfer_id = t.transfer_id
        GROUP BY t.transfer_id, t.amount_cents
        """
    ).fetchall()

    for (
        transfer_id,
        amount_cents,
        debits,
        credits,
        debit_total,
        credit_total,
    ) in rows:
        assert debits == 1, transfer_id
        assert credits == 1, transfer_id
        assert debit_total == amount_cents, transfer_id
        assert credit_total == amount_cents, transfer_id

    print(f"Ledger verification passed for {len(rows)} transfer(s).")


def demonstrate_concurrent_serialization(database: str) -> None:
    print("\n=== Concurrent Transactions ===")
    first = connect(database, timeout=2.0)
    second = connect(database, timeout=2.0)

    try:
        seed_accounts(first)

        begin(first)
        first.execute(
            """
            UPDATE accounts
            SET balance_cents = balance_cents - 1000
            WHERE account_id = 'A100'
              AND balance_cents >= 1000
            """
        )

        result: dict[str, str] = {}

        def competing_writer() -> None:
            try:
                begin(second)
                second.execute(
                    """
                    UPDATE accounts
                    SET balance_cents = balance_cents - 1000
                    WHERE account_id = 'A100'
                      AND balance_cents >= 1000
                    """
                )
                commit(second)
                result["status"] = "committed"
            except sqlite3.OperationalError as exc:
                result["status"] = f"blocked/rejected: {exc}"
                try:
                    rollback(second)
                except sqlite3.Error:
                    pass

        worker = threading.Thread(target=competing_writer)
        worker.start()
        worker.join()

        # Release the first writer after the competing transaction has had an
        # opportunity to encounter SQLite's write-lock rules.
        commit(first)

        print(f"Competing writer result: {result.get('status', 'unknown')}")

        final_balance = get_balance(first, "A100")
        assert final_balance in {money("980.00"), money("990.00")}

        print(f"Final A100 balance: {final_balance} INR")
    finally:
        first.close()
        second.close()


def demonstrate_validation(connection: sqlite3.Connection) -> None:
    print("\n=== Business Validation ===")
    seed_accounts(connection)

    invalid_cases = [
        ("empty identifier", "", "A100", "B200", "10.00"),
        ("same account", "TX-VALID-1", "A100", "A100", "10.00"),
        ("negative amount", "TX-VALID-2", "A100", "B200", "-10.00"),
        ("zero amount", "TX-VALID-3", "A100", "B200", "0.00"),
        ("unknown source", "TX-VALID-4", "NOPE", "B200", "10.00"),
    ]

    for name, transfer_id, source, destination, amount in invalid_cases:
        try:
            if not transfer_id:
                raise ValueError("Transfer identifier must not be empty")

            transfer(
                connection,
                transfer_id,
                source,
                destination,
                money(amount),
            )
        except (ValueError, sqlite3.IntegrityError) as exc:
            print(f"{name}: rejected ({exc})")

    assert get_balance(connection, "A100") == money("1000.00")
    assert get_balance(connection, "B200") == money("500.00")


def demonstrate_atomicity_of_multiple_statements(
    connection: sqlite3.Connection,
) -> None:
    print("\n=== Multi-Statement Atomicity ===")
    seed_accounts(connection)

    begin(connection)
    try:
        connection.execute(
            """
            UPDATE accounts
            SET balance_cents = balance_cents - 500
            WHERE account_id = 'A100'
            """
        )

        connection.execute(
            """
            UPDATE accounts
            SET balance_cents = balance_cents + 500
            WHERE account_id = 'B200'
            """
        )

        connection.execute(
            """
            INSERT INTO transfers(
                transfer_id, source_account, destination_account, amount_cents
            )
            VALUES (?, ?, ?, ?)
            """,
            ("TX-MULTI-001", "A100", "B200", 500),
        )

        commit(connection)
    except Exception:
        rollback(connection)
        raise

    assert get_balance(connection, "A100") == money("995.00")
    assert get_balance(connection, "B200") == money("505.00")
    print("Three dependent writes became one transaction boundary.")


def demonstrate_autocommit_warning(database: str) -> None:
    print("\n=== Autocommit and Transaction Boundaries ===")
    connection = connect(database)
    try:
        seed_accounts(connection)

        # With isolation_level=None, individual statements are committed unless
        # an explicit BEGIN is active. That behavior is useful for independent
        # operations but unsafe for a business operation requiring multiple
        # dependent statements.
        connection.execute(
            """
            UPDATE accounts
            SET balance_cents = balance_cents - 100
            WHERE account_id = 'A100'
            """
        )

        try:
            connection.execute(
                """
                UPDATE accounts
                SET balance_cents = balance_cents + 100
                WHERE account_id = 'B200'
                """
            )
            raise RuntimeError("simulated crash after independent statements")
        except RuntimeError:
            pass

        # Because the first UPDATE was already committed under autocommit,
        # there is no transaction to roll back here.
        assert get_balance(connection, "A100") == money("999.00")
        assert get_balance(connection, "B200") == money("501.00")

        print(
            "Independent autocommit statements cannot provide atomicity "
            "across a multi-statement business operation."
        )
    finally:
        connection.close()


def run_all_demos() -> None:
    with tempfile.TemporaryDirectory(prefix="acid_demo_") as directory:
        database = str(Path(directory) / "transactions.sqlite3")
        connection = connect(database)

        try:
            create_schema(connection)

            demonstrate_atomicity(connection)
            demonstrate_commit(connection)
            demonstrate_consistency(connection)
            demonstrate_constraint_rollback(connection)
            demonstrate_savepoints(connection)
            demonstrate_isolation(connection)
            demonstrate_idempotency(connection)
            demonstrate_conditional_update(connection)
            demonstrate_retry_strategy(connection)
            demonstrate_transaction_boundary_error(connection)
            demonstrate_atomicity_of_multiple_statements(connection)
            demonstrate_validation(connection)
            verify_ledger_integrity(connection)
            demonstrate_durability(connection, database)
        finally:
            try:
                connection.close()
            except sqlite3.Error:
                pass

        demonstrate_concurrent_serialization(database)
        demonstrate_autocommit_warning(database)

        print("\n=== Completed ===")
        print(
            "The demonstrations exercised atomicity, consistency, isolation, "
            "durability, savepoints, constraints, retries, idempotency, "
            "transaction boundaries, and concurrent write behavior."
        )


if __name__ == "__main__":
    run_all_demos()
