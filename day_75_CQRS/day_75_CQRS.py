#!/usr/bin/env python3
"""
CQRS: Command Query Responsibility Segregation
Separate write models from read models using commands, events,
event handling, projections, optimistic concurrency, and an event store.

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("cqrs")


# ============================================================
# 1. DOMAIN EXCEPTIONS
# ============================================================

class CQRSException(Exception):
    """Base exception for CQRS operations."""


class ValidationError(CQRSException):
    pass


class NotFoundError(CQRSException):
    pass


class ConcurrencyError(CQRSException):
    pass


class DuplicateCommandError(CQRSException):
    pass


class InsufficientFundsError(CQRSException):
    pass


class ProjectionError(CQRSException):
    pass


# ============================================================
# 2. DOMAIN ENUMERATIONS
# ============================================================

class CommandType(str, Enum):
    CREATE_ACCOUNT = "CREATE_ACCOUNT"
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"
    TRANSFER = "TRANSFER"


class EventType(str, Enum):
    ACCOUNT_CREATED = "ACCOUNT_CREATED"
    MONEY_DEPOSITED = "MONEY_DEPOSITED"
    MONEY_WITHDRAWN = "MONEY_WITHDRAWN"
    MONEY_TRANSFERRED = "MONEY_TRANSFERRED"


# ============================================================
# 3. COMMAND MODELS
# ============================================================

@dataclass(frozen=True)
class Command:
    command_id: str
    command_type: CommandType
    account_id: str
    amount: float = 0.0
    expected_version: int | None = None
    destination_account_id: str | None = None

    @staticmethod
    def create(
        command_type: CommandType,
        account_id: str,
        amount: float = 0.0,
        expected_version: int | None = None,
        destination_account_id: str | None = None,
    ) -> "Command":
        return Command(
            command_id=str(uuid.uuid4()),
            command_type=command_type,
            account_id=account_id,
            amount=amount,
            expected_version=expected_version,
            destination_account_id=destination_account_id,
        )


# ============================================================
# 4. EVENT MODEL
# ============================================================

@dataclass(frozen=True)
class DomainEvent:
    event_id: str
    event_type: EventType
    aggregate_id: str
    version: int
    payload: dict[str, Any]
    occurred_at: str

    @staticmethod
    def create(
        event_type: EventType,
        aggregate_id: str,
        version: int,
        payload: dict[str, Any],
    ) -> "DomainEvent":
        return DomainEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            aggregate_id=aggregate_id,
            version=version,
            payload=payload,
            occurred_at=datetime.now(timezone.utc).isoformat(),
        )


# ============================================================
# 5. WRITE MODEL: BANK ACCOUNT AGGREGATE
# ============================================================

class BankAccount:
    """
    The write model owns business invariants.

    Account balance is not updated directly by query operations.
    All changes are represented by domain events.
    """

    def __init__(
        self,
        account_id: str,
        owner: str,
        balance: float = 0.0,
        version: int = 0,
    ):
        self.account_id = account_id
        self.owner = owner
        self.balance = round(balance, 2)
        self.version = version

    def _validate_amount(self, amount: float) -> None:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise ValidationError("Amount must be numeric.")

        if amount <= 0 or not float(amount) < float("inf"):
            raise ValidationError("Amount must be finite and positive.")

        if round(amount, 2) != amount:
            raise ValidationError("Amount must have at most two decimal places.")

    def deposit(self, amount: float) -> DomainEvent:
        self._validate_amount(amount)

        self.balance = round(self.balance + amount, 2)
        self.version += 1

        return DomainEvent.create(
            EventType.MONEY_DEPOSITED,
            self.account_id,
            self.version,
            {"amount": round(amount, 2)},
        )

    def withdraw(self, amount: float) -> DomainEvent:
        self._validate_amount(amount)

        if amount > self.balance:
            raise InsufficientFundsError("Insufficient account balance.")

        self.balance = round(self.balance - amount, 2)
        self.version += 1

        return DomainEvent.create(
            EventType.MONEY_WITHDRAWN,
            self.account_id,
            self.version,
            {"amount": round(amount, 2)},
        )

    def apply(self, event: DomainEvent) -> None:
        """Rebuild aggregate state by replaying historical events."""

        if event.version != self.version + 1:
            raise ConcurrencyError("Invalid event sequence.")

        if event.aggregate_id != self.account_id:
            raise ValidationError("Event belongs to another account.")

        if event.event_type == EventType.MONEY_DEPOSITED:
            self.balance += event.payload["amount"]

        elif event.event_type == EventType.MONEY_WITHDRAWN:
            amount = event.payload["amount"]

            if amount > self.balance:
                raise InsufficientFundsError("Invalid historical withdrawal.")

            self.balance -= amount

        elif event.event_type == EventType.ACCOUNT_CREATED:
            self.owner = event.payload["owner"]

        self.balance = round(self.balance, 2)
        self.version = event.version


# ============================================================
# 6. EVENT STORE
# ============================================================

class EventStore:
    """
    Append-only event storage.

    A production implementation should use a transactional database
    and enforce aggregate-version uniqueness at database level.
    """

    def __init__(self):
        self._events: dict[str, list[DomainEvent]] = {}
        self._event_ids: set[str] = set()
        self._lock = threading.RLock()

    def append(
        self,
        aggregate_id: str,
        expected_version: int,
        events: list[DomainEvent],
    ) -> None:

        if not events:
            raise ValidationError("At least one event is required.")

        with self._lock:
            history = self._events.setdefault(aggregate_id, [])
            current_version = len(history)

            if current_version != expected_version:
                raise ConcurrencyError(
                    f"Expected version {expected_version}; "
                    f"actual version {current_version}."
                )

            next_version = current_version

            for event in events:
                next_version += 1

                if event.aggregate_id != aggregate_id:
                    raise ValidationError("Aggregate mismatch.")

                if event.version != next_version:
                    raise ConcurrencyError("Invalid event version.")

                if event.event_id in self._event_ids:
                    raise DuplicateCommandError("Duplicate event identifier.")

            for event in events:
                history.append(event)
                self._event_ids.add(event.event_id)

    def get_events(self, aggregate_id: str) -> list[DomainEvent]:
        with self._lock:
            return list(self._events.get(aggregate_id, []))

    def get_all_events(self) -> list[DomainEvent]:
        with self._lock:
            return [
                event
                for history in self._events.values()
                for event in history
            ]

    def current_version(self, aggregate_id: str) -> int:
        with self._lock:
            return len(self._events.get(aggregate_id, []))


# ============================================================
# 7. COMMAND IDEMPOTENCY
# ============================================================

class CommandRegistry:
    def __init__(self):
        self._processed: dict[str, Any] = {}
        self._lock = threading.RLock()

    def get(self, command_id: str) -> tuple[bool, Any]:
        with self._lock:
            if command_id in self._processed:
                return True, self._processed[command_id]
            return False, None

    def save(self, command_id: str, result: Any) -> None:
        with self._lock:
            self._processed[command_id] = result


# ============================================================
# 8. WRITE SIDE: COMMAND HANDLER
# ============================================================

class CommandHandler:

    def __init__(
        self,
        event_store: EventStore,
        registry: CommandRegistry,
    ):
        self.event_store = event_store
        self.registry = registry
        self._accounts: dict[str, BankAccount] = {}
        self._lock = threading.RLock()

    def create_account(
        self,
        account_id: str,
        owner: str,
        command_id: str | None = None,
    ) -> DomainEvent:

        if not account_id.strip() or not owner.strip():
            raise ValidationError("Account ID and owner are required.")

        command_id = command_id or str(uuid.uuid4())

        with self._lock:
            found, result = self.registry.get(command_id)
            if found:
                return result

            if account_id in self._accounts:
                raise ValidationError("Account already exists.")

            event = DomainEvent.create(
                EventType.ACCOUNT_CREATED,
                account_id,
                1,
                {"owner": owner.strip()},
            )

            self.event_store.append(account_id, 0, [event])

            account = BankAccount(account_id, owner)
            account.version = 1
            self._accounts[account_id] = account

            self.registry.save(command_id, event)
            return event

    def handle(self, command: Command) -> list[DomainEvent]:
        with self._lock:
            found, result = self.registry.get(command.command_id)

            if found:
                return result

            if command.command_type == CommandType.TRANSFER:
                raise ValidationError(
                    "Use transfer() for atomic transfer processing."
                )

            account = self._accounts.get(command.account_id)

            if account is None:
                raise NotFoundError("Account does not exist.")

            current_version = self.event_store.current_version(
                command.account_id
            )

            if account.version != current_version:
                raise ConcurrencyError("Write model is inconsistent.")

            if (
                command.expected_version is not None
                and command.expected_version != current_version
            ):
                raise ConcurrencyError("Client supplied a stale version.")

            if command.command_type == CommandType.DEPOSIT:
                event = account.deposit(command.amount)

            elif command.command_type == CommandType.WITHDRAW:
                event = account.withdraw(command.amount)

            else:
                raise ValidationError("Unsupported command.")

            try:
                self.event_store.append(
                    command.account_id,
                    current_version,
                    [event],
                )
            except Exception:
                # Do not leave in-memory state ahead of persisted events.
                account.version -= 1
                if event.event_type == EventType.MONEY_DEPOSITED:
                    account.balance = round(
                        account.balance - event.payload["amount"], 2
                    )
                else:
                    account.balance = round(
                        account.balance + event.payload["amount"], 2
                    )
                raise

            result = [event]
            self.registry.save(command.command_id, result)
            return result

    def transfer(
        self,
        source_id: str,
        destination_id: str,
        amount: float,
    ) -> list[DomainEvent]:
        """
        Transfers are committed as one logical operation.

        Both account locks are represented by the handler's global lock.
        A database-backed implementation should use one transaction.
        """

        with self._lock:
            if source_id == destination_id:
                raise ValidationError("Source and destination must differ.")

            source = self._accounts.get(source_id)
            destination = self._accounts.get(destination_id)

            if source is None or destination is None:
                raise NotFoundError("Source or destination account missing.")

            source._validate_amount(amount)

            if source.balance < amount:
                raise InsufficientFundsError("Insufficient balance.")

            source_event = DomainEvent.create(
                EventType.MONEY_WITHDRAWN,
                source_id,
                source.version + 1,
                {"amount": round(amount, 2), "transfer": destination_id},
            )

            destination_event = DomainEvent.create(
                EventType.MONEY_DEPOSITED,
                destination_id,
                destination.version + 1,
                {"amount": round(amount, 2), "transfer": source_id},
            )

            # Validate both streams before changing either stream.
            if self.event_store.current_version(source_id) != source.version:
                raise ConcurrencyError("Source account version conflict.")

            if self.event_store.current_version(destination_id) != destination.version:
                raise ConcurrencyError("Destination account version conflict.")

            # The in-memory implementation is protected by the handler lock.
            # A durable implementation must append both events transactionally.
            self.event_store.append(
                source_id, source.version, [source_event]
            )

            try:
                self.event_store.append(
                    destination_id,
                    destination.version,
                    [destination_event],
                )
            except Exception as exc:
                # This demonstrates why multi-stream atomicity requires
                # a real database transaction.
                raise CQRSException(
                    "Partial transfer detected; reconciliation required."
                ) from exc

            source.balance = round(source.balance - amount, 2)
            source.version += 1

            destination.balance = round(destination.balance + amount, 2)
            destination.version += 1

            return [source_event, destination_event]

    def get_write_state(self, account_id: str) -> BankAccount:
        with self._lock:
            account = self._accounts.get(account_id)
            if account is None:
                raise NotFoundError("Account does not exist.")

            return BankAccount(
                account.account_id,
                account.owner,
                account.balance,
                account.version,
            )


# ============================================================
# 9. READ MODEL: PROJECTION
# ============================================================

@dataclass
class AccountReadModel:
    account_id: str
    owner: str
    balance: float = 0.0
    version: int = 0
    transaction_count: int = 0
    last_updated: str | None = None


class AccountProjection:

    def __init__(self):
        self._accounts: dict[str, AccountReadModel] = {}
        self._processed_events: set[str] = set()
        self._lock = threading.RLock()

    def apply(self, event: DomainEvent) -> None:
        with self._lock:
            if event.event_id in self._processed_events:
                return

            account = self._accounts.get(event.aggregate_id)

            if event.event_type == EventType.ACCOUNT_CREATED:
                if account is not None:
                    raise ProjectionError("Account already projected.")

                account = AccountReadModel(
                    account_id=event.aggregate_id,
                    owner=event.payload["owner"],
                    version=event.version,
                    last_updated=event.occurred_at,
                )

                self._accounts[event.aggregate_id] = account

            else:
                if account is None:
                    raise ProjectionError(
                        "Cannot apply transaction before account creation."
                    )

                if event.version != account.version + 1:
                    raise ProjectionError("Projection version gap detected.")

                amount = event.payload["amount"]

                if event.event_type == EventType.MONEY_DEPOSITED:
                    account.balance += amount

                elif event.event_type == EventType.MONEY_WITHDRAWN:
                    account.balance -= amount

                account.balance = round(account.balance, 2)
                account.version = event.version
                account.transaction_count += 1
                account.last_updated = event.occurred_at

            self._processed_events.add(event.event_id)

    def rebuild(self, events: list[DomainEvent]) -> None:
        with self._lock:
            self._accounts.clear()
            self._processed_events.clear()

        for event in sorted(
            events,
            key=lambda item: (item.aggregate_id, item.version),
        ):
            self.apply(event)

    def get_account(self, account_id: str) -> dict[str, Any]:
        with self._lock:
            account = self._accounts.get(account_id)

            if account is None:
                raise NotFoundError("Read-model account not found.")

            return asdict(account)

    def get_all_accounts(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                asdict(account)
                for account in self._accounts.values()
            ]

    def total_balance(self) -> float:
        with self._lock:
            return round(
                sum(account.balance for account in self._accounts.values()),
                2,
            )


# ============================================================
# 10. EVENT DISPATCHER
# ============================================================

class EventDispatcher:

    def __init__(self):
        self._handlers: dict[
            EventType, list[Callable[[DomainEvent], None]]
        ] = {}

    def subscribe(
        self,
        event_type: EventType,
        handler: Callable[[DomainEvent], None],
    ) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: DomainEvent) -> None:
        for handler in self._handlers.get(event.event_type, []):
            handler(event)


# ============================================================
# 11. EVENT LOG PERSISTENCE
# ============================================================

class EventFileStorage:

    def save(self, events: list[DomainEvent], path: str) -> None:
        destination = Path(path)

        with destination.open("w", encoding="utf-8") as file:
            for event in events:
                record = {
                    **asdict(event),
                    "event_type": event.event_type.value,
                }
                file.write(json.dumps(record) + "\n")

    def load(self, path: str) -> list[DomainEvent]:
        source = Path(path)

        if not source.exists():
            raise FileNotFoundError(path)

        events = []

        with source.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, 1):
                try:
                    record = json.loads(line)

                    events.append(
                        DomainEvent(
                            event_id=record["event_id"],
                            event_type=EventType(record["event_type"]),
                            aggregate_id=record["aggregate_id"],
                            version=record["version"],
                            payload=record["payload"],
                            occurred_at=record["occurred_at"],
                        )
                    )
                except (ValueError, KeyError, TypeError) as exc:
                    raise ValidationError(
                        f"Invalid event record at line {line_number}."
                    ) from exc

        return events


# ============================================================
# 12. APPLICATION AND WORKFLOW
# ============================================================

class BankingCQRS:

    def __init__(self):
        self.event_store = EventStore()
        self.registry = CommandRegistry()
        self.command_handler = CommandHandler(
            self.event_store,
            self.registry,
        )
        self.read_model = AccountProjection()

    def synchronize(self) -> None:
        """
        Synchronize the read side from the event stream.

        This is a simple full replay. Incremental consumers should
        persist their own checkpoints and process events in order.
        """
        self.read_model.rebuild(self.event_store.get_all_events())

    def deposit(
        self,
        account_id: str,
        amount: float,
        expected_version: int | None = None,
    ) -> list[DomainEvent]:

        command = Command.create(
            CommandType.DEPOSIT,
            account_id,
            amount,
            expected_version,
        )

        return self.command_handler.handle(command)

    def withdraw(
        self,
        account_id: str,
        amount: float,
        expected_version: int | None = None,
    ) -> list[DomainEvent]:

        command = Command.create(
            CommandType.WITHDRAW,
            account_id,
            amount,
            expected_version,
        )

        return self.command_handler.handle(command)

    def query_account(self, account_id: str) -> dict[str, Any]:
        return self.read_model.get_account(account_id)


# ============================================================
# 13. EXECUTABLE TESTS
# ============================================================

def run_tests() -> None:
    system = BankingCQRS()

    system.command_handler.create_account("ACC-1001", "Aarav")
    system.command_handler.create_account("ACC-1002", "Meera")

    system.synchronize()

    system.deposit("ACC-1001", 10000.00, expected_version=1)
    system.deposit("ACC-1001", 2500.00, expected_version=2)
    system.withdraw("ACC-1001", 1500.00, expected_version=3)

    system.command_handler.transfer(
        "ACC-1001",
        "ACC-1002",
        2000.00,
    )

    # Read models are updated independently.
    system.synchronize()

    account = system.query_account("ACC-1001")
    destination = system.query_account("ACC-1002")

    assert account["balance"] == 9000.00
    assert destination["balance"] == 2000.00
    assert account["version"] == 5
    assert destination["version"] == 2

    # Duplicate event delivery must not change the projection twice.
    event = system.event_store.get_events("ACC-1001")[-1]
    original_balance = account["balance"]

    system.read_model.apply(event)

    assert system.read_model.get_account(
        "ACC-1001"
    )["balance"] == original_balance

    # Insufficient funds.
    try:
        system.withdraw("ACC-1001", 100000.00)
        raise AssertionError("Expected insufficient funds.")
    except InsufficientFundsError:
        logger.info("Insufficient funds correctly rejected.")

    # Stale version.
    try:
        system.deposit("ACC-1001", 100.00, expected_version=1)
        raise AssertionError("Expected concurrency error.")
    except ConcurrencyError:
        logger.info("Stale command correctly rejected.")

    # Invalid amount.
    try:
        system.deposit("ACC-1001", -10.00)
        raise AssertionError("Expected validation error.")
    except ValidationError:
        logger.info("Invalid amount correctly rejected.")

    # Projection rebuild must produce the same result.
    old_balance = system.read_model.total_balance()
    system.synchronize()

    assert system.read_model.total_balance() == old_balance

    logger.info("All CQRS tests passed.")

    print("\nREAD MODEL REPORT")

    for record in system.read_model.get_all_accounts():
        print(json.dumps(record, indent=2))

    print("\nTotal balance:", system.read_model.total_balance())

    # Persist and reload the append-only event history.
    storage = EventFileStorage()
    storage.save(system.event_store.get_all_events(), "cqrs_events.jsonl")

    recovered = storage.load("cqrs_events.jsonl")
    assert len(recovered) == len(system.event_store.get_all_events())

    print("Persisted events:", len(recovered))


if __name__ == "__main__":
    run_tests()
